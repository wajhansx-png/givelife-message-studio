"""In-app assistant and autopilot for the GiveLife studio (DeepSeek API)."""
import os, json, time, datetime, threading, urllib.request, urllib.error
from pathlib import Path

MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
API_URL = os.environ.get('DEEPSEEK_URL', 'https://api.deepseek.com/chat/completions')
ROOT = Path(__file__).resolve().parent
PKT = datetime.timezone(datetime.timedelta(hours=5))
GROUP_KEYS = ['main', 'community', 'fiverr', 'upwork', 'uet', 'toprated', 'free', 'all', 'test']


def client():
    """Returns the API key when the assistant is configured, else None."""
    return os.environ.get('DEEPSEEK_API_KEY') or None


def playbook():
    f = ROOT / 'playbook.md'
    return f.read_text(encoding='utf-8') if f.exists() else ''


SYSTEM = """You are the assistant inside the GiveLife Foundation message studio. The owner, Wajdan, types short instructions (often in a hurry, mixed English/Urdu). You act on them with tools and reply in one or two short, plain sentences.

What the studio does: GiveLife raises money for Yousuf, a 2-year-old. Confirmed facts only: fluid in his brain (can paralyse his body and damage his eyesight), both kidneys badly swollen, a hernia. Never say dying, will die, extreme pain, last chance, danger, or any fact not listed. Account: 03097458815 Easypaisa / JazzCash (Wajdan Khan).

Groups you can send to: main (GiveLife Foundation, ~130 members), community (Upwork Community 2026), fiverr (Fiverr Course 2026), upwork (Upwork Course 2026), uet (Fiverr Course UET), toprated (Top Rated Upworkers), free (all 5 freelance), all (main + 5 freelance), test (Givelife test group). Each group needs 15 minutes between posts; the server enforces this.

How to act:
- Do what the owner asks with the tools. If something is unclear, ask one short question instead of guessing.
- Amounts: "34k left" means set_left 34000. "came 2000" means money_came 2000. Never invent an amount.
- When money comes, never celebrate; the owner wants urgency kept.
- Messages: never add begging closing lines ("Please send now", "Please help if you can"). Keep the owner's format and icons.
- If the owner states a preference or rule for the future ("always...", "never...", "from now on..."), save it with remember.
- Sending to groups or people only happens when the owner asks, or in autopilot.

How the owner decides (act the same way):
- Donations slow 40+ min: fresh wording, post more often (main every 15 min), all groups. 90+ min: also DM donor contacts in small batches with the poster, Name Brother/Sister, different words for each person.
- Several posts and no money: ask the family for a new photo or update. Poster must show the current amount.
- "Done" or a payment screenshot in a group: tell the owner to check Easypaisa; never change the amount yourself.
- "Real? / papers? / proof?": answer that medical papers are available privately, and tell the owner.
- A complaint in a freelance group: stop posting there.
- Any WhatsApp warning or failed send: stop sending and tell the owner.
- Stay short. One or two sentences. Do the thing instead of describing it.
- The screen state includes "suggestions" (what the engine thinks should happen next). If the owner asks "what now?", answer from them and offer to do it.

Examples:
Owner: "post in fiverr" -> call send(target="fiverr"), reply "Posting to Fiverr Course now."
Owner: "35k" -> call set_left(35000), reply "Rs. 35,000 left. Messages updated."
Owner: "donations slow, do something" -> call new_wording(kind="group") and send(target="all"), reply "Fresh message going to all 6 groups (3-second cancel on screen)."
Owner: "never post in UET at night" -> call remember(...) and set_quiet_hours if it fits, reply "Saved. No UET posts at night."
Owner: "stop fiverr for today" -> call pause_group(key="fiverr", hours=12), reply "Fiverr paused for 12 hours."

The owner's playbook and saved rules follow. Treat them as the owner's standing instructions.
"""


