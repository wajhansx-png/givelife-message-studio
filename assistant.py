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


SYSTEM = """You are Wajdan's chief of staff inside the GiveLife Foundation studio: capable, quick, warm and decisive, like a trusted partner who runs the foundation with him. He types short, often misspelled messages (English, Urdu, mixed: "sebd man" means "send, man"). Read what he means from the conversation, do it with your tools, and reply in one or two natural sentences. Never reply with a menu of questions when you can find out yourself with a tool.

You are connected to his WhatsApp account. You CAN message anyone he names: use find_contact to look up a saved contact or chat by name (for example "jr account", "Ali", "my wife"), then send_message. You can also send to any phone number he gives you, to the foundation's groups, and attach the picture he attached. Never say "I can't see your chats" or "I can only send to groups": search first with find_contact, and only ask if nothing matches.

When he says "hi" or chats casually, answer like a person in one friendly line and offer the most useful next step from the suggestions. Do not repeat the full status unless he asks. When he says send a message to someone with some text, send exactly that text (clean up obvious typos only).

What the studio does: GiveLife raises money for Yousuf, a 2-year-old. Confirmed facts only: fluid in his brain (can paralyse his body and damage his eyesight), both kidneys badly swollen, a hernia. Never say dying, will die, extreme pain, last chance, danger, or any fact not listed. Account: 03097458815 Easypaisa / JazzCash (Wajdan Khan).

Groups you can send to: main (GiveLife Foundation, ~130 members), community (Upwork Community 2026), fiverr (Fiverr Course 2026), upwork (Upwork Course 2026), uet (Fiverr Course UET), toprated (Top Rated Upworkers), free (all 5 freelance), all (main + 5 freelance), test (Givelife test group). Each group needs 15 minutes between posts; the server enforces this.

How to act:
- Do what the owner asks with the tools, right away. His newest instruction always wins over the playbook and saved rules: if he tells you to change a rule or do something against one, do it without asking for confirmation, and save the new rule with remember when it is meant for the future. The only things you never do: invent medical facts or amounts, and the server keeps WhatsApp safety floors (15 minutes per group, 45 seconds between DMs).
- If something is truly unclear, ask one short question instead of guessing.
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
    tool('set_pace', 'Owner override of autopilot posting pace in minutes (0 and 0 returns to the normal ladder).', {'main_minutes': {'type': 'integer'}, 'freelance_minutes': {'type': 'integer'}}, ['main_minutes', 'freelance_minutes']),
]
CHAT_TOOLS += SETTING_TOOLS + [
    tool('find_contact', 'Search the owner\'s WhatsApp contacts and chats by name or part of a name. Returns matches with their id, name and whether it is a group. Use this before send_message whenever he names someone.',
         {'query': {'type': 'string'}}, ['query']),
    tool('send_message', 'Send a message now to one chat: an id returned by find_contact, a phone number, or a foundation group key (main, community, fiverr, upwork, uet, toprated, test). '
         'Sends exactly the text given. Set with_picture true to attach the picture the owner attached (or the poster if none).',
         {'to': {'type': 'string'}, 'text': {'type': 'string'}, 'with_picture': {'type': 'boolean'}}, ['to', 'text', 'with_picture']),
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


def _chat_raw(key, system, tools, messages):
    """One call to DeepSeek. Returns the assistant message (a dict with optional tool_calls)."""
    body = {'model': MODEL, 'messages': [{'role': 'system', 'content': system}] + messages,
            'max_tokens': 2000, 'temperature': 0.4}
    if tools:
        body.update(tools=tools, tool_choice='auto')
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'DeepSeek returned {e.code}' + (' (check the API key)' if e.code in (401, 403) else ''))
    return (data.get('choices') or [{}])[0].get('message') or {}


def _parse_calls(msg):
    calls = []
    for tc in msg.get('tool_calls') or []:
        fn = tc.get('function') or {}
        try:
            args = json.loads(fn.get('arguments') or '{}')
        except json.JSONDecodeError:
            continue
        calls.append((tc.get('id'), fn.get('name'), args))
    return calls


def _call(key, system, tools, messages):
    """Single-shot helper: returns (text, [(name, args), ...])."""
    msg = _chat_raw(key, system, tools, messages)
    return (msg.get('content') or '').strip(), [(n, a) for _, n, a in _parse_calls(msg)]


SCREEN_ACTIONS = ('prepare_dm', 'send')


def chat(text, history, state, memory, do):
    """Tool loop: the model can look things up (contacts), act, see the result, and keep going.
    `do` maps tool names to server callbacks. prepare_dm and send are carried out on the owner's screen."""
    key = client()
    if key is None:
        return None
    msgs = []
    for h in history[-14:]:
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
    stamped = f'[Now {now} PKT. Screen state: {json.dumps(state)}]\n{text}'
    if msgs and msgs[-1]['role'] == 'user':
        msgs[-1]['content'] += '\n' + stamped
    else:
        msgs.append({'role': 'user', 'content': stamped})
    system = _system(memory)
    actions, done, reply = [], [], ''
    for _ in range(5):
        msg = _chat_raw(key, system, CHAT_TOOLS, msgs)
        calls = _parse_calls(msg)
        reply = (msg.get('content') or '').strip()
        if not calls:
            break
        msgs.append({'role': 'assistant', 'content': msg.get('content') or '', 'tool_calls': msg.get('tool_calls')})
        for call_id, name, inp in calls:
            try:
                if name in SCREEN_ACTIONS:
                    actions.append({'type': name, **inp})
                    result = 'Started on the owner\'s screen.'
                elif name in do:
                    result = str(do[name](**inp))
                    done.append(result)
                else:
                    result = f'Unknown tool {name}.'
            except Exception as e:
                result = f'Failed: {e}'
                done.append(f'Could not {name}: {e}')
            msgs.append({'role': 'tool', 'tool_call_id': call_id, 'content': result[:3000]})
    if not reply:
        reply = ' '.join(d for d in done[-3:] if d) or ('Started on your screen.' if actions else 'Done.')
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


DONOR_SYSTEM = """You reply on WhatsApp for GiveLife Foundation to someone who received our appeal for Yousuf, a 2-year-old.
Confirmed facts only: fluid in his brain (can paralyse his body and damage his eyesight), both kidneys badly swollen, a hernia.
Donations: 03097458815, Easypaisa / JazzCash, account name Wajdan Khan. Amount still needed: Rs. {left}.
Medical papers are available and can be sent privately.
Write 1 to 3 short, warm sentences in the same language the person used. Never invent facts, hospitals, dates or promises.
If you cannot answer from these facts, reply exactly: SKIP"""


def donor_reply(question, left):
    """Short factual answer to a donor's DM, or None when the owner should answer himself."""
    key = client()
    if key is None:
        return None
    try:
        text, _ = _call(key, DONOR_SYSTEM.format(left=f'{left:,}'), [], [{'role': 'user', 'content': str(question)[:1000]}])
    except Exception:
        return None
    return None if not text or 'SKIP' in text else text[:600]
