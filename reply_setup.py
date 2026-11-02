"""Owner-written auto replies for chats where someone sends a picture or says done/donated.

The owner writes the replies; the app only chooses which one to send. A reply never claims a
payment arrived (that stays a human-confirmed entry), and is sent at most once per message.
"""
import time

KEY = 'reply_setup'
MAX_REPLIES = 10


def clean(replies):
    if not isinstance(replies, list):
        raise ValueError('Replies must be a list.')
    out = []
    for item in replies:
        if not isinstance(item, str):
            raise ValueError('Each reply must be text.')
        item = item.strip()
        if not item:
            continue
        if len(item) > 1000:
            raise ValueError('Keep each reply under 1,000 characters.')
        if item not in out:
            out.append(item)
    if len(out) > MAX_REPLIES:
        raise ValueError(f'Use up to {MAX_REPLIES} replies.')
    return out


def get(store):
    data = store.get(KEY) if store else None
    data = data if isinstance(data, dict) else {}
    return {'enabled': bool(data.get('enabled')), 'replies': [r for r in data.get('replies', []) if isinstance(r, str)],
            'since': data.get('since', 0), 'next': int(data.get('next', 0) or 0)}


def save(store, enabled, replies):
    if not store:
        raise ValueError('Saving is unavailable right now. Nothing was changed.')
    replies = clean(replies)
    if enabled and not replies:
        raise ValueError('Write at least one reply before turning this on.')
    old = get(store)
    since = old['since'] if old['enabled'] and enabled else (time.time() if enabled else old['since'])
    data = {'enabled': bool(enabled), 'replies': replies, 'since': since, 'next': old['next'] % max(1, len(replies))}
    store.put(KEY, data)
    return data


def take(store):
    """The next reply, rotating through the owner's list (saved, so it survives restarts)."""
    data = get(store)
    if not data['enabled'] or not data['replies']:
        return None
    index = data['next'] % len(data['replies'])
    store.put(KEY, {**data, 'next': (index + 1) % len(data['replies'])})
    return data['replies'][index]
