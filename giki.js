/* /giki only. The screen itself is the Volunteers screen (donors.js), pointed at the Giki list. This file adds what is
   specific to the Giki WhatsApp: its connect button, the Timer sheet, Add many, and "stay on this screen". */
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
  const HOME = 'donors/volunteers';
  const CLOCK =
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/></svg>';
  const FIELDS = [
    // [field, label, lowest, highest, step of the − / + buttons]
    ['gap_minutes', 'Minutes between DMs', 1, 10, 1],
    ['batch_size', 'DMs per batch', 1, 20, 1],
    ['rest_minutes', 'Rest between batches', 1, 120, 5],
  ];

  async function call(url, body) {
    const r = await fetch(
      url,
      body === undefined
        ? {}
        : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
    );
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.error) throw Error(d.error || 'That did not work. Nothing was changed.');
    return d;
  }
  const changed = () => document.dispatchEvent(new Event('donors-changed'));
  function say(text, error = false) {
    const n = $('donorNotice');
    if (!n) return;
    n.textContent = '';
    n.dataset.error = error;
    n.append(make('span', '', text));
    clearTimeout(say.t);
    say.t = setTimeout(() => (n.textContent = ''), 4500);
  }

  /* ---------------------------------------------------------------- stay on this screen */
  function stay() {
    if (!Nav.path().startsWith(HOME)) Nav.go(HOME, { replace: true });
  }
  for (const e of ['hashchange', 'popstate', 'studio-navigate'])
    addEventListener(e, () => setTimeout(stay, 30));

  /* ---------------------------------------------------------------- the sheet (same look as the Case page sheet) */
  const sheet = make('dialog', 'case-sheet');
  sheet.id = 'gikiSheet';
  sheet.innerHTML =
    '<header><span class="cr-grab" aria-hidden="true"></span><h2 id="csTitle"></h2></header><div id="csBody"></div><p id="csError" class="cr-error" role="alert"></p><footer id="csFoot"></footer>';
  document.body.append(sheet);
  sheet.addEventListener('click', (e) => e.target === sheet && sheet.close());
  let onClose = null;
  sheet.addEventListener('close', () => {
    const f = onClose;
    onClose = null;
    f?.();
  });
  function setFoot(buttons) {
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
          if (!keep && out !== false) sheet.close(); // a run that answers false keeps the sheet as it is
        } catch (e) {
          $('csError').textContent = e.message;
        } finally {
          for (const x of foot.children) x.disabled = false;
        }
      };
      foot.append(b);
    }
    return foot;
  }
  function openSheet(title, body, buttons, closed) {
    $('csTitle').textContent = title;
    $('csBody').replaceChildren(body);
    $('csError').textContent = '';
    if (!buttons.some((b) => !b[2])) buttons = [...buttons, ['Close', 'cr-soft', null]];
    setFoot(buttons);
    onClose = closed || null;
    if (!sheet.open) sheet.showModal();
  }

  /* ---------------------------------------------------------------- the Giki WhatsApp: status bar + connect sheet */
  let line = { state: 'unknown', tail: '' },
    pollTimer = 0;
  const bar = make('div', 'giki-bar');
  const chip = btn('', 'giki-chip', () => connectSheet());
  chip.id = 'gikiWa';
  bar.append(make('h1', 'giki-title', 'Giki'), chip);
  function paintChip() {
    const ready = line.state === 'ready';
    chip.dataset.ok = ready ? '1' : '0';
    chip.replaceChildren(
      make('span', 'cr-dot'),
      make(
        'span',
        '',
        ready
          ? 'WhatsApp' + (line.tail ? ' · …' + line.tail : '')
          : line.state === 'dropped'
            ? 'WhatsApp · reconnecting'
            : line.state === 'unknown'
              ? 'WhatsApp · checking'
              : 'Connect WhatsApp',
      ),
    );
    chip.setAttribute(
      'aria-label',
      ready ? 'Giki WhatsApp is connected' : 'Giki WhatsApp: tap to connect',
    );
  }
  async function refreshLine() {
    try {
      line = (await call('/giki/wa')).line || line;
    } catch (e) {
      line = { ...line, state: line.state === 'ready' ? 'ready' : 'unknown' };
    }
    paintChip();
    return line;
  }
  function mount() {
    const shell = $('donorsPage')?.querySelector('.donor-shell');
    if (shell && !shell.contains(bar)) shell.prepend(bar);
  }
  paintChip();
  const tick = () => {
    clearTimeout(pollTimer);
    if (!document.hidden) refreshLine();
    pollTimer = setTimeout(tick, line.state === 'ready' ? 20000 : 8000);
  };
  addEventListener('studio-unlocked', tick);
  addEventListener('focus', () => refreshLine());
  tick();

  function connectSheet() {
    const body = make('div', 'cr-sum gk-connect');
    const state = make('p', 'gk-state');
    state.setAttribute('role', 'status');
    const warn = make('p', 'cr-warn');
    warn.hidden = true;
    const link = make('div', 'gk-link');
    /* the two ways to link */
    const seg = make('div', 'cr-seg');
    const panes = { code: make('div', 'cr-pane'), qr: make('div', 'cr-pane') };
    const show = (name) => {
      for (const [k, p] of Object.entries(panes)) p.hidden = k !== name;
      for (const b of seg.children) b.dataset.on = b.dataset.k === name ? '1' : '0';
    };
    for (const [k, label] of [
      ['code', 'Phone number'],
      ['qr', 'QR code'],
    ]) {
      const b = btn(label, 'cr-seg-b', () => show(k));
      b.dataset.k = k;
      seg.append(b);
    }
    /* phone number: a code to type into WhatsApp (works on the same phone) */
    const phone = make('input', 'gk-input');
    phone.type = 'tel';
    phone.inputMode = 'tel';
    phone.autocomplete = 'off';
    phone.name = 'giki_wa_number';
    phone.id = 'gikiPhone';
    phone.placeholder = '0300 1234567';
    phone.setAttribute('aria-label', 'WhatsApp number to connect');
    const phoneLabel = make('label', 'gk-label', 'WhatsApp number to connect');
    phoneLabel.htmlFor = 'gikiPhone';
    const code = make('div', 'gk-code');
    code.hidden = true;
    code.setAttribute('aria-live', 'polite');
    const steps = make('ol', 'gk-steps');
    steps.hidden = true;
    for (const t of [
      'Open WhatsApp on that phone.',
      'Settings → Linked devices → Link a device.',
      'Tap “Link with phone number instead”.',
      'Type the code above.',
    ])
      steps.append(make('li', '', t));
    const getCode = btn('Get code', 'cr-go gk-wide', async () => {
      getCode.disabled = true;
      $('csError').textContent = '';
      try {
        const d = await call('/giki/wa', { action: 'code', phone: phone.value });
        code.textContent = d.code;
        code.hidden = steps.hidden = false;
        getCode.textContent = 'Get a new code';
        watch();
      } catch (e) {
        $('csError').textContent = e.message;
      } finally {
        getCode.disabled = false;
      }
    });
    panes.code.append(phoneLabel, phone, getCode, code, steps);
    /* QR: for scanning from another phone */
    const qrImg = make('img', 'gk-qr');
    qrImg.alt = 'QR code to link the Giki WhatsApp';
    qrImg.hidden = true;
    const qrNote = make(
      'p',
      'cr-sub',
      'Scan this from the phone you want to connect, using another phone or a computer screen.',
    );
    let qrUntil = 0,
      qrTimer = 0;
    const showQr = btn('Show QR code', 'cr-more gk-wide', async () => {
      showQr.disabled = true;
      $('csError').textContent = '';
      try {
        const d = await call('/giki/wa', { action: 'qr' });
        qrImg.src = d.qr;
        qrImg.hidden = false;
        qrUntil = Date.now() + Math.max(1, Number(d.duration) || 30) * 1000;
        showQr.textContent = 'Refresh QR code';
        watch();
      } catch (e) {
        $('csError').textContent = e.message;
      } finally {
        showQr.disabled = false;
      }
    });
    qrTimer = setInterval(() => {
      if (qrUntil && Date.now() > qrUntil) {
        qrUntil = 0;
        qrImg.hidden = true;
        showQr.textContent = 'Show QR code';
      }
    }, 1000);
    panes.qr.append(qrNote, showQr, qrImg);
    link.append(seg, panes.code, panes.qr);
    show('code');
    const drop = btn('Reconnect', 'cr-more gk-wide', async () => {
      drop.disabled = true;
      try {
        await call('/giki/wa', { action: 'reconnect' });
      } catch (e) {
        $('csError').textContent = e.message;
      }
      drop.disabled = false;
      await paint();
    });
    drop.hidden = true;
    const ready = make(
      'p',
      'cr-sub',
      'Giki messages go out from this WhatsApp. Your main WhatsApp is not used here.',
    );
    ready.hidden = true;
    body.append(state, warn, link, drop, ready);

    let watching = 0;
    function watch() {
      clearInterval(watching);
      watching = setInterval(async () => {
        if (!sheet.open) return clearInterval(watching);
        await paint();
        if (line.state === 'ready') clearInterval(watching);
      }, 3000);
    }
    async function paint() {
      await refreshLine();
      const up = line.state === 'ready';
      state.dataset.ok = up ? '1' : '0';
      state.textContent = up
        ? '✓ Connected' + (line.tail ? ' · number ends …' + line.tail : '')
        : line.state === 'dropped'
          ? 'The link dropped. Tap Reconnect.'
          : line.state === 'unknown'
            ? 'Checking…'
            : 'Not connected yet.';
      link.hidden = up || line.state === 'dropped';
      drop.hidden = line.state !== 'dropped';
      ready.hidden = !up;
      warn.hidden = !line.same_as_main;
      warn.textContent = line.same_as_main
        ? 'This is the same WhatsApp as your main one. Disconnect it and connect a different number.'
        : '';
      const linked = up || line.state === 'dropped';
      setFoot([
        ...(linked
          ? [
              [
                'Disconnect',
                'cr-end',
                async () => {
                  if (line.sending) throw Error('Stop the Giki DMs first, then disconnect.');
                  if (
                    !confirm(
                      'Disconnect the Giki WhatsApp? Giki DMs will not send until you connect it again.',
                    )
                  )
                    return false;
                  await call('/giki/wa', { action: 'logout', confirm: true });
                  await paint();
                  return false;
                },
                true,
              ],
            ]
          : []),
        ['Close', 'cr-soft', null],
      ]);
    }
    openSheet('Giki WhatsApp', body, [['Close', 'cr-soft', null]], () => {
      clearInterval(watching);
      clearInterval(qrTimer);
    });
    paint();
    if (line.state !== 'ready') watch();
  }

  /* ---------------------------------------------------------------- Timer: the same sheet as the Case page */
  async function timerSheet(tab = 'timing') {
    const body = make('div', 'cr-sum'),
      loading = make('p', 'cr-sub', 'Loading…');
    openSheet('Giki', loading, [['Close', 'cr-soft', null]]);
    let view;
    try {
      view = await call('/giki/volunteers');
    } catch (e) {
      $('csError').textContent = e.message;
      return;
    }
    const names = (view.items || []).map((x) => x.name);
    const panes = {
      message: make('div', 'cr-pane'),
      timing: make('div', 'cr-pane'),
      people: make('div', 'cr-pane'),
    };
    const seg = make('div', 'cr-seg');
    const running =
      view.delivery && ['Starting', 'Sending', 'Waiting'].includes(view.delivery.state);
    let save = null;
    const show = (name) => {
      for (const [k, p] of Object.entries(panes)) p.hidden = k !== name;
      const lit = name === 'people' ? 'timing' : name;
      for (const b of seg.children) b.dataset.on = b.dataset.k === lit ? '1' : '0';
      if (save) save.hidden = name === 'message';
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
    /* Message: the Giki message (the same one as the box on the page) */
    const text = (view.message || '').trim();
    const block = make('div', 'cr-block');
    block.append(make('b', '', 'Giki message'));
    block.append(make('p', text ? 'cr-quote' : 'cr-sub', text || 'Nothing written yet.'));
    block.append(
      btn(text ? 'Edit message' : 'Add message', text ? 'cr-more' : 'cr-act', () =>
        editSheet(view.message || ''),
      ),
    );
    panes.message.append(block);
    /* Settings: plain rows and − / + buttons so nothing needs typing */
    const inputs = {};
    for (const [name, label, lo, hi, step] of FIELDS) {
      const i = make('input', 'cr-num');
      i.type = 'number';
      i.min = lo;
      i.max = hi;
      i.inputMode = 'numeric';
      i.value = view.pace[name];
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
      const row = make('div', 'cr-set-row');
      row.append(make('span', '', label), stepper);
      panes.timing.append(row);
    }
    /* The Giki page's own choices (groups and DMs keep theirs); the files are the group message's */
    let extras = {};
    try {
      extras = await call('/group-extras');
    } catch (e) {}
    const saveGiki = async (field, value) => {
      try {
        extras = await call('/group-extras', { action: 'setup', profile: 'giki', field, value });
        paintGiki();
      } catch (e) {
        $('csError').textContent = e.message;
      }
    };
    const textRow = make('div', 'cr-set-row gk-text-on');
    const pick = make('div', 'gk-pick');
    for (const [v, label] of [
      ['video', 'Video'],
      ['poster', 'Poster'],
    ]) {
      const b = btn(label, 'cr-seg-b', () => saveGiki('text_on', v));
      b.dataset.v = v;
      b.setAttribute('aria-label', 'Case goes with the ' + label.toLowerCase());
      pick.append(b);
    }
    textRow.append(make('span', '', 'Case goes with'), pick);
    /* 2nd and 3rd messages: the poster pic and the PDF (both added on the group message page), each with its tick */
    const NAME = { poster: 'Poster pic', pdf: 'PDF' };
    const row2 = make('div', 'cr-set-row gk-msg2');
    const pick2 = make('div', 'gk-pick');
    for (const k of ['poster', 'pdf']) {
      const b = btn(NAME[k], 'cr-seg-b', () =>
        saveGiki('order', k === 'poster' ? 'poster_pdf' : 'pdf_poster'),
      );
      b.dataset.v = k;
      b.setAttribute('aria-label', '2nd message: ' + NAME[k]);
      pick2.append(b);
    }
    const tick = (id) => {
      const lab = make('label', 'gk-tick');
      const cb = make('input');
      cb.type = 'checkbox';
      cb.id = id;
      lab.append(cb, make('span', '', 'Send'));
      return { lab, cb };
    };
    const t2 = tick('gikiTick-2'),
      t3 = tick('gikiTick-3');
    row2.append(make('span', '', '2nd message'), pick2, t2.lab);
    const row3 = make('div', 'cr-set-row gk-msg3');
    const name3 = make('b', 'gk-name3');
    row3.append(make('span', '', '3rd message'), name3, t3.lab);
    let second = 'poster',
      third = 'pdf';
    t2.cb.onchange = () => saveGiki(second, t2.cb.checked);
    t3.cb.onchange = () => saveGiki(third, t3.cb.checked);
    function paintGiki() {
      const g = (extras.setup && extras.setup.giki) || { text_on: 'video', order: 'poster_pdf' };
      for (const b of pick.children) b.dataset.on = b.dataset.v === g.text_on ? '1' : '0';
      second = g.order === 'pdf_poster' ? 'pdf' : 'poster';
      third = second === 'pdf' ? 'poster' : 'pdf';
      for (const b of pick2.children) b.dataset.on = b.dataset.v === second ? '1' : '0';
      name3.textContent = NAME[third];
      for (const [t, k] of [
        [t2, second],
        [t3, third],
      ]) {
        const has = !!(extras[k] && extras[k].has); // added on the group message page
        t.cb.checked = !!g[k] && has;
        t.cb.disabled = !has;
        t.lab.title = has ? '' : 'Not added yet: add the ' + NAME[k] + ' on the group message page';
        t.lab.dataset.missing = has ? '0' : '1';
      }
    }
    paintGiki();
    panes.timing.prepend(textRow, row2, row3);
    const people = btn('', 'cr-set-row cr-set-link', () => show('people'));
    people.append(make('span', '', 'People'), make('span', 'cr-set-val', String(names.length)));
    panes.timing.append(people);
    panes.people.append(
      btn('Back to settings', 'cr-tx cr-back', () => show('timing')),
      names.length ? make('p', 'cr-names', names.join(', ')) : make('p', 'cr-sub', 'No one yet.'),
    );
    if (running)
      body.append(
        make('p', 'cr-warn', 'DMs are going out now. A new timer starts with the next DM all.'),
      );
    $('csBody').replaceChildren(body);
    const foot = setFoot([
      [
        'Save',
        'cr-go',
        async () => {
          const pace = { action: 'pace' };
          for (const [n, i] of Object.entries(inputs)) pace[n] = Number(i.value);
          await call('/giki/volunteers', pace);
          changed();
          say('Timer saved. DM all uses it.');
        },
      ],
      ['Close', 'cr-soft', null],
    ]);
    save = foot.firstElementChild;
    show(tab);
  }
  function editSheet(current) {
    const ta = make('textarea', 'cr-text');
    ta.rows = 10;
    ta.value = current;
    ta.placeholder = 'What should the Giki list share?  ({name} becomes their name)';
    ta.setAttribute('aria-label', 'Giki message');
    openSheet('Giki message', ta, [
      [
        'Save',
        'cr-go',
        async () => {
          await call('/giki/volunteers', { action: 'message', text: ta.value });
          /* the (hidden) box on the page is what DM Share and DM all read: keep it the same as what was saved */
          const box = $('volMessage');
          if (box) box.value = ta.value.trim();
          changed();
          say('Message saved.');
        },
      ],
      ['Close', 'cr-soft', null],
    ]);
    ta.focus({ preventScroll: true });
  }

  /* ---------------------------------------------------------------- Add many: a list of names and numbers */
  function importSheet() {
    const body = make('div', 'cr-sum');
    body.append(
      make(
        'p',
        'cr-sub',
        'Choose the list file, or paste names and numbers. Nothing is added until you tap Add.',
      ),
    );
    const pick = make('label', 'cr-more gk-file', 'Choose a file');
    const file = make('input');
    file.type = 'file';
    file.accept = '.md,.txt,.csv,text/plain,text/markdown,text/csv';
    file.hidden = true;
    pick.append(file);
    const ta = make('textarea', 'cr-text');
    ta.rows = 7;
    ta.placeholder = 'Name 0300 1234567\nAnother Name +92 321 7654321';
    ta.setAttribute('aria-label', 'Names and numbers');
    const result = make('p', 'cr-sub');
    result.setAttribute('role', 'status');
    let checked = '';
    file.onchange = async () => {
      const f = file.files[0];
      if (!f) return;
      if (f.size > 200000) {
        $('csError').textContent = 'This file is too big. Use a list of up to 300 people.';
        return;
      }
      ta.value = await f.text();
      pick.firstChild.nodeValue = f.name;
      ta.dispatchEvent(new Event('input'));
    };
    body.append(pick, ta, result);
    const check = async () => {
      const d = await call('/giki/volunteers', { action: 'import', text: ta.value, dry_run: true });
      checked = ta.value;
      result.textContent =
        d.found +
        ' found · ' +
        d.added +
        ' new' +
        (d.existing ? ' · ' + d.existing + ' already in the list' : '') +
        (d.own ? ' · your own number left out' : '') +
        (d.problems ? ' · ' + d.problems + ' line(s) skipped' : '') +
        '.';
      foot(d.added);
    };
    const add = async () => {
      const d = await call('/giki/volunteers', { action: 'import', text: checked });
      changed();
      say(d.reply);
    };
    const foot = (n) => {
      setFoot(
        n
          ? [
              ['Add ' + n + (n === 1 ? ' number' : ' numbers'), 'cr-go', add],
              ['Close', 'cr-soft', null],
            ]
          : [
              ['Check list', 'cr-go', check, true],
              ['Close', 'cr-soft', null],
            ],
      );
    };
    ta.addEventListener('input', () => {
      if (checked && ta.value !== checked) {
        checked = '';
        result.textContent = '';
        foot(0);
      }
    });
    openSheet('Add many', body, [['Close', 'cr-soft', null]]);
    foot(0);
  }

  async function sendTest(button) {
    const box = $('volMessage');
    button.disabled = true;
    button.textContent = 'Sending…';
    try {
      const r = await call('/giki/volunteers', { action: 'test', text: box ? box.value : '' });
      say(r.reply);
    } catch (e) {
      say(e.message, true);
    } finally {
      button.disabled = false;
      button.textContent = 'Test';
    }
  }

  /* ---------------------------------------------------------------- put the buttons where Msgs / + Add live */
  function arrange() {
    for (const bar2 of document.querySelectorAll('#donorsPage .vol-foot')) {
      /* Msgs (the donors' DM bank) is not part of the Giki list: the Timer takes its place in the bar */
      if (!bar2.querySelector(':scope > .giki-timer')) {
        const t = btn('', 'ui2-msgs-bottom giki-timer', () => timerSheet());
        t.innerHTML = CLOCK + '<span>Timer</span>';
        t.setAttribute('aria-label', 'Timer: minutes between DMs, DMs per batch, rest');
        bar2.append(t);
      }
    }
    /* The big message box is hidden. One short line stands in for it: what the share message says, Edit, Test. */
    for (const card of document.querySelectorAll('#donorsPage .vol-msg')) {
      let row = card.querySelector(':scope > .giki-share');
      if (!row) {
        row = make('div', 'giki-share');
        const text = make('div', 'giki-share-text');
        text.append(make('b', '', 'Share message'), make('span', 'giki-share-line'));
        const edit = btn('Edit', 'tool giki-edit', () =>
          editSheet(($('volMessage')?.value || '').trim()),
        );
        const test = btn('Test', 'tool giki-test', () => sendTest(test));
        test.title = 'Send the whole DM (case, then your share message) to your own WhatsApp';
        test.setAttribute(
          'aria-label',
          'Test: send the case and the share message to my own WhatsApp',
        );
        row.append(text, edit, test);
        card.prepend(row);
      }
      const now = ($('volMessage')?.value || '').trim();
      const line = row.querySelector('.giki-share-line'),
        shown = now ? now.replace(/\s+/g, ' ') : 'Not written yet';
      if (line.textContent !== shown) line.textContent = shown;
      row.querySelector('.giki-edit').textContent = now ? 'Edit' : 'Write';
      row
        .querySelector('.giki-edit')
        .setAttribute('aria-label', now ? 'Edit the share message' : 'Write the share message');
    }
    for (const form of document.querySelectorAll('#donorsPage .vol-add')) {
      if (!form.querySelector('.giki-many')) {
        const many = btn('Add many', 'giki-many', importSheet);
        form.append(many);
      }
    }
  }
  /* the Volunteers screen is rebuilt after every change: put the buttons back, at most once per frame */
  let frame = 0;
  const refit = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      mount();
      arrange();
    });
  };
  new MutationObserver(refit).observe($('donorsPage'), { childList: true, subtree: true });
  mount();
  arrange();
  stay();
})();