def tool(name, desc, props, required):
    return {'type': 'function', 'function': {'name': name, 'description': desc,
            'parameters': {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}}


CHAT_TOOLS = [
    tool('set_left', 'Set the amount still needed (Rs.). Updates both messages.', {'left': {'type': 'integer'}}, ['left']),
    tool('money_came', 'Money arrived; subtract it from the amount left.', {'amount': {'type': 'integer'}}, ['amount']),
    tool('new_wording', 'Make fresh wording for the group or DM message.', {'kind': {'type': 'string', 'enum': ['group', 'dm']}}, ['kind']),
    tool('set_message', 'Replace the group or DM message with exact text the owner gave.', {'kind': {'type': 'string', 'enum': ['group', 'dm']}, 'text': {'type': 'string'}}, ['kind', 'text']),
    tool('prepare_dm', 'Fill the DM form for one person. Name may be empty. The owner then taps Send.', {'phone': {'type': 'string'}, 'name': {'type': 'string'}, 'gender': {'type': 'string', 'enum': ['Brother', 'Sister']}}, ['phone', 'name', 'gender']),
    tool('send', 'Send the current group message (with poster) to a group target. The screen shows a 3-second cancel for "all".', {'target': {'type': 'string', 'enum': GROUP_KEYS}}, ['target']),
    tool('remember', 'Save a rule or preference the owner wants followed from now on.', {'rule': {'type': 'string'}}, ['rule']),
    tool('autopilot', 'Turn autopilot on or off.', {'on': {'type': 'boolean'}}, ['on']),
]
GROUP_ONLY = {'type': 'string', 'enum': ['main', 'community', 'fiverr', 'upwork', 'uet', 'toprated']}
SETTING_TOOLS = [
    tool('pause_group', 'Stop autopilot posting in one group for some hours.', {'key': GROUP_ONLY, 'hours': {'type': 'number'}}, ['key', 'hours']),
    tool('resume_group', 'Let autopilot post in a paused group again.', {'key': GROUP_ONLY}, ['key']),
    tool('set_quiet_hours', 'Hours (0-23, Pakistan time) when autopilot sends nothing. Same start and end turns quiet hours off.', {'start': {'type': 'integer'}, 'end': {'type': 'integer'}}, ['start', 'end']),
    tool('set_dms', 'Turn autopilot DMs to donor contacts on or off, with a daily maximum.', {'enabled': {'type': 'boolean'}, 'daily': {'type': 'integer'}}, ['enabled', 'daily']),
]
CHAT_TOOLS += SETTING_TOOLS + [
    tool('dm_list', 'Send the DM (poster or the attached picture, plus caption) to a list of people, one by one with a gap. '
         'Use when the owner gives numbers. Name: first name if it is a real name, otherwise empty (greeting becomes Brother). '
         'Gender Sister only for clearly female names or when he says sister.',
         {'people': {'type': 'array', 'items': {'type': 'object', 'properties': {'phone': {'type': 'string'}, 'name': {'type': 'string'}, 'gender': {'type': 'string', 'enum': ['Brother', 'Sister']}}, 'required': ['phone', 'name', 'gender'], 'additionalProperties': False}},
          'gap_minutes': {'type': 'number'}, 'vary': {'type': 'boolean'}, 'start_after_minutes': {'type': 'number'}},
         ['people', 'gap_minutes', 'vary', 'start_after_minutes']),
]
AUTO_TOOLS = SETTING_TOOLS + [
    tool('notify_owner', 'Send the owner a short WhatsApp note when he must act or decide.', {'text': {'type': 'string'}}, ['text']),
    tool('nothing', 'No change is needed.', {'reason': {'type': 'string'}}, ['reason']),
]


def _system(memory):
    rules = '\n'.join(f'- {m["rule"]}' for m in memory) or '- (none yet)'
    return SYSTEM + '\n\nPLAYBOOK:\n' + playbook() + '\n\nSAVED RULES FROM THE OWNER:\n' + rules


def _call(key, system, tools, messages):
    body = {'model': MODEL, 'messages': [{'role': 'system', 'content': system}] + messages,
            'tools': tools, 'tool_choice': 'auto', 'max_tokens': 2000, 'temperature': 0.3}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'DeepSeek returned {e.code}' + (' (check the API key)' if e.code in (401, 403) else ''))
    msg = (data.get('choices') or [{}])[0].get('message') or {}
    calls = []
    for tc in msg.get('tool_calls') or []:
        fn = tc.get('function') or {}
        try:
            args = json.loads(fn.get('arguments') or '{}')
        except json.JSONDecodeError:
            continue
        calls.append((fn.get('name'), args))
    return (msg.get('content') or '').strip(), calls


