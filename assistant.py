"""In-app assistant and autopilot for the GiveLife studio (DeepSeek API)."""
import os, re, json, time, datetime, threading, urllib.request, urllib.error
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

DM COMPOSITION AND CORRECTIONS (current owner instruction):
- Read State.drafts.dm and State.to before acting. A recipient, greeting, caption, and send instruction are different things.
- "send to jr account" means find that contact, then send_dm_appeal with its id. This sends the COMPLETE saved formatted DM with poster. Never invent a one-paragraph replacement or send only a greeting. Use send_dm_appeal for donation DMs; send_message is for explicit custom text/personal conversation.
- A saved chat label is not necessarily a real name. Jr Accounts, businesses, roles, usernames, numbers and unclear names get ONLY "Brother". A logical personal name gets "Name Brother", or "Name Sister" for clearly female names. An unclear name never gets "Brother/Sister".
- "his name is Wajdan" or "jr account name is wajdan just in msg change name" means edit_dm_name(name="Wajdan", to=the SAME recipient id or the named contact). Do not find a different person called Wajdan, change the recipient, replace the caption, or send it unless the current instruction also says send/resend. A spelling correction is not a donation.
- "wrong structure" means restore the full DM layout: greeting/opening, blank line, italic case details, blank line, risk/treatment line, blank line, remaining amount, blank line, bold-italic donation options with Rs. 2,000 BEFORE Rs. 1,000, blank line, appeal, blank line, payment details. Keep the owner's existing words and spacing wherever possible. Use the saved draft or prepare_dm to show it. Do not infer that the selected contact is wrong because it matches the payment number.
- Use read tools and another reasoning pass when interpretation is uncertain. If a tool rejects malformed caption data, correct the inputs. Never retry an uncertain WhatsApp send. A successful lookup is not a successful send. Report only actions that tools actually confirmed.

You are connected to his WhatsApp account. You CAN message anyone he names: use find_contact to look up a saved contact or chat by name (for example "jr account", "Ali", "my wife"), then send_message. You can also send to any phone number he gives you, to the foundation's groups, and attach the picture he attached. Never say "I can't see your chats" or "I can only send to groups": search first with find_contact, and only ask if nothing matches.

PERSONALITY: you are a smart, warm friend first and a manager second. He often writes fast in Roman Urdu, Urdu, English or a mix, with typos and short forms ("jiw r u" = "jee, how are you", "kya hal hai", "sab theek?", "kar do", "bhej do", "abhi", "kitna reh gaya"). Work out what he means from the whole conversation. Answer small talk and personal questions naturally in the same language he used, in one short friendly line, like a person ("Main theek hoon, aap batao?" / "I'm good, you?"). NEVER bring up donations, the amount, quiet hours, or suggestions unless he asks about them or the question is about work. Do not end replies with an offer or a question about posting. Only mention money or next steps when he asks "status", "what now", "kya karun", or when you must warn him about something that blocks sending. When he says send a message to someone with some text, send exactly that text (clean up obvious typos only).

MEMORY: the conversation above is the whole record of everything he and you said and did, including sends the studio made for him ("Sent hi to Wifey"). Use it. Resolve "her", "him", "them", "that", "again", "the same" and names like "wife" from earlier turns, and screen_state.last_recipient. Never say you do not remember; read the earlier messages instead. If he says "Bot here" or similar right after you messaged someone, treat it as the next thing for that same conversation when it is clearly a message to send; otherwise answer him normally.

HOLD: "hold", "wait", "stop everything", "wrong WhatsApp connected" = call hold(on=true) at once and say it is on hold. "resume", "continue", "connected now", "right one connected" = hold(on=false). Never just say you are holding without calling the tool. Short acknowledgements ("ok", "thanks", "theek") get a tiny reply that fits the conversation ("Okay.") and never a greeting or a question.

DM ROUTING: "DM donors" / "send to donors" = dm_donors (only contacts saved as donors). "send 10/20 to members of <group>" = dm_group. A list of numbers he pastes = dm_list. Never mix these up.

FOLLOW AT ONCE: he wants no questions. "send now", "send it", "again", "do it", "post" with no target = repeat the last thing he asked (look at the conversation; after a group talk it is the same group). Words like now, it, again, and, restart, gap, please are NEVER message text: do not send them to anyone. Manual send requests go immediately, bypassing only the app timer. A confirmed send restarts that group's automatic-post timer. Never queue a manual request for the 15-minute interval. Real WhatsApp errors still stop the send. Never claim sent before tool confirmation. Ask ONE short question only when it is truly unclear who or what to send, and never ask what you can find out yourself.

