"""A case's PDF and video that follow the poster message in every GROUP post.

Order in a group: the poster with its caption first, then the PDF, then the video. Each can be switched off without
being removed. They belong to the case (a new case starts with none) and are stored with the existing private
attachment storage (batch_media: type and size checked, never touches the campaign poster).
"""

import re

import batch_media

KEY = "group_extras"
KINDS = ("pdf", "video")  # the order they are sent in, after the poster
MIME = {"pdf": "application/pdf", "video": "video/mp4"}
LABEL = {"pdf": "PDF", "video": "Video"}


def _rows(store):
    raw = store.get(KEY) if store else None
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for kind in KINDS:
        row = raw.get(kind)
        if isinstance(row, dict) and re.fullmatch("[a-f0-9]{32}", str(row.get("id") or "")):
            out[kind] = {
                "id": row["id"],
                "name": str(row.get("name") or LABEL[kind])[:120],
                "on": row.get("on") is not False,
                "kb": int(row.get("kb") or 0),
            }
    return out


def _check_kind(kind):
    if kind not in KINDS:
        raise ValueError("Choose PDF or Video.")


def view(store):
    """What the owner sees: for each of PDF and Video, whether one is saved, its name, and whether it is switched on."""
    rows = _rows(store)
    return {
        kind: {
            "has": kind in rows,
            "name": rows[kind]["name"] if kind in rows else "",
            "on": bool(kind in rows and rows[kind]["on"]),
            "kb": rows[kind]["kb"] if kind in rows else 0,
        }
        for kind in KINDS
    }


def add(store, kind, data_url, name=""):
    """Save (or replace) the case's PDF or video. It starts switched ON."""
    _check_kind(kind)
    if not isinstance(data_url, str) or not data_url.startswith("data:" + MIME[kind] + ";base64,"):
        raise ValueError(
            "Choose a PDF file." if kind == "pdf" else "Choose an MP4 video (it must be MP4)."
        )
    ident = batch_media.save(store, data_url)  # checks the real file type and the 15 MB limit
    rows = _rows(store)
    size = len(data_url) * 3 // 4 // 1024
    rows[kind] = {
        "id": ident,
        "name": re.sub(r"[\r\n\t]+", " ", str(name or LABEL[kind])).strip()[:120] or LABEL[kind],
        "on": True,
        "kb": size,
    }
    store.put(KEY, rows)
    return view(store)


def set_on(store, kind, on):
    _check_kind(kind)
    if not isinstance(on, bool):
        raise ValueError("Use on or off.")
    rows = _rows(store)
    if kind not in rows:
        raise ValueError(f"There is no {LABEL[kind]} saved yet. Add one first.")
    rows[kind]["on"] = on
    store.put(KEY, rows)
    return view(store)


def remove(store, kind):
    _check_kind(kind)
    rows = _rows(store)
    rows.pop(kind, None)
    store.put(KEY, rows)
    return view(store)


def saved(store, kind):
    """The attachment id of the saved PDF or video, whether or not its GROUP switch is on (DMs have their own)."""
    _check_kind(kind)
    row = _rows(store).get(kind)
    return row["id"] if row else None


def to_send(store):
    """[(kind, attachment id)] to send after the poster, in order, only what is saved AND switched on."""
    rows = _rows(store)
    return [(k, rows[k]["id"]) for k in KINDS if k in rows and rows[k]["on"]]


def act(store, body):
    op = body.get("action")
    if op == "add":
        return add(store, body.get("kind"), body.get("data"), body.get("name"))
    if op == "toggle":
        return set_on(store, body.get("kind"), body.get("on"))
    if op == "remove":
        return remove(store, body.get("kind"))
    raise ValueError("Unknown action.")
