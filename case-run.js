/* One page to run the whole case (/new only). Everything it shows comes from /case-run, which drives the existing
   engines; every other tool (Donors, Messages, Notes, Reports, Settings) is the existing one, opened from Tools. */
(() => {
  const $ = (id) => document.getElementById(id);
  const make = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const btn = (text, cls, fn) => {
    const b = make('button', cls, text);
    b.type = 'button';
    if (fn) b.onclick = fn;
    return b;
  };
  const GEAR =
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
  const rs = (n) => 'Rs. ' + Number(n || 0).toLocaleString('en-PK');
  const clock = (sec) =>
    sec ? new Date(sec * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—';
  const STATUS = {
    idle: 'Not started',
    running: 'Running',
    paused: 'Paused',
    finished: 'Finished',
  };
  const STATE = {
    idle: 'Not started',
    queued: 'Waiting',
    running: 'Running',
    paused: 'Paused',
    done: 'Done',
    stopped: 'Stopped',
    off: 'Off',
  };
  const GIKI = {
    waiting: 'Waiting',
    agreed: 'Agreed',
    shared: 'Share messages sent',
    needs: 'Needs you',
    declined: 'Not agreed',
    uncertain: 'Check WhatsApp',
    cancelled: 'Cancelled',
  };
  const FIELDS = {
    // [field, label, lowest, highest, step of the − / + buttons]
    group: [['every_minutes', 'Minutes between posts', 15, 1440, 15]],
    dm: [
      ['gap_minutes', 'Minutes between DMs', 1, 10, 1],
      ['batch_size', 'DMs per batch', 1, 20, 1],
      ['rest_minutes', 'Rest between batches', 1, 120, 5],
    ],
  };

  let data = null,
    sig = '',
    timer = 0,
    busy = false;

  /* ---------------------------------------------------------------- server */
  async function post(body) {
    const r = await fetch('/case-run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(d.error || 'That did not work. Nothing was changed.');
    return d;
  }
  async function load() {
    try {
      const r = await fetch('/case-run');
      if (!r.ok) throw Error();
      data = await r.json();
      say('');
    } catch (e) {
      say('The case page is unavailable right now. Nothing was changed.');
    }
    paint();
    return data;
  }
  const take = (d) => {
    if (d && d.rows) {
      data = d;
      paint();
    } else load();
  };

  /* ---------------------------------------------------------------- shell */
  const page = make('dialog', 'case-page');
  page.id = 'casePage';
  page.setAttribute('aria-label', 'Case');
  page.innerHTML =
    '<div class="cr-shell"><header class="cr-top"><button type="button" id="crWa" class="cr-wa" aria-label="WhatsApp connection"></button></header>' +
    '<main class="cr-main"><p class="cr-say" id="crSay" role="status"></p>' +
    '<div class="cr-list cr-prep-row"><div class="cr-li"><b>Prepare case</b><button type="button" id="crPrepare" class="cr-tx">Open</button></div></div>' +
    '<section id="crNeedsSec" aria-labelledby="crNeedsH" hidden><h2 id="crNeedsH">Needs you <small id="crNeedsN"></small></h2><div id="crNeeds" class="cr-list"></div></section>' +
    '<section aria-labelledby="crPlanH"><h2 id="crPlanH">Sending plan</h2><div id="crRows" class="cr-list"></div></section>' +
    '<section id="crDone" class="cr-done" hidden></section></main>' +
    '<footer class="cr-foot"><div class="cr-bar"><button type="button" id="crStart" class="cr-go">Start case</button>' +
    '<button type="button" id="crPause" class="cr-stop">Pause all</button>' +
    '<button type="button" id="crFinish" class="cr-end">Finish case</button></div>' +
    '<nav class="cr-nav" aria-label="Case menu"><button type="button" id="crTools" class="cr-link">Tools</button>' +
    '<button type="button" id="crSettings" class="cr-link">Settings</button>' +
    '<button type="button" id="crBack" class="cr-link">Close</button></nav></footer></div>';
  document.body.append(page);
  const sheet = make('dialog', 'case-sheet');
  sheet.id = 'caseSheet';
  sheet.innerHTML =
    '<header><span class="cr-grab" aria-hidden="true"></span><h2 id="csTitle"></h2></header><div id="csBody"></div><p id="csError" class="cr-error" role="alert"></p><footer id="csFoot"></footer>';
  document.body.append(sheet);
  const say = (t) => {
    const n = $('crSay');
    if (n) n.textContent = t || '';
  };

  /* ---------------------------------------------------------------- the sheet (one reusable pop-up) */
  function openSheet(title, body, buttons = []) {
    $('csTitle').textContent = title;
    $('csBody').replaceChildren(body);
    $('csError').textContent = '';
    const foot = $('csFoot');
    foot.replaceChildren();
    /* every sheet closes from the bottom, in thumb reach: add Close when nothing else dismisses it */
    if (!buttons.some((b) => !b[2])) buttons = [...buttons, ['Close', 'cr-soft', null]];
    for (const [label, cls, run, keep] of buttons) {
      const b = btn(label, cls);
      b.onclick = async () => {
        if (b.disabled) return;
        for (const x of foot.children) x.disabled = true;
        $('csError').textContent = '';
        try {
          const out = run ? await run() : null;
          if (!keep) sheet.close();
          if (out !== undefined) take(out);
        } catch (e) {
          $('csError').textContent = e.message;
          for (const x of foot.children) x.disabled = false;
        }
      };
      foot.append(b);
    }
    if (!sheet.open) sheet.showModal();
    page.classList.add('cr-side'); // computer: the page moves left beside the side panel
  }
  sheet.addEventListener('close', () => page.classList.remove('cr-side'));
  sheet.addEventListener('click', (e) => e.target === sheet && sheet.close());

  /* ---------------------------------------------------------------- painting */
  function paint() {
    if (!data) return;
    const s = JSON.stringify(data);
    if (s === sig) return;
    sig = s;
    const wa = $('crWa');
    wa.replaceChildren(
      make('span', 'cr-dot'),
      make('span', '', data.whatsapp ? 'WhatsApp' : 'WhatsApp off'),
    );
    wa.dataset.ok = data.whatsapp ? '1' : '0';
    const ready = Object.values(data.checks || {}).every((v) => v === 'ok');
    $('crPrepare').replaceChildren(make('span', 'cr-open', 'Open'));
    $('crPrepare').closest('.cr-li').dataset.todo = ready ? '0' : '1';
    $('crPrepare').setAttribute(
      'aria-label',
      ready ? 'Prepare case' : 'Prepare case: something is not ready',
    );
    paintNeeds();
    paintRows();
    const run = data.status === 'running',
      paused = data.status === 'paused',
      idle = data.status === 'idle',
      fin = data.status === 'finished';
    $('crStart').textContent = paused ? 'Resume case' : 'Start case';
    $('crStart').hidden = !(idle || paused);
    $('crPause').hidden = !run;
    $('crFinish').hidden = !(run || paused);
    $('crPause').disabled = !run;
    $('crFinish').disabled = !(run || paused);
    document.querySelector('#casePage .cr-bar').hidden = fin;
    const done = $('crDone');
    done.hidden = !fin;
    $('crPlanH').parentElement.hidden = fin;
    if (!done.hidden) paintDone(done);
  }
  function needRow(it) {
    const row = make('article', 'cr-li cr-need');
    row.dataset.type = it.type;
    const text = make('div', 'cr-need-text');
    text.append(make('b', '', it.title));
    if (it.text) text.append(make('small', '', '“' + it.text + '”'));
    row.append(text, ...needButtons(it));
    return row;
  }
  function paintNeeds() {
    const box = $('crNeeds'),
      head = $('crNeedsH'),
      items = data.needs || [];
    head.querySelector('.cr-more-needs')?.remove();
    $('crNeedsN').textContent = items.length ? String(items.length) : '';
    box.replaceChildren();
    $('crNeedsSec').hidden = !items.length;
    if (!items.length) return;
    box.append(needRow(items[0]));
    if (items.length > 1)
      head.append(
        btn(`See all ${items.length}`, 'cr-more-needs', () => {
          const list = make('div', 'cr-sum');
          for (const it of data.needs) list.append(needRow(it));
          openSheet('Needs you', list, [['Close', 'cr-soft', null]]);
        }),
      );
  }
  function needButtons(it) {
    const one = (label, fn) => btn(label, 'cr-tx', fn);
    switch (it.type) {
      case 'payment':
        return [one('Check payment', () => paySheet(it))];
      case 'giki_reply':
        return [one('Read and decide', () => replySheet(it, true))];
      case 'question':
        return [one('Reply', () => replySheet(it, false))];
      case 'thank':
        return [one('Review thanks', () => thankSheet(it))];
      case 'whatsapp':
        return [
          one('Reconnect', async () => {
            try {
              await post({ action: 'need', id: it.id, op: 'reconnect' });
            } catch (e) {
              say(e.message);
            }
            document.getElementById('whatsappConnection')?.click();
          }),
        ];
      case 'uncertain':
        return it.id.startsWith('giki-')
          ? [one('Checked', () => quick(it, 'giki_checked'))]
          : [
              one('Check before retrying', () =>
                openSheet(
                  'Check before retrying',
                  make(
                    'p',
                    '',
                    'Open WhatsApp and look. Then say what you found. Nothing is retried by itself.',
                  ),
                  [
                    [
                      'It was sent',
                      'cr-go',
                      () => post({ action: 'need', id: it.id, op: 'mark_sent' }),
                    ],
                    [
                      'It was not sent',
                      'cr-soft',
                      () => post({ action: 'need', id: it.id, op: 'mark_not_sent' }),
                    ],
                  ],
                ),
              ),
            ];
      case 'audience_done':
        return [
          one('Continue waiting', () => quick(it, 'wait')),
          one('Choose another audience', async () => {
            await quick(it, 'choose_audience');
            rowSheet('important');
          }),
        ];
      case 'goal':
        return [one('Finish case', finishSheet)];
      default:
        return [one('Review', () => quick(it, 'review'))];
    }
  }
  async function quick(it, op) {
    try {
      take(await post({ action: 'need', id: it.id, op }));
    } catch (e) {
      say(e.message);
    }
  }
  function paintRows() {
    const box = $('crRows');
    box.replaceChildren();
    const live = data.status === 'running' || data.status === 'paused';
    for (const r of data.rows) {
      const li = make('article', 'cr-li cr-row');
      li.dataset.key = r.key;
      li.dataset.state = r.enabled ? r.state : 'off';
      const name = make('button', 'cr-name', '');
      name.append(make('b', '', r.title));
      if (r.note) name.append(make('small', 'cr-warn-line', r.note));
      name.onclick = () => rowSheet(r.key);
      name.setAttribute('aria-label', `${r.title}: messages and settings`);
      li.append(name);
      const acts = make('div', 'cr-acts');
      const total = (r.sent || 0) + (r.left == null ? 0 : r.left);
      if (!r.enabled) acts.append(make('span', 'cr-cnt', 'Off'));
      else if (live && r.key === 'group') acts.append(make('span', 'cr-cnt', String(r.sent || 0)));
      else if (live) acts.append(make('span', 'cr-cnt', `${r.sent || 0}/${total}`));
      if (r.action === 'start' || r.action === 'pause') {
        const run = btn(r.action === 'start' ? 'Start' : 'Pause', 'cr-tx cr-run', () =>
          rowOp(r.key, r.action),
        );
        run.dataset.act = r.action;
        acts.append(run);
      } else if (!live && r.key === 'important' && !r.enabled) {
        acts.append(btn('Choose', 'cr-tx', () => rowSheet(r.key, 'people')));
      } else if (!live && r.enabled) {
        const add = !r.has_msg;
        const edit = btn('', 'cr-tx', () => editSheet(r.key));
        edit.append(add ? 'Add' : 'Edit', make('span', 'cr-w', ' message')); // " message" hides on tiny phones
        edit.setAttribute('aria-label', `${add ? 'Add' : 'Edit'} message: ${r.title}`);
        if (add) edit.dataset.add = '1';
        acts.append(edit);
      }
      /* small settings icon: opens this row's timing straight away (same sheet as Settings tab) */
      if (data.status !== 'running') {
        // timing is locked while sending, so the icon only shows when it can be changed
        const gear = btn('', 'cr-gear', () => rowSheet(r.key, 'timing'));
        gear.innerHTML = GEAR;
        gear.setAttribute('aria-label', `Edit timing: ${r.title}`);
        acts.append(gear);
      }
      if (acts.children.length) li.append(acts);
      box.append(li);
    }
  }
  function paintDone(box) {
    box.replaceChildren(make('h2', '', 'Case finished'));
    const next = make('div', 'cr-row-actions');
    next.append(
      btn('Thank donors', 'cr-run', () => window.DonorThanks?.open?.()),
      btn('Start a new case', 'cr-more', caseSheet),
    );
    box.append(next);
    box.append(
      make(
        'p',
        'cr-sub',
        'Sending is stopped and the history is kept. Nothing below is sent until you send it yourself.',
      ),
    );
    for (const [k, label] of [
      ['update', 'Final update (for approval)'],
      ['thanks', 'Thank-you (for approval)'],
    ]) {
      const text = (data.drafts || {})[k];
      if (!text) continue;
      const area = make('textarea', 'cr-draft');
      area.value = text;
      area.readOnly = true;
      area.setAttribute('aria-label', label);
      const copy = btn('Copy', 'cr-soft', async () => {
        try {
          await navigator.clipboard.writeText(text);
          copy.textContent = 'Copied';
        } catch (e) {}
      });
      box.append(make('b', '', label), area, copy);
    }
  }

  /* ---------------------------------------------------------------- actions */
  async function rowOp(key, op) {
    try {
      take(await post({ action: 'row', key, op }));
    } catch (e) {
      say(e.message);
    }
  }

  function summaryList(s) {
    const box = make('div', 'cr-sum');
    for (const t of s.blockers) box.append(make('p', 'cr-block', t));
    for (const t of s.warnings) box.append(make('p', 'cr-warn', t));
    for (const key of ['group', 'top', 'giki', 'volunteers', 'important']) {
      const r = s.rows[key],
        p = r.plan || {};
      const what = !r.enabled
        ? 'Off'
        : key === 'group'
          ? `Every ${p.every_minutes} min`
          : `${r.count} people · ${p.gap_minutes} min apart · ${p.batch_size} per batch · ${p.rest_minutes} min break`;
      const row = make('div', 'cr-sum-row');
      row.append(make('b', '', r.title), make('span', '', what));
      box.append(row);
    }
    const msg = make('div', 'cr-sum-msg');
    for (const [k, label] of [
      ['group', 'Group message'],
      ['dm', 'Donor message'],
      ['question', 'Share question (GIKI)'],
    ]) {
      if (!s.messages[k]) continue;
      msg.append(make('b', '', label), make('p', 'cr-quote', s.messages[k].slice(0, 160)));
    }
    box.append(msg);
    return box;
  }
  async function startSheet() {
    try {
      if (data.status === 'paused') return take(await post({ action: 'resume' }));
      const s = await post({ action: 'summary' });
      const buttons = [['Cancel', 'cr-soft', null]];
      if (!s.blockers.length)
        buttons.unshift([
          'Approve and start',
          'cr-go',
          () => post({ action: 'start', token: s.token }),
        ]);
      openSheet('Start case', summaryList(s), buttons);
    } catch (e) {
      say(e.message);
    }
  }
  async function pauseAll() {
    try {
      take(await post({ action: 'pause' }));
    } catch (e) {
      say(e.message);
    }
  }
  async function finishSheet() {
    try {
      const ask = await post({ action: 'finish' });
      const body = make('div', 'cr-sum');
      body.append(
        make('p', '', `Confirmed so far: ${rs(ask.confirmed)}. ${rs(ask.left)} left.`),
        make(
          'p',
          'cr-sub',
          'This stops all future sends and group reminders, cancels sharing requests that were not sent, keeps the whole history, and prepares the final update and thank-you for your approval.',
        ),
      );
      openSheet('Finish case', body, [
        ['Finish case', 'cr-end', () => post({ action: 'finish', confirm: true })],
        ['Keep running', 'cr-soft', null],
      ]);
    } catch (e) {
      say(e.message);
    }
  }
  function field(label, input) {
    const l = make('label', 'cr-field');
    l.append(make('span', '', label), input);
    return l;
  }
  function paySheet(it) {
    const body = make('div', 'cr-sum');
    const amount = make('input');
    amount.type = 'number';
    amount.min = '1';
    amount.inputMode = 'numeric';
    amount.placeholder = 'Amount you received';
    body.append(
      make('p', '', `${it.name || 'They'} wrote:`),
      make('p', 'cr-quote', it.text || ''),
      make(
        'p',
        'cr-sub',
        'This is only a claim. Check your account, then enter what you really received.',
      ),
      field('Amount received (Rs.)', amount),
    );
    openSheet('Check payment', body, [
      [
        'Confirm payment',
        'cr-go',
        () =>
          post({ action: 'need', id: it.id, op: 'check_payment', amount: Number(amount.value) }),
      ],
      ['Not paid', 'cr-soft', () => post({ action: 'need', id: it.id, op: 'not_paid' })],
    ]);
  }
  function replySheet(it, giki) {
    const body = make('div', 'cr-sum');
    const text = make('textarea');
    text.rows = 3;
    text.placeholder = 'Your reply';
    body.append(
      make('p', '', `${it.name || 'They'} wrote:`),
      make('p', 'cr-quote', it.text || ''),
      field('Your reply (optional)', text),
    );
    const b = [];
    if (giki) {
      b.push(['Agreed', 'cr-go', () => post({ action: 'need', id: it.id, op: 'agreed' })]);
      b.push([
        'Not agreed',
        'cr-soft',
        () => post({ action: 'need', id: it.id, op: 'not_agreed' }),
      ]);
    } else b.push(['Dismiss', 'cr-soft', () => post({ action: 'need', id: it.id, op: 'dismiss' })]);
    b.unshift([
      'Send reply',
      'cr-act',
      () => {
        if (!text.value.trim()) throw Error('Write the reply first.');
        return post({ action: 'need', id: it.id, op: 'reply', text: text.value });
      },
    ]);
    openSheet(giki ? 'Read and decide' : 'Reply', body, b);
  }
  function thankSheet(it) {
    const text = make('textarea');
    text.rows = 8;
    text.value = it.text || '';
    openSheet('Thank you', field('Edit if you like, then send', text), [
      [
        'Send thanks',
        'cr-go',
        () => post({ action: 'need', id: it.id, op: 'send_thanks', text: text.value }),
      ],
      ['Not now', 'cr-soft', () => post({ action: 'need', id: it.id, op: 'dismiss' })],
    ]);
  }

  /* Row details: timing, who, what, and (Important) who to include. Saving never starts sending. */
  /* One place to write each message: the same saved messages the rest of the app sends. */
  const EDITORS = {
    group: {
      title: 'GiveLife Group message',
      load: async () => (await call('/focus-bank?kind=group')).source || '',
      save: async (text) => {
        await call('/focus-bank', { kind: 'group', text });
        await call('/focus-bank', { kind: 'group', action: 'generate' }).catch(() => {});
      },
    },
    dm: {
      title: 'Donor message',
      load: async () => {
        const d = await call('/donor-messages');
        return d.base || d.origin || ((d.items || [])[0] || {}).text || '';
      },
      save: async (text) => {
        await call('/donor-messages', { action: 'base', text });
        await call('/donor-messages', { action: 'regenerate' }).catch(() => {});
      },
    },
    question: {
      title: 'Share question',
      load: async () => (await call('/donor-messages')).follow_up || '',
      save: (text) => call('/donor-messages', { action: 'follow_up', text }),
    },
    volunteers: {
      title: 'Volunteers message',
      load: async () => (await call('/volunteers')).message || '',
      save: (text) => call('/volunteers', { action: 'message', text }),
    },
  };
  async function editSheet(key, part) {
    const kind = part || (key === 'group' ? 'group' : key === 'volunteers' ? 'volunteers' : 'dm');
    const ed = EDITORS[kind];
    const text = make('textarea', 'cr-text');
    text.rows = 10;
    text.placeholder = 'Loading…';
    text.disabled = true;
    text.setAttribute('aria-label', ed.title);
    openSheet(ed.title, text, [
      [
        'Save',
        'cr-go',
        async () => {
          if (text.disabled) throw Error('Still loading. Try again in a moment.');
          await ed.save(text.value);
          await load();
        },
      ],
      ['Close', 'cr-soft', null],
    ]);
    try {
      text.value = await ed.load();
      text.disabled = false;
      text.placeholder = kind === 'volunteers' ? 'What should volunteers share?' : '';
      text.focus({ preventScroll: true });
    } catch (e) {
      $('csError').textContent = e.message;
    }
  }
  async function rowSheet(key, tab = 'message') {
    const r = data.rows.find((x) => x.key === key);
    openSheet(r.title, make('p', 'cr-sub', 'Loading…'), [['Close', 'cr-soft', null]]); // answer the tap at once
    let s = null;
    try {
      s = await post({ action: 'summary' });
    } catch (e) {}
    const body = make('div', 'cr-sum');
    const panes = {
      message: make('div', 'cr-pane'),
      timing: make('div', 'cr-pane'),
      people: make('div', 'cr-pane'),
    };
    const seg = make('div', 'cr-seg');
    const count = s && s.rows[key] && s.rows[key].count != null ? s.rows[key].count : r.left || 0;
    const show = (name) => {
      for (const [k, el] of Object.entries(panes)) el.hidden = k !== name;
      const lit = name === 'people' ? 'timing' : name; // People is opened from Settings
      for (const b of seg.children) b.dataset.on = b.dataset.k === lit ? '1' : '0';
      const save = $('csFoot').firstElementChild;
      if (save && sheet.open) save.hidden = name === 'message'; // Save is for settings and people only
    };
    for (const [k, label] of [
      ['message', 'Message'],
      ['timing', 'Settings'],
    ]) {
      const b = btn(label, 'cr-seg-b', () => show(k));
      b.dataset.k = k;
      seg.append(b);
    }
    body.append(seg, panes.message, panes.timing, panes.people);
    /* Message */
    const kind = key === 'group' ? 'group' : key === 'volunteers' ? 'volunteers' : 'dm';
    const mtext = s ? (kind === 'dm' ? s.messages.dm : s.messages[kind]) : '';
    const block = (label, text, editLabel, fn) => {
      const w = make('div', 'cr-block');
      w.append(make('b', '', label));
      if (text) w.append(make('p', 'cr-quote', text));
      else w.append(make('p', 'cr-sub', 'Nothing written yet.'));
      w.append(btn(editLabel, text ? 'cr-more' : 'cr-act', fn));
      return w;
    };
    panes.message.append(
      block(
        kind === 'volunteers'
          ? 'Volunteers message'
          : kind === 'group'
            ? 'Group message'
            : 'Donor message',
        mtext,
        mtext ? 'Edit message' : 'Add message',
        () => editSheet(key),
      ),
    );
    if (key === 'volunteers' && !mtext)
      panes.message.append(
        btn('Use the case message', 'cr-more', async () => {
          try {
            const g = (await call('/focus-bank?kind=group')).source || '';
            await call('/volunteers', { action: 'message', text: g });
            await load();
            sheet.close();
          } catch (e) {
            $('csError').textContent = e.message;
          }
        }),
      );
    if (key === 'giki')
      panes.message.append(
        block('Share question', s ? s.messages.question : '', 'Edit question', () =>
          editSheet(key, 'question'),
        ),
      );
    /* Timing */
    /* Settings: plain rows, one switch, and − / + buttons so nothing needs typing */
    const on = make('input', 'cr-switch');
    on.type = 'checkbox';
    on.checked = r.enabled;
    const onLabel = make('label', 'cr-set-row');
    onLabel.append(make('span', '', 'Send in this case'), on);
    panes.timing.append(onLabel);
    const inputs = {};
    for (const [name, label, lo, hi, step] of FIELDS[key === 'group' ? 'group' : 'dm']) {
      const i = make('input', 'cr-num');
      i.type = 'number';
      i.min = lo;
      i.max = hi;
      i.inputMode = 'numeric';
      i.value = r.plan[name];
      i.setAttribute('aria-label', `${label} (${lo}–${hi})`);
      inputs[name] = i;
      const bump = (dir) => {
        const v = Number(i.value);
        i.value = Math.min(hi, Math.max(lo, (Number.isFinite(v) ? v : lo) + dir * step));
      };
      const less = btn('−', 'cr-step', () => bump(-1));
      less.setAttribute('aria-label', `Less: ${label}`);
      const more = btn('+', 'cr-step', () => bump(1));
      more.setAttribute('aria-label', `More: ${label}`);
      const stepper = make('div', 'cr-stepper');
      stepper.append(less, i, more);
      const line = make('div', 'cr-set-row');
      line.append(make('span', '', label), stepper);
      panes.timing.append(line);
    }
    if (key !== 'group') {
      const people = btn('', 'cr-set-row cr-set-link', () => show('people'));
      people.append(make('span', '', 'People'), make('span', 'cr-set-val', String(count)));
      panes.timing.append(people);
    }
    /* People */
    let picked = null;
    if (key === 'important') picked = await importantPicker(panes.people, s);
    if (s && s.names && s.names[key] && s.names[key].length)
      panes.people.append(make('p', 'cr-names', s.names[key].join(', ')));
    if (r.giki && r.giki.people && r.giki.people.length)
      panes.people.append(
        make('b', '', 'Sharing'),
        make(
          'p',
          'cr-names',
          r.giki.people.map((p) => `${p.name}: ${GIKI[p.step] || p.step}`).join(' · '),
        ),
      );
    if (!panes.people.children.length) panes.people.append(make('p', 'cr-sub', 'No one yet.'));
    panes.people.prepend(btn('Back to settings', 'cr-tx cr-back', () => show('timing')));
    const locked = data.status === 'running';
    if (locked)
      body.append(make('p', 'cr-warn', 'The plan is running. Pause all to change timing.'));
    show(tab === 'people' && key === 'group' ? 'message' : tab);
    openSheet(r.title, body, [
      [
        'Save',
        'cr-go',
        () => {
          if (locked) throw Error('Pause all first, then change the plan.');
          const row = { enabled: on.checked };
          for (const [n, i] of Object.entries(inputs)) row[n] = Number(i.value);
          if (picked) row.ids = picked();
          return post({ action: 'plan', plan: { [key]: row } });
        },
      ],
      ['Close', 'cr-soft', null],
    ]);
    show(tab === 'people' && key === 'group' ? 'message' : tab);
  }
  async function importantPicker(body, s) {
    let items = [];
    try {
      const d = await (await fetch('/donors?tab=important')).json();
      items = (d.items || []).filter((x) => !x.dm_sent);
    } catch (e) {}
    const chosen = new Set(((data.plan_ids && data.plan_ids.important) || []).concat([]));
    const box = make('div', 'cr-pick');
    const count = make('b', '', '');
    const upd = () => (count.textContent = `Important donors to include: ${chosen.size}`);
    for (const d of items.slice(0, 300)) {
      const l = make('label', 'cr-check');
      const c = make('input');
      c.type = 'checkbox';
      c.checked = chosen.has(d.id);
      c.onchange = () => (c.checked ? chosen.add(d.id) : chosen.delete(d.id), upd());
      l.append(c, make('span', '', d.name));
      box.append(l);
    }
    const all = btn('Select everyone shown', 'cr-soft', () => {
      for (const d of items.slice(0, 300)) chosen.add(d.id);
      for (const c of box.querySelectorAll('input')) c.checked = true;
      upd();
    });
    upd();
    body.append(
      count,
      items.length ? all : make('p', 'cr-sub', 'No Important donors are waiting.'),
      box,
    );
    return () => [...chosen];
  }

  /* ---------------------------------------------------------------- prepare case: everything in one panel */
  async function call(url, body) {
    const r = await fetch(
      url,
      body
        ? {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }
        : {},
    );
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.error) throw Error(d.error || 'That did not work. Nothing was changed.');
    return d;
  }
  const PILL = { ok: 'Ready', again: 'Check again', check: 'Not yet' };
  /* One block per message: its base text, Save Base, Next (read the versions), Test 3 versions, Looks right. */
  function block(o) {
    const box = make('details', 'cr-prep');
    box.dataset.k = o.key;
    const sum = make('summary');
    const pill = make('span', 'cr-pill');
    sum.append(make('b', '', o.title), pill);
    const text = make('textarea', 'cr-text');
    text.rows = 5;
    text.setAttribute('aria-label', o.title);
    text.placeholder = 'Loading…';
    const view = make('p', 'cr-quote');
    view.hidden = true;
    const note = make('p', 'cr-sub');
    note.setAttribute('role', 'status');
    const acts = make('div', 'cr-row-actions');
    let saved = null,
      items = [],
      at = -1;
    const setPill = () => {
      const s = o.check ? data.checks[o.check] : saved && saved.trim() ? 'ok' : 'check';
      pill.textContent = o.check ? PILL[s] : s === 'ok' ? 'Saved' : 'Not yet';
      box.dataset.s = s;
    };
    const run = (b, fn) => async () => {
      if (b.disabled) return;
      b.disabled = true;
      try {
        note.textContent = (await fn()) || '';
      } catch (e) {
        note.textContent = e.message;
      } finally {
        b.disabled = false;
        setPill();
      }
    };
    const fetchIt = async () => {
      const d = await o.load();
      items = d.items || [];
      if (saved === null || text.value === saved) text.value = d.text || '';
      saved = d.text || '';
      text.placeholder = '';
      return d;
    };
    const save = async () => {
      if (text.value === saved) return false;
      await o.save(text.value);
      saved = text.value;
      await load();
      return true;
    };
    const b = {};
    b.save = btn('Save Base', 'cr-act');
    b.save.onclick = run(b.save, async () => {
      const changed = await save();
      if (!o.versions) return changed ? 'Saved.' : 'Nothing changed.';
      if (changed || !items.length) await o.versions();
      at = -1;
      view.hidden = true;
      return changed
        ? 'Saved. Writing the wording versions now; press Next to read them.'
        : 'This is already your base. Press Next to read the versions.';
    });
    acts.append(b.save);
    if (o.versions) {
      b.next = btn('Next', 'cr-more');
      b.next.onclick = run(b.next, async () => {
        await fetchIt();
        if (!items.length) return 'No versions yet. Press Save Base, then wait a moment.';
        at = (at + 1) % items.length;
        view.textContent = items[at];
        view.hidden = false;
        return `Version ${at + 1} of ${items.length}`;
      });
      acts.append(b.next);
    }
    if (o.test) {
      b.test = btn('Test 3 versions', 'cr-more');
      b.test.onclick = run(b.test, async () => {
        await save();
        return await o.test();
      });
      acts.append(b.test);
    }
    if (o.check) {
      b.ok = btn('Looks right', 'cr-go');
      b.ok.onclick = run(b.ok, async () => {
        await save();
        take(await post({ action: 'check', name: o.check }));
        return 'Checked. If the wording changes later this shows “Check again”.';
      });
      acts.append(b.ok);
    }
    box.append(sum, ...(o.before || []), text, view, acts, note);
    box.addEventListener(
      'toggle',
      () => box.open && saved === null && fetchIt().catch((e) => (note.textContent = e.message)),
    );
    setPill();
    box.refresh = setPill;
    return box;
  }
  async function testGroup() {
    for (let i = 0; i < 3; i++) {
      const r = await call('/test', {
        message: $('csBody').querySelector('[data-k="group"] textarea').value,
      });
      if (r.code !== 'SUCCESS')
        throw Error(
          r.message || `Test ${i + 1} was not confirmed. Check the Test group before trying again.`,
        );
    }
    return 'Sent 3 versions to the Test group. Check the poster and wording there.';
  }
  async function testDonor() {
    let last = '';
    for (let i = 0; i < 3; i++) {
      const r = await call('/donor-messages', { action: 'test', poster: true });
      if (r.code && r.code !== 'SUCCESS')
        throw Error(
          r.message || `Test ${i + 1} was not confirmed. Check WhatsApp before trying again.`,
        );
      last = r.reply || '';
    }
    return `Sent 3 test DMs (last: ${last}). Check the greeting says Bhai or Sister correctly.`;
  }
  function prepareSheet() {
    const body = make('div', 'cr-sum cr-prepare');
    const c = data.case;
    const ready = (k) => PILL[data.checks[k]] || 'Not yet';
    /* Case facts, target and payment details */
    const caseBox = make('details', 'cr-prep');
    caseBox.dataset.s = data.checks.case;
    const cs = make('summary');
    cs.append(make('b', '', 'Case'), make('span', 'cr-pill', ready('case')));
    caseBox.append(
      cs,
      make('p', '', `${c.name || 'This case'} · ${rs(c.left)} left · Confirmed ${rs(c.confirmed)}`),
      make('p', 'cr-sub', `Payment: ${data.payment?.number || ''} (Easypaisa)`),
    );
    const ca = make('div', 'cr-row-actions');
    ca.append(
      btn('Change amount', 'cr-act', () => amountSheet()),
      btn('Switch or new case', 'cr-more', () => caseSheet()),
    );
    /* Case facts and the donor message written from them, right here (same server logic as Case Writer) */
    const facts = make('textarea', 'cr-text');
    facts.rows = 4;
    facts.placeholder = 'Case facts';
    facts.setAttribute('aria-label', 'Case facts');
    const written = make('p', 'cr-quote');
    written.hidden = true;
    const fnote = make('p', 'cr-sub');
    fnote.setAttribute('role', 'status');
    let cw = null;
    const cwBody = (action) => ({
      action,
      case_id: cw.case_id,
      revision: cw.revision,
      details: facts.value,
      text: cw.text || '',
      style: cw.style || 'ur_en',
    });
    const showCw = (d) => {
      cw = d;
      written.textContent = d.text || '';
      written.hidden = !d.text;
    };
    const cwRun = (b, action, done) => async () => {
      if (!cw || b.disabled) return;
      b.disabled = true;
      try {
        showCw(await call('/case-message', cwBody(action)));
        fnote.textContent = done;
        if (action === 'use') await load();
      } catch (e) {
        fnote.textContent = e.message;
      } finally {
        b.disabled = false;
      }
    };
    const fa = make('div', 'cr-row-actions');
    const fSave = btn('Save facts', 'cr-more'),
      fWrite = btn('Write message', 'cr-act'),
      fUse = btn('Use message', 'cr-go');
    fSave.onclick = cwRun(fSave, 'save', 'Saved.');
    fWrite.onclick = cwRun(fWrite, 'generate', 'Written. Read it, then Use message.');
    fUse.onclick = cwRun(fUse, 'use', 'Now your donor message.');
    fa.append(fSave, fWrite, fUse);
    caseBox.append(ca, facts, fa, written, fnote);
    caseBox.addEventListener('toggle', () => {
      if (caseBox.open && !cw)
        call('/case-message')
          .then((d) => {
            showCw(d);
            facts.value = d.details || '';
          })
          .catch((e) => (fnote.textContent = e.message));
    });
    /* Poster */
    const posterBox = make('details', 'cr-prep');
    posterBox.dataset.s = data.checks.poster;
    const ps = make('summary');
    ps.append(make('b', '', 'Poster'), make('span', 'cr-pill', ready('poster')));
    const img = make('img', 'cr-poster');
    img.alt = 'Current poster';
    posterBox.addEventListener(
      'toggle',
      () => posterBox.open && !img.src && (img.src = '/poster?v=' + Date.now()),
    );
    img.onerror = () => (img.hidden = true);
    posterBox.append(
      ps,
      img,
      btn('Change poster', 'cr-act', () => (sheet.close(), window.DonorHub?.openPoster?.())),
    );
    const group = block({
      key: 'group',
      title: 'GiveLife Group message',
      check: 'group',
      load: async () => {
        const d = await call('/focus-bank?kind=group');
        return { text: d.source, items: d.items, revision: d.revision };
      },
      save: async (text) => call('/focus-bank', { kind: 'group', text }),
      versions: () => call('/focus-bank', { kind: 'group', action: 'generate' }),
      test: testGroup,
    });
    const ask = make('textarea', 'cr-text');
    ask.rows = 3;
    ask.setAttribute('aria-label', 'Share question (GIKI)');
    let askSaved = null;
    const donor = block({
      key: 'donor',
      title: 'Donor message',
      check: 'donor',
      load: async () => {
        const d = await call('/donor-messages');
        const items = (d.items || []).map((x) => x.text).filter(Boolean);
        if (askSaved === null) ask.value = askSaved = d.follow_up || '';
        return { text: d.base || d.origin || items[0] || '', items };
      },
      save: async (text) => {
        await call('/donor-messages', { action: 'base', text });
      },
      versions: () => call('/donor-messages', { action: 'regenerate' }),
      test: testDonor,
    });
    /* the GIKI share question lives with the donor message: both are checked together */
    const askRow = make('div', 'cr-row-actions');
    askRow.append(
      btn('Save share question', 'cr-more', async () => {
        try {
          await call('/donor-messages', { action: 'follow_up', text: ask.value });
          askSaved = ask.value;
          await load();
          $('csError').textContent = '';
          donor.refresh();
        } catch (e) {
          $('csError').textContent = e.message;
        }
      }),
    );
    donor.append(make('b', 'cr-label', 'Share question (GIKI)'), ask, askRow);
    const vol = block({
      key: 'volunteers',
      title: 'Volunteers sharing request',
      load: async () => ({ text: (await call('/volunteers')).message || '' }),
      save: (text) => call('/volunteers', { action: 'message', text }),
    });
    const boxes = [caseBox, posterBox, group, donor, vol];
    /* open the first thing that is not ready, so the next step is always in front of you */
    (boxes.find((x) => x.dataset.s !== 'ok') || group).open = true;
    body.append(...boxes);
    openSheet('Prepare case', body, [['Done', 'cr-go', null]]);
  }

  function amountSheet() {
    const input = make('input');
    input.type = 'number';
    input.min = '0';
    input.inputMode = 'numeric';
    input.value = data.case.left;
    openSheet('Amount still needed', field('Rs. left for this case', input), [
      ['Save', 'cr-go', () => post({ action: 'left', left: Number(input.value) })],
      ['Cancel', 'cr-soft', null],
    ]);
    setTimeout(() => input.select(), 50);
  }
  async function cases(body) {
    const r = await fetch('/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(d.error || 'That did not work. Nothing was changed.');
    location.reload(); // every screen reads the new case
  }
  function caseSheet() {
    const body = make('div', 'cr-sum');
    const pick = make('select');
    for (const c of data.cases || []) {
      const o = new Option(c.name, c.id, false, c.current);
      pick.append(o);
    }
    const name = make('input'),
      left = make('input');
    name.placeholder = 'For example the child’s name';
    left.type = 'number';
    left.inputMode = 'numeric';
    left.placeholder = 'Amount needed';
    body.append(
      field('Open a saved case', pick),
      btn('Open this case', 'cr-more', async () => {
        try {
          await cases({ action: 'switch', id: pick.value });
        } catch (e) {
          $('csError').textContent = e.message;
        }
      }),
      make('b', '', 'Start a new case'),
      make('p', 'cr-sub', 'Starts from zero: no old amount, stars, sent marks or plan are reused.'),
      field('Name', name),
      field('Amount needed (Rs.)', left),
    );
    openSheet('Case', body, [
      [
        'Start new case',
        'cr-go',
        () => cases({ action: 'new', name: name.value, left: Number(left.value) }),
      ],
      ['Close', 'cr-soft', null],
    ]);
  }

  /* ---------------------------------------------------------------- tools menu (the existing tools) */
  const press = (id) => () => document.getElementById(id)?.click();
  /* Nav.go only records a route; each page opens from its own button, so press the same buttons the tabs press. */
  const donors = (tab) => () => {
    document.getElementById('openDonors')?.click();
    if (tab)
      setTimeout(() => document.querySelector(`#donorsPage [data-tab="${tab}"]`)?.click(), 700);
  };
  const TOOLS = [
    ['Daily'],
    ['Donors', donors()],
    ['Message and send', () => Nav.go('')],
    ['Chat', press('chatOpen')],
    ['Notes', press('donorNotesShortcut')],
    ['Thank donors', () => window.DonorThanks?.open?.()],
    ['Reports', () => document.querySelector('.report-open')?.click()],
    ['Messages'],
    ['Message versions and tests', () => Nav.go('preview')],
    ['Case Writer', () => window.CaseWriter?.open?.()],
    ['Volunteers', donors('volunteers')],
    ['Auto replies', () => document.querySelector('.reply-open')?.click()],
    ['Setup'],
    ['WhatsApp connection', press('whatsappConnection')],
    ['Resume group messages', () => document.querySelector('.resume-open')?.click()],
    ['Find groups', () => (location.href = '/new/group-finder')],
    ['Settings', press('gear')],
  ];
  /* Settings: the few things that belong to the case, then the shared app settings */
  function settingsSheet() {
    const mk = (label, value, action, fn) => {
      const row = make('div', 'cr-li');
      row.append(make('b', '', label));
      if (value) row.append(make('span', 'cr-cnt', value));
      row.append(btn(action, 'cr-tx', fn));
      return row;
    };
    const close = (fn) => () => (sheet.close(), fn());
    const body = make('div', 'cr-sets');
    const a = make('div', 'cr-list'),
      b = make('div', 'cr-list');
    a.append(
      mk('Case', data.case.name || '', 'Change', () => caseSheet()),
      mk('Amount left', rs(data.case.left), 'Change', () => amountSheet()),
      mk(
        'Poster',
        '',
        'Change',
        close(() => window.DonorHub?.openPoster?.()),
      ),
    );
    b.append(
      mk('Sending times', '', 'Open', () => timingSheet()),
      mk(
        'Auto replies',
        '',
        'Open',
        close(() => document.querySelector('.reply-open')?.click()),
      ),
      mk('WhatsApp', data.whatsapp ? 'On' : 'Off', 'Open', close(press('whatsappConnection'))),
      mk('App settings', '', 'Open', close(press('gear'))),
    );
    body.append(a, b);
    openSheet('Settings', body, [['Close', 'cr-soft', null]]);
  }
  function timingSheet() {
    const list = make('div', 'cr-list');
    for (const r of data.rows) {
      const row = make('div', 'cr-li');
      row.append(
        make('b', '', r.title),
        btn('Open', 'cr-tx', () => rowSheet(r.key, 'timing')),
      );
      list.append(row);
    }
    openSheet('Sending times', list, [['Close', 'cr-soft', null]]);
  }
  /* Tools opens as a bottom sheet (never a menu dropping from the top) */
  function toolsSheet() {
    const list = make('div', 'cr-menu');
    list.id = 'crMenu';
    for (const [label, fn] of TOOLS)
      list.append(
        fn ? btn(label, 'cr-tool', () => (sheet.close(), fn())) : make('h3', 'cr-tool-h', label),
      );
    openSheet('Tools', list, [['Close', 'cr-soft', null]]);
  }

  /* ---------------------------------------------------------------- open / close with the address */
  const path = () => (typeof Nav !== 'undefined' ? Nav.path() : '');
  function poll() {
    clearInterval(timer);
    timer = setInterval(() => page.open && !document.hidden && !busy && load(), 3000);
  }
  function show() {
    if (!page.open) page.showModal();
    load();
    poll();
  }
  function sync() {
    const p = path();
    if (p === 'case') show();
    else if ((p === '' || p === 'preview') && page.open) page.close('route');
  }
  page.addEventListener('close', () => {
    clearInterval(timer);
    if (page.returnValue !== 'route') Nav.leave('case');
  });
  page.addEventListener('cancel', () => (page.returnValue = ''));
  $('crBack').onclick = () => page.close();
  $('crPrepare').onclick = () => data && prepareSheet();
  $('crTools').onclick = toolsSheet;
  $('crSettings').onclick = () => data && settingsSheet();
  $('crWa').onclick = press('whatsappConnection');
  $('crStart').onclick = () => data && startSheet();
  $('crPause').onclick = () => data && pauseAll();
  $('crFinish').onclick = () => data && finishSheet();
  addEventListener('studio-navigate', sync);
  addEventListener('popstate', sync);
  addEventListener('hashchange', sync);
  window.CaseRun = { open: () => Nav.go('case'), load };

  /* When a case is running or paused, the app opens on this page. */
  (async () => {
    try {
      const d = await (await fetch('/case-run')).json();
      if (d && d.rows) {
        data = d; // ready before the page opens, so it shows at once
        paint();
      }
      if ((d.status === 'running' || d.status === 'paused') && path() === '')
        Nav.go('case', { replace: true });
      else sync();
    } catch (e) {
      sync();
    }
  })();
})();
