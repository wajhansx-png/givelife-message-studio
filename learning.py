"""What the autopilot learns while the owner is away.

Everything here is plain data in one dict (`L`), stored with the engine state:
  variants  - which appeal wordings were posted and how often money followed within the hour
  recent    - the last posts [[time, variant], ...] so a donation can be credited to the post before it
  hours     - how many donations arrived in each hour of the day (Pakistan time)
  donors    - people who said they donated: {phone: {'name', 'first', 'last', 'count', 'dm'}}
  followups - gentle reminders to send later: [{'phone', 'name', 'due', 'kind'}]
"""

import hashlib, random, time, datetime

PKT = datetime.timezone(datetime.timedelta(hours=5))
WINDOW = 3600  # a donation within an hour of a post is credited to that post


def new():
    return {"variants": {}, "recent": [], "hours": {}, "donors": {}, "followups": []}


def _v(L, variant):
    return L["variants"].setdefault(str(variant), {"posts": 0, "wins": 0})


def _text_key(text):
    return hashlib.sha1(" ".join(str(text).split()).encode("utf-8")).hexdigest()[:16]


def record_post(L, variant, ts=None, text=None):
    """A post went out. With its text, the exact wording is tracked so real outcomes can teach later drafts."""
    ts = ts or time.time()
    _v(L, variant)["posts"] += 1
    key = None
    if text and str(text).strip():
        key = _text_key(text)
        texts = L.setdefault("texts", {})
        row = texts.setdefault(key, {"text": str(text)[:2000], "posts": 0, "wins": 0})
        row["posts"] += 1
        row["last"] = ts
        if len(texts) > 80:  # keep the most recent wordings only
            for old in sorted(texts, key=lambda k: texts[k].get("last", 0))[: len(texts) - 80]:
                texts.pop(old, None)
    L["recent"] = (L["recent"] + [[ts, variant, key]])[-40:]


def proven_texts(L, limit=2, min_posts=3):
    """Real past wordings that were followed by donations, best first (never invented)."""
    rows = [r for r in L.get("texts", {}).values() if r.get("wins") and r.get("posts", 0) >= min_posts]
    rows.sort(key=lambda r: -((r["wins"] + 1) / (r["posts"] + 2)))
    return [r["text"] for r in rows[:limit]]


def credit_money(L, ts=None):
    """Money arrived: credit the latest post of the last hour and count the hour of day."""
    ts = ts or time.time()
    hour = str(datetime.datetime.fromtimestamp(ts, PKT).hour)
    L["hours"][hour] = L["hours"].get(hour, 0) + 1
    for entry in reversed(L["recent"]):
        t, variant = entry[0], entry[1]
        if 0 <= ts - t <= WINDOW:
            _v(L, variant)["wins"] += 1
            key = entry[2] if len(entry) > 2 else None
            if key and key in L.get("texts", {}):
                L["texts"][key]["wins"] += 1
            return variant
    return None


def pick_variant(L, count, avoid=()):
    """Thompson sampling: favour wordings that brought money, still try the others."""
    best, best_score = None, -1.0
    for i in range(count):
        if i in avoid and count > len(avoid):
            continue
        v = L["variants"].get(str(i), {"posts": 0, "wins": 0})
        score = random.betavariate(v["wins"] + 1, max(0, v["posts"] - v["wins"]) + 1)
        if score > best_score:
            best, best_score = i, score
    return best if best is not None else 0


def hot_hours(L, top=3):
    total = sum(L["hours"].values())
    if total < 3:
        return []
    ranked = sorted(L["hours"].items(), key=lambda kv: -kv[1])[:top]
    return [int(h) for h, c in ranked if c >= 2]


def add_donor(L, phone, name="", ts=None):
    ts = ts or time.time()
    d = L["donors"].setdefault(phone, {"name": name, "first": ts, "last": ts, "count": 0, "dm": 0})
    d["last"] = ts
    d["count"] += 1
    if name and not d.get("name"):
        d["name"] = name


def repeat_donors(L, cooldown_days=3, now=None):
    """Donors we have not written to for a few days: candidates to thank again and ask to help once more."""
    now = now or time.time()
    return [
        (p, d.get("name", ""))
        for p, d in L["donors"].items()
        if now - max(d["last"], d.get("dm", 0)) >= cooldown_days * 86400
    ]


def mark_dm(L, phone, ts=None):
    if phone in L["donors"]:
        L["donors"][phone]["dm"] = ts or time.time()


def add_followup(L, phone, name, due, kind="later"):
    if any(f["phone"] == phone and f["kind"] == kind for f in L["followups"]):
        return False
    L["followups"].append({"phone": phone, "name": name, "due": due, "kind": kind})
    return True


def followups_due(L, now=None):
    now = now or time.time()
    due = [f for f in L["followups"] if f["due"] <= now]
    L["followups"] = [f for f in L["followups"] if f["due"] > now]
    return due


def tomorrow_at(hour, now=None):
    now = now or time.time()
    d = datetime.datetime.fromtimestamp(now, PKT) + datetime.timedelta(days=1)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).timestamp()


def insights(L, names=None):
    """Short plain sentences the owner can read."""
    out = []
    ranked = sorted(
        ((int(k), v) for k, v in L["variants"].items() if v["posts"] >= 3),
        key=lambda kv: -(kv[1]["wins"] / kv[1]["posts"]),
    )
    if ranked and ranked[0][1]["wins"]:
        i, v = ranked[0]
        label = (names or {}).get(i, f"wording #{i + 1}")
        out.append(f'"{label}" works best so far ({v["wins"]} donations after {v["posts"]} posts).')
    hh = hot_hours(L)
    if hh:
        out.append(
            "Money mostly comes around "
            + ", ".join(f"{h:02d}:00" for h in sorted(hh))
            + ", so I post a little faster then."
        )
    if L["donors"]:
        out.append(
            f"{len(L['donors'])} people have said they donated; I will thank them again in a few days and ask them to help once more."
        )
    return out
