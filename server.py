import sys
import caption_facts, case_plan, message_rules, team_rules
import json, subprocess, urllib.request, urllib.parse, threading, time, uuid, datetime, math, re, secrets, os, base64, hashlib, gzip
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from persist import configured_store, atomic_write
import manual_commands
import dm_composer, reply_setup
import ai_call

DM_DAILY_CAP = 0  # 0 = no daily DM limit (old 40 ceiling removed)
DM_MIN_GAP = 0  # 0 = no server-side minimum; the gap the owner picks for a batch is what is used
import dm_templates
from state_shapes import mapping, memories, history as valid_history
import chat_policy
import timed_tasks
import draft_flow
import draft_workflow
from chat_memory import Knowledge, safe_text
from functools import wraps

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR", "/data/studio"))
DATA.mkdir(parents=True, exist_ok=True)
DRAFT = DATA / "drafts.json"
DEVICE = os.environ.get("WHATSAPP_DEVICE_ID", "")
GOWA_URL = os.environ.get("GOWA_URL", "http://127.0.0.1:3000").rstrip("/")
GROUPS = {
    "main": ("GiveLife Foundation", "120363423121755785@g.us"),
    "community": ("Upwork Community 2026", "120363398623589385@g.us"),
    "fiverr": ("Fiverr Course 2026", "120363411617215937@g.us"),
    "upwork": ("Upwork Course 2026", "120363430624868021@g.us"),
    "uet": ("Fiverr Course UET", "120363412286860707@g.us"),
    "toprated": ("Top Rated Upworkers", "120363427826119453@g.us"),
}
FREELANCE = ["community", "fiverr", "upwork", "uet", "toprated"]
LAST_LOCAL = {}
JOBS = {}
JOB_CANCEL = {}
REQUEST_JOBS = {}
LOCK = threading.RLock()
SEND_LOCK = threading.RLock()
ACTIVE = None
WIRE_LOCK = threading.RLock()
OWNER_REVISION = 0
OWNER_GUARD = threading.local()
REQUEST_STOP = threading.local()  # .fn() is True once the owner tapped Stop for this request
STOP_EVENTS = {}  # stop_id -> Event, set by /stop-send


class SendStopped(Exception):
    pass


def check_stop():
    stop = getattr(REQUEST_STOP, "fn", None)
    if stop and stop():
        raise SendStopped()


def _stop_id(sid):
    return sid if isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,100}", sid) else None


def stop_event(sid):
    with LOCK:
        while len(STOP_EVENTS) > 200 and sid not in STOP_EVENTS:
            STOP_EVENTS.pop(next(iter(STOP_EVENTS)))
        return STOP_EVENTS.setdefault(sid, threading.Event())


def watch_stop(sid):
    """Make check_stop() honour Stop for this request thread (only when the page sent a stop_id)."""
    sid = _stop_id(sid)
    REQUEST_STOP.fn = stop_event(sid).is_set if sid else None


def unwatch_stop(sid):
    REQUEST_STOP.fn = None
    sid = _stop_id(sid)
    if sid:
        with LOCK:
            STOP_EVENTS.pop(sid, None)


def stop_job(ident):
    """Stop a manual group job: nothing further is sent. A message already uploading cannot be recalled."""
    with LOCK:
        job, event = JOBS.get(ident), JOB_CANCEL.get(ident)
        if not job or not event or job.get("done"):
            return False
        event.set()
        job["cancel_reason"] = "Stopped by owner."
        return True


ASSIST_TASKS = {}
EVAL_TASKS = {}

