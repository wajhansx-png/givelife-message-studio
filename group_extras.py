"""A case's PDF and video that follow the poster message in every GROUP post.

Order: the file that carries the case text first (the video, or the poster: the owner picks, per case), then the
poster or video alone, then the PDF. Each can be switched off without
being removed. They belong to the case (a new case starts with none) and are stored with the existing private
attachment storage (batch_media: type and size checked, never touches the campaign poster).
"""

import re

import batch_media

KEY = "group_extras"
KINDS = ("pdf", "video", "poster")  # "poster" = the AFTER poster: a separate picture sent after the message
TEXT_ON = ("video", "poster")  # which file carries the case text; a new case starts with the video
MIME = {"pdf": "application/pdf", "video": "video/mp4", "poster": "image/jpeg"}
LABEL = {"pdf": "PDF", "video": "Video", "poster": "Poster"}
IMAGES = ("image/jpeg", "image/png", "image/webp")


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


PROFILES = ("group", "dm", "giki")  # each one has its own choices; the files are the group message's
FLAGS = ("poster", "video", "pdf")
ORDERS = ("poster_pdf", "pdf_poster")  # older saved order (2nd / 3rd): still read
SLOT_KINDS = ("poster", "pdf", "video")  # Giki: what the 2nd and the 3rd message can be


def _raw(store):
    raw = store.get(KEY) if store else None
    return raw if isinstance(raw, dict) else {}


def _save(store, rows):
    """Save the files, keeping every setting stored next to them."""
    raw = _raw(store)
    store.put(KEY, {**{k: v for k, v in raw.items() if k not in KINDS}, **rows})


def text_on(store, profile="group"):
    raw = _raw(store)
    value = raw.get("text_on") if profile == "group" else (raw.get("setup") or {}).get(profile, {}).get("text_on")
    return value if value in TEXT_ON else "poster" if profile == "giki" else "video"  # Giki: poster with caption


def set_text_on(store, value, profile="group"):
    return set_setup(store, profile, "text_on", value)


def setup(store, profile):
    """{text_on, poster, video, pdf} for groups, DMs or the Giki page. Groups keep the switches next to the files."""
    if profile not in PROFILES:
        raise ValueError("Choose groups, DMs or Giki.")
    raw, rows = _raw(store), _rows(store)
    if profile == "group":
        return {
            "text_on": text_on(store),
            "poster": bool("poster" in rows and rows["poster"]["on"]),
            "video": bool("video" in rows and rows["video"]["on"]),
            "pdf": bool("pdf" in rows and rows["pdf"]["on"]),
        }
    own = (raw.get("setup") or {}).get(profile) or {}
    return {
        "text_on": text_on(store, profile),
        "poster": own.get("poster") is True,  # the after poster goes only when ticked
        "video": own.get("video") is True,
        "pdf": own.get("pdf") is True,
        "order": own.get("order") if own.get("order") in ORDERS else "poster_pdf",
        **_slots(own),
    }


def _slots(own):
    """{"second": kind, "third": kind}: what the Giki 2nd and 3rd messages are (never the same thing twice)."""
    old = "pdf" if own.get("order") == "pdf_poster" else "poster"
    second = own.get("second") if own.get("second") in SLOT_KINDS else old
    third = own.get("third") if own.get("third") in SLOT_KINDS else ("poster" if old == "pdf" else "pdf")
    if third == second:
        third = next(k for k in SLOT_KINDS if k != second)
    return {"second": second, "third": third}


def set_setup(store, profile, field, value):
    if profile not in PROFILES:
        raise ValueError("Choose groups, DMs or Giki.")
    if field == "text_on":
        if value not in TEXT_ON:
            raise ValueError("Choose Video or Poster for the text.")
    elif field == "order":
        if profile == "group" or value not in ORDERS:
            raise ValueError("Choose Poster or PDF for the 2nd message.")
    elif field in ("second", "third"):
        if profile != "giki" or value not in SLOT_KINDS:
            raise ValueError("Choose Poster pic, PDF or Video.")
        raw = _raw(store)
        all_setup = dict(raw.get("setup") or {})
        own = dict(all_setup.get(profile) or {})
        now = _slots(own)
        other = "third" if field == "second" else "second"
        if now[other] == value:  # picking what the other slot has: they swap
            own[other] = now[field]
        own[field] = value
        own.pop("order", None)
        all_setup[profile] = own
        store.put(KEY, {**raw, "setup": all_setup})
        return view(store)
    elif field not in FLAGS or not isinstance(value, bool):
        raise ValueError("Use on or off.")
    raw = _raw(store)
    if profile == "group" and field in KINDS:
        return set_on(store, field, value)
    if profile == "group":
        raw = {**raw, "text_on": value}
    else:
        all_setup = dict(raw.get("setup") or {})
        all_setup[profile] = {**(all_setup.get(profile) or {}), field: value}
        raw = {**raw, "setup": all_setup}
    store.put(KEY, raw)
    return view(store)


