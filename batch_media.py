"""Private, immutable batch attachments. Never changes the campaign poster."""

import base64, json, os, re, stat, tempfile, threading, time, uuid, weakref
from collections import OrderedDict
from pathlib import Path

TYPES = {
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": (".webp", b"RIFF"),
    "application/pdf": (".pdf", b"%PDF-"),
    "video/mp4": (".mp4", None),
}

# Immutable attachment ids can reuse their exact disk copy. Only small metadata
# lives here; the potentially 15 MB file and its base64 value are never cached
# in Python. Bound both metadata and locks even during long-lived campaigns.
_CACHE_LIMIT = 128
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_LOAD_LOCKS = tuple(threading.Lock() for _ in range(32))


def _signature(path):
    try:
        info = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def save(store, data):
    if not store:
        raise ValueError("Private attachment storage is unavailable.")
    if not isinstance(data, str):
        raise ValueError("Choose an image, MP4 video or PDF.")
    match = re.fullmatch(r"data:([^;,]+);base64,([A-Za-z0-9+/=\r\n]+)", data)
    if not match or match[1] not in TYPES:
        raise ValueError("Choose a JPEG, PNG, WebP image, MP4 video or PDF.")
    try:
        raw = base64.b64decode(match[2], validate=True)
    except Exception:
        raise ValueError("The attachment could not be read.") from None
    if not 0 < len(raw) <= 15_000_000:
        raise ValueError("Choose a file under 15 MB.")
    ext, magic = TYPES[match[1]]
    if (
        magic
        and not raw.startswith(magic)
        or ext == ".mp4"
        and raw[4:8] != b"ftyp"
        or ext == ".webp"
        and raw[8:12] != b"WEBP"
    ):
        raise ValueError("The file contents do not match its type.")
    ident = uuid.uuid4().hex
    store.put(
        "batch_media_" + ident,
        {"mime": match[1], "data": base64.b64encode(raw).decode(), "created": time.time()},
    )
    return ident


def load(store, ident, folder):
    if not isinstance(ident, str) or not re.fullmatch("[a-f0-9]{32}", ident):
        raise ValueError("Choose the attachment again.")
    if store is None:
        raise ValueError("The attachment is unavailable. Choose it again.")
    folder = Path(folder).resolve()
    key = id(store), folder, ident
    with _LOAD_LOCKS[hash(key) % len(_LOAD_LOCKS)]:
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached:
                owner, path, mime, signature = cached
                if owner() is store and signature is not None and _signature(path) == signature:
                    _CACHE.move_to_end(key)
                    return path, mime
                _CACHE.pop(key, None)
        row = store.get("batch_media_" + ident)
        if isinstance(row, str):
            try:
                row = json.loads(row)
            except ValueError:
                row = None
        if not isinstance(row, dict) or row.get("mime") not in TYPES:
            raise ValueError("The attachment is unavailable. Choose it again.")
        mime = row["mime"]
        # Different stores can have the same id during tests or migrations. Their
        # published copies must never overwrite one another while being sent.
        path = folder / (f"bulk-{id(store):x}-{ident}" + TYPES[mime][0])
        raw = base64.b64decode(row["data"], validate=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".bulk-{ident}-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(raw)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        try:
            owner = weakref.ref(store)
        except TypeError:
            return path, mime  # unusual store adapters remain correct without caching
        with _CACHE_LOCK:
            _CACHE[key] = owner, path, mime, _signature(path)
            _CACHE.move_to_end(key)
            while len(_CACHE) > _CACHE_LIMIT:
                _CACHE.popitem(last=False)
        return path, mime