NEW_UI_PREFIX = "html body.ui2" + "".join(":not(#%s)" % c for c in "abcdefgh")  # beats every existing rule
SITE_ICONS = {
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon.ico": ("favicon.ico", "image/png"),
    "/favicon-32.png": ("favicon-32.png", "image/png"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
}


def prune_finished(table, keep=100, protect=(), *, finished=lambda v: bool(v.get("done"))):
    """Long-running host: drop the oldest finished entries so in-memory job tables cannot grow forever.
    Unfinished work and anything named in `protect` is never dropped; saved copies stay in the store."""
    try:
        extra = len(table) - keep
        for key in list(table):
            if extra <= 0:
                break
            if key in protect:
                continue
            value = table.get(key)
            if isinstance(value, dict) and finished(value):
                table.pop(key, None)
                extra -= 1
    except Exception:
        pass


def serialized_send(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with WIRE_LOCK:
            for secret_name in ("DEEPSEEK_API_KEY", "UI_ACCESS_KEY", "DB_URI"):
                secret = os.environ.get(secret_name, "")
                if len(secret) > 8 and any(
                    secret in str(value) for value in (*args, *kwargs.values())
                ):
                    raise ValueError(
                        "Private service credentials cannot be included in outgoing messages."
                    )
            revision = getattr(OWNER_GUARD, "revision", None)
            if revision is not None and revision != OWNER_REVISION:
                raise ValueError("Superseded by your newer instruction. Nothing was sent.")
            event = getattr(OWNER_GUARD, "cancel_event", None)
            if event is not None and event.is_set():
                return {"code": "CANCELLED", "message": "Stopped by the newer instruction."}
            return fn(*args, **kwargs)

    return call


STORE = configured_store()
CAMPAIGN_CONTACTED = (
    set(json.loads((ROOT / "campaign-blocks.json").read_text()))
    if (ROOT / "campaign-blocks.json").exists()
    else set()
)
BLOCKED = set(CAMPAIGN_CONTACTED)


def persist_file(key, path):
    if STORE:
        write = getattr(
            STORE, "put_retry", STORE.put
        )  # retries in the background if the database blips
        write(key, path.read_text(encoding="utf-8"))


_DRAFT_REPAIR = threading.Lock()


def read_drafts():
    """The saved messages. A damaged file is set aside (never deleted) and the last database copy is
    restored in its place, so one bad write can never break every screen that shows a draft."""
    try:
        data = json.loads(DRAFT.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        raise ValueError("drafts file is not an object")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        pass
    with _DRAFT_REPAIR:
        try:
            data = json.loads(DRAFT.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data  # another request already repaired it
        except (OSError, ValueError):
            pass
        restored = {}
        try:
            if STORE:
                copy = STORE.get("drafts") or ""
                copy = json.loads(copy) if isinstance(copy, str) else copy
                restored = copy if isinstance(copy, dict) else {}
        except Exception:
            restored = {}
        try:
            os.replace(DRAFT, DRAFT.with_name(DRAFT.name + ".corrupt"))
        except OSError:
            pass
        if restored:
            try:
                atomic_write(DRAFT, json.dumps(restored, ensure_ascii=False))
            except OSError:
                pass
        print("[drafts] damaged file set aside; " + ("restored from database" if restored else "starting empty"), flush=True)
        return restored


def api(path):
    req = urllib.request.Request(GOWA_URL + path, headers={"X-Device-Id": DEVICE})
    with urllib.request.urlopen(req, timeout=12) as r:
        return mapping(json.load(r))


def api_result(path):
    return mapping(mapping(api(path)).get("results"))


def api_messages(path):
    data = api_result(path).get("data", [])
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


_CHAT_STAMPS = {"at": 0.0, "map": {}}
_CHAT_CACHE = {}  # jid -> (stamp, messages, fetched_at)
_CHAT_LOCK = threading.Lock()


def _chat_stamps():
    """last_message_time per chat from one small list call, refreshed at most every 15 s."""
    with _CHAT_LOCK:
        if time.time() - _CHAT_STAMPS["at"] < 15:
            return _CHAT_STAMPS["map"]
    try:
        data = api_result("/chats?limit=100").get("data", [])
    except Exception:
        return {}
    stamps = {
        str(c.get("jid")): str(c.get("last_message_time") or "")
        for c in data
        if isinstance(c, dict) and c.get("jid")
    }
    with _CHAT_LOCK:
        _CHAT_STAMPS.update(at=time.time(), map=stamps)
    return stamps


def _seconds_since(stamp):
    try:
        t = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except Exception:
        return None


def scan_messages(jid):
    """Reply-scan read of a chat. A chat nobody has written in since we last read it is served
    from memory: every read is a remote database query, and re-reading ~60 idle chats every two
    minutes used up the free database transfer quota. A chat is only reused when its last
    message was already 3+ minutes old when read, so a new message can never be missed.
    Sending and delete checks never use this; they always read live."""
    path = "/chat/" + urllib.parse.quote(jid, safe="") + "/messages?limit=20"
    stamp = _chat_stamps().get(jid)
    if stamp:
        with _CHAT_LOCK:
            hit = _CHAT_CACHE.get(jid)
        if hit and hit[0] == stamp and time.time() - hit[2] < 900:
            return list(hit[1])
    messages = api_messages(path)
    if stamp:
        settled = _seconds_since(stamp)
        if settled is not None and settled >= 180:
            with _CHAT_LOCK:
                if len(_CHAT_CACHE) >= 200:  # bounded: forget the oldest chats first
                    for old in sorted(_CHAT_CACHE, key=lambda k: _CHAT_CACHE[k][2])[:50]:
                        _CHAT_CACHE.pop(old, None)
                _CHAT_CACHE[jid] = (stamp, messages, time.time())
    return messages


def custom_recipient(body):
    target = str(body.get("target", ""))
    if target == "test":
        return "120363431210327603@g.us", True
    if target in GROUPS:
        return GROUPS[target][1], True
    if target != "phone":
        raise ValueError("Choose a saved group or phone number.")
    phone = re.sub(r"[\s()+-]", "", str(body.get("phone", "")))
    if phone.startswith("00"):
        phone = phone[2:]
    if phone.startswith("03") and len(phone) == 11:
        phone = "92" + phone[1:]
    if not re.fullmatch(r"[1-9]\d{7,14}", phone):
        raise ValueError("Enter a valid phone number with country code, such as +92…")
    return phone, False


def send_custom(body):
    jid, is_group = custom_recipient(body)
    message = body.get("message", "")
    if (
        is_group
        and read_left() <= 0
        and isinstance(message, str)
        and completed_case_appeal(message)
    ):
        raise ValueError("Not sent: completed case cannot use an old fundraising request.")
    if is_group:
        message = focus_bank().get("group").get("source", "")
    if isinstance(message, str) and body.get("kind") in (
        "dm_appeal",
        "donor_registry",
        "donor_manual",
        "donor_batch",
        "owner_text",
    ):
        message = caption_facts.current(sys.modules[__name__], message)
        body = {**body, "message": message}
    if not isinstance(message, str):
        raise ValueError("Message must be text.")
    # A closed case refuses every donor appeal first, with the clearest reason.
    if (
        not is_group
        and body.get("kind") in ("dm_appeal", "donor_registry", "donor_manual", "donor_batch")
        and read_left() <= 0
    ):
        raise ValueError(
            "Not sent: the case is complete (Rs. 0 left). Set a new amount left before sending an appeal."
        )
    if read_left() <= 0 and completed_case_appeal(message):
        raise ValueError(
            "Not sent: this completed case caption contains a fundraising appeal. Replace it with a thank-you message."
        )
    if read_left() <= 0 and body.get("poster") is True:
        body = {**body, "poster": False}  # do not attach the old fundraising poster to a thank-you
    if not is_group and body.get("kind") in (
        "dm_appeal",
        "donor_registry",
        "donor_manual",
        "donor_batch",
    ):
        if read_left() <= 0:
            raise ValueError(
                "Not sent: the case is complete (Rs. 0 left). Set a new amount left before sending an appeal."
            )
        normal = (
            donors().book.normal_amount_for_phone(body.get("phone", "")) if body.get("phone") else 0
        )
        message = greet_text(message, body.get("name", ""), body.get("gender", "Brother"), normal)
        if dm_composer.unverified_medical_claim(message):
            raise ValueError(
                "Not sent: the saved DM contains an unverified claim about spreading paralysis or finger numbness. Correct the caption first."
            )
        if not dm_composer.complete(message):
            raise ValueError(
                "The full DM is incomplete. Restore its paragraphs and payment details before sending."
            )
    if not is_group and body.get("kind") == "owner_text" and "gender" in body:
        message = dm_composer.personalize(
            message, body.get("name", ""), body.get("gender", "Brother")
        )
    if not is_group and body.get("kind") in ("volunteer_batch", "volunteer_manual"):
        message = message.replace("{name}", str(body.get("name") or "").strip() or "friend")
    if not message.strip() or len(message) > 10000:
        raise ValueError("Write a message of 1 to 10,000 characters.")
    if not STORE:
        raise ValueError("Persistent send records are unavailable. Try again later.")
    manual = body.get("kind") in ("donor_manual", "team_msg", "owner_text")
    explicit_batch = body.get("kind") in ("donor_batch", "volunteer_batch", "volunteer_flow")
    if not SEND_LOCK.acquire(blocking=manual or explicit_batch):
        raise ValueError("Another send is running. Please wait for it to finish.")
    try:
        try:
            status = api_result("/devices/" + DEVICE + "/status")
        except Exception:
            status = {}  # the WhatsApp service is restarting or unreachable: nothing was sent
        if not status.get("is_connected") or not status.get("is_logged_in"):
            raise ValueError("WhatsApp is disconnected. Tap WhatsApp to reconnect.")
        now = time.time()
        saved = STORE.get("last_sent", {})
        if not is_group:
            digest = hashlib.sha256(jid.encode()).hexdigest()
            alternate = hashlib.sha256((jid + "@s.whatsapp.net").encode()).hexdigest()
            explicit = manual or explicit_batch
            records = (
                {
                    key: STORE.get(key)
                    for key in (
                        "optout_" + alternate,
                        "optout_" + digest,
                        "dm_recipient_" + alternate,
                        "dm_recipient_" + digest,
                    )
                }
                if not hasattr(STORE, "get_many")
                else STORE.get_many(
                    (
                        "optout_" + alternate,
                        "optout_" + digest,
                        "dm_recipient_" + alternate,
                        "dm_recipient_" + digest,
                    )
                )
            )
            if jid == norm_phone(OWNER_PHONE):
                raise ValueError("Your own account is excluded from donor sending.")
            exclusions = BLOCKED - CAMPAIGN_CONTACTED if explicit else BLOCKED
            # A deliberate one-person send by the owner overrides an auto-detected opt-out; batches and automation still honour it.
            if not manual and (
                alternate in exclusions
                or digest in exclusions
                or records.get("optout_" + alternate)
                or records.get("optout_" + digest)
            ):
                raise ValueError("This recipient is blocked or opted out.")
            if not explicit:
                for key in ("dm_recipient_" + alternate, "dm_recipient_" + digest):
                    previous = records.get(key)
                    if previous:
                        raise ValueError(
                            "This recipient was contacted before. Check WhatsApp before sending again."
                        )
            ledger = STORE.get("dm_daily", {})
            day = (
                datetime.datetime.fromtimestamp(now, datetime.timezone(datetime.timedelta(hours=5)))
                .date()
                .isoformat()
            )
            if ledger.get("day") != day:
                ledger = {"day": day, "count": 0, "last": ledger.get("last", 0)}
            # DM Guard: optional ceiling (DM_DAILY_CAP, off when 0) for every batch and Auto path; owner one-person sends are never blocked (but count).
            if DM_DAILY_CAP and not manual and ledger["count"] >= DM_DAILY_CAP:
                raise ValueError(
                    f"The {DM_DAILY_CAP}-DM daily limit has been reached. More tomorrow."
                )
            if not manual and ledger.get("optouts", 0) >= 2:
                raise ValueError("DMs paused for today: 2 people asked not to be messaged.")
            if (
                DM_MIN_GAP
                and not manual
                and not (explicit_batch and body.get("first_in_batch") is True)
                and now - ledger.get("last", 0) < DM_MIN_GAP
            ):
                raise ValueError(f"Wait at least {DM_MIN_GAP // 60} minutes between DMs.")
            check_stop()  # last point where Stop leaves no trace
            prior_ledger = dict(ledger)
            prior_recipient = records.get("dm_recipient_" + digest) or {}
            ledger.update(count=ledger["count"] + 1, last=now)
            STORE.put("dm_daily", ledger)
            STORE.put("dm_recipient_" + digest, {"state": "uncertain", "time": now})
        # Every group delivery (including direct/custom sends) uses the shared saved bank.
        if is_group:
            message = focus_bank().reserve_groups(message, 1)[0]
        # Reserve before dispatch. A network failure must not silently allow duplicates.
        try:
            if body.get("attachment"):
                result = send_batch_attachment(jid, message, body["attachment"])
            elif body.get("poster") is True:
                result = send_image(jid, message)
            else:
                check_stop()
                req = urllib.request.Request(
                    GOWA_URL + "/send/message",
                    data=json.dumps({"phone": jid, "message": message}).encode(),
                    headers={"X-Device-Id": DEVICE, "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=40) as response:
                    result = mapping(json.load(response))
        except SendStopped:
            # Nothing was uploaded: undo the "contacted" reservation so this person can be sent to later.
            if not is_group:
                STORE.put("dm_daily", prior_ledger)
                STORE.put("dm_recipient_" + digest, prior_recipient)
            raise
        except Exception:
            result = {
                "code": "UNCERTAIN",
                "message": "Send not confirmed. Check WhatsApp before retrying.",
            }
        if is_group and result.get("code") == "SUCCESS":
            saved[jid] = time.time()
            STORE.put("last_sent", saved)
            LAST_LOCAL[jid] = time.time()
            record_delivery(jid, message, result)
        STORE.put(
            "custom_receipt_" + uuid.uuid4().hex,
            {
                "time": now,
                "jid": jid,
                "code": result.get("code"),
                "message_id": mapping(result.get("results")).get("message_id"),
            },
        )
        if not is_group:
            STORE.put(
                "dm_recipient_" + digest, {"state": result.get("code", "UNCERTAIN"), "time": now}
            )
        if result.get("code") == "SUCCESS":
            remember_manual(
                {
                    "kind": "text",
                    "to": jid,
                    "text": message,
                    "with_picture": body.get("poster") is True,
                }
            )
        return result
    finally:
        SEND_LOCK.release()


HOOKS = [
    (
        "Imagine it was your own 2-year-old.",
        "If it were your child, you would not wait. Send what you can now.",
    ),
    (
        "Rs. 1,000 is a small bill for you. For Yousuf it is a real part of his treatment.",
        "Do not think about the amount. Think about him. Send Rs. 1,000 or Rs. 2,000.",
    ),
    (
        "Everyone here will read this. If everyone only reads, he gets nothing.",
        "Do not leave it for the next person. The next person is thinking the same.",
    ),
    (
        "His mother is watching him. She cannot do anything. You can.",
        "You cannot fix his illness yourself, but you can fund his treatment.",
    ),
    (
        "Doctors can treat this. Only one thing is missing: people like you.",
        "Your Rs. 1,000 or 2,000 can help him get treatment.",
    ),
    (
        "He is 2. He cannot ask for help. This message is his voice.",
        "Be his voice. Send Rs. 1,000 or Rs. 2,000.",
    ),
    (
        "Scroll past this, and nothing changes for him. Send Rs. 1,000, and something does.",
        "One send. One minute. It matters to a 2-year-old and his family.",
    ),
    ("Only {P2} people are needed.", "Be one of the {P2}. Not tomorrow. Now."),
]


def read_left():
    state = (DATA / "state.md").read_text(encoding="utf-8-sig")
    m = re.search(r"^LEFT:\s*(\d+)", state, re.M)
    return int(m[1]) if m else 39000


def poster_left():
    m = re.search(
        r"^POSTER_LEFT:\s*(\d+)", (DATA / "state.md").read_text(encoding="utf-8-sig"), re.M
    )
    return int(m[1]) if m else None


def write_left(left):
    f = DATA / "state.md"
    state = f.read_text(encoding="utf-8-sig")
    state = (
        re.sub(r"^LEFT:.*$", "LEFT: " + str(left), state, flags=re.M)
        if re.search(r"^LEFT:", state, re.M)
        else "LEFT: " + str(left) + "\n" + state
    )
    atomic_write(f, state)
    persist_file("campaign", f)


ALMOST = [
    (
        "We are almost there. Only Rs. {L} left for Yousuf.",
        "Just {P2} people can finish this today.",
    ),
    (
        "Rs. {L} is all that stands between Yousuf and his treatment.",
        "Be one of the last {P2}. Today.",
    ),
    (
        "The last few people decide it. Rs. {L} left.",
        "If {P2} people send Rs. 2,000 now, it is done.",
    ),
]


def active_case_name():
    """Use the actual selected case rather than an older hard-coded patient's story."""
    raw = STORE.get("cases", {}) if STORE else {}
    if (not isinstance(raw, dict) or not raw) and (DATA / "cases.json").exists():
        try:
            raw = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
    if not isinstance(raw, dict):
        return "Current case"
    name = next(
        (
            c.get("name", "Current case")
            for c in raw.get("cases", [])
            if isinstance(c, dict) and c.get("id") == raw.get("current")
        ),
        "Current case",
    )
    if name == "Current case" and DRAFT.exists():
        # A legacy case had no title. Preserve its saved Yousuf draft instead of
        # unexpectedly replacing that existing message during a balance update.
        try:
            saved = read_drafts()
            if re.search(r"(?i)\bYousuf\b", str(saved.get("group", ""))):
                return "Yousuf"
        except (OSError, ValueError, TypeError):
            pass
    return name


def _case_title(name):
    return " ".join(str(name or "Current case").replace("*", " ").split())[:60] or "Current case"


def build_group(n, left, case_name=None):
    name = _case_title(case_name if case_name is not None else active_case_name())
    p2, p1 = math.ceil(left / 2000), math.ceil(left / 1000)
    if left <= 0:
        return f"*{name}: Case complete.*\n\nThank you to everyone who supported this case. There is Rs. 0 left to raise.\n\n- GiveLife Foundation"
    if name.casefold() not in ("yousuf", "current case"):
        # Details are intentionally generic until the owner supplies verified facts.
        return (
            f"*GiveLife Foundation: Support needed for {name}*\n\n"
            "Please review the case details and help if you can.\n\n"
            f"*_Rs. {left:,} LEFT_*\n\n"
            f"*_{p2} people donating Rs. 2,000_*\n"
            f"*_OR {p1} people donating Rs. 1,000_* 🤲\n\n"
            "*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n"
            "- GiveLife Foundation"
        )
    pool = ALMOST if 0 < left <= 10000 else None
    hook = (
        (pool[n % len(pool)][0] if pool else HOOKS[n % 8][0])
        .replace("{P2}", str(p2))
        .replace("{L}", f"{left:,}")
    )
    push = (
        (pool[(n + 1) % len(pool)][1] if pool else HOOKS[(n * 3 + 1) % 8][1])
        .replace("{P2}", str(p2))
        .replace("{L}", f"{left:,}")
    )
    return (
        f"*{hook}*\n\nFluid in Yousuf's brain *can paralyse his body and damage his eyesight.* Both his kidneys are badly swollen. 💔\n\n"
        f"*_Rs. {left:,} LEFT_*\n\n*_{p2} people donating Rs. 2,000_*\n*_OR {p1} people donating Rs. 1,000_* 🤲\n{push}\n\n"
        "*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n\nReply *Done* after you donate.\n- GiveLife Foundation"
    )


def build_dm(sel, left, case_name=None):
    name = _case_title(case_name if case_name is not None else active_case_name())
    if left <= 0:
        return f"Assalam o alaikum Brother,\n\nThe case for {name} has been completed. Thank you to everyone who helped.\n\n- GiveLife Foundation"
    if name.casefold() not in ("yousuf", "current case"):
        p2, p1 = math.ceil(left / 2000), math.ceil(left / 1000)
        return (
            f"Assalam o alaikum Brother,\n\nGiveLife Foundation is collecting support for {name}. "
            "Please review the case details before donating.\n\n"
            f"*Rs. {left:,} left*\n"
            f"{p2} people giving Rs. 2,000 or {p1} giving Rs. 1,000 can help complete the amount.\n\n"
            "*03097458815* EASYPAISA ONLY (Wajdan Khan)\n\n- GiveLife Foundation"
        )
    index = sel[0] if isinstance(sel, (list, tuple)) and sel else sel if isinstance(sel, int) else 0
    return dm_templates.build(index, left)


def variant(advance):
    file = DATA / "variant-state.json"
    try:
        n = int(json.loads(file.read_text()).get("index", 0)) if file.exists() else 0
    except (OSError, ValueError, TypeError, AttributeError):
        n = 0  # a damaged counter only restarts the rotation
    if advance:
        atomic_write(file, json.dumps({"index": n + 1}))
        persist_file("variants", file)
        n += 1
    return n


def dm_selection(new):
    file = DATA / "dm-state.json"
    try:
        raw = json.loads(file.read_text())
    except (OSError, ValueError):
        raw = [0]
    if isinstance(raw, int):
        raw = [raw]
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], int):
        raw = [0]
    index = raw[0] % dm_templates.COUNT
    if new:
        import random

        old = index
        if dm_templates.COUNT > 1:  # with one template there is nothing else to pick (and no endless loop)
            while True:
                index = random.randrange(dm_templates.COUNT)
                if index != old:
                    break
        atomic_write(file, json.dumps([index]))
    return [index]


def completed_case_appeal(text):
    """Detect fundraising in closed-case drafts without blocking proper completion thanks.

    Do not confuse 'Rs. 0 left to raise' in an accurate completion update with a
    request for 'Rs. 0 LEFT' and zero donors. Normalize WhatsApp formatting first.
    """
    value = re.sub(r"[*_]+", " ", str(text or ""))
    return bool(
        re.search(
            r"(?i)\b(?:rs\.?\s*0\s*(?:left(?!\s+to\s+raise)|still\s+needed|needed|remaining)"
            r"|rs\.?\s*[1-9][\d,]*\s+(?:left|needed|remaining)"
            r"|0\s+people\s+(?:donating|giving)"
            r"|people\s+(?:donating|giving)\s+rs\.?\s*[\d,]+"
            r"|(?:donate|donation|donating|contribute)\s+(?:now|today|to|rs\.?|for|here|via)"
            r"|help\s+(?:him|her|them|this\s+child)\s+(?:get|pay\s+for)\s+treatment"
            r"|reply\s+done\s+after\s+you\s+donate"
            r"|easypaisa|jazzcash|\d+\s+people\s+can\s+(?:finish|complete))\b",
            value,
        )
    )


def ensure_completed_drafts():
    """Repair legacy mixed completion/appeal drafts once, before showing them."""
    if read_left() > 0 or not DRAFT.exists():
        return
    with LOCK:
        drafts = read_drafts()
        changed = False
        for kind in ("group", "dm"):
            if completed_case_appeal(drafts.get(kind, "")):
                drafts[kind] = (
                    build_group(variant(False), 0)
                    if kind == "group"
                    else build_dm(dm_selection(False), 0)
                )
                changed = True
        if changed:
            atomic_write(DRAFT, json.dumps(drafts, ensure_ascii=False))
            persist_file("drafts", DRAFT)


def save_draft(key, text):
    with LOCK:
        revision = getattr(OWNER_GUARD, "revision", None)
        if revision is not None and revision != OWNER_REVISION:
            raise ValueError(
                "Superseded by your newer instruction. The old draft edit was not saved."
            )
        if key in ("group", "dm") and read_left() <= 0 and completed_case_appeal(text):
            raise ValueError(
                "This case is completed. A saved caption cannot request new donations or show Rs. 0 LEFT. Use a completion or thank-you message instead. Nothing was saved."
            )
        draft = read_drafts()
        draft[key] = text
        atomic_write(DRAFT, json.dumps(draft, ensure_ascii=False))
        persist_file("drafts", DRAFT)


_FOCUS_BANK = None


from focus_bank import VersionsPaused


_SINGLETON_LOCK = threading.RLock()  # two threads must never build two copies of a send registry


def focus_bank():
    global _FOCUS_BANK
    if _FOCUS_BANK is None:
        with _SINGLETON_LOCK:
            if _FOCUS_BANK is None:
                from focus_bank import FocusBank

                _FOCUS_BANK = FocusBank(sys.modules[__name__])
    return _FOCUS_BANK


def get_message(kind):
    if kind not in ("group", "dm"):
        raise ValueError("Choose group or DM.")
    with LOCK:
        ensure_completed_drafts()
        return {"kind": kind, "text": read_drafts()[kind]}


def next_message():
    bank = focus_bank().get("group") if STORE else {}
    if bank.get("revision"):
        items = bank.get("items", [])
        if not items:
            return get_message("group")["text"]
        # same amount refresh as a real send, so the preview never shows an old balance
        text = caption_facts.current(sys.modules[__name__], items[int(time.time()) % len(items)])
        save_draft("group", text)
        return text
    with LOCK:
        text = build_group(variant(True), read_left())
        save_draft("group", text)
        return text


def next_dm():
    bank = focus_bank().get("dm") if STORE else {}
    if bank.get("revision"):
        if not bank.get("items"):
            return get_message("dm")["text"]
        text = focus_bank().next_dm_version() or get_message("dm")["text"]
        save_draft("dm", text)
        return text
    with LOCK:
        text = build_dm(dm_selection(True), read_left())
        save_draft("dm", text)
        return text


def regenerate_drafts(left, case_name=None):
    """Fresh captions for this case only; do not inherit another patient's medical facts."""
    with LOCK:
        draft = read_drafts() if DRAFT.exists() else {}
        draft["group"] = build_group(variant(False), left, case_name)
        draft["dm"] = build_dm(dm_selection(False), left, case_name)
        atomic_write(DRAFT, json.dumps(draft, ensure_ascii=False))
        persist_file("drafts", DRAFT)


def set_left(left):
    with LOCK:
        revision = getattr(OWNER_GUARD, "revision", None)
        if revision is not None and revision != OWNER_REVISION:
            raise ValueError("Superseded by your newer instruction. The amount was not changed.")
        old = read_left()
        before = read_drafts() if DRAFT.exists() else {}
        task = workflow()
        custom = next((k for k in ("group", "dm") if task.current(k, before.get(k, ""))), None)
        write_left(left)
        if int(left) <= 0:
            CAMPAIGN["stop"] = True
            if DONORS is not None and DONORS.jobs.active:
                try:
                    DONORS.jobs.cancel()
                    auto_log("Case complete (Rs. 0 left): the running donor DM batch was stopped.")
                except Exception:
                    pass
            if auto_on():
                set_auto(False)
        try:
            ENGINE.amount_updated()
        except NameError:
            pass
        if int(left) <= 0:
            # Never keep fundraising wording such as "0 people donating" in a closed case,
            # even when the owner previously saved a custom caption.
            g = build_group(variant(False), 0)
            d = build_dm(dm_selection(False), 0)
        else:
            # Keep exactly the owner's saved Group and DM wording (including
            # medical facts, appeal angle and formatting), changing only
            # the balance and the calculated people counts. The old branch
            # rebuilt generic drafts when no special workflow was active.
            g = (
                draft_workflow.update_amount(before["group"], old, left)
                if isinstance(before.get("group"), str) and before["group"].strip()
                else build_group(variant(False), left)
            )
            d = (
                draft_workflow.update_amount(before["dm"], old, left)
                if isinstance(before.get("dm"), str) and before["dm"].strip()
                else build_dm(dm_selection(False), left)
            )
        save_draft("group", g)
        save_draft("dm", d)
        if int(left) > 0:
            caption_facts.transform_banks(
                sys.modules[__name__], lambda text: draft_workflow.update_amount(text, old, left)
            )
        if custom:
            task.commit(custom, g if custom == "group" else d)
        return g, d


def poster_media(use="group"):
    """Return the selected media; never silently send an old image in place of a missing video."""
    for prefix in (("dm-",) if use == "dm" else ()) + ("",):
        key = "dm_poster" if prefix else "poster"
        kind = DATA / (prefix + "poster-kind.txt")
        video = DATA / (prefix + "poster.mp4")
        picture = DATA / (prefix + "poster.jpg")
        try:
            selected = kind.read_text(encoding="utf-8").strip()
        except OSError:
            selected = STORE.get(key + "_kind", "image") if STORE else "image"
        if selected == "video":
            if not video.exists() and STORE:
                encoded = STORE.get(key + "_video_b64")
                if encoded:
                    try:
                        write_atomic(video, base64.b64decode(encoded, validate=True))
                        write_atomic(kind, b"video")
                    except (ValueError, OSError, base64.binascii.Error):
                        pass
            # Fail closed instead of sending a previous fundraising picture.
            return video
        if picture.exists():
            return picture
        if STORE:
            encoded = STORE.get(key + "_b64")
            if encoded:
                try:
                    write_atomic(picture, base64.b64decode(encoded, validate=True))
                    write_atomic(kind, b"image")
                    return picture
                except (ValueError, OSError, base64.binascii.Error):
                    pass
    return DATA / "poster.jpg"


def post_media(jid, cap, path):
    """Send one picture or MP4 video with its caption file through the WhatsApp gateway."""
    if not Path(path).is_file():
        raise ValueError(
            "The saved poster is missing. Please upload the poster again before sending."
        )
    video = str(path).endswith(".mp4")
    return subprocess.run(
        [
            "curl",
            "-s",
            "--max-time",
            "150" if video else "60",
            "-X",
            "POST",
            GOWA_URL + ("/send/video" if video else "/send/image"),
            "-H",
            f"X-Device-Id: {DEVICE}",
            "-F",
            f"phone={jid}",
            "-F",
            (f"video=@{path};type=video/mp4" if video else f"image=@{path};type=image/jpeg"),
            "-F",
            f"caption=<{cap}",
            "-F",
            "compress=false",
        ],
        capture_output=True,
    )


@serialized_send
def send_batch_attachment(jid, caption, ident):
    import batch_media

    path, mime = batch_media.load(STORE, ident, ATT)
    field = "video" if mime == "video/mp4" else "image" if mime.startswith("image/") else "file"
    cap = ATT / ("caption-" + uuid.uuid4().hex + ".txt")
    atomic_write(cap, caption)
    try:
        r = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                "150",
                "-X",
                "POST",
                GOWA_URL + "/send/" + field,
                "-H",
                f"X-Device-Id: {DEVICE}",
                "-F",
                f"phone={jid}",
                "-F",
                f"{field}=@{path};type={mime}",
                "-F",
                f"caption=<{cap}",
            ],
            capture_output=True,
        )
        try:
            return mapping(json.loads(r.stdout))
        except Exception:
            return {
                "code": "UNCERTAIN",
                "message": "Attachment delivery was not confirmed. Check WhatsApp; do not resend automatically.",
            }
    finally:
        cap.unlink(missing_ok=True)


@serialized_send
def send_image(jid, caption, check_gap=False, _retry=True):
    caption = dm_composer.payment_fix(caption)
    if on_hold():
        return {"code": "ERROR", "message": "On hold: you told me to wait."}
    if jid in NEVER_GROUPS:
        return {"code": "ERROR", "message": "This group is never used."}
    try:
        status = api_result("/devices/" + DEVICE + "/status")
    except Exception:
        status = {}  # gateway restarting or unreachable: nothing was sent
    if not status.get("is_connected") or not status.get("is_logged_in"):
        return {"code": "ERROR", "message": "WhatsApp disconnected. Log in again."}
    if check_gap:
        saved = STORE.get("last_sent", {}) if STORE else {}
        if jid in saved:
            age = time.time() - saved[jid]
            if age < 900:
                return {
                    "code": "COOLDOWN",
                    "message": f"Posted recently. Try in {math.ceil((900 - age) / 60)} min.",
                }
        messages = api_messages("/chat/" + urllib.parse.quote(jid, safe="") + "/messages?limit=50")
        outgoing = [m for m in messages if m.get("is_from_me") is True]
        if outgoing:
            latest = max(
                datetime.datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
                for m in outgoing
            )
            age = (datetime.datetime.now(datetime.timezone.utc) - latest).total_seconds()
            if age < 900:
                return {
                    "code": "COOLDOWN",
                    "message": f"Posted recently. Try in {math.ceil((900 - age) / 60)} min.",
                }
    check_stop()
    cap = DATA / ("caption-" + uuid.uuid4().hex + ".txt")
    atomic_write(cap, caption)
    r = post_media(jid, cap, poster_media("group" if str(jid).endswith("@g.us") else "dm"))
    cap.unlink(missing_ok=True)
    try:
        result = mapping(json.loads(r.stdout))
    except Exception:
        result = {"code": "ERROR", "message": "Send not confirmed. Check WhatsApp before retrying."}
    if STORE:
        receipt = {
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "jid": jid,
            "code": result.get("code"),
            "message_id": mapping(result.get("results")).get("message_id"),
        }
        STORE.put("receipt_" + uuid.uuid4().hex, receipt)
        if result.get("code") == "SUCCESS":
            saved = STORE.get("last_sent", {})
            saved[jid] = time.time()
            STORE.put("last_sent", saved)
    if result.get("code") == "SUCCESS":
        LAST_LOCAL[jid] = time.time()
        record_delivery(jid, caption, result)
    elif _retry and jid.endswith("@g.us") and NOT_MEMBER.search(str(result.get("message", ""))):
        key = next((k for k, v in GROUPS.items() if v[1] == jid), None)
        chk = check_groups(True)
        if key and GROUPS[key][1] != jid:
            return send_image(GROUPS[key][1], caption, check_gap, False)
        if key and GROUPS[key][0] in chk.get("missing", []):
            result = {
                "code": "ERROR",
                "message": "The WhatsApp number linked to the studio is not in "
                + GROUPS[key][0]
                + ". Link the number that is in the groups.",
            }
    with (DATA / "group-send-log.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "jid": jid,
                    "caption": caption,
                    "response": result,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return result


QUEUED = {}  # legacy timers are deliberately not resumed or recreated


def cancel_jobs(reason="Replaced by a new manual send."):
    with LOCK:
        QUEUED.clear()
        for ident, event in JOB_CANCEL.items():
            if not JOBS.get(ident, {}).get("done"):
                event.set()
                JOBS[ident]["cancel_reason"] = reason


def save_job(ident):
    if STORE:
        STORE.put("send_job_" + ident, JOBS[ident])


def get_job(ident):
    job = JOBS.get(ident)
    if job is not None:
        return job
    job = STORE.get("send_job_" + ident) if STORE else None
    if job and not job.get("done"):
        job.update(
            done=True,
            message="The service restarted before this send was confirmed. Check WhatsApp; it will not retry automatically.",
        )
        if STORE:
            STORE.put("send_job_" + ident, job)
    return job


def start_send_job(keys, caption, manual=False, request_id=None, with_picture=True):
    global ACTIVE
    check_hold()
    keys = list(dict.fromkeys(keys))
    if read_left() <= 0 and isinstance(caption, str) and completed_case_appeal(caption):
        raise ValueError("Not sent: completed case cannot reuse an old fundraising caption.")
    # A send's supplied caption cannot bypass or replace the saved Group tab bank.
    if not STORE:
        raise ValueError("Persistent Group rotation is unavailable. Nothing sent.")
    bank = focus_bank().get("group")
    caption = bank.get("source", "")
    if not caption.strip():
        raise ValueError("Save the Group message first.")
    if read_left() <= 0:
        if completed_case_appeal(caption) or any(
            completed_case_appeal(v) for v in bank.get("items", [])
        ):
            raise ValueError(
                "Not sent: the completed case caption still requests donations. Nothing was sent."
            )
        # The previous fundraising poster can remain on disk after closure.
        # Avoid attaching it to a completion announcement.
        with_picture = False
    if not keys or any(k not in GROUPS and k != "test" for k in keys):
        raise ValueError("Unknown group.")
    if request_id and not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", str(request_id)):
        raise ValueError("Invalid send request id.")
    with LOCK:
        existing = REQUEST_JOBS.get(request_id) if request_id else None
        if not existing and request_id and STORE:
            old = STORE.get("manual_request_" + request_id)
            existing = old.get("job_id") if old else None
        if existing:
            return existing
        if ACTIVE:
            current = JOBS.get(ACTIVE, {})
            if (
                manual
                and current.get("manual")
                and current.get("keys") == keys
                and current.get("caption") == caption
                and current.get("with_picture", True) == with_picture
            ):
                return ACTIVE  # a double click observes the existing in-flight send; never duplicates it
            if not manual:
                return None
            cancel_jobs()
        try:
            captions = focus_bank().reserve_groups(caption, len(keys), auto=not manual)
        except VersionsPaused as exc:
            if manual:
                raise
            ENGINE.notify("versions-paused", str(exc), 3 * 3600)
            return None
        ident = uuid.uuid4().hex
        prune_finished(JOBS, 100, protect=(ACTIVE, LAST_JOB.get("id")))
        for stale in [k for k in JOB_CANCEL if k not in JOBS]:
            JOB_CANCEL.pop(stale, None)
        JOBS[ident] = {
            "done": False,
            "results": [],
            "message": "Sending now…",
            "manual": bool(manual),
            "keys": keys,
            "caption": caption,
            "with_picture": bool(with_picture),
        }
        if captions:
            JOBS[ident]["captions"] = captions
        JOB_CANCEL[ident] = threading.Event()
        ACTIVE = ident
        LAST_JOB["id"] = ident
        if request_id:
            REQUEST_JOBS[request_id] = ident
            while len(REQUEST_JOBS) > 500:  # the store keeps every request id; memory need not
                REQUEST_JOBS.pop(next(iter(REQUEST_JOBS)), None)
            if STORE:
                STORE.put("manual_request_" + request_id, {"job_id": ident})
        save_job(ident)
    threading.Thread(target=run_job, args=(ident, keys, caption), daemon=True).start()
    return ident


GROUP_RECONNECT_TRIES = 40  # x 15 s: wait up to 10 minutes for WhatsApp before giving up on a group


def _not_sent_disconnected(result):
    return (
        isinstance(result, dict)
        and result.get("code") == "ERROR"
        and str(result.get("message", "")).startswith("WhatsApp disconnected")
    )


def _group_attempt(job, jid, outgoing):
    """One try at one group. Transport trouble becomes a result, never an exception that ends the job."""
    try:
        if job.get("with_picture", True):
            return send_image(jid, outgoing, not job.get("manual", False))
        result = send_text(jid, outgoing)
        if result.get("code") == "SUCCESS":
            record_delivery(jid, outgoing, result)
            LAST_LOCAL[jid] = time.time()
            if STORE:
                saved = STORE.get("last_sent", {})
                saved[jid] = time.time()
                STORE.put("last_sent", saved)
        return result
    except ValueError:
        raise  # hold, missing poster: a clear reason for the whole job
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), ConnectionRefusedError):
            return {"code": "ERROR", "message": "WhatsApp disconnected. Nothing was sent."}
        return {
            "code": "UNCERTAIN",
            "message": "Send not confirmed. Check WhatsApp before retrying.",
        }
    except Exception:
        return {
            "code": "UNCERTAIN",
            "message": "Send not confirmed. Check WhatsApp before retrying.",
        }


def run_job(job_id, keys, caption, queue=False):
    global ACTIVE
    job = JOBS[job_id]
    event = JOB_CANCEL.setdefault(job_id, threading.Event())
    last_send = None
    failed_in_row = 0
    try:
        for index, key in enumerate(keys):
            outgoing = caption_facts.current(
                sys.modules[__name__], job.get("captions", [caption] * len(keys))[index]
            )
            if event.is_set() or on_hold():
                break
            name, jid = (
                ("Givelife test", "120363431210327603@g.us") if key == "test" else GROUPS[key]
            )
            if last_send is not None:
                job.update(
                    message="Waiting 60 seconds between recipients before " + name,
                    next_send_at=time.time() + max(0, 60 - (time.monotonic() - last_send)),
                    next_target=key,
                )
                save_job(job_id)
                if event.wait(max(0, 60 - (time.monotonic() - last_send))):
                    break
            result, stop_all = None, False
            for attempt in range(GROUP_RECONNECT_TRIES + 1):
                with SEND_LOCK:
                    if event.is_set() or on_hold():
                        stop_all = True
                        break
                    job.update(message="Sending to " + name, next_send_at=None, next_target=key)
                    save_job(job_id)
                    outgoing = caption_facts.current(sys.modules[__name__], outgoing)
                    OWNER_GUARD.cancel_event = event
                    try:
                        result = _group_attempt(job, jid, outgoing)
                    finally:
                        OWNER_GUARD.cancel_event = None
                if not _not_sent_disconnected(result) or attempt == GROUP_RECONNECT_TRIES:
                    break
                # Nothing left the phone, so waiting and trying this same group again is safe.
                job.update(
                    message="WhatsApp is reconnecting. " + name + " is sent when it is back."
                )
                save_job(job_id)
                if event.wait(15):
                    stop_all = True
                    break
            if stop_all:
                break
            job["results"].append({"group": name, **result})
            save_job(job_id)
            if result.get("code") == "SUCCESS":
                last_send = time.monotonic()
                failed_in_row = 0
            elif result.get("code") != "COOLDOWN":
                # Never retry an uncertain/error result for this group; carry on with the others.
                failed_in_row += 1
                if failed_in_row >= 3 or _not_sent_disconnected(result):
                    break
        sent = sum(r.get("code") == "SUCCESS" for r in job["results"])
        if sent and job.get("manual"):
            # Owner-sent and scheduled group posts teach too (Auto posts are recorded by the engine).
            try:
                learning_mod.record_text(ENGINE.L, caption)
            except Exception:
                pass
        if (
            sent
            and not job.get("manual")
            and not event.is_set()
            and ACTIVE == job_id
            and read_drafts().get("group") == caption
        ):
            job["next_caption"] = next_message()
        from group_delivery import summarize

        job["message"] = (
            (job.get("cancel_reason", "Stopped by owner.") + " ")
            if event.is_set() or on_hold()
            else ""
        ) + summarize(job["results"], keys)
        job["done"] = True
        save_job(job_id)
        auto_log(
            job["message"]
            + " "
            + ", ".join(
                r["group"]
                + (" ✓" if r.get("code") == "SUCCESS" else " ✗ " + str(r.get("message", ""))[:100])
                for r in job["results"]
            ),
            quiet=bool(job.get("manual")),
        )
    except Exception as exc:
        from group_delivery import summarize

        detail = (
            " Reason: " + safe_text(str(exc), 180)
            if isinstance(exc, ValueError)
            else " The app encountered an unexpected send error; check server logs."
        )
        job.update(done=True, message=summarize(job.get("results", []), keys) + detail)
        save_job(job_id)
    finally:
        with LOCK:
            if ACTIVE == job_id:
                ACTIVE = None


import assistant

MEMORY = DATA / "memory.json"
AUTO = DATA / "autopilot.json"
AUTOLOG = []
if STORE:
    for key, f in (("memory", MEMORY), ("autopilot", AUTO)):
        v = STORE.get(key)
        if v:
            atomic_write(f, v if isinstance(v, str) else json.dumps(v))

CHATLOG = DATA / "chat.json"
RECIP = DATA / "recipient.json"
if STORE:
    for key, f in (("chat", CHATLOG), ("recipient", RECIP)):
        v = STORE.get(key)
        if v:
            atomic_write(f, v if isinstance(v, str) else json.dumps(v))
CHAT_LOCK = threading.Lock()
KNOWLEDGE = Knowledge(DATA, STORE)
_WORKFLOW = None
_WORKFLOW_STORE = None


def workflow():
    global _WORKFLOW, _WORKFLOW_STORE
    with LOCK:
        if _WORKFLOW is None or _WORKFLOW_STORE is not STORE:
            _WORKFLOW = draft_workflow.DraftWorkflow(DATA / "draft-workflow.json", STORE)
            _WORKFLOW_STORE = STORE
        return _WORKFLOW


def next_chat_actions():
    return workflow().suggest(get_message("group")["text"])


def execute_chat_action(ident):
    if not isinstance(ident, str):
        raise ValueError("Choose a current chat action.")
    with LOCK:
        caption = get_message("group")["text"]
        work = workflow()
        action = work.action(ident, caption)
        if action["type"] == "preview":
            return {"reply": caption}
        if action["type"] == "choose":
            return {"choose_group": True, "reply": "Choose a group on the main screen."}
        if action.get("job_id"):
            return {
                "job_id": action["job_id"],
                "caption": caption,
                "reply": "Showing the existing send status. Nothing was sent again.",
            }
        if not wa_ok():
            raise ValueError("WhatsApp is disconnected. Reconnect before sending.")
        key = action["target"]
        if key not in (*GROUPS, "test", "all", "free"):
            raise ValueError("Choose a known group.")
        keys = list(GROUPS) if key == "all" else FREELANCE if key == "free" else [key]
        ident_job = start_send_job(
            keys,
            caption,
            manual=True,
            request_id="chat-action-" + ident,
            with_picture=action["poster"],
        )
        work.started(ident, ident_job)
        if key != "test":
            remember_manual({"kind": "appeal", "target": key})
        label = (
            "Givelife test"
            if key == "test"
            else "all 6 groups"
            if key == "all"
            else "5 freelance groups"
            if key == "free"
            else GROUPS[key][0]
        )
        return {
            "reply": "Sending the saved "
            + ("poster + caption" if action["poster"] else "text-only message")
            + " to "
            + label
            + ".",
            "job_id": ident_job,
            "caption": caption,
        }


def chat_get(n=300):
    try:
        return valid_history(CHATLOG.read_text(encoding="utf-8"))[-n:] if CHATLOG.exists() else []
    except Exception:
        return []


def chat_add(who, text, err=False, turn_id=None, model=""):
    who = who if who in ("you", "app", "auto") else "app"
    text = str(text)[:4000]
    if not text.strip():
        return
    with CHAT_LOCK:
        items = chat_get(300)
        ident = str(turn_id or uuid.uuid4().hex)
        if any(x.get("id") == ident for x in items):
            return ident
        items.append(
            {
                "id": ident,
                "who": who,
                "text": text,
                "err": bool(err),
                "t": int(time.time() * 1000),
            }
        )
        atomic_write(CHATLOG, json.dumps(items[-300:], ensure_ascii=False))
        persist_file("chat", CHATLOG)
        KNOWLEDGE.archive(who, text, ident)
        return ident


def mem_get():
    try:
        old = memories(MEMORY.read_text(encoding="utf-8")) if MEMORY.exists() else []
        engine = globals().get("ENGINE")
        if engine:
            old.extend(
                {"rule": r["text"], "time": 0}
                for r in engine.rules()
                if r.get("kind") == "note"
                and isinstance(r.get("text"), str)
                and re.search(r"(?i)\b(always|never|remember|from now|in future)\b", r["text"])
            )
        KNOWLEDGE.import_legacy(old)
        known = {e.get("text") for e in KNOWLEDGE.data["entries"]}
        active = [
            {"rule": e["text"], "time": e.get("time", 0), "source": e.get("source")}
            for e in KNOWLEDGE.data["entries"]
            if e.get("active")
        ]
        return [m for m in old if m.get("rule") not in known] + active
    except (ValueError, OSError):
        return []


if not KNOWLEDGE.data["turns"]:
    for item in chat_get(300):
        KNOWLEDGE.data["turns"].append(
            {
                "id": item.get("id") or uuid.uuid4().hex,
                "who": item["who"],
                "text": safe_text(item["text"]),
                "time": item.get("t", 0) / 1000,
                "source": "owner_input" if item["who"] == "you" else "app_output",
            }
        )
    if KNOWLEDGE.data["turns"]:
        KNOWLEDGE.save()


def mem_add(rule):
    rule = str(rule).strip()[:300]
    if not rule:
        return "Nothing to save."
    m = mem_get()
    m.append({"rule": rule, "time": time.time()})
    atomic_write(MEMORY, json.dumps(m, ensure_ascii=False))
    persist_file("memory", MEMORY)
    KNOWLEDGE.remember(rule)
    return (KNOWLEDGE.sync_error + " " if KNOWLEDGE.sync_error else "Saved for the future: ") + rule


HOLD = DATA / "hold.json"
if STORE:
    _v = STORE.get("hold")
    if _v:
        atomic_write(HOLD, _v if isinstance(_v, str) else json.dumps(_v))


def on_hold():
    try:
        return (
            bool(json.loads(HOLD.read_text(encoding="utf-8")).get("on")) if HOLD.exists() else False
        )
    except Exception:
        return True


def check_hold():
    if on_hold():
        raise ValueError(
            'On hold: you told me to wait. Say "resume" when the right WhatsApp is connected.'
        )


def set_hold(on):
    """Hold = nothing is sent anywhere (no posts, DMs, alerts) and Auto is paused until the owner says resume."""
    on = bool(on)
    try:
        prev = json.loads(HOLD.read_text(encoding="utf-8")) if HOLD.exists() else {}
        prev = prev if isinstance(prev, dict) else {}
    except (OSError, ValueError):
        prev = {"on": True} if HOLD.exists() else {}  # unreadable hold counts as on (as on_hold does), so "resume" can clear it
    if on and not prev.get("on"):
        was = auto_on()
        atomic_write(HOLD, json.dumps({"on": True, "was_auto": was, "since": time.time()}))
        CAMPAIGN["stop"] = True
        cancel_jobs("Stopped by owner.")
        if DONORS:
            DONORS.jobs.cancel()
        if was:
            atomic_write(AUTO, json.dumps({"on": False, "since": time.time()}))
            persist_file("autopilot", AUTO)
        persist_file("hold", HOLD)
        auto_log("ON HOLD: all sending stopped until you say resume.")
        return 'On hold. Nothing will be sent anywhere. Say "resume" when the right WhatsApp is connected.'
    if not on and prev.get("on"):
        atomic_write(HOLD, json.dumps({"on": False}))
        persist_file("hold", HOLD)
        if prev.get("was_auto"):
            set_auto(True)
        auto_log("Hold released.")
        return "Hold released." + (" Auto is back on." if prev.get("was_auto") else "")
    return "Already on hold." if on else "Nothing was on hold."


def auto_on():
    try:
        return bool(json.loads(AUTO.read_text()).get("on")) if AUTO.exists() else False
    except (OSError, ValueError, AttributeError):
        return False  # unreadable setting: Auto stays off rather than failing every screen


def set_auto(on):
    if on and not auto_on():
        ENGINE.activated()
    atomic_write(AUTO, json.dumps({"on": bool(on), "since": time.time()}))
    persist_file("autopilot", AUTO)
    auto_log("Autopilot turned " + ("ON" if on else "OFF") + ".")
    return (
        (
            "Autopilot is on. I will post on schedule, watch replies, DM donor contacts carefully and message you on WhatsApp when I need you."
            + (
                ""
                if assistant.client()
                else " (AI key not set yet, so I follow the fixed playbook only.)"
            )
        )
        if on
        else "Autopilot is off."
    )


def auto_log(text, quiet=False):
    AUTOLOG.append({"time": time.time(), "text": text, "q": quiet})
    del AUTOLOG[:-50]


def wa_ok():
    try:
        s = api_result("/devices/" + DEVICE + "/status")
        return bool(s.get("is_connected") and s.get("is_logged_in"))
    except Exception:
        return False


NEVER_GROUPS = {
    "120363432572916292@g.us",
    "120363431093838536@g.us",
}  # 37-member GiveLife copy, Exclusive Upwork Course
GROUP_CHECK = {"time": 0, "missing": [], "checked": False}
NOT_MEMBER = re.compile(
    r"(?i)not participating|not in (the )?group|not-authorized|forbidden|item-not-found|failed to get group"
)


def my_groups():
    """Groups the linked WhatsApp number is in: [(jid, name, members)]."""
    out = []
    for x in _items(api("/user/my/groups")):
        if not isinstance(x, dict):
            continue
        jid = str(x.get("JID") or x.get("jid") or x.get("id") or "")
        gn = x.get("GroupName")
        name = str(
            (gn.get("Name") if isinstance(gn, dict) else "")
            or x.get("Name")
            or x.get("name")
            or x.get("subject")
            or ""
        ).strip()
        people = x.get("Participants") or x.get("participants") or []
        if jid.endswith("@g.us") and jid not in NEVER_GROUPS:
            out.append((jid, name, len(people) if isinstance(people, list) else 0))
    return out


def check_groups(force=False):
    """Make sure every saved group is one the linked number is in; fix a changed JID by its name."""
    if not force and time.time() - GROUP_CHECK["time"] < 600:
        return GROUP_CHECK
    GROUP_CHECK["time"] = time.time()
    try:
        mine = my_groups()
    except Exception:
        return GROUP_CHECK
    if not mine:
        return GROUP_CHECK
    ids = {j for j, _, _ in mine}
    missing = []
    fixed = {}
    for key, (name, jid) in list(GROUPS.items()):
        if jid in ids:
            continue
        same = [g for g in mine if g[1].strip().lower() == name.lower()]
        if same:
            best = max(same, key=lambda g: g[2])
            if key == "main" and best[2] and best[2] < 80:
                missing.append(name)
                continue  # never fall back to a small copy of the main group
            GROUPS[key] = (name, best[0])
            fixed[key] = best[0]
        else:
            missing.append(name)
    if fixed and STORE:
        STORE.put("group_jids", {k: GROUPS[k][1] for k in GROUPS})
    GROUP_CHECK.update(missing=missing, checked=True, fixed=list(fixed))
    return GROUP_CHECK


if STORE:
    for k, j in (STORE.get("group_jids") or {}).items():
        if k in GROUPS and j not in NEVER_GROUPS:
            GROUPS[k] = (GROUPS[k][0], j)


def studio_state():
    saved = STORE.get("last_sent", {}) if STORE else {}
    since = {
        k: (round((time.time() - saved[v[1]]) / 60) if v[1] in saved else None)
        for k, v in GROUPS.items()
    }
    dm_context = (
        {
            "paused": DONORS.paused,
            "counts": DONORS.book.list()["counts"],
            "batch": DONORS.jobs.status(),
        }
        if DONORS
        else {"state": "Directory not opened yet"}
    )
    try:
        schedules = timed_scheduler().summary()
    except Exception:
        schedules = None
    return {
        "left": read_left(),
        "case_name": active_case_name(),
        "case_closed": read_left() <= 0,
        "whatsapp": wa_ok(),
        "minutes_since_post": since,
        "autopilot": auto_on(),
        "donor_context": dm_context,
        "schedules": schedules,
    }


def _items(resp):
    r = resp.get("results", resp) if isinstance(resp, dict) else resp
    if isinstance(r, dict):
        r = r.get("data") or r.get("contacts") or r.get("chats") or []
    return r if isinstance(r, list) else []


def _norm_item(x):
    if not isinstance(x, dict):
        return None
    jid = str(x.get("jid") or x.get("chat_jid") or x.get("JID") or x.get("id") or "")
    name = str(
        x.get("name")
        or x.get("push_name")
        or x.get("display_name")
        or x.get("full_name")
        or x.get("first_name")
        or x.get("PushName")
        or x.get("FullName")
        or ""
    ).strip()
    return (
        {"name": name or jid.split("@")[0], "id": jid, "group": jid.endswith("@g.us")}
        if jid
        else None
    )


def find_data(query):
    q = str(query).strip().lower()
    words = [w for w in re.split(r"\s+", q) if w]
    if not words:
        return [], 0
    found = {}
    pool = {}
    checked = 0
    for path in (
        "/chats?limit=300&search=" + urllib.parse.quote(q),
        "/chats?limit=100",
        "/chats",
        "/user/my/contacts",
    ):
        try:
            items = _items(api(path))
        except Exception:
            continue
        checked += len(items)
        for it in items:
            n = _norm_item(it)
            if not n or n["id"] in found:
                continue
            hay = (n["name"] + " " + n["id"].split("@")[0]).lower()
            pool[n["id"]] = n
            norm = re.sub(r"[^a-z0-9 ]", "", hay)
            if all(w in hay or w in norm for w in words) or q in hay:
                found[n["id"]] = n
    if not found and pool:
        import difflib

        for jid, n in pool.items():
            if difflib.SequenceMatcher(None, q, n["name"].lower()).ratio() >= 0.62:
                found[jid] = n
    out = sorted(found.values(), key=lambda n: (n["group"], len(n["name"])))[:8]
    return out, checked


def find_contacts(query):
    out, checked = find_data(query)
    if not out:
        return f'No chat or contact matches "{query}" (checked {checked} chats and contacts). Tell the owner honestly and ask for the number.'
    return json.dumps(out, ensure_ascii=False)


def send_free(to, text, with_picture, literal=False):
    check_hold()
    text = str(text).strip()
    if read_left() <= 0 and completed_case_appeal(text):
        raise ValueError("Not sent: the case has ended and this text asks for donations.")
    if read_left() <= 0:
        with_picture = False
    if not text or len(text) > 4000:
        raise ValueError("Message must be 1 to 4,000 characters.")
    if not literal and (
        manual_commands.control_payload(text)
        or (
            manual_commands.group(text)
            and re.search(r"(?i)\b(now|message|restart|gap|poster|send)\b", text)
        )
    ):
        raise ValueError(
            "That is a send instruction, not message text. Use send_appeal for the current group caption."
        )
    to = str(to).strip()
    key = manual_commands.group(to)
    if not wa_ok():
        raise ValueError("WhatsApp is not connected. Link it first.")
    if key:
        if key in ("all", "free"):
            raise ValueError("Use the group appeal action for a broadcast.")
        target = "120363431210327603@g.us" if key == "test" else GROUPS[key][1]
    elif to.endswith("@g.us"):
        if to not in [v[1] for v in GROUPS.values()] and to != "120363431210327603@g.us":
            raise ValueError("That group is not one of the foundation groups.")
        target = to
    elif to.endswith("@s.whatsapp.net"):
        target = to
    else:
        phone = norm_phone(to)
        if not phone:
            raise ValueError("That is not a valid group, contact id or phone number.")
        target = phone + "@s.whatsapp.net"
    with SEND_LOCK:
        check_hold()
        if target.endswith("@g.us"):
            text = focus_bank().reserve_groups(get_message("group")["text"], 1)[0]
            if read_left() <= 0 and completed_case_appeal(text):
                raise ValueError(
                    "Completed case: saved Group caption still asks for donations. Nothing sent."
                )
        img = image_path(current_chat_image() or "poster") if with_picture else None
        result = send_with_image(target, text, img)
    if result.get("code") != "SUCCESS":
        raise ValueError(
            "Not confirmed: "
            + str(result.get("message", ""))[:100]
            + " Check WhatsApp before retrying."
        )
    record_delivery(target, text, result)
    if target.endswith("@g.us"):
        LAST_LOCAL[target] = time.time()
        if STORE:
            saved = STORE.get("last_sent", {})
            saved[target] = time.time()
            STORE.put("last_sent", saved)
    remember_recipient(to if key else target.split("@")[0], target)
    remember_manual(
        {"kind": "text", "to": target, "text": text, "with_picture": bool(with_picture)}
    )
    auto_log(
        "Confirmed message sent to "
        + (
            GROUPS[key][0]
            if key in GROUPS
            else "Givelife test"
            if key == "test"
            else "…" + target.split("@")[0][-4:]
        ),
        True,
    )
    return "Sent."


LAST_RECIPIENT = {}


def remember_recipient(name, jid):
    LAST_RECIPIENT.clear()
    LAST_RECIPIENT.update(name=name, id=jid)
    try:
        atomic_write(RECIP, json.dumps(LAST_RECIPIENT))
        persist_file("recipient", RECIP)
    except Exception:
        pass


try:
    if RECIP.exists():
        LAST_RECIPIENT.update(json.loads(RECIP.read_text(encoding="utf-8")))
except Exception:
    pass


def send_scheduled(target, text):
    t = str(target)
    keys = (
        [k for k in GROUPS]
        if t == "all"
        else FREELANCE
        if t == "free"
        else [t]
        if t in GROUPS
        else None
    )
    if keys:
        caption = text or read_drafts().get("group", "")
        if not start_keys_job(keys, caption):
            raise ValueError("another send is running")
        return
    send_free(t, text or read_drafts().get("group", ""), True)


def rule_from_text(text):
    import rules as R

    rule, msg = R.parse(text)
    return rule, msg


def send_appeal(target, request_id=None):
    t = manual_commands.group(str(target)) or str(target).strip().lower()
    keys = (
        list(GROUPS)
        if t == "all"
        else FREELANCE
        if t == "free"
        else [t]
        if t in GROUPS or t == "test"
        else None
    )
    if not keys:
        raise ValueError("Unknown group. GiveLife main is the main foundation group.")
    remember_manual({"kind": "appeal", "target": t})
    if not wa_ok():
        raise ValueError(
            "WhatsApp is not connected. Link it from the WhatsApp button, then send again."
        )
    caption = read_drafts().get("group", "")
    work = workflow()
    options = work.options("group", caption)
    if work.data.get("kind") == "group" and work.data.get("state") == "editing":
        raise ValueError("The requested draft edit is not saved yet. Nothing was sent.")
    if t != "test":
        work.select(t, caption)
    ident = start_send_job(
        keys,
        caption,
        manual=True,
        request_id=request_id,
        with_picture=options.get("poster", True) if options else True,
    )
    name = (
        "GiveLife main"
        if t == "main"
        else "all 6 groups"
        if t == "all"
        else "all 5 freelance groups"
        if t == "free"
        else "Givelife test"
        if t == "test"
        else GROUPS[t][0]
    )
    return {
        "reply": "Sending to "
        + name
        + " now. The automatic-post timer restarts after confirmation.",
        "job_id": ident,
        "caption": caption,
    }


def add_rule_text(text):
    if timed_tasks.requested(text):
        response = timed_chat_command(text)
        if response is not None:
            return response
    rule, msg = rule_from_text(text)
    if not rule:
        return "That did not look like a rule."
    ENGINE.add_rule(rule)
    return "Rule added: " + msg


_TIMED = None
_TIMED_STORE = None
_TIMED_LOCK = threading.RLock()


def timed_scheduler():
    global _TIMED, _TIMED_STORE
    with _TIMED_LOCK:
        if _TIMED is None or _TIMED_STORE is not STORE:

            def dispatch(task):
                if task["action"] == "resume":
                    keys = []
                    for key in task["targets"]:
                        keys.extend(
                            list(GROUPS) if key == "all" else FREELANCE if key == "free" else [key]
                        )
                    if any(k not in GROUPS for k in keys):
                        raise ValueError(
                            "Choose production groups to resume, or Auto for global resume."
                        )
                    for key in dict.fromkeys(keys):
                        ENGINE.resume(key)
                    set_hold(False)
                    if not auto_on():
                        set_auto(True)
                    if on_hold() or not auto_on():
                        raise ValueError("Resume was not fully confirmed.")
                    return {
                        "message": "Scheduled resume completed. Auto is ON; only named group pauses were lifted."
                    }
                if task["action"] != "send":
                    on = task["action"] == "auto_on"
                    reply = set_auto(on)
                    if auto_on() != on:
                        raise ValueError("Auto mode could not be changed.")
                    return {"message": reply}
                keys = []
                for key in task["targets"]:
                    keys.extend(
                        list(GROUPS) if key == "all" else FREELANCE if key == "free" else [key]
                    )
                keys = list(dict.fromkeys(keys))
                if read_left() <= 0 and not task.get("text"):
                    raise ValueError(
                        "Not sent: the case is complete (Rs. 0 left). Set a new amount left first."
                    )
                caption = task.get("text") or read_drafts()["group"]
                # A due scheduled send does not preempt the owner's current manual batch.
                with LOCK:
                    if ACTIVE:
                        raise ValueError(
                            "Another batch started. Check activity before rescheduling."
                        )
                    ident = start_send_job(
                        keys,
                        caption,
                        manual=True,
                        request_id="schedule-" + task["id"] + "-" + str(int(task["due"])),
                    )
                return {"job_id": ident, "expected": len(keys)}

            def ready(task):
                if task["action"] in ("auto_off", "resume"):
                    return True
                if on_hold():
                    return False
                return task["action"] != "send" or (not ACTIVE and wa_ok())

            def cancel(ident):
                event = JOB_CANCEL.get(ident)
                if event:
                    event.set()

            _TIMED = timed_tasks.Scheduler(
                DATA / "timed-tasks.json", STORE, dispatch, get_job, ready, cancel
            )
            _TIMED_STORE = STORE
        return _TIMED


def timed_chat_command(text, request_id=None):
    if not fast_command_eligible(text):
        return None
    if timed_tasks.parse(text) is None:
        return None
    return timed_scheduler().command(text, request_id)


_loop_failed = set()


def _loop_failure(name, text, exc):
    """A background check failed: say so once in the activity log (not every second); it retries on its own."""
    if name not in _loop_failed:
        _loop_failed.add(name)
        try:
            auto_log(text + " (" + type(exc).__name__ + "). It will retry by itself.")
        except Exception:
            pass


def timed_loop():
    next_heal = 0.0
    while True:
        try:
            donors().tick_resume()
            _loop_failed.discard("resume")
        except Exception as exc:
            _loop_failure("resume", "Donor batch resume check failed", exc)
        if time.monotonic() >= next_heal:
            next_heal = time.monotonic() + 10
            try:
                if STORE:
                    focus_bank().heal()  # keeps saved versions topped up with no button press
                _loop_failed.discard("heal")
            except Exception as exc:
                _loop_failure("heal", "Wording top-up check failed", exc)
        try:
            timed_scheduler().tick()
            _loop_failed.discard("timed")
        except Exception as exc:
            _loop_failure(
                "timed",
                "Timed scheduler could not read or save its records. No automatic retry of dispatched actions",
                exc,
            )
            time.sleep(60)
        time.sleep(1)


CHAT_IMAGE = {}


def current_chat_image():
    return getattr(OWNER_GUARD, "image", CHAT_IMAGE.get("id"))


def generate_dm_variants(source="", count=10):
    """Generate reworded versions of the exact message supplied, save them in Messages and show the first on the DM screen."""
    source = str(source or "").strip()
    if not source:
        source = get_message("dm")["text"]
    try:
        count = max(1, min(20, int(count or 10)))
    except (TypeError, ValueError):
        raise ValueError("Choose a number of versions from 1 to 20.")
    bank = donors().messages.generate(source, count)
    first = bank["items"][0]["text"]
    save_draft("dm", first)
    total = len(bank["items"])
    requested = int(bank.get("requested") or count)
    extra = ""
    if total > requested:
        extra = (
            f" {total - requested} more were added so 20-person batches still have unique wording."
        )
    if bank.get("warning"):
        extra += " " + str(bank["warning"])
    return {
        "reply": f"Prepared {requested} versions from your message. The first is on the DM screen; open Donors → Messages to see all {total}. Nothing was sent."
        + extra,
        "generated": requested,
        "bank_count": total,
        "first": first[:240],
    }


def base_chat_callbacks():
    def came(amount):
        if int(amount) < 0 or int(amount) > read_left():
            raise ValueError(
                "That donation does not fit the remaining amount. Check the balance before recording it."
            )
        nl = max(0, read_left() - int(amount))
        set_left(nl)
        return f"Rs. {int(amount):,} came. Rs. {nl:,} left."

    return {
        "shortcut_action": lambda **args: None,
        "app_status": app_status,
        "donor_action": lambda **args: None,
        "team_action": lambda **args: None,
        "volunteer_action": lambda **args: None,
        "case_action": lambda **args: None,
        "send_text_list": lambda **args: None,
        "set_left": lambda left: (
            set_left(int(left)),
            f"Rs. {int(left):,} left. Messages updated.",
        )[1],
        "money_came": came,
        "new_wording": lambda kind: (
            next_message() if kind == "group" else next_dm(),
            "New " + kind + " wording ready.",
        )[1],
        "set_message": lambda kind, text: (
            save_draft(kind, text),
            kind.upper() + " message saved.",
        )[1],
        "generate_dm_variants": generate_dm_variants,
        "get_message": get_message,
        "remember": mem_add,
        "autopilot": set_auto,
        **engine_do(),
        "find_contact": find_contacts,
        "search_memory": lambda query: KNOWLEDGE.retrieve(query),
        "send_message": send_free,
        "send_dm_appeal": send_dm_appeal,
        "edit_dm_name": edit_dm_name,
        "delete_last_message": delete_last_group,
        "prepare_dm": prepare_dm,
        "send_appeal": lambda target: send_appeal(target),
        "recent_activity": lambda: (
            send_status_text()
            + "\nRecent activity: "
            + (" | ".join(x["text"] for x in AUTOLOG[-4:]) or "No new receipt this session.")
        ),
        "add_rule": lambda text: add_rule_text(text),
        "schedule_task": lambda: None,
        "list_schedules": lambda: timed_scheduler().list(),
        "list_rules": lambda: (
            "; ".join(f"#{r['id']} {r['text']}" for r in ENGINE.rule_list()) or "No rules yet."
        ),
        "delete_rule": lambda rule_id: (
            "Rule removed." if ENGINE.delete_rule(rule_id) else "No such rule."
        ),
        "hold": set_hold,
        "dm_donors": lambda count=10: dm_batch_now("donors", count),
        "dm_group": lambda group, count=10: dm_batch_now("group", count, group),
        "dm_list": lambda people, gap_minutes, vary, start_after_minutes: start_campaign(
            {
                "people": people,
                "gap_seconds": float(gap_minutes) * 60,
                "vary": vary,
                "start_after_seconds": float(start_after_minutes) * 60,
                "image": current_chat_image() or "poster",
            }
        ),
    }


import autopilot, learning as learning_mod, random as _random

OWNER_PHONE = os.environ.get("OWNER_PHONE", "923205069925")
TEST_DM_PHONE = os.environ.get("TEST_DM_PHONE", "923097458815")  # Test DMs go to this number


@serialized_send
def send_text(jid, text):
    text = dm_composer.payment_fix(text)
    check_hold()
    check_stop()
    req = urllib.request.Request(
        GOWA_URL + "/send/message",
        data=json.dumps({"phone": jid, "message": text}).encode(),
        headers={"X-Device-Id": DEVICE, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return mapping(json.load(r))


def last_sent_by_key():
    saved = dict(LAST_LOCAL)
    if STORE:
        for jid, stamp in STORE.get("last_sent", {}).items():
            saved[jid] = max(saved.get(jid, 0), stamp)
    return {k: saved.get(v[1]) for k, v in GROUPS.items()}


def dashboard_send_times():
    """Receipt timestamps only; no WhatsApp reads or inferred sends."""
    saved = dict(LAST_LOCAL)
    remote = STORE.get("last_sent", {}) if STORE else {}
    if isinstance(remote, dict):
        for jid, stamp in remote.items():
            if (
                isinstance(stamp, (int, float))
                and not isinstance(stamp, bool)
                and math.isfinite(stamp)
                and 0 < stamp <= time.time() + 60
            ):
                saved[jid] = max(saved.get(jid, 0), stamp)
    return {
        key: stamp
        if isinstance(stamp, (int, float))
        and not isinstance(stamp, bool)
        and math.isfinite(stamp)
        and 0 < stamp <= time.time() + 60
        else None
        for key, jid in {
            **{k: v[1] for k, v in GROUPS.items()},
            "test": "120363431210327603@g.us",
        }.items()
        for stamp in [saved.get(jid)]
    }


LAST_JOB = {}


def last_results():
    j = JOBS.get(LAST_JOB.get("id"))
    if not j or not j.get("done"):
        return []
    names = {v[0]: k for k, v in GROUPS.items()}
    return [
        (names.get(r.get("group"), r.get("group")), r.get("code"), str(r.get("message", "")))
        for r in j["results"]
    ]


def start_keys_job(keys, caption, queue=False):
    return bool(start_send_job([k for k in GROUPS if k in keys], caption, manual=False))


def group_messages(jid):
    return api_messages("/chat/" + urllib.parse.quote(jid, safe="") + "/messages?limit=20")


def already_dmed(digest):
    return digest in BLOCKED or bool(
        STORE and (STORE.get("dm_recipient_" + digest) or STORE.get("optout_" + digest))
    )


FEMALE = set(
    "ayesha aisha fatima zainab maryam mariam laiba sana hira iqra amna sawaira yusra areeba mahnoor noor kiran sadia saba rabia hina nida mehwish sidra anam anum bushra khadija asma uzma sara sarah zoya alina hajra dania rimsha mehak esha ifra aleena maham momina tehreem eman iman aiman kinza fiza javeria sobia shazia nadia farah rida ramsha warda wajeeha hafsa sumaira tayyaba uswa zara zahra nimra minahil bisma".split()
)
FEMALE |= dm_composer.FEMALE_NAMES
NOT_NAME = re.compile(
    r"(?i)\b(web|develop|graphic|entrepreneur|official|store|shop|studio|agency|design|market|services?|tech|digital|freelanc|admin|group|team|seo|business|donor|member|upwork|fiverr)"
)
PERSONAL = re.compile(
    r"(?i)(wife|wifey|\bmom\b|\bmum\b|mother|\bdad\b|father|baba|papa|\babu\b|abbu|ammi|amma|family|bhai|\bbro\b|\bsis\b|baji|uncle|aunt|chacha|mama|khala|dada|nani|nana|\bhome\b|\blove\b|jaan|janu|honey|dear|hubby|husband|\bson\b|daughter|boss|jr account)|[\u2764\U0001F495\U0001F60D\U0001F496\U0001F48B]"
)


def clean_first_name(name):
    if not name or NOT_NAME.search(name):
        return ""
    return dm_composer.first_name(name)


def dm_text(name, tier="member"):
    left = read_left()
    first = clean_first_name(re.sub(r"(?i)\bdonors?\b", "", str(name or "")).strip())
    who = dm_composer.greeting(first, dm_composer.gender(name, first) if first else "Brother")
    acct = "📲 *03097458815* — EASYPAISA ONLY\nWajdan Khan (GiveLife Foundation account)"
    if tier == "repeat":
        return f"{who}, JazakAllah for supporting GiveLife before. 🤲\n\nRs. {left:,} is still needed for {active_case_name()}. Could you help once more, or share this case with family and friends?\n\n{acct}"
    if tier == "reminder":
        return f"{who}, a gentle reminder about {active_case_name()}. 🤲\n\nRs. {left:,} is still needed. If you have already donated, JazakAllah. If not, whenever you can:\n\n{acct}\n\nReply *Done* after you donate."
    # Every other Auto DM comes from the saved Donors > Messages bank (shared rotation), never
    # from built-in templates. A missing/invalid bank raises and Auto stops with a clear reason.
    return dm_composer.personalize(
        donors().messages.reserve_one(), first, "Sister" if first.lower() in FEMALE else "Brother"
    )


def log_resume(what):
    """Remember every immediate resume so the Report can list it."""
    if not STORE:
        return
    items = STORE.get("resume_log", []) or []
    items.append({"what": what, "at": time.time()})
    STORE.put("resume_log", items[-30:])


def send_dm_test(text, poster=True):
    """A clearly marked test DM to the owner's own WhatsApp. Never touches donor records or rotation."""
    if not wa_ok():
        raise ValueError("WhatsApp is not connected. Link it first.")
    me = norm_phone(TEST_DM_PHONE or OWNER_PHONE)
    if not me:
        raise ValueError("Your own WhatsApp number is not known yet. Nothing was sent.")
    body = "🧪 TEST DM (only you see this)\n\n" + str(text)
    with SEND_LOCK:
        check_hold()
        result = send_image(me, body) if poster else send_text(me, body)
    if result.get("code") != "SUCCESS":
        raise ValueError(
            "Test not confirmed: " + str(result.get("message", ""))[:100] + " Check WhatsApp."
        )
    return {"code": "SUCCESS", "reply": "Test DM sent to your own WhatsApp."}


def send_dm(phone, text, digest):
    if STORE:
        STORE.put("dm_recipient_" + digest, {"state": "uncertain", "time": time.time()})
    r = send_image(phone, text)
    if STORE:
        STORE.put(
            "dm_recipient_" + digest, {"state": r.get("code", "UNCERTAIN"), "time": time.time()}
        )
    return r


ATT = DATA / "attachments"
ATT.mkdir(exist_ok=True)
if STORE:
    _p = STORE.get("poster_b64")
    if _p:
        (DATA / "poster.jpg").write_bytes(base64.b64decode(_p))
    _v = STORE.get("poster_video_b64")
    if _v:
        (DATA / "poster.mp4").write_bytes(base64.b64decode(_v))
    if STORE.get("poster_kind") == "video" and _v:
        atomic_write((DATA / "poster-kind.txt"), "video")
    elif STORE.get("poster_kind") == "video":
        # Preserve the selected media kind. A missing video must not trigger an old poster.
        atomic_write((DATA / "poster-kind.txt"), "video")
if STORE:
    # Older versions saved the poster dialog as a DM-only copy, so group posts kept the old poster.
    # That copy is the owner's latest choice: make it the shared poster once.
    _dp = STORE.get("dm_poster_b64")
    _dv = STORE.get("dm_poster_video_b64")
    _dk = STORE.get("dm_poster_kind")
    if _dk == "video" and _dv:
        (DATA / "poster.mp4").write_bytes(base64.b64decode(_dv))
        atomic_write((DATA / "poster-kind.txt"), "video")
        STORE.put("poster_video_b64", _dv)
        STORE.put("poster_kind", "video")
    elif _dp and _dk in ("image", None, ""):
        (DATA / "poster.jpg").write_bytes(base64.b64decode(_dp))
        atomic_write((DATA / "poster-kind.txt"), "image")
        STORE.put("poster_b64", _dp)
        STORE.put("poster_kind", "image")
    if _dp or _dv or _dk:
        for k in ("dm_poster_b64", "dm_poster_video_b64", "dm_poster_kind"):
            STORE.put(k, "")
CAMPAIGN = {
    "running": False,
    "stop": False,
    "total": 0,
    "sent": 0,
    "failed": 0,
    "skipped": 0,
    "next_at": 0,
    "current": "",
    "log": [],
    "id": None,
}


def clear_dm_poster():
    for name in ("dm-poster.jpg", "dm-poster.mp4", "dm-poster-kind.txt"):
        (DATA / name).unlink(missing_ok=True)
    if STORE:
        for k in ("dm_poster_b64", "dm_poster_video_b64", "dm_poster_kind"):
            STORE.put(k, "")


def write_atomic(path, raw):
    """Replace a file in one step, so a send in progress reads the old or the new poster, never half."""
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_bytes(raw)
    temp.replace(path)


def save_upload(data_url, use):
    if use == "bulk":
        import batch_media

        return batch_media.save(STORE, data_url)
    if use == "papers":
        return "papers-" + str(save_papers(data_url))
    # One poster for groups and DMs: the poster dialog (use='dm_poster') replaces both, never a DM-only copy.
    if use == "dm_poster":
        use = "poster"
    pre = ""
    key = "poster"
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    if data_url.startswith("data:video/"):
        if len(raw) > 15_000_000:
            raise ValueError("Video is too big (max 15 MB, the WhatsApp limit).")
        if raw[4:8] != b"ftyp":
            raise ValueError("Use an MP4 video (H.264). Other video types are not accepted.")
        if use == "poster":
            # Render's local filesystem is temporary. Persist the ENTIRE accepted video
            # before activating it; otherwise a restart silently loses files over 3 MB.
            if STORE:
                STORE.put(key + "_video_b64", base64.b64encode(raw).decode())
                STORE.put(key + "_kind", "video")
            write_atomic(DATA / (pre + "poster.mp4"), raw)
            write_atomic(DATA / (pre + "poster-kind.txt"), b"video")
            clear_dm_poster()
            return "poster"
        aid = uuid.uuid4().hex[:12]
        (ATT / (aid + ".mp4")).write_bytes(raw)
        return aid
    if len(raw) > 8_000_000:
        raise ValueError("Picture is too big (max 8 MB).")
    if use == "poster":
        if not raw.startswith(b"\xff\xd8\xff"):
            raise ValueError(
                "Choose a JPEG poster. The upload control converts your picture automatically."
            )
        if STORE:
            STORE.put(key + "_b64", base64.b64encode(raw).decode())
            STORE.put(key + "_kind", "image")
        write_atomic(DATA / (pre + "poster.jpg"), raw)
        write_atomic(DATA / (pre + "poster-kind.txt"), b"image")
        clear_dm_poster()
        return "poster"
    aid = uuid.uuid4().hex[:12]
    (ATT / (aid + ".jpg")).write_bytes(raw)
    return aid


def image_path(image):
    if image in (None, "", "none"):
        return None
    if image == "poster":
        return poster_media()
    stem = re.sub(r"[^a-f0-9]", "", str(image))
    for ext in (".jpg", ".mp4"):
        p = ATT / (stem + ext)
        if p.exists():
            return p
    return poster_media()


@serialized_send
def send_with_image(jid, caption, img):
    check_hold()
    if img is None:
        req = urllib.request.Request(
            GOWA_URL + "/send/message",
            data=json.dumps({"phone": jid, "message": caption}).encode(),
            headers={"X-Device-Id": DEVICE, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=40) as r:
            return mapping(json.load(r))
    cap = DATA / ("caption-" + uuid.uuid4().hex + ".txt")
    atomic_write(cap, caption)
    r = post_media(jid, cap, img)
    cap.unlink(missing_ok=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"code": "ERROR", "message": "Send not confirmed. Check WhatsApp before retrying."}


def norm_phone(p):
    p = re.sub(r"[\s()+-]", "", str(p))
    if p.startswith("00"):
        p = p[2:]
    if re.fullmatch(r"03\d{9}", p):
        p = "92" + p[1:]
    return p if re.fullmatch(r"[1-9]\d{7,14}", p) else ""


def greet_text(text, name, gender, normal_amount=0):
    text = dm_composer.personalize(text, clean_first_name(name), gender)
    if normal_amount and normal_amount > 0:
        try:
            left = read_left()
        except (OSError, ValueError):
            left = 0
        if left > 0:
            text = normal_donation_line(text, int(normal_amount), left)
    return text


OPTION_LINE = re.compile(
    r"^(\*_)([^\n]*?(?:people|donors)[^\n]*?Rs\.?\s?([\d,]+)[^\n]*?)(_\*)([^\n]*)$"
)


def normal_donation_line(text, normal, left):
    """For a donor with a usual amount: first 'Just N people donating Rs. <usual> will save him', then the shared
    2,000 line follows as 'OR … as well'. Any option line with the same amount as the usual one is dropped."""
    import math

    lines = text.split("\n")
    first = None
    for index, line in enumerate(lines):
        m = OPTION_LINE.match(line)
        if m:
            first = index
            break
    if first is None:
        return text
    people = math.ceil(left / normal)
    mine = f"*_Just {people:,} people donating Rs. {normal:,} will save him_*"
    out = []
    for index, line in enumerate(lines):
        m = OPTION_LINE.match(line)
        if not m:
            out.append(line)
            continue
        amount = int(m[3].replace(",", "") or 0)
        if index == first:
            out.append(mine)
            if amount != normal:
                body = re.sub(r"(?i)^(?:just|only|or)\s+", "", m[2]).strip()
                out.append(
                    f"{m[1]}OR {body}{'' if body.lower().endswith('as well') else ' as well'}{m[4]}{m[5]}"
                )
        elif amount != normal:
            out.append(line)
    return "\n".join(out)


CAMPAIGN_START = threading.Lock()


def dm_campaign(people, gap, image, vary, message, start_after, rest_every, rest_minutes):
    c = CAMPAIGN
    c.update(
        running=True, stop=False, total=len(people), sent=0, failed=0, skipped=0, log=[], current=""
    )
    try:
        if start_after > 0:
            c["next_at"] = time.time() + start_after
            c["current"] = f"Starting in {round(start_after / 60, 1)} min"
            while time.time() < c["next_at"]:
                if c["stop"]:
                    return
                time.sleep(2)
        for i, p in enumerate(people):
            img = image_path(image)  # a poster changed mid-batch applies to the next person
            if c["stop"]:
                c["log"].append("Stopped by owner.")
                return
            phone = norm_phone(p.get("phone", ""))
            name = str(p.get("name", "") or "").strip()[:30]
            gender = p.get("gender", "Brother")
            if not phone:
                c["skipped"] += 1
                continue
            digest = hashlib.sha256((phone + "@s.whatsapp.net").encode()).hexdigest()
            if digest in BLOCKED or (STORE and STORE.get("optout_" + digest)):
                c["skipped"] += 1
                c["log"].append(f"Skipped …{phone[-4:]} (asked not to be messaged)")
                continue
            if STORE and STORE.get("dm_recipient_" + digest) and not p.get("again"):
                c["skipped"] += 1
                c["log"].append(f"Skipped …{phone[-4:]} (already messaged)")
                continue
            if not wa_ok():
                c["log"].append("WhatsApp disconnected. Stopped.")
                return
            base = (
                dm_text(name, p["tier"])
                if p.get("tier")
                else (
                    build_dm([_random.randrange(dm_templates.COUNT)], read_left())
                    if (vary or not message)
                    else message
                )
            )
            normal = donors().book.normal_amount_for_phone(phone)
            text = greet_text(base, name, gender, normal)
            c["current"] = f"Sending to {(name + ' ') if name else ''}{gender} …{phone[-4:]}"
            if STORE:
                STORE.put("dm_recipient_" + digest, {"state": "uncertain", "time": time.time()})
            r = send_with_image(phone, text, img)
            if STORE:
                STORE.put(
                    "dm_recipient_" + digest,
                    {"state": r.get("code", "UNCERTAIN"), "time": time.time()},
                )
            if r.get("code") != "SUCCESS":
                c["failed"] += 1
                c["log"].append(
                    f"Failed …{phone[-4:]}: {str(r.get('message', ''))[:80]}. Stopped to protect your number."
                )
                return
            c["sent"] += 1
            note_dm(phone)
            c["log"].append(f"✓ {(name + ' ') if name else ''}{gender} …{phone[-4:]}")
            if i < len(people) - 1:
                wait = _random.uniform(max(gap, 180), max(gap, 420))
                if rest_every and c["sent"] % rest_every == 0:
                    wait = max(wait, rest_minutes * 60)
                    c["log"].append(f"Resting {rest_minutes} min after {c['sent']} messages")
                c["next_at"] = time.time() + wait
                c["current"] = "Waiting"
                while time.time() < c["next_at"]:
                    if c["stop"]:
                        c["log"].append("Stopped by owner.")
                        return
                    time.sleep(2)
    finally:
        c["running"] = False
        c["current"] = ""
        c["next_at"] = 0
        auto_log(
            f"DM list finished: {c['sent']} sent, {c['skipped']} skipped, {c['failed']} failed."
        )


def start_campaign(body):
    if DONORS and DONORS.jobs.active:
        raise ValueError("A donor batch is already running. Stop it first or wait.")
    people = [p for p in body.get("people", []) if isinstance(p, dict)][:300]
    if not people:
        raise ValueError("No phone numbers found.")
    gap = max(45.0, float(body.get("gap_seconds", 90)))
    args = (
        people,
        gap,
        body.get("image", "poster"),
        bool(body.get("vary", True)),
        str(body.get("message", "") or ""),
        max(0.0, float(body.get("start_after_seconds", 0))),
        int(body.get("rest_every", 10)),
        float(body.get("rest_minutes", 10)),
    )
    # Claim the run before the worker starts: two quick requests must never both pass the check
    # and start two lists that send to the same people.
    with CAMPAIGN_START:
        if CAMPAIGN["running"]:
            raise ValueError("A DM list is already sending. Stop it first or wait.")
        CAMPAIGN["running"] = True
    try:
        threading.Thread(target=dm_campaign, args=args, daemon=True).start()
    except Exception:
        CAMPAIGN["running"] = False
        raise
    return (
        f"Sending to {len(people)} people, about {round(gap / 60, 1)} min apart"
        + (f", starting in {round(args[5] / 60, 1)} min" if args[5] else "")
        + "."
    )


PAPERS = DATA / "papers"
PAPERS.mkdir(exist_ok=True)
if STORE:
    for _i, _b in enumerate(STORE.get("papers_b64", []) or []):
        (PAPERS / f"paper-{_i}.jpg").write_bytes(base64.b64decode(_b))
RECENT_LOCAL = []


def thank_text():
    return (
        "JazakAllah 🤲 May Allah reward you and your family.\n\n"
        f"One more favour: please share the poster for {active_case_name()} on your WhatsApp status and in your family groups. "
        "Every share reaches someone who can help.\n- GiveLife Foundation"
    )


def share_text():
    left = read_left()
    return (
        f"*Rs. {left:,} is still left for {active_case_name()}.* 💔\n\nIf you cannot donate right now, you can still help: "
        "*share this poster on your WhatsApp status* and send it to 3 friends today. Sharing costs nothing and reaches new donors. 🤲\n\n"
        "*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation"
    )


def done_text():
    return (
        f"Alhamdulillah. The amount for {active_case_name()} is complete. 🤲\n\n"
        "JazakAllah to everyone who donated, shared and prayed. May Allah reward you all.\n- GiveLife Foundation"
    )


def sender_phone(m):
    j = str(m.get("sender_jid") or m.get("sender") or "")
    p = j.split("@")[0].split(":")[0]
    return p if j.endswith("@s.whatsapp.net") and p.isdigit() else ""


def has_papers():
    return any(PAPERS.glob("*.jpg"))


def send_papers(phone):
    files = sorted(PAPERS.glob("*.jpg"))[:6]
    if not files:
        return False
    for i, f in enumerate(files):
        send_with_image(
            phone + "@s.whatsapp.net",
            f"Medical papers for {active_case_name()} (GiveLife Foundation)." if i == 0 else "",
            f,
        )
        time.sleep(3)
    return True


def save_papers(data_url):
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    n = len(list(PAPERS.glob("*.jpg")))
    (PAPERS / f"paper-{n}.jpg").write_bytes(raw)
    if STORE:
        saved = STORE.get("papers_b64", []) or []
        saved.append(base64.b64encode(raw).decode())
        STORE.put("papers_b64", saved[-6:])
    return n + 1


def note_dm(phone):
    item = [phone, time.time()]
    if STORE:
        r = [
            x
            for x in (STORE.get("recent_dms", []) or [])
            if time.time() - x[1] < 7 * 86400 and x[0] != phone
        ]
        r.append(item)
        STORE.put("recent_dms", r[-300:])
    else:
        RECENT_LOCAL.append(item)
        del RECENT_LOCAL[:-300]


def recent_dms():
    r = (STORE.get("recent_dms", []) if STORE else RECENT_LOCAL) or []
    return [(p, t) for p, t in r if time.time() - t < 7 * 86400][-60:]


def optout(phone):
    d = hashlib.sha256((phone + "@s.whatsapp.net").encode()).hexdigest()
    if STORE:
        if not STORE.get("optout_" + d):
            ledger = STORE.get("dm_daily", {}) or {}
            ledger["optouts"] = ledger.get("optouts", 0) + 1
            STORE.put("dm_daily", ledger)
        STORE.put("optout_" + d, True)
    BLOCKED.add(d)


def is_opted_out(phone):
    """True when this person asked not to be messaged (either stored form of the key)."""
    if not STORE:
        return False
    keys = (
        "optout_" + hashlib.sha256((phone + "@s.whatsapp.net").encode()).hexdigest(),
        "optout_" + hashlib.sha256(str(phone).encode()).hexdigest(),
    )
    return any(STORE.get(k) for k in keys)


def saved_auto_group_caption():
    """One authoritative source: the saved Group editor and its version bank."""
    caption = get_message("group")["text"]
    if not caption.strip():
        raise ValueError("Save a message in Group before Auto can post.")
    if STORE:
        bank = focus_bank()
        row = bank.get("group")
        if not row.get("revision"):
            row = bank.save("group", caption)
        return row["source"]
    return caption


def start_auto_group_job(keys, _legacy_caption=None):
    # Ignore independent milestone/share/template copy supplied by old Auto paths.
    # The shared sender reserves unused versions from this same saved source.
    return start_keys_job(keys, saved_auto_group_caption())


def auto_post_saved_to_all(_legacy_caption=None):
    return start_auto_group_job(list(GROUPS))


def variant_pool():
    return "owner"


def variant_count():
    return 1


def caption_variant(i):
    return saved_auto_group_caption()


def variant_names():
    return {0: "Saved Group message bank"}


def goal_value():
    m = re.search(r"^GOAL:\s*(\d+)", (DATA / "state.md").read_text(encoding="utf-8-sig"), re.M)
    return int(m[1]) if m else 0


def update_text(came, left):
    """Use verified active-case wording; never reuse another patient's diagnosis."""
    if active_case_name().casefold() != "yousuf":
        return (
            f"Rs. {came:,} came in for {active_case_name()}. Rs. {left:,} is still needed. "
            "We need your help to complete the amount.\n\n"
            "*03097458815* EASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation"
        )
    p2 = math.ceil(left / 2000)
    return (
        f"🔴 *Rs. {came:,} came in. It is NOT enough.*\n\n⚠️ Fluid in Yousuf's brain *can still paralyse his body and damage his eyesight.* Both his kidneys are still badly swollen.\n\n"
        f"💰 *Rs. {left:,} still LEFT*\n*{p2} people x Rs. 2,000 — he needs you now*\n\n*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\nReply *Done* after you donate.\n- GiveLife Foundation"
    )


def milestone_text(raised, left):
    p2, p1 = math.ceil(left / 2000), math.ceil(left / 1000)
    return (
        f"*Rs. {raised:,} has been raised for {active_case_name()}. Rs. {left:,} is still missing.* 💔\n\n*_{p2} people donating Rs. 2,000_*\n*_OR {p1} people donating Rs. 1,000_* 🤲\n\n"
        "*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n\nReply *Done* after you donate.\n- GiveLife Foundation"
    )


def job_message():
    j = JOBS.get(ACTIVE) if ACTIVE else None
    return j.get("message", "") if j else ""


def recent_chats():
    out = []
    try:
        items = _items(api("/chats?limit=60"))
    except Exception:
        return out
    for it in items:
        n = _norm_item(it)
        if n and not n["group"] and n["id"].endswith("@s.whatsapp.net"):
            phone = n["id"].split("@")[0]
            if phone != OWNER_PHONE and not PERSONAL.search(n["name"]):
                out.append((phone, n["name"]))
    return out[:40]


def group_members(key="main"):
    jid = GROUPS[key][1]
    if jid in NEVER_GROUPS:
        return []
    try:
        data = api("/group/participants?group_id=" + urllib.parse.quote(jid, safe="")).get(
            "results", {}
        )
    except Exception:
        return []
    out = []
    for p in data.get("participants", []) if isinstance(data, dict) else []:
        phone = str(p.get("phone_number") or "")
        name = str(p.get("display_name") or "")
        if phone.isdigit() and phone != OWNER_PHONE and not PERSONAL.search(name):
            out.append((phone, name))
    return out


DONOR_WORD = re.compile(r"(?i)\bdonors?\b")


def donor_contacts():
    """Existing donors: people saved in his phone with "donor" in the name, plus group members labelled donor."""
    out = []
    seen = set()
    try:
        items = _items(api("/user/my/contacts"))
    except Exception:
        items = []
    for it in items:
        n = _norm_item(it)
        if (
            n
            and n["id"].endswith("@s.whatsapp.net")
            and DONOR_WORD.search(n["name"])
            and not PERSONAL.search(n["name"])
        ):
            phone = n["id"].split("@")[0]
            if phone != OWNER_PHONE and phone not in seen:
                seen.add(phone)
                out.append((phone, n["name"]))
    for phone, name in group_members("main"):
        if DONOR_WORD.search(name) and phone not in seen:
            seen.add(phone)
            out.append((phone, name))
    return out


def _batch_people(pairs, tier, count):
    """Turn (phone,name) pairs into campaign people, skipping anyone who opted out or was messaged in the last 3 days."""
    people = []
    for phone, name in pairs:
        if len(people) >= count:
            break
        d = hashlib.sha256((phone + "@s.whatsapp.net").encode()).hexdigest()
        if d in BLOCKED or (STORE and STORE.get("optout_" + d)):
            continue
        rec = STORE.get("dm_recipient_" + d) if STORE else None
        again = False
        if rec:
            if tier == "repeat" and time.time() - float(rec.get("time", 0)) > 3 * 86400:
                again = True
            else:
                continue
        first = clean_first_name(DONOR_WORD.sub("", str(name or "")).strip())
        people.append(
            {
                "phone": phone,
                "name": first,
                "gender": "Sister" if first.lower() in FEMALE else "Brother",
                "tier": tier,
                "again": again,
            }
        )
    return people


def dm_batch_now(kind, count=10, group="main"):
    if kind == "donors":
        return donors().jobs.start(
            scope="all", gap_seconds=60, limit=max(1, min(1000, int(count)))
        )["reply"]
    count = max(1, min(int(count or 10), 50))
    if kind == "donors":
        pairs = donor_contacts() + learning_mod.repeat_donors(ENGINE.L)
        pairs = list({p: (p, n) for p, n in pairs}.values())
        label = "existing donors"
        tier = "repeat"
        if not pairs:
            return 'I found no contacts saved with "donor" in the name yet. Save donors like "Ali Donor" in your phone, or send me a list of numbers.'
    else:
        if group not in GROUPS:
            raise ValueError("Unknown group.")
        pairs = group_members(group)
        _random.shuffle(pairs)
        label = "members of " + GROUPS[group][0]
        tier = "member"
        if not pairs:
            return (
                "I could not read the members of "
                + GROUPS[group][0]
                + ". Check the linked WhatsApp number is in that group."
            )
    people = _batch_people(pairs, tier, count)
    if not people:
        return f"Everyone I found in {label} was already messaged recently or asked not to be."
    msg = start_campaign(
        {
            "people": people,
            "gap_seconds": 100,
            "vary": True,
            "image": "poster",
            "rest_every": 10,
            "rest_minutes": 10,
        }
    )
    return f"DMs to {len(people)} {label}. " + msg


def outreach(caps):
    """Who to DM next, best first: past donors, donor-labelled contacts, group members, saved chats."""
    picked = []
    seen = set()

    def add(tier, people):
        n = 0
        for phone, name in people:
            if n >= caps.get(tier, 0) or phone in seen:
                continue
            d = hashlib.sha256((phone + "@s.whatsapp.net").encode()).hexdigest()
            if d in BLOCKED or (STORE and STORE.get("optout_" + d)):
                continue
            if tier != "repeat" and already_dmed(d):
                continue
            seen.add(phone)
            picked.append((phone, name, tier))
            n += 1

    add("repeat", learning_mod.repeat_donors(ENGINE.L))
    members = group_members()
    _random.shuffle(members)
    add("donor", donor_contacts())
    add("member", [(p, n) for p, n in members if not DONOR_WORD.search(n)])
    chats = recent_chats()
    _random.shuffle(chats)
    add("saved", chats)
    return picked


def ai_test():
    key = assistant.client()
    if not key:
        return {
            "ok": False,
            "error": "No DeepSeek key yet. Add DEEPSEEK_API_KEY in Render, then deploy.",
        }
    t0 = time.time()
    try:
        text, _ = assistant._call(
            key,
            "Reply with one word only.",
            [],
            [{"role": "user", "content": "Reply with exactly: OK"}],
        )
    except Exception as e:
        m = str(e)
        hint = (
            " The key looks wrong or revoked."
            if "401" in m or "403" in m
            else " The DeepSeek balance may be empty."
            if "402" in m
            else " Check the internet or try again."
        )
        return {"ok": False, "error": m[:120] + hint}
    return {"ok": True, "ms": round((time.time() - t0) * 1000), "reply": text[:40]}


# ---- case plan (verified facts -> PDF messages -> automatic Normal/Slow) ----
def plan_get():
    plan = STORE.get("case_plan") if STORE else None
    return plan if isinstance(plan, dict) and plan.get("state") in case_plan.STATES else None


def plan_put(plan):
    if not STORE:
        raise ValueError("Persistent storage is unavailable. Nothing was changed.")
    STORE.put("case_plan", plan)


def plan_active():
    plan = plan_get()
    return bool(plan) and plan["state"] in case_plan.ACTIVE


def plan_apply(text, plan=None):
    """Make `text` the saved Group message, only if it passes every PDF check. '' = done, else the reason."""
    plan = plan or plan_get()
    bad = message_rules.problems(text, left=read_left(), facts=plan["facts"], exact=False)
    if bad:
        return " ".join(bad)
    if get_message("group")["text"] != text:
        focus_bank().save(
            "group", text
        )  # the new message is saved; versions come from the Generate button
    return ""


def alert_jids():
    """Extra people to alert about the case plan: only numbers the owner put in AUTO_ALERT_PHONES."""
    out = []
    for raw in os.environ.get("AUTO_ALERT_PHONES", "").split(","):
        phone = norm_phone(raw.strip()) if raw.strip() else ""
        if phone and phone != norm_phone(OWNER_PHONE):
            out.append(phone + "@s.whatsapp.net")
    return out


AUTO_CONTROLS = None
_AUTO_CONTROLS_LOCK = threading.Lock()


def auto_controls():
    global AUTO_CONTROLS
    with _AUTO_CONTROLS_LOCK:
        if AUTO_CONTROLS is None:
            import auto_controls as module

            AUTO_CONTROLS = module.AutoControls(sys.modules[__name__])
        return AUTO_CONTROLS


MSTYLE_LOCK = threading.Lock()
MSTYLE_MEMORY = {}


def message_style(body):
    """One of the four editor buttons: write a new message from the live case, never sending anything."""
    import message_styles

    style = body.get("style")
    kind = "dm" if body.get("kind") == "dm" else "group"
    if style not in message_styles.STYLES:
        raise ValueError("Choose one of the four message buttons.")
    left = read_left()
    if left <= 0:
        raise ValueError("The case is complete (Rs. 0 left). Nothing was written.")
    api = assistant.client()
    if api is None:
        raise RuntimeError("AI is not connected, so nothing was written. Your message is unchanged.")
    if not MSTYLE_LOCK.acquire(blocking=False):
        raise ValueError("A message is already being written. Wait a moment.")
    try:
        group, dm = get_message("group")["text"], get_message("dm")["text"]
        current = str(body.get("current") or "")[:6000]
        plan = plan_get()
        facts = [f"Case: {active_case_name()}"]
        if plan and plan.get("facts"):
            facts.append("Verified case facts: " + json.dumps(plan["facts"], ensure_ascii=False))
        facts += [t for t in (current, group, dm) if t.strip()]
        ctx = {
            "left": left,
            "facts": "\n\n".join(facts),
            "group_text": group,
            "dm_text": dm,
            "current_text": current or (dm if kind == "dm" else group),
        }

        def chat(system, prompt):
            msg = assistant._chat_raw(
                api, system, [], [{"role": "user", "content": prompt}], max_tokens=1500, thinking_mode=False
            )
            return msg.get("content", "") if isinstance(msg, dict) else ""

        state = (STORE.get("message_styles") if STORE else None) or MSTYLE_MEMORY
        result, new_state = message_styles.generate(
            style, ctx, state if isinstance(state, dict) else {}, chat, __import__("ai_call").json_of
        )
        MSTYLE_MEMORY.clear()
        MSTYLE_MEMORY.update(new_state)
        if STORE:
            STORE.put("message_styles", new_state)
        return {**result, "left": left, "kind": kind}
    finally:
        MSTYLE_LOCK.release()


def plan_view():
    plan, left = plan_get(), read_left()
    checks = {}
    if plan and plan["state"] != "done":
        for mode in ("normal", "slow"):
            text = case_plan.message_for(plan, mode, left)
            checks[mode] = {
                "text": text,
                "problems": message_rules.problems(
                    text, left=left, facts=plan["facts"], exact=False
                ),
            }
    return {
        "plan": plan,
        "checks": checks,
        "left": left,
        "case": active_case_name(),
        "rounding": (
            f"Rs. {left:,} is not a multiple of Rs. 2,000, so line 3 rounds up "
            f"({-(-left // 2000)} people × Rs. 2,000 or {-(-left // 1000)} × Rs. 1,000), as the app always does."
            if left > 0 and left % team_rules.BIG_GIFT
            else ""
        ),
        "in_work_hours": team_rules.in_work_hours(),
        "work_hours": team_rules.WORK_HOURS_TEXT,
        "auto_on": bool(auto_on()),
        "team_alerts": len(alert_jids()),
        "slow_after": team_rules.SLOW_AFTER_MINUTES,
        "minutes_since_money": int(ENGINE.level()[3]),
    }


def plan_mutate(body):
    action = str(body.get("action", ""))
    with LOCK:
        plan, left = plan_get(), read_left()
        if action == "create":
            if plan and plan["state"] in case_plan.ACTIVE:
                raise ValueError("Stop the running case plan before starting a new one.")
            plan = case_plan.new_case(body.get("facts"), left, active_case_name())
        elif action == "approve":
            plan = case_plan.approve(plan, left)
        elif action == "stop":
            if not plan or plan["state"] not in case_plan.ACTIVE:
                raise ValueError("No running case plan to stop.")
            plan = case_plan.stop(plan, "Stopped by the owner.")
        elif action == "resume":
            plan = case_plan.resume(plan)
        elif action == "clear":
            if plan and plan["state"] in case_plan.ACTIVE:
                raise ValueError("Stop the case plan before clearing it.")
            plan = {"state": "cleared"}
        else:
            raise ValueError("Unknown action.")
        plan_put(plan)
    if action in ("approve", "resume"):
        ENGINE.plan_tick()  # applies the right message now; never sends anything
    return plan_view()


def group_timer_waiting(key):
    """True while a timer button (15m/30m/45m/1h) is waiting to send to this group.
    Auto must stay quiet for that group until the timer's time, then the timer sends."""
    if _TIMED is None or _TIMED_STORE is not STORE:
        return False
    with _TIMED.lock:
        return any(
            t["state"] in ("pending", "dispatching")
            and t.get("scope")
            and t["action"] == "send"
            and key in t.get("targets", [])
            for t in _TIMED.tasks
        )


ENGINE = autopilot.Engine(
    {
        "DATA": DATA,
        "timer_waiting": group_timer_waiting,
        "store_get": lambda k: STORE.get(k) if STORE else None,
        "persist": persist_file,
        "log": auto_log,
        "send_text": send_text,
        "owner_jid": lambda: OWNER_PHONE + "@s.whatsapp.net",
        "plan_get": plan_get,
        "plan_put": plan_put,
        "plan_active": plan_active,
        "plan_apply": plan_apply,
        "alert_jids": alert_jids,
        "case_name": lambda: active_case_name(),
        "caption_now": lambda text: caption_facts.current(sys.modules[__name__], text),
        "enabled": auto_on,
        "read_left": read_left,
        "wa_ok": wa_ok,
        "busy": lambda: ACTIVE is not None,
        "last_sent": last_sent_by_key,
        "groups": lambda: list(GROUPS),
        "group_jids": lambda: {k: v[1] for k, v in GROUPS.items()},
        "caption": lambda: read_drafts().get("group", ""),
        "start_job": start_auto_group_job,
        "last_results": last_results,
        "messages": scan_messages,
        "poster_left": poster_left,
        "sender_phone": sender_phone,
        "send_papers": send_papers,
        "has_papers": has_papers,
        "thank_text": thank_text,
        "share_text": share_text,
        "done_text": done_text,
        "post_text_all": auto_post_saved_to_all,
        "recent_dms": recent_dms,
        "note_dm": note_dm,
        "optout": optout,
        "is_opted_out": is_opted_out,
        "group_link": lambda: (
            os.environ.get("FOUNDATION_GROUP_LINK", "")
            or str((STORE.get("foundation_group_link") if STORE else "") or "")
        ),
        "ai_chat": ai_call.chat,
        "send_custom": send_custom,
        "poster_caption": lambda: get_message("group")["text"],
        "volunteers": lambda: [
            r
            for r in donors().volunteers.book._load()["records"]
            if r.get("phone") and not r.get("deleted")
        ],
        "case_id": lambda: active_case_name() or "case",
        "send_scheduled": send_scheduled,
        "donor_answer": lambda q: assistant.donor_reply(q, read_left()),
        "already_dmed": already_dmed,
        "dm_text": dm_text,
        "send_dm": send_dm,
        "reply_setup": lambda: reply_setup.get(STORE),
        "known_contact": lambda phone: donors().book.has_phone(phone),
        "reply_take": lambda: reply_setup.take(STORE),
        "caption_variant": caption_variant,
        "variant_count": variant_count,
        "variant_pool": variant_pool,
        "variant_names": variant_names,
        "goal": goal_value,
        "milestone_text": milestone_text,
        "update_text": update_text,
        "wa_reconnect": lambda: api("/app/reconnect"),
        "on_hold": on_hold,
        "dm_busy": lambda: bool(CAMPAIGN.get("running")),
        "job_message": job_message,
        "recent_chats": recent_chats,
        "outreach": outreach,
    }
)
__import__("dm_variants").OWNER_STYLE = lambda: focus_bank().owner_style(
    get_message("group")["text"]
)
__import__("dm_variants").CORRECTIONS = lambda: [m.get("rule", "") for m in mem_get()][-15:]
__import__("dm_variants").PROVEN = lambda: (
    (learning_mod.proven_texts(ENGINE.L, 1) + donors().book.proven_dm_texts(1))
    or learning_mod.proven_texts(ENGINE.L)
)


def engine_do(auto_review=False):
    return {
        "set_pace": lambda main_minutes, freelance_minutes: ENGINE.set_pace(
            main_minutes, freelance_minutes
        ),
        "pause_group": lambda key, hours: ENGINE.pause(key, hours),
        "resume_group": lambda key: ENGINE.resume(key),
        "set_group_pace": lambda target, minutes: set_group_pace(target, minutes),
        "set_quiet_hours": lambda start, end: ENGINE.set_quiet(start, end),
        "set_dms": lambda enabled, daily: (
            "DMs remain off by the owner instruction."
            if auto_review and enabled and not ENGINE.s.get("dm_enabled")
            else ENGINE.set_dms(enabled, daily)
        ),
        "notify_owner": lambda text: (
            ENGINE.notify("ai-" + str(int(time.time())), text, 0),
            "Owner told.",
        )[1],
    }


PILOT = assistant.Autopilot(
    lambda: {**studio_state(), "autopilot": ENGINE.summary()},
    mem_get,
    lambda: engine_do(True),
    auto_log,
    auto_on,
)

MANUAL_STATE = DATA / "manual-context.json"
LAST_MANUAL = mapping(STORE.get("manual_context", {})) if STORE else {}
if not LAST_MANUAL and MANUAL_STATE.exists():
    try:
        LAST_MANUAL = mapping(MANUAL_STATE.read_text(encoding="utf-8"))
    except Exception:
        LAST_MANUAL = {}
DELIVERIES = mapping(STORE.get("last_deliveries", {})) if STORE else {}
DM_NAMES = mapping(STORE.get("dm_names", {})) if STORE else {}
CONTACT_CONTEXT = {}
if not LAST_MANUAL:
    for old in reversed(chat_get(300)):
        if old.get("who") != "you":
            continue
        plan = manual_commands.parse(old.get("text", "")) or {}
        if plan.get("kind") in ("appeal", "select"):
            LAST_MANUAL.update(kind="appeal", target=plan["target"])
            break


def remember_manual(value):
    global LAST_MANUAL
    value = mapping(value)
    LAST_MANUAL = dict(value)
    atomic_write(MANUAL_STATE, json.dumps(value, ensure_ascii=False))
    if STORE:
        STORE.put("manual_context", dict(value))


def record_delivery(jid, text, result):
    if result.get("code") != "SUCCESS":
        return
    ident = mapping(result.get("results")).get("message_id")
    DELIVERIES[jid] = {"message_id": ident, "text": text, "time": time.time()}
    if STORE:
        STORE.put("last_deliveries", DELIVERIES)


def resolve_person(to):
    # The registered teammate is a verified app contact even when WhatsApp's
    # contact search does not contain their display name.
    candidate = str(to or "").strip()
    if candidate and re.fullmatch(r"[A-Za-z][A-Za-z\s._-]{0,60}", candidate):
        try:
            teammate = donors().team._load().get("member") or {}
            name = str(teammate.get("name") or "").strip()
            if name and candidate.casefold() in (name.casefold(), name.split()[0].casefold()):
                number = norm_phone(str(teammate.get("phone") or ""))
                if number:
                    return number + "@s.whatsapp.net"
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
    key = manual_commands.group(to)
    if key:
        return key
    if norm_phone(to) or str(to).endswith(("@s.whatsapp.net", "@g.us")):
        return str(to)
    found, checked = find_data(to)
    for item in found:
        CONTACT_CONTEXT[item["id"]] = item
    exact = [x for x in found if x["name"].casefold() == str(to).casefold()]
    if len(exact) == 1:
        return exact[0]["id"]
    if len(found) == 1:
        return found[0]["id"]
    if not found:
        raise ValueError("No matching contact. Give the phone number.")
    KNOWLEDGE.data["pending"] = {
        "kind": "recipient",
        "query": str(to),
        "candidates": found[:8],
        "created": time.time(),
    }
    KNOWLEDGE.save()
    raise ValueError(
        "More than one contact matches: "
        + ", ".join(x["name"] + " (…" + x["id"].split("@")[0][-4:] + ")" for x in found[:4])
        + ". Give the full name or last four digits."
    )


def dm_recipient(to=None):
    target = resolve_person(to) if to else LAST_MANUAL.get("to")
    if (
        not target
        or target in GROUPS
        or target in ("all", "free", "test")
        or str(target).endswith("@g.us")
    ):
        raise ValueError("Which person should receive the DM? Give their contact name or number.")
    phone = norm_phone(str(target).split("@")[0])
    if not phone:
        raise ValueError("That is not a valid DM number.")
    return phone + "@s.whatsapp.net"


LEGACY_DM = re.compile(
    r"(?i)(?:\bname\s+(?:brother|sister)\b|we picked you because|you were the first person we thought of|🚨|•\s*\*_|could you be one of them today to start his treatment\?|dY[\W_]|\ufffd)"
)


def ensure_dm_structure():
    """Put the canonical structured DM on the screen once, without replacing a custom complete draft."""
    try:
        with LOCK:
            draft = read_drafts()
            dm = draft.get("dm", "")
            if (
                isinstance(dm, str)
                and dm.strip()
                and dm_composer.complete(dm)
                and not LEGACY_DM.search(dm)
            ):
                return
            try:
                left = read_left()
            except (OSError, ValueError):
                left = 39000
            draft["dm"] = build_dm([0], left)
            atomic_write(DRAFT, json.dumps(draft, ensure_ascii=False))
            persist_file("drafts", DRAFT)
    except (OSError, ValueError, TypeError, KeyError):
        pass


def current_dm_caption(name="", gender="Brother"):
    text = read_drafts().get("dm", "")
    # Repair old incomplete/flattened model output, keeping the structured saved draft otherwise.
    if not dm_composer.complete(text):
        text = build_dm(dm_selection(False), read_left())
    text = greet_text(text, name, gender)
    if not dm_composer.complete(text):
        raise ValueError("The full DM caption is incomplete. Nothing was sent.")
    return text


def edit_dm_name(name, to=""):
    jid = dm_recipient(to)
    first = clean_first_name(name)
    gender = "Sister" if first.lower() in FEMALE else "Brother"
    DM_NAMES[jid] = {"name": first, "gender": gender}
    if STORE:
        STORE.put("dm_names", DM_NAMES)
    caption = current_dm_caption(first, gender)
    save_draft("dm", caption)
    remember_manual(
        {
            "kind": "dm_appeal",
            "to": jid,
            "name": first,
            "gender": gender,
            "text": caption,
            "with_picture": True,
        }
    )
    return (
        "Greeting changed to "
        + dm_composer.greeting(first, gender)
        + ". The full DM and the same recipient are kept. Nothing was sent."
    )


def send_dm_appeal(to="", name="", gender="Brother"):
    jid = dm_recipient(to)
    identity = DM_NAMES.get(jid) or {}
    first = (
        identity.get("name")
        if identity
        else clean_first_name(name or CONTACT_CONTEXT.get(jid, {}).get("name", ""))
    )
    gender = (
        identity.get("gender")
        if identity
        else ("Sister" if first.lower() in FEMALE or (first and gender == "Sister") else "Brother")
    )
    caption = current_dm_caption(first, gender)
    send_free(jid, caption, True)
    remember_manual(
        {
            "kind": "dm_appeal",
            "to": jid,
            "name": first,
            "gender": gender,
            "text": caption,
            "with_picture": True,
        }
    )
    return (
        "WhatsApp confirmed the full DM with poster to " + dm_composer.greeting(first, gender) + "."
    )


def prepare_dm(phone, name="", gender="Brother"):
    phone = norm_phone(phone)
    if not phone:
        raise ValueError("Provide a valid phone number before preparing the DM.")
    name = clean_first_name(name)
    gender = "Sister" if name and gender == "Sister" else "Brother"
    save_draft("dm", current_dm_caption(name, gender))
    return {
        "reply": "Full DM prepared for "
        + dm_composer.greeting(name, gender)
        + ". Nothing was sent.",
        "actions": [{"type": "prepare_dm", "phone": phone, "name": name, "gender": gender}],
    }


def delete_last_group(target=None):
    key = manual_commands.group(target or "") or (
        LAST_MANUAL.get("target") if LAST_MANUAL.get("kind") == "appeal" else None
    )
    if key not in GROUPS and key != "test":
        raise ValueError("Which group? Name the group whose last sent message should be deleted.")
    jid = "120363431210327603@g.us" if key == "test" else GROUPS[key][1]
    entry = DELIVERIES.get(jid, {})
    ident = entry.get("message_id")
    if not ident:
        own = [m for m in group_messages(jid) if m.get("is_from_me") is True and m.get("id")]
        own.sort(key=lambda m: str(m.get("timestamp", "")), reverse=True)
        if own:
            ident = own[0]["id"]
    if not ident:
        raise ValueError(
            "I cannot identify an own sent message in that group. No message was deleted."
        )
    check_hold()
    req = urllib.request.Request(
        GOWA_URL + "/message/" + urllib.parse.quote(str(ident), safe="") + "/revoke",
        data=json.dumps({"phone": jid}).encode(),
        headers={"X-Device-Id": DEVICE, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with WIRE_LOCK:
            check_hold()
            revision = getattr(OWNER_GUARD, "revision", None)
            if revision is not None and revision != OWNER_REVISION:
                raise ValueError("Superseded by a newer instruction.")
            with urllib.request.urlopen(req, timeout=20) as response:
                result = mapping(json.load(response))
    except Exception:
        raise ValueError(
            "WhatsApp did not confirm deletion. Check the group on your phone."
        ) from None
    if result.get("code") != "SUCCESS":
        raise ValueError("WhatsApp refused deletion. Check the message on your phone.")
    DELIVERIES.pop(jid, None)
    if STORE:
        STORE.put("last_deliveries", DELIVERIES)
    return (
        "WhatsApp confirmed deletion of the last own message in "
        + ("Givelife test" if key == "test" else GROUPS[key][0])
        + "."
    )


TEXT_LIST_JOBS = {}


def _owner_words(prompt):
    return re.sub(r"\s+", " ", chat_policy.owner_text(prompt)).casefold()


def _owner_quotes(prompt):
    """Text the owner put in quotes in this message (the app hides quoted text from instruction parsing, so it is checked here)."""
    return [
        re.sub(r"\s+", " ", q).strip().casefold()
        for q in re.findall(
            r'["\u201c\u201d]([^"\u201c\u201d]{1,4000})["\u201c\u201d]', str(prompt)
        )
    ]


def _owner_wrote(prompt, text):
    t = re.sub(r"\s+", " ", str(text)).strip().casefold()
    return bool(t) and (
        t in _owner_words(prompt) or any(t == q or t in q for q in _owner_quotes(prompt))
    )


def app_status():
    """One read of everything current, so a multi-step job starts from facts, not guesses."""
    out = {
        k: v
        for k, v in studio_state().items()
        if k
        in (
            "left",
            "case_name",
            "case_closed",
            "whatsapp",
            "autopilot",
            "minutes_since_post",
            "donor_context",
            "schedules",
        )
    }
    try:
        out["team"] = donors().team.summary()
    except Exception as e:
        out["team"] = "unavailable: " + safe_text(e, 80)
    out["shortcuts"] = [x["name"] for x in KNOWLEDGE.shortcut_list()]
    out["past_problems"] = [x["text"] for x in KNOWLEDGE.lessons_for("", 4)] or [
        x["error"] for x in KNOWLEDGE.data.get("lessons", [])[-3:]
    ]
    return out


def agent_action(name, prompt, args, owner):
    """Chat actions for team tasks, volunteers, cases and owner-written text to a list. Every change is checked against the owner's own words."""
    own = _owner_words(prompt)
    act = str(args.get("action", ""))
    says = lambda pattern: bool(re.search(pattern, own))
    if name == "shortcut_action":
        if act == "list":
            return (
                "; ".join(f"{x['name']} → {x['steps']}" for x in KNOWLEDGE.shortcut_list())
                or "No shortcuts yet."
            )
        if act == "save":
            if not says(r"\b(save|make|create|add|when i say)\b"):
                raise ValueError("Saving a shortcut needs your clear request. Nothing was saved.")
            return (
                "Shortcut saved: "
                + KNOWLEDGE.shortcut_save(args.get("name"), args.get("steps"))
                + ". Send just that name to run it."
            )
        if act == "delete":
            return (
                "Shortcut removed."
                if KNOWLEDGE.shortcut_delete(args.get("name"))
                else "No such shortcut."
            )
        raise ValueError("Unknown shortcut action.")
    if name == "team_action":
        t = donors().team
        if act == "status":
            return t.summary()
        if act == "plan":
            # NEVER trust an AI-generated deadline or rewritten task. Only the current
            # owner's words are allowed to supply scheduling instructions.
            task_source = chat_policy.owner_text(prompt).strip()
            task_source = re.sub(
                r"(?is)^(?:in\s+(?:the\s+)?tasks?\s*[,;:]?\s*)?(?:please\s+)?(?:give|add|assign|create|set)\s+(?:a\s+)?tasks?\s+(?:to|for|:)?\s*",
                "",
                task_source,
            )
            task_source = task_source or chat_policy.owner_text(prompt).strip()
            v = t.plan(task_source)
            lines = [
                f"{i + 1}. {x['text']} ("
                + (
                    f"ask {x['start_label']}, due {x['due_label']}"
                    if x["due_at"] is not None
                    else "no deadline; no automatic send"
                )
                + ")"
                for i, x in enumerate(v["plan"]["items"])
            ]
            return (
                "Plan (nothing sent yet):\n" + "\n".join(lines) + '\nSay "confirm tasks" to save.'
            )
        if act == "confirm":
            if not says(r"\b(confirm|start|yes|go ahead|haan|theek)\b"):
                raise ValueError('Starting tasks needs your clear "confirm". Nothing was sent.')
            return t.confirm_plan()["reply"]
        if act in ("verify", "reject", "cancel"):
            if not says(
                {
                    "verify": r"\b(verif|approve|done|ok|correct|good)",
                    "reject": r"\b(reject|not done|redo|again|wrong|send back)",
                    "cancel": r"\b(cancel|remove|drop|no need)",
                }[act]
            ):
                raise ValueError("That does not match your instruction. Nothing was changed.")
            ident = t.match_task(args.get("task", ""))
            return {
                "verify": lambda: (t.verify(ident), "Verified.")[1],
                "reject": lambda: (t.reject(ident, args.get("note", "")), "Sent back to him.")[1],
                "cancel": lambda: (t.cancel(ident), "Cancelled.")[1],
            }[act]()
        if act in ("pause", "resume"):
            if not says(r"\b(pause|stop|hold|resume|continue|start)\b"):
                raise ValueError("That does not match your instruction.")
            t.pause(act == "pause")
            return "Team follow-up " + ("paused." if act == "pause" else "resumed.")
        if act == "set_member":
            phone = norm_phone(str(args.get("phone", "")))
            if phone not in {
                norm_phone(x)
                for x in re.findall(
                    r"(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}", chat_policy.owner_text(prompt)
                )
            }:
                raise ValueError("Give the teammate's number in your message.")
            t.set_member(args.get("name", ""), phone)
            return "Teammate saved."
    if name == "volunteer_action":
        v = donors().volunteers
        if act == "list":
            names = [r["name"] for r in v.book.list("all")["items"]]
            return (
                f"{len(names)} volunteers: " + ", ".join(names[:20])
                if names
                else "No volunteers yet."
            )
        if act == "add":
            phone = str(args.get("phone", ""))
            if norm_phone(phone) not in {
                norm_phone(x)
                for x in re.findall(
                    r"(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}", chat_policy.owner_text(prompt)
                )
            }:
                raise ValueError("Give the volunteer's number in your message.")
            v.mutate({"action": "add", "name": args.get("name", ""), "phone": phone})
            return "Volunteer added."
        if act == "remove":
            v.mutate({"action": "delete", "id": args.get("name", "")})
            return "Volunteer removed."
        if act == "set_message":
            text = str(args.get("text", ""))
            if not _owner_wrote(prompt, text):
                raise ValueError(
                    "The volunteer message must be your exact words. Put it in quotes."
                )
            v.set_message(text)
            return "Volunteer message saved."
        if act in ("send_all", "send_one"):
            if not owner["send"]:
                raise ValueError('Sending needs your clear "send". Nothing was sent.')
            body = {"action": act, "request_id": "chat-" + uuid.uuid4().hex, "gap_seconds": 180}
            if act == "send_one":
                body["id"] = v.book.resolve(args.get("name", ""))["id"]
            r = v.mutate(body)
            return (
                r.get("reply")
                or "Volunteer sending started. Each person gets it once, a few minutes apart."
            )
    if name == "case_action":
        c = donors().cases
        if act == "list":
            return "; ".join(
                f"{x['name']}"
                + (" (open)" if x["current"] else "")
                + ("" if x.get("left") is None else f" Rs. {x['left']:,} left")
                for x in c.view()["cases"]
            )
        if act == "new":
            if not says(r"\b(new|start|begin|naya|nayi)\b"):
                raise ValueError("Starting a new case needs your clear request.")
            left = args.get("left")
            if left not in [
                int(x.replace(",", ""))
                for x in re.findall(r"\d[\d,]{2,}", chat_policy.owner_text(prompt))
            ] + [int(float(m) * 1000) for m in re.findall(r"(\d+(?:\.\d+)?)\s*k\b", own)]:
                raise ValueError("Say the amount needed for the new case in your message.")
            return c.new(args.get("name", ""), left)["reply"]
        if act in ("switch", "rename"):
            target = str(args.get("name", "")).strip()
            if act == "rename":
                return (c.rename(c.view()["current"], target), "Case renamed.")[1]
            match = [x for x in c.view()["cases"] if x["name"].casefold() == target.casefold()]
            if len(match) != 1:
                raise ValueError("No saved case has that name.")
            return c.switch(match[0]["id"])["reply"]
    if name == "send_text_list":
        text = str(args.get("text", "")).strip()
        if not _owner_wrote(prompt, text):
            raise ValueError(
                "I only send your exact words. Put the message in quotes and try again. Nothing was sent."
            )
        allowed = {
            norm_phone(x)
            for x in re.findall(
                r"(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}", chat_policy.owner_text(prompt)
            )
        }
        phones = list(dict.fromkeys(norm_phone(str(p)) for p in args.get("phones", [])))
        if not phones or any(p not in allowed for p in phones):
            raise ValueError("Every number must be written in your message. Nothing was sent.")
        if norm_phone(OWNER_PHONE) in phones:
            raise ValueError("Your own number cannot be in the list.")
        if len(phones) > 25:
            raise ValueError("Send to at most 25 numbers at a time.")
        check_hold()
        if any(not j.get("done") for j in TEXT_LIST_JOBS.values()):
            raise ValueError(
                "A message list is already sending. Wait for it to finish. Nothing was sent."
            )
        jid = uuid.uuid4().hex[:8]
        prune_finished(TEXT_LIST_JOBS, 20)
        TEXT_LIST_JOBS[jid] = {"total": len(phones), "sent": 0, "failed": [], "done": False}

        def run():
            job = TEXT_LIST_JOBS[jid]
            for i, p in enumerate(phones):
                if i:
                    time.sleep(__import__("random").uniform(60, 90))
                if on_hold():
                    job["failed"] += phones[i:]
                    break
                try:
                    r = send_custom(
                        {
                            "kind": "owner_text",
                            "target": "phone",
                            "phone": p,
                            "message": text,
                            "poster": False,
                        }
                    )
                    if isinstance(r, dict) and r.get("code") == "SUCCESS":
                        job["sent"] += 1
                    else:
                        job["failed"].append(p)
                except Exception:
                    job["failed"].append(p)
            tail = (
                (
                    "Not delivered to: "
                    + ", ".join("…" + x[-4:] for x in job["failed"])
                    + ". Check WhatsApp before trying again."
                )
                if job["failed"]
                else "All delivered."
            )
            chat_add(
                "app",
                f"Your message went to {job['sent']} of {job['total']} numbers. " + tail,
                turn_id="textlist-" + jid,
            )

        def guarded():
            try:
                run()
            except Exception:
                job = TEXT_LIST_JOBS[jid]
                chat_add(
                    "app",
                    f"The message list stopped unexpectedly after {job['sent']} of {job['total']} numbers. "
                    "Check WhatsApp before trying again; nothing is retried automatically.",
                    turn_id="textlist-" + jid,
                )
            finally:
                TEXT_LIST_JOBS[jid]["done"] = True

        threading.Thread(target=guarded, daemon=True, name="text-list-" + jid).start()
        return f"Sending your message to {len(phones)} numbers, about one a minute. I will post the result here when it finishes."
    raise ValueError("Unknown action.")


def chat_callbacks(
    prompt="",
    revision=None,
    task_id=None,
    selection=None,
    selection_kind="group",
    history=None,
    screen=None,
):
    callbacks = base_chat_callbacks()
    cache = {}
    verified = set()
    owner = chat_policy.intent(prompt)
    dm_revision = donors().revision
    variant = chat_policy.variant_request(owner["text"])
    draft_state = {
        "draft_task": dict(workflow().data),
        "drafts": read_drafts(),
        "screen": mapping(screen),
    }
    contextual_edit = draft_flow.contextual_edit(owner["text"], history or [], draft_state)
    edit_kind = (
        selection_kind
        if selection is not None
        else draft_flow.current_kind(owner["text"], draft_state)
    )
    if (
        (
            (
                draft_flow.editing_request(owner["text"])
                and chat_policy.permitted("set_message", prompt)
            )
            or contextual_edit
        )
        and not variant
        or selection is not None
    ) and (revision is None or revision == OWNER_REVISION):
        kind = edit_kind
        workflow().begin(owner["text"], kind, get_message(kind)["text"])
    sending = owner["send"]
    dm_allowed = owner["batch"]
    send_tools = {
        "send_message",
        "send_appeal",
        "send_dm_appeal",
        "dm_list",
        "dm_donors",
        "dm_group",
    }
    read_tools = chat_policy.READ

    def allowed_groups():
        destination = manual_commands.parse(prompt) or {}
        if destination.get("kind") in ("text", "appeal_to"):
            selected = manual_commands.group(destination.get("to", ""))
            if not selected:
                return set()
            return (
                set(GROUPS) | {"all"}
                if selected == "all"
                else set(FREELANCE) | {"free"}
                if selected == "free"
                else {selected}
            )
        keys = set(manual_commands.groups(chat_policy.owner_text(prompt)))
        if not keys and re.search(r"(?i)\b(?:him|her|contact|phone|dms?)\b", owner["text"]):
            return set()
        if not keys and manual_commands.has_group_exclusion(chat_policy.owner_text(prompt)):
            raise ValueError(
                "No clear eligible groups remain after the exclusion. Name the groups to send to."
            )
        if not keys:
            task = workflow().data
            if task.get("kind") == "group":
                if task.get("target"):
                    keys.add(task["target"])
                else:
                    raise ValueError(
                        "This draft has no selected group. Choose its recipient before sending."
                    )
            elif LAST_MANUAL.get("kind") == "appeal":
                keys.add(LAST_MANUAL.get("target"))
            elif LAST_MANUAL.get("kind") == "appeals":
                keys.update(LAST_MANUAL.get("targets", []))
            else:
                keys.update(k for k, v in GROUPS.items() if v[1] == LAST_MANUAL.get("to"))
            if LAST_MANUAL.get("to") == "120363431210327603@g.us":
                keys.add("test")
        # A contact lookup cannot re-authorize a group explicitly excluded by the owner.
        if not manual_commands.groups(chat_policy.owner_text(prompt)):
            keys.update(k for k, v in GROUPS.items() if v[1] in verified or v[1] in prompt)
        if "all" in keys:
            keys.update(GROUPS)
        if "free" in keys:
            keys.update(FREELANCE)
        return keys

    def wrapped(name, fn):
        def call(**args):
            if revision is not None and revision != OWNER_REVISION and name not in read_tools:
                raise ValueError("Superseded by your newer instruction. No old action was sent.")
            private_send = (
                name in ("send_dm_appeal", "dm_list", "dm_donors", "dm_group")
                or name == "donor_action"
                and args.get("action") == "send"
                or name == "send_message"
                and not (
                    manual_commands.group(str(args.get("to", "")))
                    or str(args.get("to", "")).endswith("@g.us")
                )
            )
            if private_send and dm_revision != donors().revision:
                raise ValueError(
                    "Personal DMs were stopped by your newer instruction. No old DM request was sent."
                )
            if name == "donor_action":
                return donors().model_tool(prompt, task_id, **args)
            if name in (
                "team_action",
                "volunteer_action",
                "case_action",
                "send_text_list",
                "shortcut_action",
            ):
                if not chat_policy.permitted(name, prompt):
                    raise ValueError(
                        "The current instruction does not ask for this. Nothing was changed or sent."
                    )
                return agent_action(name, prompt, args, owner)
            if name == "dm_donors":
                if not chat_policy.permitted(name, prompt):
                    raise ValueError(
                        "The current instruction does not authorize DMs. Nothing was sent."
                    )
                return donors().model_tool(prompt, task_id, "send")
            if not chat_policy.permitted(name, prompt) and not (
                name == "set_message"
                and (selection is not None or contextual_edit)
                and not chat_policy.task_assignment_only(prompt)
            ):
                if name in send_tools and not sending:
                    raise ValueError(
                        "The current instruction does not ask to send. Nothing was sent."
                    )
                if name in ("dm_list", "dm_donors", "dm_group"):
                    raise ValueError(
                        "The current instruction does not authorize DMs. Nothing was sent."
                    )
                raise ValueError(
                    "The current instruction does not authorize "
                    + name
                    + ". Nothing was changed or sent."
                )
            if (
                name == "set_message"
                and (contextual_edit or draft_flow.editing_request(owner["text"]))
                and not (
                    re.search(r"(?i)\bdm\b", owner["text"])
                    and re.search(r"(?i)\bgroup\b", owner["text"])
                )
                and args.get("kind") != edit_kind
            ):
                raise ValueError(
                    "This edit refers to the active "
                    + edit_kind
                    + " draft. Use that kind; no other draft was changed."
                )
            if name in send_tools and not sending:
                raise ValueError("The current instruction does not ask to send. Nothing was sent.")
            if name in ("dm_list", "dm_donors", "dm_group") and not dm_allowed:
                raise ValueError(
                    "The current instruction does not authorize DMs. Nothing was sent."
                )
            if name == "delete_last_message" and (
                not re.search(r"(?i)\b(delete|remove|revoke)\b", prompt)
                or re.search(r"(?i)\b(don'?t|do not|never)\b.*\b(delete|remove|revoke)\b", prompt)
            ):
                raise ValueError("No deletion was requested. Nothing was deleted.")
            if name == "remember" and not re.search(
                r"(?i)\b(always|never|remember|from now|in future|yaad rakho)\b", prompt
            ):
                raise ValueError(
                    "This is a current edit, not a request to save a future preference."
                )
            if (
                name == "set_dms"
                and args.get("enabled")
                and not re.search(
                    r"(?i)\b(dm|dms)\b.*\b(on|enable|start)\b|\b(enable|start)\b.*\b(dm|dms)\b",
                    prompt,
                )
            ):
                raise ValueError("DMs cannot be enabled without your current instruction.")
            if name == "autopilot" and not re.search(r"(?i)\b(auto|autopilot)\b", prompt):
                raise ValueError("This request does not change Auto mode.")
            if name == "autopilot":
                desired = chat_policy.switch_request(prompt, "auto")
                if desired is None or args.get("on") is not desired:
                    raise ValueError(
                        "The Auto switch does not match the current instruction. Nothing was changed."
                    )
            if name == "set_dms":
                desired = chat_policy.switch_request(prompt, "dm")
                if desired is not None and args.get("enabled") is not desired:
                    raise ValueError(
                        "The DM switch does not match the current instruction. Nothing was changed."
                    )
            if name in ("pause_group", "resume_group", "set_group_pace"):
                named = manual_commands.groups(owner["text"])
                target = args.get("key", args.get("target"))
                if not named:
                    raise ValueError(
                        "Name the group whose posting settings should change. No settings were changed."
                    )
                expanded = set(
                    k
                    for key in named
                    for k in (GROUPS if key == "all" else FREELANCE if key == "free" else [key])
                )
                permitted_target = (
                    set(GROUPS)
                    if target == "all"
                    else set(FREELANCE)
                    if target == "free"
                    else {target}
                )
                if named and not permitted_target.issubset(expanded):
                    raise ValueError(
                        "That group setting is outside the groups named in your instruction."
                    )
                if name == "set_group_pace":
                    import rules

                    expected = rules.pace_rules(owner["text"])
                    single, _ = rules.parse(owner["text"])
                    if not expected and single and single.get("kind") == "gap":
                        expected = [single]
                    if expected and not any(
                        r["group"] == target and r["minutes"] == args.get("minutes")
                        for r in expected
                    ):
                        raise ValueError(
                            "The interval does not match your instruction. Nothing was changed."
                        )
            if name == "delete_last_message":
                named = manual_commands.groups(owner["text"])
                target = args.get("target") or (
                    LAST_MANUAL.get("target") if LAST_MANUAL.get("kind") == "appeal" else None
                )
                if (named and (len(named) != 1 or target not in named)) or (
                    not named and args.get("target") and target != LAST_MANUAL.get("target")
                ):
                    raise ValueError(
                        "The deletion target does not match your current group. Nothing was deleted."
                    )
            if name == "dm_list":
                explicit = {
                    norm_phone(x)
                    for x in re.findall(
                        r"(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}", chat_policy.owner_text(prompt)
                    )
                }
                if any(
                    norm_phone(p.get("phone", "")) not in explicit
                    and norm_phone(p.get("phone", "")) + "@s.whatsapp.net" not in verified
                    for p in args.get("people", [])
                ):
                    raise ValueError(
                        "Every DM-list recipient must come from this owner instruction or a verified lookup."
                    )
            if name == "set_pace" and not manual_commands.groups(owner["text"]):
                raise ValueError(
                    "Name the group posting scope. A personal message cannot change group posting."
                )
            if name in ("set_left", "money_came"):
                plans = chat_policy.financial_plans(prompt)
                expected = [
                    p.get("amount")
                    for p in plans
                    if (p.get("kind") == "money") == (name == "money_came")
                ]
                if args.get("left" if name == "set_left" else "amount") not in expected:
                    raise ValueError(
                        "That amount does not match the current owner instruction. No money was changed."
                    )
            if name in ("send_message", "send_dm_appeal", "prepare_dm"):
                dest = str(args.get("to") or args.get("phone") or "")
                group_key = manual_commands.group(dest)
                if group_key:
                    if group_key not in allowed_groups():
                        raise ValueError(
                            "Name the intended group before sending. This group is not authorized by the current request or selected context."
                        )
                else:
                    phone = norm_phone(dest.split("@")[0])
                    jid = phone + "@s.whatsapp.net" if phone else dest
                    explicit = {
                        norm_phone(x)
                        for x in re.findall(
                            r"(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}", chat_policy.owner_text(prompt)
                        )
                    }
                    if not phone and not dest.endswith("@g.us"):
                        dest = resolve_person(dest)
                        jid = dest
                    same = jid == LAST_MANUAL.get("to") and bool(
                        re.search(
                            r"(?i)\b(him|her|them|same|again|it|resend)\b|^send\s+(?:now|hi|ok)$",
                            prompt.strip(),
                        )
                    )
                    if jid not in verified and phone not in explicit and not same:
                        raise ValueError(
                            "Recipient must be verified with find_contact from this instruction before sending or preparing."
                        )
            if name == "send_appeal":
                if args.get("target") not in allowed_groups():
                    raise ValueError(
                        "Name the intended group before sending. This group is not authorized by the current request or selected context."
                    )
            if name == "dm_group" and args.get("group") not in allowed_groups():
                raise ValueError("DM members only of the group named in the owner request.")
            cache_key = name + json.dumps(args, sort_keys=True, ensure_ascii=False)
            if name in send_tools | {"delete_last_message"} and cache_key in cache:
                return cache[cache_key]
            previous = getattr(OWNER_GUARD, "revision", None)
            OWNER_GUARD.revision = revision
            try:
                if name == "schedule_task" or name == "add_rule" and timed_tasks.requested(prompt):
                    result = timed_chat_command(prompt, task_id)
                    if result is None:
                        raise ValueError(
                            "Give a group/action and a future time. Nothing was scheduled or sent."
                        )
                elif name == "send_appeal":
                    workflow().apply_options(owner["text"], get_message("group")["text"])
                    result = send_appeal(
                        args.get("target"),
                        (task_id + "-" + hashlib.sha256(cache_key.encode()).hexdigest()[:16])
                        if task_id
                        else None,
                    )
                elif name == "send_message":
                    literal = bool(
                        re.search(
                            r'["“\']' + re.escape(str(args.get("text", ""))) + r'["”\']', prompt
                        )
                    )
                    target = resolve_person(args.get("to", ""))
                    import task_intent

                    quoted_steps = task_intent.quoted_sends(prompt)
                    if len(quoted_steps) > 1:
                        # Each contact gets the exact text from THEIR clause, never the first
                        # quoted message copied into every later send.
                        match_key = lambda value: (
                            norm_phone(str(value).split("@")[0]) or str(value).casefold()
                        )
                        intended = [
                            row
                            for row in quoted_steps
                            if match_key(resolve_person(row["to"])) == match_key(target)
                        ]
                        if len(intended) != 1:
                            raise ValueError(
                                "The exact text for this recipient is ambiguous. Nothing was sent."
                            )
                        args["text"] = intended[0]["text"]
                        literal = True
                    else:
                        custom = manual_commands.parse(prompt) or {}
                        quoted = re.search(
                            r'(?is)^(?:send|resend|text|message)\s+["“](.+?)["”]', prompt.strip()
                        )
                        if quoted:
                            args["text"] = quoted[1]
                            literal = True
                        elif custom.get("kind") == "text" and not literal:
                            args["text"] = custom["text"]
                            literal = True
                            args["with_picture"] = bool(
                                re.search(
                                    r"(?i)\b(poster|image|picture)\b",
                                    chat_policy.owner_text(prompt),
                                )
                            )
                    # The model selects recipients; the stored template supplies fundraising captions.
                    appeal = (
                        not literal
                        and not str(target).endswith("@g.us")
                        and target not in GROUPS
                        and target not in ("test", "all", "free")
                        and (
                            args.get("with_picture")
                            or re.search(r"(?i)\b(dm|appeal|donation|poster|structure)\b", prompt)
                            or re.search(r"(?i)Yous[au]f|03097458815", str(args.get("text", "")))
                        )
                    )
                    group_target = (
                        target
                        if target in GROUPS or target == "test"
                        else next((k for k, v in GROUPS.items() if v[1] == target), None)
                    )
                    if (
                        not literal
                        and group_target
                        and workflow().options("group", get_message("group")["text"])
                    ):
                        workflow().apply_options(owner["text"], get_message("group")["text"])
                        result = send_appeal(group_target)
                    elif appeal:
                        result = send_dm_appeal(target)
                    else:
                        result = send_free(
                            target,
                            args.get("text", ""),
                            args.get("with_picture", False),
                            literal=literal,
                        )
                elif name == "find_contact":
                    result = fn(**args)
                    try:
                        items = json.loads(result)
                        for item in items:
                            CONTACT_CONTEXT[item["id"]] = item
                        exact = [
                            x
                            for x in items
                            if x.get("name", "").casefold() == str(args.get("query", "")).casefold()
                        ]
                        selected = exact if len(exact) == 1 else items if len(items) == 1 else []
                        words = manual_commands.norm(args.get("query", "")).split()
                        if words and all(word in manual_commands.norm(prompt) for word in words):
                            verified.update(x["id"] for x in selected)
                    except (ValueError, TypeError, KeyError):
                        pass
                elif name == "set_message":
                    if selection is not None and args.get("kind") != selection_kind:
                        raise ValueError(
                            "Apply the chosen option to the same draft. The other message was kept."
                        )
                    if not isinstance(args.get("text"), str) or not args["text"].strip():
                        raise ValueError(
                            "The revised caption is empty. The saved message was kept."
                        )
                    draft_amount = manual_commands.balance_amount(args["text"], allow_with=False)
                    if draft_amount is not None and draft_amount != read_left():
                        raise ValueError(
                            "The caption balance does not match the confirmed amount remaining. Use the current balance."
                        )
                    if args.get("kind") == "dm" and read_left() > 0:
                        if re.search(
                            r"(?i)\bname\b.*\b(is|change|to)\b|\b(change|correct)\b.*\bname\b",
                            prompt,
                        ):
                            raise ValueError(
                                "Use edit_dm_name to change only the greeting; keep the full message."
                            )
                        if not dm_composer.complete(args.get("text", "")):
                            raise ValueError(
                                "Keep the full DM with blank lines, formatting, amount, donation options and payment details. Do not replace it with a name or one-paragraph summary."
                            )
                    work = workflow()
                    work.begin(owner["text"], args["kind"], get_message(args["kind"])["text"])
                    work.validate(args["text"])
                    result = fn(**args)
                    work.commit(args["kind"], args["text"])
                    if read_left() <= 0:
                        # A completed case may still have its old fundraising poster on disk.
                        # Saved thank-you drafts default to text-only, never the old poster.
                        with work.lock:
                            work.data["poster"] = False
                            work.persist()
                    result = (
                        args["kind"].upper()
                        + " message saved ("
                        + ("poster + caption" if work.data.get("poster", True) else "text only")
                        + ").\n\n"
                        + args["text"]
                    )
                elif name == "remember":
                    result = mem_add(prompt)
                else:
                    result = fn(**args)
            finally:
                OWNER_GUARD.revision = previous
            if name in send_tools | {"delete_last_message"}:
                cache[cache_key] = result
            return result

        return call

    return {name: wrapped(name, fn) for name, fn in callbacks.items()}


def manual_recipient():
    global LAST_MANUAL
    LAST_MANUAL = mapping(LAST_MANUAL)
    if LAST_MANUAL.get("kind") == "appeal":
        key = LAST_MANUAL.get("target")
        return {
            "target": key,
            "name": "GiveLife main" if key == "main" else key,
            "id": GROUPS[key][1] if key in GROUPS else "",
            "group": True,
        }
    if LAST_MANUAL.get("kind") in ("text", "dm_appeal"):
        return {
            "id": LAST_MANUAL.get("to"),
            "name": LAST_MANUAL.get("name")
            or CONTACT_CONTEXT.get(LAST_MANUAL.get("to"), {}).get("name", ""),
            "group": str(LAST_MANUAL.get("to", "")).endswith("@g.us"),
            "message_type": LAST_MANUAL.get("kind"),
            "last_caption": LAST_MANUAL.get("text", ""),
        }
    return None


def assistant_task(body):
    global OWNER_REVISION
    text = KNOWLEDGE.expand(str(body.get("text", ""))[:10000])
    ident = str(body.get("request_id") or uuid.uuid4().hex)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", ident):
        raise ValueError("Invalid request id.")
    with LOCK:
        if ident in ASSIST_TASKS:
            return ident
        saved = mapping(STORE.get("assistant_task_" + ident)) if STORE else {}
        if saved:
            ASSIST_TASKS[ident] = (
                saved
                if saved.get("done")
                else {
                    "done": True,
                    "error": "This request was interrupted by a restart. Check confirmed activity; it will not be repeated automatically.",
                }
            )
            return ident
        effective = chat_policy.followup(text, chat_get(40))["text"]
        if (
            draft_flow.selected_option(text, chat_get(40)) is not None
            or draft_flow.contextual_edit(
                chat_policy.owner_text(text),
                chat_get(40),
                {
                    "draft_task": workflow().data,
                    "drafts": read_drafts(),
                },
            )
            or chat_policy.intent(effective)["negative"]
            or re.fullmatch(r"(?i)\s*(?:no|cancel|stop|wait)\s*", text)
            or any(
                chat_policy.permitted(name, effective)
                for name in base_chat_callbacks()
                if name not in chat_policy.READ
            )
        ):
            OWNER_REVISION += 1
        revision = OWNER_REVISION
        prune_finished(ASSIST_TASKS, 100)
        ASSIST_TASKS[ident] = {"done": False}
        if STORE:
            STORE.put("assistant_task_" + ident, {"done": False, "started": time.time()})

    def run():
        try:
            OWNER_GUARD.image = body.get("image")
            hist = chat_get(300)
            KNOWLEDGE.report_correction(text)
            if hist and hist[-1]["who"] == "you" and hist[-1]["text"].strip() == text.strip():
                hist = hist[:-1]
            preferences = mem_get()
            import conversation_insights

            review_data = {}
            if conversation_insights.wants_review(text):
                # Entire available saved OWNER history (including older turns outside the
                # active 300-message chat); no old assistant answers can become facts.
                with KNOWLEDGE.lock:
                    past_turns = [dict(row) for row in KNOWLEDGE.data.get("turns", [])]
                    corrections = [
                        {"who": "you", "text": row.get("correction", ""), "time": row.get("time")}
                        for row in KNOWLEDGE.data.get("feedback", [])
                        if row.get("status") in ("confirmed_by_owner", "reported_needs_review")
                        and row.get("correction")
                    ]
                    failures = [dict(row) for row in KNOWLEDGE.data.get("lessons", [])]
                review_data = conversation_insights.build_history_review(
                    past_turns + corrections, hist
                )
                review_data["tool_failure_patterns"] = conversation_insights.summarize_failures(
                    failures
                )
            selection = draft_flow.selected_option(text, hist)
            follow = chat_policy.followup(text, hist)
            image_attached = str(body.get("image") or "")
            if image_attached and chat_policy.variant_request(text):
                output = {
                    "reply": "I cannot read the attached image with this model, so please paste the message text. Paste it and I will generate the 10 versions you need.",
                    "actions": [],
                    "done": [],
                    "jobs": [],
                    "diagnostics": {
                        "model": assistant.active_model(),
                        "iterations": 0,
                        "duration_ms": 0,
                        "tools": [],
                        "errors": [],
                    },
                }
            else:
                import task_intent

                retrieval_query = task_intent.retrieval_query(
                    text,
                    hist,
                    draft_flow.active_task(
                        {
                            "draft_task": workflow().data,
                            "drafts": read_drafts(),
                        }
                    ),
                )
                output = assistant.chat(
                    text,
                    hist or body.get("history", []),
                    {
                        **studio_state(),
                        "last_recipient": manual_recipient(),
                        "draft_task": workflow().data,
                        "drafts": read_drafts(),
                        "recipient_names": DM_NAMES,
                        "retrieved": KNOWLEDGE.retrieve(retrieval_query)
                        + KNOWLEDGE.lessons_for(retrieval_query),
                        "pending_task": KNOWLEDGE.data.get("pending", {}),
                        "history_review": review_data,
                        "rules": ENGINE.rule_list(),
                        "recent_activity": [x["text"] for x in AUTOLOG[-4:]],
                        "send_status": send_status_text(),
                        "engine": ENGINE.summary(),
                        "suggestions": [x["text"] for x in ENGINE.suggestions()],
                        "screen": body.get("screen", {}),
                    },
                    preferences,
                    chat_callbacks(
                        follow["text"],
                        revision,
                        ident,
                        selection,
                        draft_flow.option_kind(hist, mapping(body.get("screen")).get("view")),
                        hist,
                        mapping(body.get("screen")),
                    ),
                )
            if output is None:
                ASSIST_TASKS[ident].update(
                    done=True, error="The AI is not connected. Direct commands still work."
                )
                return
            output.update(
                **read_drafts(),
                left=read_left(),
                autopilot=auto_on(),
                dm_identity=dm_identity(),
            )
            output["superseded"] = revision != OWNER_REVISION
            if any(
                isinstance(t, dict)
                and t.get("tool") == "generate_dm_variants"
                and t.get("status") == "completed"
                for t in mapping(output.get("diagnostics")).get("tools", [])
            ):
                output["donors_changed"] = True
            output["turn_id"] = uuid.uuid4().hex
            diag = mapping(output.get("diagnostics"))
            for t in diag.get("tools", []):
                if isinstance(t, dict) and t.get("status") in ("rejected", "failed", "error"):
                    KNOWLEDGE.learn_failure(
                        t.get("tool"), t.get("error") or "was " + str(t.get("status")), text
                    )
            for e in diag.get("errors", []):
                KNOWLEDGE.learn_failure("chat", e, text)
            if output.get("done") or output.get("jobs"):
                tip = KNOWLEDGE.count_habit(text)
                if tip:
                    output["reply"] = (output.get("reply", "") + "\n\n" + tip).strip()
            KNOWLEDGE.archive("app", output.get("reply", ""), output["turn_id"])
            KNOWLEDGE.trace(
                {"request_id": ident, "route": "model", **output.get("diagnostics", {})}
            )
            ASSIST_TASKS[ident].update(done=True, result=output)
        except Exception as e:
            ASSIST_TASKS[ident].update(
                done=True,
                error="The assistant could not complete this request: "
                + safe_text(e, 160)
                + ". It will not retry automatically.",
            )
            try:
                KNOWLEDGE.trace({"request_id": ident, "error": safe_text(e, 160)})
            except Exception:
                pass
        finally:
            if hasattr(OWNER_GUARD, "image"):
                del OWNER_GUARD.image
            if STORE:
                STORE.put("assistant_task_" + ident, ASSIST_TASKS[ident])

    threading.Thread(target=run, daemon=True).start()
    return ident


def edit_donation_order():
    left = read_left()
    drafts = read_drafts()
    updated = {}
    work = workflow()
    custom = next((k for k, v in drafts.items() if work.current(k, v)), None)
    for kind, text in drafts.items():
        lines = text.split("\n")
        indices = [
            i
            for i, line in enumerate(lines)
            if re.search(r"(?i)\d+\s+people\b", line)
            and re.search(r"(?:1[ ,]?000|2[ ,]?000)", line)
        ]
        if indices:
            first = min(indices)
            replacement = [
                f"*_{math.ceil(left / 2000)} people donating Rs. 2,000_*",
                f"*_OR {math.ceil(left / 1000)} people donating Rs. 1,000_* 🤲",
            ]
            if len(indices) == 1:
                lines[first] = " ".join(replacement)
            else:
                lines[first] = replacement[0]
                lines[indices[1]] = replacement[1]
            updated[kind] = "\n".join(lines)
        else:
            updated[kind] = text
    with LOCK:
        atomic_write(DRAFT, json.dumps(updated, ensure_ascii=False))
        persist_file("drafts", DRAFT)
        if custom:
            work.revise(updated[custom])
    return f"Rs. 2,000 option first, then Rs. 1,000. The amount left stays Rs. {left:,}."


def remove_arrival_line():
    drafts = read_drafts()
    work = workflow()
    custom = next((k for k, v in drafts.items() if work.current(k, v)), None)
    for kind, text in drafts.items():
        lines = [
            line
            for line in text.split("\n")
            if not re.search(r"(?i)\b(came(?: in)?|received|has arrived|arrived)\b", line)
        ]
        drafts[kind] = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    with LOCK:
        atomic_write(DRAFT, json.dumps(drafts, ensure_ascii=False))
        persist_file("drafts", DRAFT)
        if custom:
            work.revise(drafts[custom])
    return f"Removed the money-arrival wording from the captions. Amount left is still Rs. {read_left():,}. No future rule was added."


def send_selected_groups(targets, request_id=None):
    keys = []
    for target in targets:
        keys.extend(
            list(GROUPS) if target == "all" else FREELANCE if target == "free" else [target]
        )
    keys = list(dict.fromkeys(keys))
    remember_manual({"kind": "appeals", "targets": targets})
    if not wa_ok():
        raise ValueError("WhatsApp is not connected. Link it first.")
    caption = read_drafts().get("group", "")
    options = workflow().options("group", caption)
    ident = start_send_job(
        keys,
        caption,
        True,
        request_id,
        with_picture=options.get("poster", True) if options else True,
    )
    return {
        "reply": f"Starting the manual send to {len(keys)} selected groups now.",
        "job_id": ident,
        "caption": caption,
    }


def team_chat(text):
    """Chat shortcuts for the teammate's tasks; errors become a plain reply so the owner sees why."""
    raw = str(text).strip()
    if not re.match(
        r"(?i)^(?:please\s+)?(?:(?:give|set|assign|add)\s+)?(?:(?:today'?s|todays|these|new)\s+)?(?:tasks?|todo|team|confirm tasks?|cancel tasks?|start tasks?|yes tasks?|send tasks?|verify task|cancel task|pause team|resume team|pause tasks|resume tasks|set\s+(?:my\s+)?(?:team\s*mate|teammate|team member))\b",
        raw,
    ) and not re.match(r"(?i)^task\s+#?\d", raw):
        return None
    import chat_policy

    try:
        return donors().team.command(raw, chat_policy.owner_text(raw).strip())
    except ValueError as e:
        return {"reply": str(e)}


def execute_manual_command(text, request_id=None, message_kind="group"):
    global OWNER_REVISION
    # Do not let a one-action fast-path silently swallow half a compound request.
    # The full owner instruction goes to the tool agent; historical data cannot authorize it.
    import task_intent

    if task_intent.compound(text):
        return {"handled": False}
    team_result = team_chat(text)
    if team_result is not None:
        return {"handled": True, **team_result}
    donor_result = donors().command(text, request_id)
    if donor_result is not None:
        return {"handled": True, **donor_result, "donors_changed": True}
    preview = draft_flow.preview_request(text)
    if preview:
        kind = (
            draft_flow.current_kind(
                text,
                {
                    "screen": {"view": message_kind},
                    "draft_task": workflow().data,
                    "drafts": read_drafts(),
                },
            )
            if preview == "current"
            else preview
        )
        return {"handled": True, "reply": get_message(kind)["text"]}
    if not fast_command_eligible(text):
        return {"handled": False}
    timed = timed_chat_command(text, request_id)
    if timed is not None:
        return {"handled": True, "reply": timed}
    import rules

    literal_plan = manual_commands.parse(text) or {}
    pace = [] if literal_plan.get("kind") == "text" else rules.pace_rules(text)
    rule, description = (None, "") if literal_plan.get("kind") == "text" else rules.parse(text)
    if not pace and rule and rule.get("kind") == "gap":
        pace = [rule]
    if pace:
        # "Post in all every 15 min" is an execution request, not merely an
        # interval-setting request. A closed case or global hold must never restart it.
        start_posting = bool(
            re.match(r"(?i)^\s*(?:please\s+)?(?:post|send|start\s+(?:posting|sending))\b", text)
        )
        if start_posting:
            if on_hold():
                raise ValueError(
                    "Everything is on hold. Nothing was scheduled or sent. Say resume explicitly first."
                )
            if read_left() <= 0:
                raise ValueError(
                    "The current case is complete (Rs. 0 left). Nothing was scheduled or sent. Start a new case before fundraising posts."
                )
            if not wa_ok():
                raise ValueError(
                    "WhatsApp is disconnected. Nothing was scheduled or sent. Connect WhatsApp and repeat the instruction."
                )
        with LOCK:
            OWNER_REVISION += 1
        for item in pace:
            ENGINE.add_rule(item)
        if start_posting:
            targets = [
                key
                for item in pace
                for key in (
                    list(GROUPS)
                    if item["group"] == "all"
                    else FREELANCE
                    if item["group"] == "free"
                    else [item["group"]]
                )
            ]
            for key in dict.fromkeys(targets):
                ENGINE.resume(key)
            set_auto(True)
        return {
            "handled": True,
            "reply": "; ".join(rules.describe(item) for item in pace)
            + (
                ". Auto ON; scheduled posting is active. No send is confirmed yet."
                if start_posting
                else ". Interval saved. Auto "
                + ("ON." if auto_on() else "OFF; nothing will post until enabled.")
            ),
        }
    plan = manual_commands.parse(text)
    if not plan:
        return {"handled": False}
    # "go ahead" / "continue" answer the assistant's last question. They only mean "lift the hold" while a hold is on.
    if (
        plan["kind"] == "resume"
        and not on_hold()
        and re.fullmatch(
            r"(?i)\s*(?:please\s+)?(?:go ahead|continue|go on|carry on)\s*[.!]*\s*", str(text)
        )
    ):
        return {"handled": False}
    # "do it" / "go" / "send it" right after the assistant asked something is the answer to that question, not "resend the last message".
    if (
        plan["kind"] == "repeat"
        and re.fullmatch(
            r"(?i)\s*(?:please\s+)?(?:do it|do that|go|go ahead|send it|ok|okay|yes)\s*[.!]*\s*",
            str(text),
        )
        and chat_policy.followup(text, chat_get(8))["inherited"]
    ):
        return {"handled": False}
    if plan["kind"] == "say":
        # Only meaningful inside a plain-text chat; otherwise the assistant reads it with its context.
        if LAST_MANUAL.get("kind") != "text" or not LAST_MANUAL.get("to"):
            return {"handled": False}
        words = (plan["name"].strip().title() + " " if plan["name"] else "") + plan["text"]
        with LOCK:
            OWNER_REVISION += 1
        OWNER_GUARD.revision = OWNER_REVISION
        send_free(LAST_MANUAL["to"], words, False, literal=True)
        remember_manual({**LAST_MANUAL, "kind": "text", "text": words})
        return {"handled": True, "reply": "Sent \u201c" + words + "\u201d to the same chat."}
    if plan["kind"] in ("appeal", "appeals", "repeat"):
        workflow().apply_options(chat_policy.owner_text(text), get_message("group")["text"])
    with LOCK:
        if plan["kind"] != "status":
            OWNER_REVISION += 1
    OWNER_GUARD.revision = OWNER_REVISION
    kind = plan["kind"]
    out = {"handled": True}
    if kind == "no_groups":
        raise ValueError(
            "No clear eligible groups remain after the exclusion. Name the groups to send to."
        )
    if kind == "refuse_target":
        raise ValueError("That group is excluded. Nothing was sent.")
    if kind == "stop_dms":
        out["reply"] = donors().pause_personal()["reply"]
    elif kind == "hold":
        out["reply"] = set_hold(True)
    elif kind == "resume":
        out["reply"] = set_hold(False)
    elif kind == "resume_dms":
        out["reply"] = donors().resume_personal()
    elif kind == "donation_order":
        out["reply"] = edit_donation_order()
    elif kind == "remove_arrival_line":
        out["reply"] = remove_arrival_line()
    elif kind == "dm_name":
        out["reply"] = edit_dm_name(plan["name"], plan.get("to", ""))
    elif kind == "status":
        out["reply"] = send_status_text(plan.get("freelance", False))
    elif kind == "money":
        if plan["amount"] > read_left():
            raise ValueError(
                "That donation is larger than the amount remaining. Tell me the correct remaining amount."
            )
        set_left(read_left() - plan["amount"])
        out["reply"] = f"Recorded Rs. {plan['amount']:,} received. Rs. {read_left():,} left."
    elif kind == "amount":
        set_left(plan["amount"])
        out["reply"] = f"Rs. {plan['amount']:,} left. Captions updated."
    elif kind == "delete":
        out["reply"] = delete_last_group(plan.get("target"))
    elif kind == "select":
        workflow().select(plan["target"], get_message("group")["text"])
        remember_manual({"kind": "appeal", "target": plan["target"]})
        out["reply"] = (
            "Selected " + ("GiveLife main" if plan["target"] == "main" else plan["target"]) + "."
        )
    elif kind == "repeat":
        task = workflow().data
        task_target = draft_workflow.repeat_target(task, get_message("group")["text"])
        if task_target:
            out.update(send_appeal(task_target, request_id))
            out.update(**read_drafts(), left=read_left())
            return out
        if not LAST_MANUAL:
            raise ValueError("Who should receive it? Name a group or contact.")
        if LAST_MANUAL.get("kind") == "appeals":
            out.update(send_selected_groups(LAST_MANUAL["targets"], request_id))
        elif LAST_MANUAL.get("kind") == "appeal":
            out.update(send_appeal(LAST_MANUAL["target"], request_id))
        elif LAST_MANUAL.get("kind") == "dm_appeal":
            out["reply"] = send_dm_appeal(
                LAST_MANUAL["to"], LAST_MANUAL.get("name", ""), LAST_MANUAL.get("gender", "Brother")
            )
        elif LAST_MANUAL.get("kind") == "text":
            send_free(
                LAST_MANUAL["to"],
                LAST_MANUAL["text"],
                LAST_MANUAL.get("with_picture", False),
                literal=True,
            )
            out["reply"] = "WhatsApp confirmed the repeated message."
        else:
            raise ValueError("There is no previous manual send to repeat.")
    elif kind == "appeals":
        if plan.get("amount") is not None:
            set_left(plan["amount"])
        out.update(send_selected_groups(plan["targets"], request_id))
    elif kind == "appeal":
        if plan.get("amount") is not None:
            set_left(plan["amount"])
        out.update(send_appeal(plan["target"], request_id))
    elif kind == "appeal_to":
        target = resolve_person(plan["to"])
        if target in GROUPS or target in ("all", "free", "test"):
            out.update(send_appeal(target, request_id))
        else:
            out["reply"] = send_dm_appeal(target)
    elif kind == "text":
        target = (
            resolve_person(plan["to"])
            if plan.get("to")
            else (
                LAST_MANUAL.get("to")
                if LAST_MANUAL.get("kind") == "text"
                else LAST_MANUAL.get("target")
                if LAST_MANUAL.get("kind") == "appeal"
                else None
            )
        )
        if not target:
            raise ValueError("Who should receive this text? Give a name, number or group.")
        send_free(target, plan["text"], False, literal=True)
        out["reply"] = "WhatsApp confirmed the message."
    drafts = read_drafts()
    out.update(group=drafts["group"], dm=drafts["dm"], left=read_left())
    return out


def manual_command(text, request_id=None, message_kind="group"):
    previous = getattr(OWNER_GUARD, "revision", None)
    try:
        try:
            janazah_time = caption_facts.parse_time(str(text))
        except ValueError as error:
            return {"handled": True, "reply": str(error)}
        if janazah_time:
            return {
                "handled": True,
                "reply": caption_facts.set_time(sys.modules[__name__], janazah_time),
            }
        if draft_flow.preview_request(text):
            return execute_manual_command(text, request_id, message_kind)
        pending = KNOWLEDGE.data.get("pending", {})
        if pending.get("created", 0) < time.time() - 600:
            pending = {}
            KNOWLEDGE.data["pending"] = {}
        if pending and str(text).strip().casefold() in ("cancel", "forget it", "stop", "no"):
            KNOWLEDGE.data["pending"] = {}
            KNOWLEDGE.save()
            return {
                "handled": True,
                "reply": "Cancelled the pending recipient selection. Nothing was sent.",
            }
        matches = [
            x
            for x in pending.get("candidates", [])
            if str(text).strip().casefold()
            in (x["name"].casefold(), x["id"].split("@")[0], x["id"].split("@")[0][-4:])
        ]
        if len(matches) == 1 and pending.get("action"):
            target = matches[0]["id"]
            action = pending["action"]
            KNOWLEDGE.data["pending"] = {}
            KNOWLEDGE.save()
            with LOCK:
                global OWNER_REVISION
                OWNER_REVISION += 1
                OWNER_GUARD.revision = OWNER_REVISION
            send_free(target, action["text"], False, literal=True)
            return {
                "handled": True,
                "reply": "WhatsApp confirmed your earlier message to " + matches[0]["name"] + ".",
            }
        if pending.get("action"):
            fresh = manual_commands.parse(text) or {}
            if fresh.get("kind") not in (None, "status"):
                KNOWLEDGE.data["pending"] = {}
                KNOWLEDGE.save()
        try:
            result = execute_manual_command(text, request_id, message_kind)
        except ValueError:
            plan = manual_commands.parse(text) or {}
            if (
                plan.get("kind") == "text"
                and KNOWLEDGE.data.get("pending", {}).get("kind") == "recipient"
            ):
                KNOWLEDGE.data["pending"]["action"] = {
                    "text": plan["text"],
                    "to_query": plan.get("to"),
                }
                KNOWLEDGE.save()
            raise
        if result.get("handled") and not result.get("donors_changed"):
            result["dm_identity"] = dm_identity()
        return result
    finally:
        OWNER_GUARD.revision = previous


def dm_identity():
    if LAST_MANUAL.get("kind") == "dm_appeal":
        return {
            "name": LAST_MANUAL.get("name", ""),
            "phone": LAST_MANUAL.get("to", "").split("@")[0],
            "gender": LAST_MANUAL.get("gender", "Brother"),
        }
    return None


fast_command_eligible = chat_policy.fast_command_eligible


def set_group_pace(target, minutes):
    if target not in (*GROUPS, "free", "all"):
        raise ValueError("Choose a known group or freelance/all.")
    minutes = max(15, min(1440, int(minutes)))
    ENGINE.add_rule({"kind": "gap", "group": target, "minutes": minutes})
    return (
        f"Automatic posts in {target}: every {minutes} minutes. Other groups keep their settings."
    )


def send_status_text(freelance=False):
    summary = ENGINE.summary()
    last = last_sent_by_key()
    keys = FREELANCE if freelance else list(GROUPS)
    lines = ["Auto is " + ("on" if auto_on() else "off") + "."]
    current = get_job(ACTIVE) if ACTIVE else None
    if current:
        lines.append(current.get("message", "A send is running."))
    for key in keys:
        every = summary["group_intervals"][key]
        stamp = last.get(key)
        elapsed = max(0, (time.time() - stamp) / 60) if stamp else None
        state = (
            "paused"
            if ENGINE.blocked(key)
            else (
                "due now"
                if elapsed is None or elapsed >= every
                else f"next in {math.ceil(every - elapsed)} min"
            )
        )
        lines.append(
            f"{GROUPS[key][0]}: every {every} min, "
            + (
                f"last confirmed {int(elapsed)} min ago"
                if elapsed is not None
                else "no confirmed send recorded"
            )
            + ", "
            + state
            + "."
        )
    if auto_on():
        lines.append(
            "Due groups send automatically while WhatsApp is connected and sending is not on hold; batch recipients stay 60 seconds apart."
        )
    return "\n".join(lines)


def live_snapshot():
    on = auto_on()
    summary = ENGINE.summary()
    hold = on_hold()
    job = get_job(ACTIVE) if ACTIVE else None
    status = (
        ENGINE.status()
        if on
        else {
            "now": (
                "On hold: waiting for resume"
                if hold
                else job.get("message", "Sending…")
                if job and not job.get("done")
                else "Automatic actions off"
            ),
            "state": "paused" if hold else "sending" if job and not job.get("done") else "off",
            "next": [],
            "last_reply_read": ENGINE.s.get("last_reply_read"),
            "today": {"posts": summary.get("posts_today", 0), "dms": summary.get("dms_today", 0)},
        }
    )
    if job and not job.get("done"):
        status["job"] = {k: job.get(k) for k in ("message", "next_send_at", "next_target")}
    if DONORS and DONORS.jobs.active:
        dj = DONORS.jobs.status()
        status.update(
            state="sending",
            now="Donor DMs: "
            + str(dj.get("sent", 0))
            + "/"
            + str(dj.get("total", 0))
            + " sent · "
            + str(dj.get("current") or dj.get("state", "Waiting")),
        )
    if AUTOLOG:
        status["last_event"] = {k: AUTOLOG[-1].get(k) for k in ("text", "time")}
    if _TIMED is not None and _TIMED_STORE is STORE:
        with _TIMED.lock:
            upcoming = sorted(
                (t for t in _TIMED.tasks if t["state"] == "pending"), key=lambda t: t["due"]
            )
        if upcoming:
            t = upcoming[0]
            label = (
                ", ".join(t.get("targets", []))
                if t["action"] == "send"
                else "Auto ON"
                if t["action"] == "auto_on"
                else "Auto OFF"
                if t["action"] == "auto_off"
                else "Resume Auto"
            )
            status["scheduled"] = {"due_at": t["due"], "label": label}
        status["group_timers"] = {
            t["scope"]: {"id": t["id"], "due_at": t["due"], "delay": t.get("delay")}
            for t in upcoming
            if t.get("scope") and t["action"] == "send"
        }
    with LOCK:
        current = {"left": read_left(), "drafts": read_drafts()}
    return {
        "on": on,
        "ai": bool(assistant.client()),
        "log": AUTOLOG[-20:],
        "summary": summary,
        "status": status,
        "hold": hold,
        "last_sent": dashboard_send_times(),
        **current,
    }


DONORS = None
GROUP_RESEARCH = None


def group_research():
    global GROUP_RESEARCH
    with LOCK:
        if GROUP_RESEARCH is None or GROUP_RESEARCH.store is not STORE:
            from group_finder_integration import GroupFinder

            GROUP_RESEARCH = GroupFinder(__import__(__name__))
        return GROUP_RESEARCH


def recover_group_research():
    # A research-record or database failure must not prevent the rest of the studio starting.
    wait = 30
    for _ in range(20):  # backs off 30s..10min and then stops; the rest of the studio is unaffected
        try:
            group_research().service.start_worker()
            return
        except Exception:
            time.sleep(wait)
            wait = min(wait * 2, 600)


def donors():
    global DONORS
    if DONORS is None or DONORS.book.store is not STORE:
        with _SINGLETON_LOCK:  # one registry only, or two could each send the same donor
            if DONORS is None or DONORS.book.store is not STORE:
                import donor_integration, sys

                DONORS = donor_integration.DonorIntegration(sys.modules[__name__])
    return DONORS


class Handler(BaseHTTPRequestHandler):
    def remote_config(self):
        return {
            "key": os.environ.get("UI_ACCESS_KEY", ""),
            "origins": [x for x in os.environ.get("ALLOWED_ORIGINS", "").split(",") if x],
        }

    def authorized(self):
        key = self.remote_config().get("key", "")
        return bool(key) and secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + key
        )

    def do_OPTIONS(self):
        self.reply({})

    def reply(self, data, kind="application/json", status=200, extra_headers=None):
        self.response_sent = True
        if not isinstance(data, (str, bytes)):
            data = json.dumps(data, ensure_ascii=False)
        self.send_response(status)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        if "Cache-Control" not in (extra_headers or {}):
            self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in self.remote_config().get("origins", []):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data if isinstance(data, bytes) else data.encode())

    _STATIC = {}

    def reply_new_ui(self):
        """The same app on its own path (/new) with the redesign switched on. "/" is never touched."""
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        html = html.replace('<body class="nomsg"', '<body class="nomsg ui2"', 1)
        html = html.replace(
            '<link rel="stylesheet" href="/responsive.css" />',
            '<link rel="stylesheet" href="/responsive.css" />\n    <link rel="stylesheet" href="/new-ui.css" />',
            1,
        )
        html = html.replace("</body>", '<script src="/new-ui.js"></script></body>', 1)
        return self.reply(
            html.encode("utf-8"), "text/html", extra_headers={"Cache-Control": "no-cache"}
        )

    def reply_new_group_finder(self):
        """Group finder inside the redesign (/new/group-finder): same page, the new look added. /group-finder is untouched."""
        html = (ROOT / "group-finder.html").read_text(encoding="utf-8")
        html = html.replace("<body>", '<body class="ui2 ui2-gf">', 1)
        html = html.replace(
            '<link rel="stylesheet" href="/group-finder.css">',
            '<link rel="stylesheet" href="/group-finder.css"><link rel="stylesheet" href="/new-ui.css">',
            1,
        )
        html = html.replace("</body>", '<script src="/new-ui.js"></script></body>', 1)
        return self.reply(
            html.encode("utf-8"), "text/html", extra_headers={"Cache-Control": "no-cache"}
        )

    def reply_new_ui_css(self):
        """new-ui.css is written with .UI2 where every rule needs the same strong prefix; expand it here."""
        css = (ROOT / "new-ui.css").read_text(encoding="utf-8").replace(".UI2", NEW_UI_PREFIX)
        return self.reply(
            css.encode("utf-8"), "text/css", extra_headers={"Cache-Control": "no-cache"}
        )

    def reply_file(self, name, kind):
        """App files: revalidated every time (ETag, so a new deploy shows at once) and gzipped, so repeat opens are tiny."""
        path = ROOT / name
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
        hit = Handler._STATIC.get(name)
        if not hit or hit[0] != key:
            raw = path.read_bytes()
            etag = '"' + hashlib.sha1(raw).hexdigest()[:24] + '"'
            gz = gzip.compress(raw, 6) if len(raw) > 1024 else None
            hit = Handler._STATIC[name] = (key, raw, etag, gz)
        _, raw, etag, gz = hit
        head = {"Cache-Control": "no-cache", "ETag": etag, "Vary": "Accept-Encoding"}
        if self.headers.get("If-None-Match") == etag:
            self.response_sent = True
            self.send_response(304)
            for k, v in head.items():
                self.send_header(k, v)
            self.end_headers()
            return
        if gz and "gzip" in self.headers.get("Accept-Encoding", ""):
            return self.reply(gz, kind, extra_headers={**head, "Content-Encoding": "gzip"})
        return self.reply(raw, kind, extra_headers=head)

    timeout = 120  # a stalled or half-open client can never pin a worker thread forever

    def do_GET(self):
        self.response_sent = False
        try:
            self._get()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass  # the browser went away mid-reply; nothing to answer
        except Exception:
            if not self.response_sent:
                try:
                    self.reply(
                        {"error": "This page could not load right now. Try again in a moment."},
                        status=500,
                    )
                except Exception:
                    pass

    def _get(self):
        if self.path == "/health":
            return self.reply(
                {
                    "ok": True,
                    "version": (os.environ.get("RENDER_GIT_COMMIT") or "local")[:7],
                    "ai_provider": (
                        "DeepSeek ("
                        + (os.environ.get("DEEPSEEK_REASONING_MODEL") or assistant.MODEL)
                        + ")"
                    )
                    if assistant.client()
                    else "Not connected",
                }
            )
        icon = SITE_ICONS.get(self.path.split("?")[0])
        if icon:
            return self.reply((ROOT / "icons" / icon[0]).read_bytes(), icon[1])
        if self.path.split("?")[0] in (
            "/group-finder",
            "/group-finder.js",
            "/group-finder.css",
            "/case-plan",
            "/case-plan.js",
            "/case-plan.css",
        ):
            name = self.path.split("?")[0][1:]
            name = name + ".html" if name in ("group-finder", "case-plan") else name
            return self.reply_file(
                name,
                "text/html"
                if name.endswith(".html")
                else "text/css"
                if name.endswith(".css")
                else "application/javascript",
            )
        if self.path.split("?")[0] in ("/new", "/new/"):
            return self.reply_new_ui()
        if self.path.split("?")[0] == "/new/group-finder":
            return self.reply_new_group_finder()
        if self.path.split("?")[0] == "/new-ui.css":
            return self.reply_new_ui_css()
        if self.path.split("?")[0] == "/new-ui.js":
            return self.reply_file("new-ui.js", "application/javascript")
        if self.path in (
            "/",
            "/app.js",
            "/format.js",
            "/connection.js",
            "/donors.js",
            "/replies.js",
            "/notes.js",
            "/notes.css",
            "/donors.css",
            "/studio.css",
            "/compact-nav.js",
            "/compact-nav.css",
            "/focus-editor.js",
            "/format-toolbar.js",
            "/format-toolbar.css",
            "/auto-controls.css",
            "/focus-editor.css",
            "/comfort.js",
            "/comfort.css",
            "/responsive.css",
        ):
            name = "index.html" if self.path == "/" else self.path[1:]
            return self.reply_file(
                name,
                "text/html"
                if self.path == "/"
                else "text/css"
                if self.path.endswith(".css")
                else "application/javascript",
            )
        if not self.authorized():
            return self.reply({"error": "Access key required"}, status=401)
        if self.path.split("?")[0] == "/api/case-plan":
            return self.reply(plan_view())
        if self.path.split("?")[0] == "/api/group-finder":
            try:
                return self.reply(group_research().snapshot(self.path))
            except (ValueError, TypeError):
                return self.reply({"error": "Choose valid research filters."}, status=400)
            except Exception:
                return self.reply(
                    {
                        "error": "Research records could not be loaded. Existing records were preserved."
                    },
                    status=502,
                )
        if self.path.split("?")[0] == "/donors":
            try:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                return self.reply(donors().book.list(q.get("tab", ["all"])[0], q.get("q", [""])[0]))
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path == "/notes":
            import notes_store

            try:
                unlocked = notes_store.allowed(STORE, self.headers.get("Cookie"))
                if not unlocked:
                    return self.reply({"locked": True}, extra_headers={"Cache-Control": "no-store"})
                token = notes_store.cookie_token(self.headers.get("Cookie"))
                return self.reply(
                    {"locked": False, **notes_store.load(STORE)},
                    extra_headers={
                        "Set-Cookie": notes_store.device_cookie(
                            token, https=self.headers.get("X-Forwarded-Proto", "https") != "http"
                        )
                    },
                )
            except Exception:
                return self.reply(
                    {
                        "error": "Notes are temporarily unavailable. Your saved notes were not changed."
                    },
                    status=503,
                )
        if self.path == "/donor-delivery":
            return self.reply(
                {
                    **donors().jobs.status(),
                    "paused": bool(donors().paused),
                    "resume": donors().resume_status(),
                    "auto": donors().auto.status(),
                }
            )
        if self.path == "/cases":
            try:
                return self.reply(donors().cases.view())
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path.split("?")[0] == "/volunteers":
            try:
                return self.reply(
                    donors().volunteers.view(
                        urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(
                            "q", [""]
                        )[0]
                    )
                )
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path.startswith("/focus-bank?"):
            kind = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(
                "kind", ["group"]
            )[0]
            if kind not in ("group", "dm"):
                return self.reply({"error": "Choose group or DM."}, status=400)
            bank = focus_bank()
            bank.start(
                kind
            )  # resume generation if needed; never rewrite the bank just because the tab opened
            return self.reply(bank.get(kind))
        if self.path == "/donor-messages":
            return self.reply({**donors().messages.get(), "follow_up": donors().follow_up_text()})
        if self.path == "/wa-status":
            try:
                return self.reply(api("/devices/" + DEVICE + "/status"))
            except Exception:
                return self.reply(
                    {"error": "WhatsApp is restarting. Try again shortly."}, status=502
                )
        if self.path == "/drafts":
            ensure_completed_drafts()
            self.reply(read_drafts())  # a damaged file is repaired first, never passed to the browser
        elif self.path == "/auto-controls":
            try:
                self.reply(auto_controls().view())
            except Exception:
                self.reply({"error": "The Auto controls could not be read. Nothing was changed."}, status=503)
        elif self.path == "/report":
            # Every resume (donor DMs and groups) and how many people the Reply feature answered.
            PKT = datetime.timezone(datetime.timedelta(hours=5))
            clock = lambda ts: datetime.datetime.fromtimestamp(ts, PKT).strftime("%d %b, %I:%M %p")
            names = {"main": "GiveLife"}
            resumes = []
            try:
                for t in timed_scheduler().tasks:
                    if t.get("action") != "resume":
                        continue
                    keys = t.get("targets") or []
                    what = (
                        "All groups"
                        if set(keys) >= set(GROUPS)
                        else "Freelance groups"
                        if set(keys) == set(FREELANCE)
                        else ", ".join(names.get(k, GROUPS.get(k, [k])[0]) for k in keys)
                    )
                    resumes.append(
                        {
                            "what": what,
                            "when": clock(t.get("due", 0)),
                            "due": t.get("due", 0),
                            "state": str(t.get("state", "")).title(),
                        }
                    )
            except Exception:
                pass
            try:
                dr = donors().resume_status()
                if dr.get("due"):
                    resumes.append(
                        {
                            "what": "Donor DMs",
                            "when": clock(dr["due"]),
                            "due": dr["due"],
                            "state": str(dr.get("state", "")).title(),
                        }
                    )
            except Exception:
                pass
            for x in (STORE.get("resume_log", []) if STORE else []) or []:
                resumes.append(
                    {
                        "what": x.get("what", ""),
                        "when": clock(x.get("at", 0)),
                        "due": x.get("at", 0),
                        "state": "Done now",
                    }
                )
            resumes.sort(key=lambda r: -r["due"])
            day = datetime.datetime.now(PKT).date().isoformat()
            self.reply(
                {
                    "resumes": resumes[:12],
                    "replies": {
                        "today": (ENGINE.s.get("reply_people_by_day") or {}).get(day, 0),
                        "total": ENGINE.s.get("reply_people_total", 0),
                        "on": bool(reply_setup.get(STORE).get("enabled")),
                    },
                }
            )
        elif self.path == "/chat-next-actions":
            self.reply({"items": next_chat_actions()})
        elif self.path == "/poster":
            img = poster_media()
            if not img.is_file():
                return self.reply(
                    {"error": "Selected poster is missing. Upload it again."}, status=404
                )
            if img.suffix == ".mp4":
                # The compact chat icon is an image; never show an outdated JPEG.
                return self.reply(
                    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect x="2" y="2" width="44" height="44" rx="9" fill="#5c40c9"/><path d="M19 12v24l19-12z" fill="#fff"/></svg>',
                    "image/svg+xml",
                )
            self.reply(img.read_bytes(), "image/jpeg")
        elif self.path == "/dm-poster":
            img = poster_media("dm")
            if not img.is_file():
                return self.reply(
                    {"error": "Selected poster is missing. Upload it again."}, status=404
                )
            self.reply(img.read_bytes(), "video/mp4" if img.suffix == ".mp4" else "image/jpeg")
        elif self.path == "/format.js":
            self.reply((ROOT / "format.js").read_bytes(), "application/javascript")
        elif self.path == "/app.js":
            self.reply((ROOT / "app.js").read_bytes(), "application/javascript")
        elif self.path == "/left":
            self.reply({"left": read_left()})
        elif self.path.startswith("/autopilot"):
            self.reply(live_snapshot())
        elif self.path == "/memory":
            self.reply(mem_get())
        elif self.path == "/knowledge":
            mem_get()
            self.reply(KNOWLEDGE.summary())
        elif self.path.startswith("/assistant-evaluate/"):
            result = EVAL_TASKS.get(self.path.split("/")[-1])
            self.reply(result or {"error": "Unknown evaluation."}, status=200 if result else 404)
        elif self.path == "/campaign":
            self.reply(
                {
                    **{k: v for k, v in CAMPAIGN.items() if k != "stop"},
                    "log": CAMPAIGN["log"][-8:],
                    "wait": max(0, round(CAMPAIGN["next_at"] - time.time())),
                }
            )
        elif self.path == "/rules":
            self.reply({"items": ENGINE.rule_list(), "autopilot": auto_on()})
        elif self.path == "/reply-setup":
            self.reply({**reply_setup.get(STORE), "autopilot": auto_on()})
        elif self.path == "/ai-test":
            self.reply(ai_test())
        elif self.path == "/wa-check":
            c = check_groups(True)
            self.reply(
                {
                    "checked": c.get("checked"),
                    "missing": c.get("missing", []),
                    "fixed": c.get("fixed", []),
                    "whatsapp": wa_ok(),
                }
            )
        elif self.path == "/chat":
            self.reply({"items": chat_get(200)})
        elif self.path == "/suggestions":
            self.reply(
                {"items": ENGINE.suggestions(), "autopilot": auto_on(), "summary": ENGINE.summary()}
            )
        elif self.path == "/groups":
            self.reply([{"key": k, "name": v[0]} for k, v in GROUPS.items()])
        elif self.path.startswith("/assistant-status/"):
            ident = self.path.split("/")[-1]
            task = ASSIST_TASKS.get(ident)
            if task is None and STORE:
                task = mapping(STORE.get("assistant_task_" + ident)) or None
                if task and not task.get("done"):
                    task = {
                        "done": True,
                        "error": "The service restarted before completion. Check recent activity; this action will not repeat automatically.",
                    }
            self.reply(
                task
                or {
                    "error": "This request is no longer tracked after a service restart. Check recent activity before trying again."
                },
                status=200 if task else 404,
            )
        elif self.path.startswith("/send-status/"):
            job = get_job(self.path.split("/")[-1])
            self.reply(job or {"error": "Unknown job"}, status=200 if job else 404)
        elif self.path == "/":
            self.reply((ROOT / "index.html").read_bytes(), "text/html")
        else:
            self.reply({}, status=404)

    def do_POST(self):
        self.response_sent = False
        try:
            self._post()
        except (ValueError, TypeError, KeyError):
            if not self.response_sent:
                self.reply(
                    {"error": "The request data is invalid. Correct the fields and try again."},
                    status=400,
                )
        except Exception:
            if not self.response_sent:
                self.reply(
                    {
                        "error": "This request did not complete reliably. Check confirmed activity before repeating any send."
                    },
                    status=502,
                )

    def _post(self):
        global ACTIVE, OWNER_REVISION
        if not self.authorized():
            return self.reply({"error": "Access key required"}, status=401)
        if self.path != "/api/group-finder":
            ENGINE.touch_owner()
        if self.path not in (
            "/chat-log",
            "/rule-text",
            "/assistant",
            "/command",
            "/feedback",
            "/knowledge",
            "/assistant-evaluate",
            "/donors",
            "/volunteers",
            "/cases",
            "/donor-messages",
            "/donor-delivery",
            "/donor-send",
            "/donor-paste",
            "/api/group-finder",
            "/api/case-plan",
        ):
            with LOCK:
                OWNER_REVISION += 1
            OWNER_GUARD.revision = OWNER_REVISION
        origin = self.headers.get("Origin")
        same_origin = origin and urllib.parse.urlparse(origin).netloc == self.headers.get("Host")
        if origin and not same_origin and origin not in self.remote_config().get("origins", []):
            return self.reply({}, status=403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= (22_000_000 if self.path == "/upload-image" else 12_000_000):
                return self.reply({"error": "Request is empty or too large."}, status=400)
            body = json.loads(self.rfile.read(length))
        except Exception:
            return self.reply({"error": "Invalid request"}, status=400)
        if not isinstance(body, dict):
            return self.reply({"error": "Request must be a JSON object."}, status=400)
        if self.path == "/api/case-plan":
            try:
                return self.reply(plan_mutate(body))
            except ValueError as e:
                return self.reply({"error": str(e)[:300]}, status=400)
        if self.path == "/api/group-finder":
            from group_finder import Conflict
            from group_research import ResearchError

            try:
                return self.reply(group_research().mutate(body))
            except Conflict as e:
                return self.reply({"error": str(e)}, status=409)
            except ResearchError as e:
                return self.reply({"error": str(e), "code": e.code}, status=502)
            except (ValueError, TypeError, KeyError) as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path == "/notes":
            import notes_store

            action = body.get("action")
            if action == "unlock":
                try:
                    token = notes_store.unlock(STORE, body.get("password"), self.client_address[0])
                    return self.reply(
                        {"locked": False, **notes_store.load(STORE)},
                        extra_headers={
                            "Set-Cookie": notes_store.device_cookie(
                                token,
                                https=self.headers.get("X-Forwarded-Proto", "https") != "http",
                            )
                        },
                    )
                except ValueError as e:
                    return self.reply({"error": str(e)}, status=403)
                except Exception:
                    return self.reply(
                        {"error": "Unable to unlock notes. Try again later."}, status=503
                    )
            if action == "lock":
                try:
                    notes_store.lock_device(STORE, self.headers.get("Cookie"))
                except Exception:
                    return self.reply(
                        {"error": "Could not revoke this desktop unlock."}, status=503
                    )
                return self.reply(
                    {"locked": True},
                    extra_headers={
                        "Set-Cookie": notes_store.clear_cookie(
                            https=self.headers.get("X-Forwarded-Proto", "https") != "http"
                        )
                    },
                )
            try:
                if not notes_store.allowed(STORE, self.headers.get("Cookie")):
                    return self.reply({"error": "Unlock private notes first."}, status=403)
                if action == "save":
                    return self.reply(
                        notes_store.save(STORE, body.get("html"), body.get("revision"))
                    )
                raise ValueError("Unknown notes action.")
            except ValueError as e:
                return self.reply(
                    {"error": str(e)}, status=409 if "another window" in str(e) else 400
                )
            except Exception:
                return self.reply(
                    {
                        "error": "Notes could not be saved. Your existing saved notes were preserved."
                    },
                    status=503,
                )
        if self.path == "/cases":
            try:
                c = donors().cases
                act = body.get("action")
                if act == "new":
                    return self.reply(c.new(body.get("name"), body.get("left")))
                if act == "switch":
                    return self.reply(c.switch(body.get("id")))
                if act == "rename":
                    return self.reply(c.rename(body.get("id"), body.get("name")))
                raise ValueError("Unknown case action.")
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path == "/volunteers":
            try:
                return self.reply(donors().volunteers.mutate(body))
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path in (
            "/donors",
            "/donor-delivery",
            "/donor-send",
            "/donor-messages",
            "/donor-paste",
        ):
            try:
                if self.path == "/donor-paste":
                    if body.get("action") == "preview":
                        return self.reply(
                            donors().pasted.preview(body.get("text"), body.get("gap_seconds", 240))
                        )
                    if body.get("action") == "start":
                        return self.reply(
                            donors().pasted.start(
                                body.get("token"),
                                body.get("gap_seconds", 240),
                                body.get("request_id"),
                                body.get("poster", True),
                                body.get("message"),
                                body.get("attachment"),
                            )
                        )
                    raise ValueError("Choose preview or start for the pasted donor list.")
                if self.path == "/donors":
                    return self.reply(donors().mutate(body))
                if self.path == "/donor-send":
                    return self.reply(
                        donors().send_one(
                            body.get("id"),
                            body.get("request_id"),
                            poster=body.get("poster", True),
                            follow_up=body.get("follow_up") is True,
                        )
                    )
                if self.path == "/donor-messages":
                    if body.get("action") == "regenerate":
                        return self.reply(donors().messages.start_regeneration())
                    if body.get("action") == "generate":
                        source = str(body.get("source", "") or "")
                        if not source.strip():
                            raise ValueError("Paste the complete message you want versions of.")
                        return self.reply(donors().messages.generate(source, body.get("count", 10)))
                    if body.get("action") == "follow_up":
                        return self.reply(donors().set_follow_up(body.get("text")))
                    if body.get("action") == "base":
                        return self.reply(donors().messages.set_base(body.get("text")))
                    if body.get("action") == "test":
                        return self.reply(donors().test_dm(body.get("poster", True)))
                    return self.reply(donors().messages.update(body.get("id"), body.get("text")))
                if body.get("test"):
                    return self.reply(donors().test_dm(body.get("poster", True)))
                if body.get("toggle"):
                    return self.reply(donors().toggle())
                if type(body.get("auto")) is bool:
                    return self.reply(
                        donors().auto.set(
                            body["auto"],
                            body.get("follow_up") is True,
                            body.get("poster") is not False,
                        )
                    )
                if isinstance(body.get("auto_options"), dict):
                    opts = body["auto_options"]
                    return self.reply(
                        donors().auto.set_options(opts.get("follow_up"), opts.get("poster"))
                    )
                if body.get("configure"):
                    return self.reply(
                        donors().configure_job(body["configure"], body.get("settings"))
                    )
                if body.get("stop"):
                    return self.reply(donors().pause_personal())
                if body.get("resume_at") is not None:
                    return self.reply(
                        donors().schedule_resume(body["resume_at"], body.get("request_id"))
                    )
                if body.get("resume") is True:
                    return self.reply(donors().resume_all())
                if CAMPAIGN.get("running"):
                    raise ValueError("Another DM campaign is running. Stop it first.")
                return self.reply(
                    donors().start_batch(
                        **{
                            k: v
                            for k, v in body.items()
                            if k
                            in (
                                "scope",
                                "gap_seconds",
                                "ids",
                                "limit",
                                "request_id",
                                "poster",
                                "chunk",
                                "rest_seconds",
                                "fresh",
                                "rests",
                                "jitter",
                                "skip_contacted",
                                "follow_up",
                            )
                        }
                    )
                )
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path == "/focus-bank":
            try:
                kind = body.get("kind")
                bank = focus_bank()
                if kind not in ("group", "dm"):
                    raise ValueError("Choose group or DM.")
                action = body.get("action")
                if action == "manual":
                    return self.reply(bank.manual(kind, body.get("messages")))
                if action == "generate":
                    return self.reply(bank.generate(kind))
                if action in ("retry", "regenerate"):
                    return self.reply(bank.retry(kind, fresh=action == "regenerate"))
                return self.reply(bank.save(kind, body.get("text"), body.get("revision")))
            except ValueError as e:
                return self.reply({"error": str(e)}, status=409)
        if self.path == "/auto-controls":
            try:
                controls = auto_controls()
                if "on" in body:
                    return self.reply(controls.set(body.get("control"), body.get("on"), body.get("settings")))
                return self.reply(controls.edit(body.get("control"), body.get("settings")))
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path == "/message-style":
            try:
                return self.reply(message_style(body))
            except RuntimeError as e:
                return self.reply({"error": str(e)}, status=503)
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
        if self.path == "/drafts":
            if any(
                not isinstance(body.get(k), str) or len(body[k]) > 10000 for k in ("group", "dm")
            ):
                return self.reply(
                    {"error": "Both captions must be text, at most 10,000 characters each."},
                    status=400,
                )
            with LOCK:
                previous = {k: get_message(k)["text"] for k in ("group", "dm")}
                old = get_message("group")["text"]
                work = workflow()
                active = work.current("group", old)
                atomic_write(
                    DRAFT,
                    json.dumps({k: str(body[k]) for k in ("group", "dm")}, ensure_ascii=False),
                )
                persist_file("drafts", DRAFT)
                if active and body["group"] != old:
                    work.revise(body["group"])
            if STORE:
                for kind in ("group", "dm"):
                    if body[kind] != previous[kind]:
                        focus_bank().save(kind, body[kind])
            self.reply({"saved": True})
        elif self.path == "/chat-action":
            try:
                self.reply(execute_chat_action(body.get("action_id")))
            except ValueError as e:
                self.reply({"error": str(e)}, status=409)
        elif self.path == "/wa-reconnect":
            try:
                api("/app/reconnect")
                self.reply({"ok": True})
            except Exception:
                self.reply(
                    {"error": "Could not restore the connection. Try linking with a QR code."},
                    status=502,
                )
        elif self.path == "/wa-logout":
            if body.get("confirm") is not True:
                return self.reply({"error": "Confirm disconnect first."}, status=400)
            if not SEND_LOCK.acquire(blocking=False):
                return self.reply(
                    {"error": "A send is running. Wait before disconnecting."}, status=409
                )
            try:
                api("/app/logout")
                self.reply({"ok": True})
            except Exception:
                self.reply(
                    {"error": "Disconnect was not confirmed. Check the connection status."},
                    status=502,
                )
            finally:
                SEND_LOCK.release()
        elif self.path == "/stop-send":
            if _stop_id(body.get("stop_id")):
                stop_event(body["stop_id"]).set()
            if isinstance(body.get("job_id"), str):
                stop_job(body["job_id"])
            self.reply({"ok": True})
        elif self.path == "/send-custom":
            try:
                watch_stop(body.get("stop_id"))
                self.reply(send_custom(body))
            except SendStopped:
                self.reply({"code": "STOPPED", "message": "Sending stopped. Nothing was sent."})
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
            except Exception:
                self.reply(
                    {"error": "Could not prepare this send. No automatic retry will occur."},
                    status=502,
                )
            finally:
                unwatch_stop(body.get("stop_id"))
        elif self.path == "/wa-login":
            try:
                data = api("/devices/" + DEVICE + "/login")
                url = mapping(data.get("results")).get("qr_link", "")
                path = urllib.parse.urlparse(url).path
                if not path.startswith("/statics/qrcode/"):
                    return self.reply({"error": "QR not available; check connection."}, status=400)
                with urllib.request.urlopen(GOWA_URL + path, timeout=10) as qr:
                    encoded = base64.b64encode(qr.read()).decode()
                self.reply(
                    {
                        "qr": "data:image/png;base64," + encoded,
                        "duration": data["results"].get("qr_duration", 30),
                    }
                )
            except Exception as e:
                self.reply({"error": "Could not get QR: " + str(e)}, status=502)
        elif self.path == "/next-message":
            self.reply({"message": next_message()})
        elif self.path == "/next-dm":
            self.reply({"message": next_dm()})
        elif self.path == "/memory":
            self.reply({"reply": mem_add(body.get("rule", ""))})
        elif self.path == "/hold":
            self.reply({"reply": set_hold(body.get("on", True)), "hold": on_hold()})
        elif self.path == "/dm-batch":
            try:
                self.reply(
                    {
                        "reply": dm_batch_now(
                            body.get("kind", "donors"),
                            body.get("count", 10),
                            body.get("group", "main"),
                        )
                    }
                )
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/chat-log":
            self.reply(
                {
                    "ok": True,
                    "turn_id": chat_add(
                        body.get("who"),
                        body.get("text", ""),
                        body.get("err"),
                        body.get("turn_id"),
                        body.get("model", ""),
                    ),
                }
            )
        elif self.path == "/knowledge":
            self.reply(
                {
                    "removed": KNOWLEDGE.forget(str(body.get("forget", ""))),
                    "memory": KNOWLEDGE.summary(),
                }
            )
        elif self.path == "/feedback":
            try:
                self.reply(
                    {
                        "saved": KNOWLEDGE.feedback(
                            str(body.get("turn_id", "")),
                            body.get("correction", ""),
                            body.get("remember") is True,
                        ),
                        "warning": KNOWLEDGE.sync_error,
                    }
                )
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/assistant-evaluate":
            import chat_eval

            cases = body.get("cases", chat_eval.DEFAULT_CASES)
            try:
                cases = chat_eval.validate_cases(cases)
            except ValueError as e:
                return self.reply({"error": str(e)}, status=400)
            running = next((k for k, v in EVAL_TASKS.items() if not v.get("done")), None)
            if running:
                return self.reply({"eval_id": running})
            ident = uuid.uuid4().hex
            prune_finished(EVAL_TASKS, 20)
            EVAL_TASKS[ident] = {"done": False, "results": [], "total": len(cases)}

            def evaluate():
                for key in cases:
                    try:
                        result = chat_eval.run_case(key)
                    except Exception as e:
                        result = {
                            "case": key,
                            "passed": False,
                            "error": str(e)[:160],
                            "sandbox": True,
                        }
                    EVAL_TASKS[ident]["results"].append(result)
                EVAL_TASKS[ident]["done"] = True
                KNOWLEDGE.trace(
                    {
                        "evaluation": ident,
                        "passed": sum(x["passed"] for x in EVAL_TASKS[ident]["results"]),
                        "total": len(cases),
                        "sandbox": True,
                    }
                )

            threading.Thread(target=evaluate, daemon=True).start()
            self.reply({"eval_id": ident})
        elif self.path == "/autopilot":
            self.reply({"reply": set_auto(bool(body.get("on"))), "on": auto_on()})
        elif self.path == "/reply-setup":
            try:
                self.reply(
                    {
                        **reply_setup.save(
                            STORE,
                            bool(body.get("enabled")),
                            body.get("replies", []),
                            body.get("new_replies"),
                        ),
                        "autopilot": auto_on(),
                    }
                )
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/upload-image":
            try:
                self.reply(
                    {"id": save_upload(str(body.get("data", "")), body.get("use", "attachment"))}
                )
            except Exception as e:
                self.reply({"error": str(e)[:120]}, status=400)
        elif self.path == "/campaign":
            if body.get("stop"):
                CAMPAIGN["stop"] = True
                return self.reply({"reply": "Stopping the DM list."})
            try:
                self.reply({"reply": start_campaign(body)})
            except Exception as e:
                self.reply({"error": str(e)[:160]}, status=400)
        elif self.path == "/find":
            out, checked = find_data(str(body.get("query", "")))
            self.reply({"items": out, "checked": checked})
        elif self.path == "/command":
            if not isinstance(body.get("text", ""), str) or len(body.get("text", "")) > 10000:
                return self.reply(
                    {"error": "Command must be text of at most 10,000 characters."}, status=400
                )
            try:
                self.reply(
                    manual_command(
                        str(body.get("text", "")), body.get("request_id"), body.get("view", "group")
                    )
                )
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/send-now":
            if not isinstance(body.get("text"), str) or not isinstance(body.get("to", ""), str):
                return self.reply({"error": "Recipient and message must be text."}, status=400)
            to = str(body.get("to", "")).strip() or LAST_RECIPIENT.get("id", "")
            if not to:
                return self.reply(
                    {"error": "Who should I send it to? Say: send hi to <name or number>."},
                    status=400,
                )
            try:
                send_free(
                    to,
                    body.get("text", ""),
                    bool(body.get("with_picture")),
                    literal=body.get("literal") is True,
                )
                self.reply({"ok": True, "to": LAST_RECIPIENT.get("name", "")})
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
            except Exception as e:
                self.reply({"error": "Could not send: " + str(e)[:100]}, status=502)
        elif self.path == "/rule-text":
            rule, msg = rule_from_text(str(body.get("text", "")))
            if not rule:
                return self.reply({"rule": False})
            if not auto_on():
                return self.reply({"rule": True, "saved": False, "summary": msg})
            ENGINE.add_rule(rule)
            self.reply({"rule": True, "saved": True, "summary": msg})
        elif self.path == "/rules":
            self.reply(
                {"removed": ENGINE.delete_rule(body.get("delete")), "items": ENGINE.rule_list()}
            )
        elif self.path == "/suggestion":
            msg = ENGINE.run_suggestion(str(body.get("action", "")))
            if msg is None:
                return self.reply(
                    {"error": "This one is done from the screen or by you."}, status=400
                )
            self.reply({"reply": msg})
        elif self.path == "/autopilot-settings":
            a = str(body.get("action", ""))
            key = str(body.get("key", ""))
            if a in ("pause", "resume") and key not in GROUPS:
                return self.reply({"error": "Unknown group. Use: " + ", ".join(GROUPS)}, status=400)
            try:
                msg = (
                    ENGINE.pause(key, float(body.get("hours", 24)))
                    if a == "pause"
                    else ENGINE.resume(key)
                    if a == "resume"
                    else ENGINE.set_quiet(int(body.get("start", 0)), int(body.get("end", 0)))
                    if a == "quiet"
                    else ENGINE.set_dms(
                        bool(body.get("enabled", True)),
                        int(body.get("daily", 30)),
                        body.get("new_people"),
                    )
                    if a == "dms"
                    else ENGINE.set_pace(body.get("main"), body.get("freelance"))
                    if a == "pace"
                    else None
                )
            except Exception as e:
                return self.reply({"error": str(e)[:120]}, status=400)
            if msg is None:
                return self.reply({"error": "Unknown setting"}, status=400)
            self.reply({"reply": msg, "summary": ENGINE.summary()})
        elif self.path == "/assistant":
            text = body.get("text", "")
            if not isinstance(text, str) or len(text) > 10000:
                return self.reply(
                    {"error": "Use a text message of at most 10,000 characters."}, status=400
                )
            if not text.strip():
                return self.reply({"error": "Type something first."}, status=400)
            try:
                direct = manual_command(
                    text, body.get("request_id"), mapping(body.get("screen")).get("view", "group")
                )
                if direct.get("handled"):
                    plan = manual_commands.parse(text) or {}
                    KNOWLEDGE.trace(
                        {
                            "request_id": safe_text(body.get("request_id"), 100),
                            "route": "command",
                            "intent": [plan.get("kind") or "draft"],
                            "ok": not direct.get("error"),
                        }
                    )
                    return self.reply(direct)
                ident = assistant_task(body)
                self.reply({"task_id": ident})
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/left":
            if isinstance(body.get("left"), bool):
                return self.reply({"error": "Amount must be a number."}, status=400)
            try:
                left = int(body.get("left"))
            except Exception:
                return self.reply(
                    {"error": "Enter the amount as a number, like 34000."}, status=400
                )
            if not 0 <= left <= 10000000:
                return self.reply({"error": "Amount looks wrong."}, status=400)
            g, d = set_left(left)
            self.reply({"left": left, "group": g, "dm": d})
        elif self.path == "/send-group":
            if not isinstance(body.get("group"), str) or not isinstance(body.get("message"), str):
                return self.reply({"error": "Group and caption must be text."}, status=400)
            key = body.get("group")
            caption = str(body.get("message", ""))
            if key not in GROUPS and key not in ("all", "free"):
                return self.reply({"error": "Unknown group"}, status=400)
            try:
                OWNER_REVISION += 1
                remember_manual({"kind": "appeal", "target": key})
                options = workflow().options("group", caption)
                workflow().select(key, caption)
                ident = start_send_job(
                    list(GROUPS) if key == "all" else FREELANCE if key == "free" else [key],
                    caption,
                    True,
                    body.get("request_id"),
                    with_picture=options.get("poster", True) if options else True,
                )
                self.reply({"job_id": ident})
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/schedule-group" and body.get("cancel"):
            sched = timed_scheduler()
            with sched.lock:
                task = next(
                    (
                        x
                        for x in sched.tasks
                        if x.get("id") == body.get("cancel") and x.get("scope")
                    ),
                    None,
                )
                if not task or task["state"] != "pending":
                    return self.reply(
                        {"error": "That timer already ran or was cancelled."}, status=400
                    )
                sched.cancel_task(task)
            self.reply({"cancelled": True})
        elif self.path == "/schedule-group":
            if not isinstance(body.get("group"), str):
                return self.reply({"error": "Group must be text."}, status=400)
            key = body.get("group")
            if key not in GROUPS and key not in ("all", "free"):
                return self.reply({"error": "Unknown group"}, status=400)
            try:
                delay = int(body.get("delay_minutes", 0))
                if not 1 <= delay <= 1440:
                    raise ValueError("Delay must be 1–1440 minutes.")
                caption = str(body.get("message") or "")
                if not caption.strip():
                    caption = read_drafts().get("group", "")
                if not caption.strip():
                    raise ValueError("Save a group message first, then schedule.")
                keys = list(GROUPS) if key == "all" else FREELANCE if key == "free" else [key]
                due = time.time() + delay * 60
                PKT = datetime.timezone(datetime.timedelta(hours=5))
                when = datetime.datetime.fromtimestamp(due, PKT)
                # The saved message is read when the send is due, so a changed amount left is never sent stale.
                task = {
                    "action": "send",
                    "targets": keys,
                    "text": None,
                    "due": due,
                    "daily": False,
                    "clock": when.strftime("%H:%M"),
                    "id": uuid.uuid4().hex[:8],
                    "state": "pending",
                    "created": time.time(),
                    "request_id": body.get("request_id"),
                    "signature": "ui-" + uuid.uuid4().hex,
                    "scope": key,
                    "delay": delay,
                }
                sched = timed_scheduler()
                with sched.lock:
                    # One timer per group button: a new time replaces the pending one.
                    for old_task in [
                        x for x in sched.tasks if x.get("scope") == key and x["state"] == "pending"
                    ]:
                        sched.cancel_task(old_task)
                    if (
                        sum(
                            x["state"] in ("pending", "running", "dispatching") for x in sched.tasks
                        )
                        >= 100
                    ):
                        raise ValueError("Too many pending schedules. Cancel one first.")
                    sched.tasks.append(task)
                    sched.save()
                name = (
                    "all 6 groups"
                    if key == "all"
                    else "all 5 freelance groups"
                    if key == "free"
                    else (GROUPS[key][0] if key in GROUPS else key)
                )
                mins_label = (
                    str(delay) + " min"
                    if delay < 60
                    else ("1 hour" if delay == 60 else str(delay // 60) + " hr")
                )
                self.reply(
                    {
                        "scheduled": True,
                        "task_id": task["id"],
                        "due_at": due,
                        "message": "Scheduled: send to "
                        + name
                        + " in "
                        + mins_label
                        + ". (Task #"
                        + task["id"]
                        + ")",
                    }
                )
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/schedule-resume":
            # Resume GiveLife or the freelance groups now, or at a Pakistan time (HH:MM, today or tomorrow).
            which = body.get("which")
            if which not in ("main", "free", "all"):
                return self.reply({"error": "Choose GiveLife, Freelance or All."}, status=400)
            keys = list(GROUPS) if which == "all" else FREELANCE if which == "free" else ["main"]
            name = {"main": "GiveLife", "free": "all freelance groups", "all": "all groups"}[which]
            try:
                at = str(body.get("at") or "").strip()
                if not at:
                    for key in keys:
                        ENGINE.resume(key)
                    set_hold(False)
                    if not auto_on():
                        set_auto(True)
                    log_resume(
                        {"main": "GiveLife", "free": "Freelance groups", "all": "All groups"}[which]
                    )
                    return self.reply({"message": "Resumed " + name + " now."})
                if not re.fullmatch(r"\d{1,2}:\d{2}", at):
                    raise ValueError("Choose a time like 14:30.")
                PKT = datetime.timezone(datetime.timedelta(hours=5))
                now = datetime.datetime.now(PKT)
                hh, mm = map(int, at.split(":"))
                if not (0 <= hh < 24 and 0 <= mm < 60):
                    raise ValueError("Choose a valid time.")
                when = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if when <= now:
                    when += datetime.timedelta(days=1)
                task = {
                    "action": "resume",
                    "targets": keys,
                    "due": when.timestamp(),
                    "daily": False,
                    "clock": when.strftime("%H:%M"),
                    "id": uuid.uuid4().hex[:8],
                    "state": "pending",
                    "created": time.time(),
                    "request_id": body.get("request_id"),
                    "signature": "ui-resume-" + uuid.uuid4().hex,
                }
                sched = timed_scheduler()
                with sched.lock:
                    sched.tasks.append(task)
                    sched.save()
                self.reply(
                    {
                        "message": "Resume "
                        + name
                        + " at "
                        + when.strftime("%I:%M %p").lstrip("0")
                        + (" tomorrow" if when.date() > now.date() else "")
                        + " (Pakistan time)."
                    }
                )
            except ValueError as e:
                self.reply({"error": str(e)}, status=400)
        elif self.path == "/test":
            caption = str(body.get("message", ""))
            if not caption.strip():
                return self.reply({"error": "Message is empty"}, status=400)
            try:
                watch_stop(body.get("stop_id"))
                options = workflow().options("group", caption)
                with SEND_LOCK:
                    check_stop()
                    try:
                        caption = focus_bank().reserve_groups(caption, 1)[0]
                    except ValueError as e:
                        # A test only checks delivery; it must not wait for the ten-version bank to finish generating.
                        if not any(
                            x in str(e)
                            for x in (
                                "distinct saved versions",
                                "Could not safely create",
                                "Save a Group message",
                            )
                        ):
                            raise
                    if read_left() <= 0 and completed_case_appeal(caption):
                        raise ValueError(
                            "Completed case: saved Group version still asks for donations. Nothing sent."
                        )
                    picture = read_left() > 0 and (not options or options.get("poster", True))
                    result = (
                        send_image("120363431210327603@g.us", caption)
                        if picture
                        else send_text("120363431210327603@g.us", caption)
                    )
                    if not picture and result.get("code") == "SUCCESS":
                        jid = "120363431210327603@g.us"
                        stamp = time.time()
                        LAST_LOCAL[jid] = stamp
                        record_delivery(jid, caption, result)
                        if STORE:
                            saved = STORE.get("last_sent", {})
                            saved[jid] = stamp
                            STORE.put("last_sent", saved)
                self.reply(result)
            except SendStopped:
                self.reply({"code": "STOPPED", "message": "Sending stopped. Nothing was sent."})
            except Exception as e:
                self.reply({"code": "ERROR", "message": str(e)})
            finally:
                unwatch_stop(body.get("stop_id"))
        else:
            self.reply({}, status=404)

    def log_message(self, *args):
        pass


def team_loop():
    """Every 20 seconds: read the teammate's replies, mark late tasks, send the next due message."""
    time.sleep(15)
    while True:
        try:
            donors().team.tick()
        except Exception:
            pass
        time.sleep(20)


def donor_autopilot():
    """Keeps a free host awake while a batch the owner started is running. Never resumes a batch by itself."""
    import urllib.request

    url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    while True:
        time.sleep(540)
        try:
            if url and (donors().jobs.active or donors().volunteers.jobs.active):
                urllib.request.urlopen(url + "/health", timeout=20).read()
        except Exception:
            pass


def donor_auto_loop():
    """Follows the Donors Auto switch: switches it off when its batch ends or stops. Never starts a new audience."""
    while True:
        time.sleep(15)
        try:
            donors().auto.tick()
        except Exception as exc:
            print("[donor-auto] " + type(exc).__name__, flush=True)


def resume_batches_after_restart(wait=10, tries=90, sleep=time.sleep):
    """A deploy or restart must not stop a DM batch that was running. Once WhatsApp is connected again,
    carry on with each batch that was in flight (donor and volunteer). Anyone already sent, unconfirmed or
    caught mid-send is skipped, so nobody gets a second DM; batches the owner stopped stay stopped.
    Returns the number of batches resumed."""
    registries = []
    for pick in (lambda: donors().jobs, lambda: donors().volunteers.jobs):
        try:
            registries.append(pick())
        except Exception:
            pass
    resumed = 0
    for _ in range(tries):
        pending = [jobs for jobs in registries if jobs.connected()]
        for jobs in pending:
            try:
                if jobs.recover():
                    resumed += 1
            except Exception as exc:
                print("[resume] " + type(exc).__name__, flush=True)
            registries.remove(jobs)
        if not registries:
            break
        sleep(wait)
    return resumed


ensure_dm_structure()
if __name__ == "__main__":
    # One background worker failing to start must never keep the website itself from starting.
    def start_worker(name, start):
        try:
            start()
        except Exception as exc:
            print("[startup] " + name + " did not start: " + type(exc).__name__, flush=True)

    def spawn(target, name):
        start_worker(name, threading.Thread(target=target, daemon=True, name=name).start)

    spawn(resume_batches_after_restart, "dm-resume")
    spawn(recover_group_research, "research-recovery")
    spawn(donor_autopilot, "keep-awake")
    spawn(donor_auto_loop, "donor-auto")
    # Team was removed from the interface. Retain records without hidden outreach.
    if os.environ.get("GIVELIFE_TEAM_ENABLED") == "1":
        spawn(team_loop, "team-loop")
    start_worker("autopilot advisor", PILOT.start)
    start_worker("auto engine", ENGINE.start)
    spawn(timed_loop, "timed-tasks")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
