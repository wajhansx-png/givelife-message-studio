"""Volunteer Guide: one message, wait for the reply, then choose the next. Code decides; no bursts.

State per volunteer (engine.s["vol_flow"][phone]):
  step: asked | poster | done | waiting_owner | stopped,  at: last send time,  checked: "are you done?" sent,
  seen: reply ids handled,  case: the case revision this round belongs to,  remind_at: one "later" reminder.
Every send goes through the server's guarded path (consent, opt-outs, 40/day, 3+ min gaps).
"""

import datetime, re, time
import reply_intent

YES = re.compile(r"(?i)^\W*(yes|yeah|yup|ok(?:ay|ies)?|sure|send|haan|han|ji|jee|g|theek|thik)\b")
CHECK_AFTER = 4 * 3600
GIVE_UP_AFTER = 24 * 3600


def ask_text(name, giki=False):
    where = "your class group" if giki else "your class and friends' groups"
    return (
        f"{name} Bhai,\n\nA family needs urgent help with a case we are handling."
        f" Could you please share it in {where}?\n\nYour one share may reach someone who can help."
        " It takes 30 seconds. 🤲\n\nShall I send you the poster?"
    )


def start_round(engine, volunteers, case_id, limit=1):
    """Send the first personal ask to at most `limit` volunteers not yet asked for this case."""
    flow = engine.s.setdefault("vol_flow", {})
    sent = 0
    for v in volunteers:
        phone = str(v.get("phone") or "")
        if not phone or (flow.get(phone) or {}).get("case") == case_id or sent >= limit:
            continue
        name = (str(v.get("name") or "").split() or ["Brother"])[0].capitalize()
        giki = "giki" in str(v.get("name", "")).lower() or "giki" in str(v.get("tags", "")).lower()
        if _send(engine, phone, ask_text(name, giki)):
            flow[phone] = {
                "step": "asked",
                "at": time.time(),
                "case": case_id,
                "seen": [],
                "name": name,
            }
            sent += 1
    return sent


def _send(engine, phone, text, poster=False):
    try:
        r = engine.h["send_custom"](
            {
                "target": "phone",
                "phone": phone,
                "message": text,
                "kind": "volunteer_flow",
                "poster": poster,
            }
        )
        return (r or {}).get("code", "SUCCESS") == "SUCCESS"
    except Exception as e:
        engine.log(f"Volunteer …{phone[-4:]}: not sent ({str(e)[:80]}).")
        return False


def tick(engine, now=None):
    """Read each active volunteer chat once and take at most one step per person."""
    now = now or time.time()
    for phone, st in list(engine.s.get("vol_flow", {}).items()):
        if st.get("step") in ("done", "stopped", "waiting_owner"):
            continue
        try:
            msgs = engine.h["messages"](phone + "@s.whatsapp.net") or []
        except Exception:
            continue
        new = [
            m
            for m in msgs
            if not m.get("is_from_me") and m.get("id") not in st["seen"] and _t(m) >= st["at"]
        ]
        if new:
            m = new[-1]
            st["seen"] = (st["seen"] + [x.get("id") for x in new])[-50:]
            react(engine, phone, st, str(m.get("content") or ""), m.get("media_type", ""))
        elif st["step"] == "poster" and not st.get("checked") and now - st["at"] > CHECK_AFTER:
            if _send(engine, phone, "Brother, are you done?"):
                st.update(checked=True, at=now)
        elif st.get("remind_at") and now >= st["remind_at"]:
            st.pop("remind_at")
            if _send(
                engine, phone, "Sorry to interrupt, brother. Could you share this one today? 🤲"
            ):
                st["at"] = now
        elif now - st["at"] > GIVE_UP_AFTER and (st.get("checked") or st["step"] == "asked"):
            st["step"] = "done"  # no reply: never chase further for this case


def react(engine, phone, st, text, media=""):
    tail = phone[-4:]
    label, why = reply_intent.classify(text, media, "share" if st["step"] == "poster" else "")
    if st["step"] == "asked" and label in ("ack", "other") and YES.match(text):
        if _send(engine, phone, engine.h["poster_caption"](), poster=True):
            st.update(step="poster", at=time.time())
        return
    if label == "other" and text.strip() and engine.h.get("ai_chat"):
        label, why = reply_intent.ai_classify(engine.h["ai_chat"], text, [("them", text)])
    jid = phone + "@s.whatsapp.net"
    if label in ("shared", "both", "donated"):
        if label in ("donated", "both"):
            engine.thank(phone)
        if label in ("shared", "both"):
            engine.share_thanks(phone, jid)
        st["step"] = "done"
        engine.log(f"Volunteer …{tail}: {label} ({why}).")
    elif label == "ack":
        pass
    elif label in ("later", "not_done") and not st.get("reminded"):
        st.update(reminded=True, remind_at=time.time() + 24 * 3600)
    elif label == "opt_out":
        engine.h["optout"](phone)
        st["step"] = "stopped"
    else:
        st["step"] = "waiting_owner"
        engine.notify(
            f"vol-{phone}-{int(time.time())}",
            f'Volunteer …{tail} replied: "{text[:120]}". Please answer.',
            0,
        )


def _t(m):
    try:
        return datetime.datetime.fromisoformat(
            str(m.get("timestamp", "")).replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return time.time()