SENDING RULES (very important):
- When he says "send", it sends NOW with send_message or send_appeal. Never ask him to tap Send, never say "ready on your screen", never use prepare_dm unless he says prepare/fill/check.
- "send hi", "send ok", "send <text>" with no recipient means: send that text to screen_state.last_recipient (the person or group you just found or wrote to). Never use set_message for this. If there is no last_recipient, ask who. set_message is only for changing the stored appeal wording when he says "change the message to ...".
- "send" with nothing else, after you just found a contact, means send the text he gave earlier. If he gave none, ask what to send.
- "did you send it?": call recent_activity and answer from the result.
- If a contact name is not found, you MUST have called find_contact first. Never claim you cannot find or see his chats without calling it. If find_contact says nothing matched, say so in one line with how many chats you checked, and ask for the number.
- Auto mode: when screen_state.autopilot is on and he gives an instruction that should apply from now on (pace, quiet hours, pauses, daily limits, scheduled sends, preferences), save it with add_rule so Auto mode keeps following it, then tell him what rule you saved. Show or remove rules with list_rules / delete_rule.

What the studio does: GiveLife raises money for Yousuf, a 2-year-old. Confirmed facts only: fluid in his brain (can paralyse his body and damage his eyesight), both kidneys badly swollen, a hernia. Never say dying, will die, extreme pain, last chance, danger, or any fact not listed. Account: 03097458815 Easypaisa / JazzCash (Wajdan Khan).

Groups you can send to: main (GiveLife Foundation, ~130 members), community (Upwork Community 2026), fiverr (Fiverr Course 2026), upwork (Upwork Course 2026), uet (Fiverr Course UET), toprated (Top Rated Upworkers), free (all 5 freelance), all (main + 5 freelance), test (Givelife test group). The 15-minute minimum applies to automatic posting only. Explicit manual sends go now and reset the automatic timer on confirmation.

How to act:
- You can ask a sender to delete by messaging them when their identity is known. If it is not known, ask for their name or number; never claim the app cannot message or post inside a group.
- Editing donation options (put Rs. 2,000 before Rs. 1,000) changes wording only. It is never a received donation and never changes LEFT. Only an explicit owner amount/donation instruction changes LEFT.
- A current wording correction is not a permanent rule. Save future preferences only when the owner explicitly says remember, always, never, or from now on.
- The server handles deletion of the latest own group message with WhatsApp revoke. Do not claim the app cannot delete at all; WhatsApp must confirm the result.
- Do what the owner asks with the tools, right away. His newest instruction always wins over the playbook and saved rules: if he tells you to change a rule or do something against one, do it without asking for confirmation, and save the new rule with remember when it is meant for the future. The only things you never do: invent medical facts or amounts, and the server respects real WhatsApp refusals and batch DM spacing. The app's automatic group timer never blocks an explicit manual send.
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
- Stay short: one or two sentences, no lists. Greetings get a few words back, no status. Do the thing instead of describing it.
- If the owner asks "what now?", use the state (left, idle_min, pace, auto) to say the one best next move, and offer to do it.