def lead(store, profile="group"):
    """The video's attachment id when it carries the case text for this place, else None. For groups the video must
    also be switched on."""
    rows = _rows(store)
    if text_on(store, profile) != "video" or "video" not in rows:
        return None
    if profile == "group" and not rows["video"]["on"]:
        return None
    return rows["video"]["id"]


def after_poster(store, profile="group"):
    """The after poster's attachment id when it is saved and ticked for this place, else None."""
    rows = _rows(store)
    if "poster" in rows and setup(store, profile)["poster"]:
        return rows["poster"]["id"]
    return None


def after_items(store, profile):
    """[(kind, attachment id)] sent right after a DM's first message, in order (groups get theirs with to_send).
    Giki: the 2nd and 3rd messages (poster pic and PDF, each ticked on its own, in the chosen order). DMs: the after
    poster when ticked (their PDF / video go with the DM ticks)."""
    if profile == "group":
        return []
    rows, mine = _rows(store), setup(store, profile)
    if profile == "dm":
        kinds = ["poster"]
    else:
        kinds = [mine["second"], mine["third"]]
        led = lead(store, profile)  # the video already went with the case: never twice
    return [
        (k, rows[k]["id"])
        for k in kinds
        if mine[k] and k in rows and not (profile == "giki" and k == "video" and led)
    ]


def extras_for(store, profile):
    """{"pdf": bool, "video": bool}: the files that follow the first message for DMs or Giki (only saved ones; the
    video only when it did not carry the text)."""
    rows, mine = _rows(store), setup(store, profile)
    led = lead(store, profile)
    return {
        # Giki's PDF goes as its 2nd / 3rd message (after_items); for DMs it follows the DM ticks
        "pdf": bool(mine["pdf"] and "pdf" in rows and profile != "giki"),
        "video": bool(mine["video"] and "video" in rows and not led and profile != "giki"),
    }


def _check_kind(kind):
    if kind not in KINDS:
        raise ValueError("Choose PDF, Video or Poster.")


def view(store):
    """What the owner sees: for each of PDF and Video, whether one is saved, its name, and whether it is switched on."""
    rows = _rows(store)
    out = {
        kind: {
            "has": kind in rows,
            "name": rows[kind]["name"] if kind in rows else "",
            "on": bool(kind in rows and rows[kind]["on"]),
            "kb": rows[kind]["kb"] if kind in rows else 0,
        }
        for kind in KINDS
    }
    out["text_on"] = text_on(store)
    out["setup"] = {p: setup(store, p) for p in PROFILES}
    return out


def add(store, kind, data_url, name=""):
    """Save (or replace) the case's PDF or video. It starts switched ON."""
    _check_kind(kind)
    allowed = IMAGES if kind == "poster" else (MIME[kind],)
    if not isinstance(data_url, str) or not any(
        data_url.startswith("data:" + m + ";base64,") for m in allowed
    ):
        raise ValueError(
            "Choose a PDF file."
            if kind == "pdf"
            else "Choose a picture (JPEG, PNG or WebP)."
            if kind == "poster"
            else "Choose an MP4 video (it must be MP4)."
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
    _save(store, rows)
    return view(store)


def set_on(store, kind, on):
    _check_kind(kind)
    if not isinstance(on, bool):
        raise ValueError("Use on or off.")
    rows = _rows(store)
    if kind not in rows:
        raise ValueError(f"There is no {LABEL[kind]} saved yet. Add one first.")
    rows[kind]["on"] = on
    _save(store, rows)
    return view(store)


def remove(store, kind):
    _check_kind(kind)
    rows = _rows(store)
    rows.pop(kind, None)
    _save(store, rows)
    return view(store)


def saved(store, kind):
    """The attachment id of the saved PDF or video, whether or not its GROUP switch is on (DMs have their own)."""
    _check_kind(kind)
    row = _rows(store).get(kind)
    return row["id"] if row else None


def to_send(store):
    """[(kind, attachment id)] to send after the poster, in order, only what is saved AND switched on."""
    rows = _rows(store)
    led = lead(store)
    return [
        (k, rows[k]["id"])
        # after the message: the after poster, the video (unless it carried the text), then the PDF
        for k in ("poster", "video", "pdf")
        if k in rows and rows[k]["on"] and not (k == "video" and led)
    ]


def act(store, body):
    op = body.get("action")
    if op == "add":
        return add(store, body.get("kind"), body.get("data"), body.get("name"))
    if op == "toggle":
        return set_on(store, body.get("kind"), body.get("on"))
    if op == "text_on":
        return set_setup(store, body.get("profile", "group"), "text_on", body.get("value"))
    if op == "setup":
        return set_setup(store, body.get("profile"), body.get("field"), body.get("value"))
    if op == "remove":
        return remove(store, body.get("kind"))
    raise ValueError("Unknown action.")
