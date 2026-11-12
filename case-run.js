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
    group: [['every_minutes', 'Minutes between posts', 15, 1440]],
    dm: [
      ['gap_minutes', 'Minutes between DMs', 1, 10],
      ['batch_size', 'DMs per batch', 1, 20],
      ['rest_minutes', 'Minutes of rest between batches', 1, 120],
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
    '<div class="cr-shell"><div class="cr-head"><div class="cr-top"><h1 id="crName">Case</h1><span class="cr-pill" id="crStatus"></span></div>' +
    '<p class="cr-meta" id="crMeta"></p><div class="cr-tools-row"><button type="button" id="crPrepare" class="cr-soft">Prepare case</button>' +
    '<details class="cr-tools" id="crTools"><summary>Tools</summary><div class="cr-menu" id="crMenu"></div></details>' +
    '<button type="button" id="crBack" class="cr-soft">Close</button></div></div>' +
    '<main class="cr-main"><p class="cr-say" id="crSay" role="status"></p>' +
    '<section aria-labelledby="crNeedsH"><h2 id="crNeedsH">Needs you <small id="crNeedsN"></small></h2><div id="crNeeds" class="cr-needs"></div></section>' +
    '<section aria-labelledby="crPlanH"><h2 id="crPlanH">Sending plan</h2><div id="crRows" class="cr-rows"></div></section>' +
    '<section id="crDone" class="cr-done" hidden></section></main>' +
    '<footer class="cr-bar"><button type="button" id="crStart" class="cr-go">Start case</button>' +
    '<button type="button" id="crPause" class="cr-stop">Pause all</button>' +
    '<button type="button" id="crFinish" class="cr-end">Finish case</button></footer></div>';
  document.body.append(page);
  const sheet = make('dialog', 'case-sheet');
  sheet.id = 'caseSheet';
  sheet.innerHTML =
    '<header><h2 id="csTitle"></h2><button type="button" id="csClose" aria-label="Close">×</button></header><div id="csBody"></div><p id="csError" class="cr-error" role="alert"></p><footer id="csFoot"></footer>';
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
  }
  $('csClose').onclick = () => sheet.close();
  sheet.addEventListener('click', (e) => e.target === sheet && sheet.close());

  /* ---------------------------------------------------------------- painting */
  function paint() {
    if (!data) return;
    const s = JSON.stringify(data);
    if (s === sig) return;
    sig = s;
    $('crName').textContent = data.case.name || 'Case';
    const st = $('crStatus');
    st.textContent = STATUS[data.status] || data.status;
    st.dataset.s = data.status;
    $('crMeta').textContent =
      `Confirmed ${rs(data.case.confirmed)} · ${rs(data.case.left)} left · WhatsApp ${data.whatsapp ? 'connected' : 'not connected'}`;
    $('crMeta').dataset.wa = data.whatsapp ? '1' : '0';
    paintNeeds();
    paintRows();
    const run = data.status === 'running',
      paused = data.status === 'paused',
      idle = data.status === 'idle';
    const start = $('crStart');
    start.textContent = paused ? 'Resume case' : 'Start case';
    start.disabled = !(idle || paused);
    $('crPause').disabled = !run;
    $('crFinish').disabled = !(run || paused);
    const done = $('crDone');
    done.hidden = data.status !== 'finished';
    if (!done.hidden) paintDone(done);
  }
  function paintNeeds() {
    const box = $('crNeeds'),
      items = data.needs || [];
    $('crNeedsN').textContent = items.length ? String(items.length) : '';
    box.replaceChildren();
    if (!items.length) {
      box.append(make('p', 'cr-empty', 'Nothing needs you.'));
      return;
    }
    for (const it of items) {
      const row = make('article', 'cr-need');
      row.dataset.type = it.type;
      const text = make('div', 'cr-need-text');
      text.append(make('b', '', it.title));
      if (it.text) text.append(make('small', '', '“' + it.text + '”'));
      row.append(text, ...needButtons(it));
      box.append(row);
    }
  }
  function needButtons(it) {
    const one = (label, fn) => btn(label, 'cr-act', fn);
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
    for (const r of data.rows) {
      const card = make('article', 'cr-row');
      card.dataset.key = r.key;
      card.dataset.state = r.enabled ? r.state : 'off';
      const head = make('div', 'cr-row-head');
      head.append(
        make('b', '', r.title),
        make('span', 'cr-pill', r.enabled ? STATE[r.state] || r.state : 'Off'),
      );
      const next = r.next_at ? clock(r.next_at) : '—';
      const line = make(
        'p',
        'cr-line',
        r.key === 'group'
          ? `Posted today ${r.sent} · Next ${next}`
          : `Sent ${r.sent} · Left ${r.left == null ? 0 : r.left} · Next ${next}`,
      );
      card.append(head, line);
      if (r.giki) {
        const g = r.giki;
        card.dataset.giki =
          `Waiting ${g.waiting} · Agreed ${g.agreed} · Shared ${g.shared}` +
          (g.needs ? ` · Needs you ${g.needs}` : '');
        card.append(make('p', 'cr-sub', card.dataset.giki));
      }
      const plan =
        r.key === 'group'
          ? `Every ${r.plan.every_minutes} min`
          : r.key === 'important' && !r.enabled
            ? 'Off until you choose people'
            : `${r.plan.gap_minutes} min apart · ${r.plan.batch_size} per batch · ${r.plan.rest_minutes} min break`;
      const foot = make('div', 'cr-foot'),
        subs = make('div', 'cr-subs');
      subs.append(make('p', 'cr-sub', r.note || plan));
      const acts = make('div', 'cr-row-actions');
      if (r.action !== 'none') {
        const label = { start: 'Start', pause: 'Pause', review: 'Review' }[r.action];
        acts.append(
          btn(label, 'cr-run', () =>
            r.action === 'review' ? rowSheet(r.key) : rowOp(r.key, r.action),
          ),
        );
      }
      acts.append(btn('More', 'cr-more', () => rowSheet(r.key)));
      foot.append(subs, acts);
      card.append(foot);
      box.append(card);
    }
  }
  function paintDone(box) {
    box.replaceChildren(make('h2', '', 'Case finished'));
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
  async function rowSheet(key) {
    const r = data.rows.find((x) => x.key === key);
    const body = make('div', 'cr-sum');
    let s = null;
    try {
      s = await post({ action: 'summary' });
    } catch (e) {}
    const on = make('input');
    on.type = 'checkbox';
    on.checked = r.enabled;
    const onLabel = make('label', 'cr-check');
    onLabel.append(on, make('span', '', 'Include in this case'));
    body.append(
      make('p', 'cr-sub', `${r.title} · ${r.enabled ? STATE[r.state] || r.state : 'Off'}`),
      onLabel,
    );
    const inputs = {};
    for (const [name, label, lo, hi] of FIELDS[key === 'group' ? 'group' : 'dm']) {
      const i = make('input');
      i.type = 'number';
      i.min = lo;
      i.max = hi;
      i.value = r.plan[name];
      inputs[name] = i;
      body.append(field(`${label} (${lo}–${hi})`, i));
    }
    let picked = null;
    if (key === 'important') picked = await importantPicker(body, s);
    if (s && s.names && s.names[key] && s.names[key].length)
      body.append(
        make('b', '', `Names (${s.rows[key].count})`),
        make('p', 'cr-names', s.names[key].join(', ')),
      );
    if (r.giki && r.giki.people)
      body.append(
        make('b', '', 'Sharing'),
        make(
          'p',
          'cr-names',
          r.giki.people.map((p) => `${p.name}: ${GIKI[p.step] || p.step}`).join(' · '),
        ),
      );
    if (s && key === 'group')
      body.append(make('b', '', 'Message'), make('p', 'cr-quote', s.messages.group));
    if (s && key !== 'group' && s.messages.dm && key !== 'volunteers')
      body.append(make('b', '', 'Message'), make('p', 'cr-quote', s.messages.dm));
    if (s && key === 'giki')
      body.append(make('b', '', 'Share question'), make('p', 'cr-quote', s.messages.question));
    const locked = data.status === 'running';
    if (locked) body.append(make('p', 'cr-warn', 'The plan is running. Pause all to change it.'));
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

  function prepareSheet() {
    const body = make('div', 'cr-sum');
    const rows = [
      ['case', 'Case ready', 'Case Writer', () => window.CaseWriter?.open?.()],
      ['poster', 'Poster ready', 'Open Settings (poster)', press('gear')],
      ['group', 'Group messages checked', 'Open group message', () => Nav.go('preview')],
      ['donor', 'Donor messages checked', 'Open donor messages', donors('messages')],
    ];
    for (const [key, label, open, fn] of rows) {
      const state = data.checks[key];
      const row = make('div', 'cr-check-row');
      row.dataset.s = state;
      row.append(
        make('b', '', label),
        make(
          'span',
          'cr-pill',
          state === 'ok' ? 'Ready' : state === 'again' ? 'Check again' : 'Not yet',
        ),
      );
      const acts = make('div', 'cr-row-actions');
      acts.append(btn(open, 'cr-more', () => (sheet.close(), fn())));
      if (key === 'group' || key === 'donor')
        acts.append(
          btn('Mark checked', 'cr-act', async () => {
            try {
              take(await post({ action: 'check', name: key }));
              sheet.close();
              prepareSheet();
            } catch (e) {
              $('csError').textContent = e.message;
            }
          }),
        );
      row.append(acts);
      body.append(row);
    }
    body.append(
      make(
        'p',
        'cr-sub',
        'Save Base makes five wording versions; read them with Next and use Test to send three different versions to your test group. Then mark the messages checked. If the wording changes later they show “Check again”.',
      ),
    );
    const vol = btn(
      'Open the volunteer sharing request',
      'cr-more',
      () => (sheet.close(), donors('volunteers')()),
    );
    body.append(vol);
    openSheet('Prepare case', body, [['Done', 'cr-go', null]]);
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
    ['Donors', donors()],
    ['Messages (versions, edit, test)', () => Nav.go('preview')],
    ['Message screen and send', () => Nav.go('')],
    ['Case Writer', () => window.CaseWriter?.open?.()],
    ['Notes', press('donorNotesShortcut')],
    ['Chat', press('chatOpen')],
    ['Find groups', () => (location.href = '/new/group-finder')],
    ['Reports', () => document.querySelector('.report-open')?.click()],
    ['Settings', press('gear')],
  ];
  for (const [label, fn] of TOOLS)
    $('crMenu').append(
      btn(label, 'cr-tool', () => {
        $('crTools').open = false;
        fn();
      }),
    );

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
      if ((d.status === 'running' || d.status === 'paused') && path() === '')
        Nav.go('case', { replace: true });
      else sync();
    } catch (e) {
      sync();
    }
  })();
})();