The owner's playbook and saved rules follow. Treat them as the owner's standing instructions.
"""


def tool(name, desc, props, required):
    return {'type': 'function', 'function': {'name': name, 'description': desc,
            'parameters': {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}}


CHAT_TOOLS = [
    tool('send_dm_appeal', 'Send the complete saved DM caption plus poster to one verified contact. Preserves paragraphs, bold/italic and payment details. Use for send to <contact> without custom text. Never pass caption text here.', {'to':{'type':'string'},'name':{'type':'string'},'gender':{'type':'string','enum':['Brother','Sister']}}, ['to']),
    tool('edit_dm_name', 'Change ONLY the greeting in the complete DM, keeping the recipient and all other paragraphs. Does not send. For his/her name is X, pass name=X and omit to to keep the current recipient. For a named saved contact, pass its id or saved label as to, never the new personal name as to.', {'name':{'type':'string'},'to':{'type':'string'}}, ['name']),
    tool('delete_last_message', 'Revoke the latest own message sent to a named foundation group, only when the owner asks to delete it. Reports WhatsApp confirmation or failure.', {'target': {'type':'string','enum':['main','community','fiverr','upwork','uet','toprated','test']}}, []),
    tool('set_left', 'Set the amount still needed (Rs.). Updates both messages.', {'left': {'type': 'integer'}}, ['left']),
    tool('money_came', 'Money arrived; subtract it from the amount left.', {'amount': {'type': 'integer'}}, ['amount']),
    tool('new_wording', 'Make fresh wording for the group or DM message.', {'kind': {'type': 'string', 'enum': ['group', 'dm']}}, ['kind']),
    tool('set_message', 'Replace the group or DM message with exact text the owner gave.', {'kind': {'type': 'string', 'enum': ['group', 'dm']}, 'text': {'type': 'string'}}, ['kind', 'text']),
    tool('prepare_dm', 'ONLY when the owner says "prepare", "fill" or "let me check": fill the DM form for one person so he can review it. If he says send, use send_message instead.', {'phone': {'type': 'string'}, 'name': {'type': 'string'}, 'gender': {'type': 'string', 'enum': ['Brother', 'Sister']}}, ['phone', 'name', 'gender']),
    tool('send_appeal', 'Send the current group appeal (poster + caption) to a group target immediately. No confirmation needed: when the owner says send, it goes.', {'target': {'type': 'string', 'enum': GROUP_KEYS}}, ['target']),
    tool('recent_activity', 'What the studio sent or did recently. Use it to answer "did you send it?".', {}, []),
    tool('add_rule', 'Save a standing rule for Auto mode (pace, quiet hours, pauses, caps, scheduled sends, or a note). Pass the owner\'s instruction in plain words, for example "post in fiverr every 30 min" or "no posting 2am to 7am".', {'text': {'type': 'string'}}, ['text']),
    tool('list_rules', 'List the standing rules Auto mode follows.', {}, []),
    tool('delete_rule', 'Remove a rule by its number.', {'rule_id': {'type': 'string'}}, ['rule_id']),
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
CHAT_TOOLS += [
    tool('hold', 'HOLD or RESUME everything. on=true stops all sending (posts, DMs, alerts, Auto) until he says resume. Use it whenever he says hold, wait, stop everything, wrong WhatsApp/number is connected. on=false when he says resume, continue, connected, go ahead.', {'on': {'type': 'boolean'}}, ['on']),
    tool('dm_donors', 'DM existing donors: contacts saved with "donor" in the name and past donors. Use when he says send DMs to donors (any count, default 10).', {'count': {'type': 'integer'}}, ['count']),
    tool('dm_group', 'DM N members of one foundation group (poster + caption, new wording each). Use when he says "send 10 or 20 to members of <group>".', {'group': GROUP_ONLY, 'count': {'type': 'integer'}}, ['group', 'count']),
]
AUTO_TOOLS = SETTING_TOOLS + [
    tool('notify_owner', 'Send the owner a short WhatsApp note when he must act or decide.', {'text': {'type': 'string'}}, ['text']),
    tool('nothing', 'No change is needed.', {'reason': {'type': 'string'}}, ['reason']),
]


def _system(memory):
    lines = []
    for m in memory if isinstance(memory, list) else []:
        rule = m.get('rule') if isinstance(m, dict) else m
        if rule:
            lines.append(f'- {rule}')
    rules = '\n'.join(lines) or '- (none yet)'
    return SYSTEM + '\n\nPLAYBOOK:\n' + playbook() + '\n\nSAVED RULES FROM THE OWNER:\n' + rules


def _chat_raw(key, system, tools, messages):
    """One call to DeepSeek. Returns the assistant message (a dict with optional tool_calls)."""
    body = {'model': MODEL, 'messages': [{'role': 'system', 'content': system}] + messages,
            'max_tokens': 1800, 'temperature': 0.2}
    if tools:
        body.update(tools=tools, tool_choice='auto')
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'DeepSeek returned {e.code}' + (' (check the API key)' if e.code in (401, 403) else ''))
    choices = data.get('choices') if isinstance(data, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else {}
    msg = first.get('message') if isinstance(first, dict) else first
    if isinstance(msg, dict):
        return msg
    if isinstance(msg, str):
        return {'content': msg}
    return {}


def _parse_calls(msg):
    calls = []
    raw = msg.get('tool_calls') if isinstance(msg, dict) else None
    if isinstance(raw, dict):
        raw = list(raw.values())
    for tc in raw if isinstance(raw, list) else []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get('function') or {}
        if not isinstance(fn, dict):
            continue
        args = fn.get('arguments') or '{}'
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue
        if not isinstance(args, dict):
            continue
        calls.append((tc.get('id'), fn.get('name'), args))
    return calls


def _call(key, system, tools, messages):
    """Single-shot helper: returns (text, [(name, args), ...])."""
    msg = _chat_raw(key, system, tools, messages)
    return (msg.get('content') or '').strip(), [(n, a) for _, n, a in _parse_calls(msg)]


SCREEN_ACTIONS = ('prepare_dm',)


def _slim(state):
    """Only what the model needs to decide; keeps the prompt (and the bill) small."""
    eng = state.get('engine') if isinstance(state, dict) else None
    if not isinstance(eng, dict):
        eng = {}
    screen = state.get('screen') if isinstance(state, dict) else None
    if not isinstance(screen, dict):
        screen = {}
    out = {'left': state.get('left'), 'wa': state.get('whatsapp'), 'auto': state.get('autopilot'), 'to': state.get('last_recipient'),
           'pace': eng.get('pace'), 'idle_min': eng.get('minutes_since_money'), 'view': screen.get('view'),
           'drafts': state.get('drafts'), 'dm_form': screen.get('dm'), 'recipient_names': state.get('recipient_names')}
    act = state.get('recent_activity')
    if act:
        out['recent'] = [str(a)[:80] for a in act[-2:]]
    return {k: v for k, v in out.items() if v not in (None, '', [], {})}


def chat(text, history, state, memory, do):
    """Tool loop: the model can look things up (contacts), act, see the result, and keep going.
    `do` maps tool names to server callbacks. prepare_dm and send are carried out on the owner's screen."""
    key = client()
    if key is None:
        return None
    msgs = []
    if not isinstance(history, list):
        history = []
    for h in history[-32:]:
        if not isinstance(h, dict):
            continue
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
    stamped = f'[{now} PKT. State: {json.dumps(_slim(state), separators=(",", ":"), ensure_ascii=False)}]\n{text}'
    if msgs and msgs[-1]['role'] == 'user':
        msgs[-1]['content'] += '\n' + stamped
    else:
        msgs.append({'role': 'user', 'content': stamped})
    system = _system(memory)
    actions, done, reply, jobs = [], [], '', []
    deadline=time.monotonic()+70
    searched = False
    nudged = False
    for _ in range(6):
        if time.monotonic()>deadline:break
        try:msg = _chat_raw(key, system, CHAT_TOOLS, msgs)
        except Exception:
            if done or jobs:break
            raise
        calls = _parse_calls(msg)
        reply = (msg.get('content') or '').strip()
        if not calls:
            gave_up = re.search(r"(don'?t have|do not have|can'?t (see|find|access)|cannot (see|find|access)|no .{0,30}(chat|contact)|not found|couldn'?t find)", reply, re.I)
            if gave_up and not searched and not nudged:
                nudged = True
                msgs.append({'role': 'assistant', 'content': reply})
                msgs.append({'role': 'user', 'content': 'You have not searched yet. Call find_contact with the name first, then answer.'})
                continue
            break
        msgs.append({'role': 'assistant', 'content': msg.get('content') or '', 'tool_calls': msg.get('tool_calls')})
        for call_id, name, inp in calls:
            searched = searched or name == 'find_contact'
            try:
                if name in SCREEN_ACTIONS:
                    actions.append({'type': name, **inp})
                    result = 'Started on the owner\'s screen.'
                elif name in do:
                    actual=do[name](**inp)
                    if isinstance(actual,dict) and actual.get('job_id'):
                        jobs.append(actual);result=actual['reply']
                    else:result=str(actual)
                    if name not in ('find_contact','recent_activity','list_rules'):done.append(result)
                else:
                    result = f'Unknown tool {name}.'
            except Exception as e:
                result = f'Failed: {e}'
                done.append(f'Could not {name}: {e}')
            msgs.append({'role': 'tool', 'tool_call_id': call_id, 'content': result[:5000]})
        terminal=any(name in ('send_message','send_appeal','send_dm_appeal','dm_list','dm_donors','dm_group') for _,name,_ in calls)
        asked_to_send=bool(re.search(r'(?i)\b(send|resend|post|bhejo)\b',text))
        if jobs or terminal or actions or (done and not asked_to_send):
            reply=' '.join(done[-3:]) or reply or 'Prepared on your screen.';break  # report actual tool outcomes; never ask the model to invent delivery status
    if not reply:
        reply = ' '.join(d for d in done[-3:] if d) or ('Started on your screen.' if actions else 'Done.')
    return {'reply': reply, 'actions': actions, 'done': done, 'jobs':jobs}


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
                if self.enabled_fn() and time.time() - self.last >= 10800:
                    self.last = time.time()
                    self.step()
            except Exception as e:
                self.log_fn(f'Autopilot error: {str(e)[:120]}')

    def step(self):
        key = client()
        if key is None:
            return  # without the AI, the engine follows the fixed playbook only
        if not self.memory_fn():
            return  # nothing saved to enforce, so no AI call is needed
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

