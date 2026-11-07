"""One small door to DeepSeek for structured jobs: JSON only, cached, counted, never any send tools."""

import hashlib, json, re, threading, time
import assistant

_CACHE, _LOCK = {}, threading.Lock()
COUNT = {"day": "", "calls": 0}
SYSTEM = (
    "You are a careful classifier and reviewer. Reply with one JSON object only. Never add facts."
)


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5 * 3600))


def chat(prompt, max_tokens=800):
    """Raw text from the model, or '' when AI is not connected. Same prompt is answered from cache."""
    key = hashlib.sha256(prompt.encode()).hexdigest()
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    api = assistant.client()
    if api is None:
        return ""
    msg = assistant._chat_raw(
        api,
        SYSTEM,
        [],
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        thinking_mode=False,
    )
    text = msg.get("content", "") if isinstance(msg, dict) else ""
    with _LOCK:
        if COUNT["day"] != _today():
            COUNT.update(day=_today(), calls=0)
        COUNT["calls"] += 1
        if text:  # an empty answer is a failure, never remembered as the answer
            _CACHE[key] = text
            if len(_CACHE) > 500:
                _CACHE.pop(next(iter(_CACHE)))
    return text


def json_of(raw):
    """Parse a JSON object from model text; None when invalid."""
    raw = re.sub(r"^```(?:json)?|```$", "", str(raw or "").strip()).strip()
    try:
        data = json.loads(raw, strict=False)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0), strict=False) if m else None
        except Exception:
            data = None
    return data if isinstance(data, dict) else None