def chat(text, history, state, memory, do):
    """do: dict of server callbacks. Returns reply text, client actions and changes."""
    c = client()
    if c is None:
        return None
    msgs = []
    for h in history[-12:]:
        role = 'user' if h.get('who') == 'you' else 'assistant'
        t = str(h.get('text', ''))[:2000]
        if not t:
            continue
        if msgs and msgs[-1]['role'] == role:
            msgs[-1]['content'] += '\n' + t
        else:
            msgs.append({'role': role, 'content': t})
    while msgs and msgs[0]['role'] != 'user':
        msgs.pop(0)
    now = datetime.datetime.now(PKT).strftime('%Y-%m-%d %H:%M')
    msgs.append({'role': 'user', 'content': f'[Now {now} PKT. Screen state: {json.dumps(state)}]\n{text}'})
    if len(msgs) > 1 and msgs[-2]['role'] == 'user':
        msgs[-2:] = [{'role': 'user', 'content': msgs[-2]['content'] + '\n' + msgs[-1]['content']}]
    reply, calls = _call(c, _system(memory), CHAT_TOOLS, msgs)
    actions, done = [], []
    for name, inp in calls:
        try:
            if name in do:
                done.append(do[name](**inp))
            elif name in ('prepare_dm', 'send'):
                actions.append({'type': name, **inp})
        except Exception as e:
            done.append(f'Could not {name}: {e}')
    if not reply:
        reply = ' '.join(d for d in done if d) or ('Ready on your screen.' if actions else 'Done.')
    return {'reply': reply, 'actions': actions, 'done': done}


class Autopilot:
    """AI advisor: every 30 minutes, while on, turns the owner's saved rules into engine settings.
    The engine (autopilot.py) does the posting itself; this only adjusts it."""

    def __init__(self, state_fn, memory_fn, do_fn, log_fn, enabled_fn):
        self.state_fn, self.memory_fn, self.do_fn, self.log_fn, self.enabled_fn = state_fn, memory_fn, do_fn, log_fn, enabled_fn
        self.last = 0

    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            time.sleep(60)
            try:
                if self.enabled_fn() and time.time() - self.last >= 1800:
                    self.last = time.time()
                    self.step()
            except Exception as e:
                self.log_fn(f'Autopilot error: {str(e)[:120]}')

    def step(self):
        key = client()
        if key is None:
            return  # without the AI, the engine follows the fixed playbook only
        state = self.state_fn()
        now = datetime.datetime.now(PKT).strftime('%Y-%m-%d %H:%M')
        prompt = (f'[Autopilot review at {now} PKT]\nState: {json.dumps(state)}\n'
                  'The engine posts on its own using the escalation ladder. Check that its settings (paused groups, quiet hours, '
                  'DMs) follow the playbook and the owner\'s saved rules, and change them only if a rule requires it. '
                  'Use notify_owner only for something he must do. If nothing needs changing, call nothing.')
        reply, calls = _call(key, _system(self.memory_fn()), AUTO_TOOLS, [{'role': 'user', 'content': prompt}])
        do = self.do_fn()
        for name, inp in calls[:3]:
            if name in do:
                self.log_fn('Autopilot rule check: ' + str(do[name](**inp)))
