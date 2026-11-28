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
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".bulk-{ident}-", suffix=".tmp", dir=folder
        )
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


# ---- Smaller files, once: every send uploads (and WhatsApp encrypts) the whole file again, so a big case video or
# picture costs time and CPU on EVERY message. Right after it is saved it is made smaller one time in the background
# (videos up to 1280 px, pictures up to 1600 px, the sizes WhatsApp itself sends). The original is used until the
# smaller copy is ready, and kept when the smaller copy would not be clearly smaller.
SHRINK_VIDEO_OVER = 3_000_000
SHRINK_IMAGE_OVER = 600_000


def _ffmpeg(args, timeout=900):
    import shutil, subprocess

    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    nice = ["nice", "-n", "19"] if shutil.which("nice") else []
    try:
        done = subprocess.run(
            nice + [exe, "-hide_banner", "-loglevel", "error", "-y", *args],
            capture_output=True,
            timeout=timeout,
        )
    except Exception:
        return False
    return done.returncode == 0


def shrink(store, ident, folder):
    """Replace the saved file with a smaller copy when that helps. Returns True when it was replaced."""
    key = "batch_media_" + ident
    row = store.get(key)
    if isinstance(row, str):
        row = json.loads(row)
    if not isinstance(row, dict) or row.get("shrunk"):
        return False
    mime, data = row.get("mime"), row.get("data")
    raw = base64.b64decode(data, validate=True)
    video = mime == "video/mp4" and len(raw) > SHRINK_VIDEO_OVER
    image = mime in ("image/jpeg", "image/png", "image/webp") and len(raw) > SHRINK_IMAGE_OVER
    if not (video or image):
        return False
    folder = Path(folder)
    work = Path(tempfile.mkdtemp(prefix=".shrink-", dir=folder))
    try:
        src = work / ("in" + TYPES[mime][0])
        src.write_bytes(raw)
        if video:
            out = work / "out.mp4"
            fit = "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'"
            ok = _ffmpeg(
                [
                    "-i",
                    str(src),
                    "-vf",
                    fit,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "28",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "96k",
                    "-movflags",
                    "+faststart",
                    "-threads",
                    "1",
                    str(out),
                ]
            )
            new_mime = "video/mp4"
        else:
            out = work / "out.jpg"
            fit = "scale='if(gt(iw,ih),min(1600,iw),-2)':'if(gt(iw,ih),-2,min(1600,ih))'"
            ok = _ffmpeg(["-i", str(src), "-vf", fit, "-q:v", "4", "-frames:v", "1", str(out)])
            new_mime = "image/jpeg"
        if not ok or not out.is_file():
            return False
        small = out.read_bytes()
        if not small or len(small) > len(raw) * 0.8 or (video and small[4:8] != b"ftyp"):
            store.put(key, {**row, "shrunk": True})  # not worth it: never try again
            return False
        latest = store.get(key)
        if isinstance(latest, str):
            latest = json.loads(latest)
        if not isinstance(latest, dict) or latest.get("data") != data:
            return False  # replaced meanwhile
        store.put(
            key,
            {
                **row,
                "mime": new_mime,
                "data": base64.b64encode(small).decode(),
                "shrunk": True,
                "original_bytes": len(raw),
            },
        )
        with _CACHE_LOCK:
            for k in [k for k in _CACHE if k[2] == ident]:
                _CACHE.pop(k, None)
        return True
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def shrink_later(store, ident, folder):
    """shrink() in the background, so the upload answers at once."""

    def run():
        try:
            shrink(store, ident, folder)
        except Exception as exc:
            print("media_shrink_failed", ident, str(exc)[:200], flush=True)

    threading.Thread(target=run, daemon=True, name="media-shrink").start()
