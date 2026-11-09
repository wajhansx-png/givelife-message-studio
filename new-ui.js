/* Redesign helpers, loaded only at /new. They move or relabel existing controls; nothing here sends anything. */
(() => {
  function arrangeReader() {
    const screen = document.getElementById('messageFocus');
    const workspace = screen?.querySelector('.focus-workspace');
    const paper = workspace?.querySelector('.focus-paper');
    const rail = workspace?.querySelector('.focus-rail');
    if (!screen || !workspace || !paper || !rail || screen.dataset.ui2Layout) return;
    const header = screen.querySelector(':scope > header');
    const top = document.createElement('div');
    top.className = 'ui2-reader-top';
    const status = document.getElementById('focusState');
    if (status) status.classList.add('ui2-reader-status', 'sr-only');
    const version = document.getElementById('focusVersion');
    const back = document.getElementById('focusBack');
    if (!version || !back) return;
    const backTop = document.createElement('button');
    backTop.type = 'button';
    backTop.className = 'back-action ui2-reader-back';
    backTop.textContent = '← Back';
    backTop.setAttribute('aria-label', 'Back to messages');
    backTop.addEventListener('click', () => back.click());
    top.append(backTop, version);
    header?.prepend(top);

    const actions = document.createElement('div');
    actions.className = 'ui2-reader-actions';
    for (const id of ['focusNext', 'focusTest']) {
      const button = document.getElementById(id);
      if (button) actions.append(button);
    }
    const more = rail.querySelector('.focus-rail-more');
    if (more) actions.append(more);
    paper.after(actions);

    const dock = document.createElement('nav');
    dock.className = 'ui2-reader-dock';
    dock.setAttribute('aria-label', 'Message actions');
    for (const id of ['focusEdit', 'focusCopy', 'focusSave', 'focusBack']) {
      const button = document.getElementById(id);
      if (button) dock.append(button);
    }
    screen.append(dock);
    screen.dataset.ui2Layout = '1';
  }
  function arrangeStatus() {
    const app = document.querySelector('.app');
    const live = document.getElementById('live');
    const brand = app?.querySelector(':scope > .brandbar');
    if (!app || !live || !brand || document.querySelector('.ui2-status-row')) return;
    const whatsapp = document.getElementById('whatsappConnection');
    const amount = document.getElementById('leftChip');
    if (!whatsapp || !amount) return;
    whatsapp.setAttribute('aria-label', 'WhatsApp status');
    whatsapp.title = 'WhatsApp status';
    const row = document.createElement('div');
    row.className = 'ui2-status-row';
    row.append(whatsapp, amount);
    live.before(row);
  }
  const run = () => {
    arrangeReader();
    arrangeStatus();
  };
  run();
  new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
})();

/* 1. The home screen itself now shows the message beside the send list on a computer (see "Home" below),
   so it no longer jumps into the full-screen reader. */

/* 2. DM speed dialog (PDF page 24, V4 page 21): How fast? Slow / Normal / Fast, the four wait times, one summary
   line, and everything else folded under "More options (poster, follow-up, vary gap, test DM)".
   Every choice still sets the dialog's own fields, so saving and sending are unchanged. */
(() => {
  const LABELS = {
    batchCount: 'How many people',
    batchLimit: 'DMs in each batch',
    batchPause: 'Rest between batches',
  };
  const PRESETS = [
    ['slow', 'Slow', 8, '10', '30'],
    ['normal', 'Normal', 4, '20', '20'],
    ['fast', 'Fast', 2, '20', '20'],
  ];
  const $ = (id) => document.getElementById(id);
  const mk = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const set = (sel, v) => {
    if (!sel || sel.value === v) return;
    sel.value = v;
    sel.dispatchEvent(new Event('input', { bubbles: true }));
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  };
  function build(picker) {
    const form = $('donorBatchForm'),
      gapRow = picker.querySelector('.bm-gap');
    if (!form || !gapRow || $('ui2Speed')) return;
    const close = mk('button', 'ui2-x', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close');
    close.addEventListener('click', () => $('batchCancel')?.click());
    picker.prepend(close);
    const speed = mk('div', 'bm-row ui2-speed');
    speed.id = 'ui2Speed';
    speed.append(mk('label', '', 'How fast?'));
    const row = mk('div', 'ui2-speed-row');
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', 'How fast');
    for (const [key, label, gap, per, rest] of PRESETS) {
      const b = mk('button', 'ui2-speed-btn', label);
      b.type = 'button';
      b.dataset.speed = key;
      b.addEventListener('click', () => {
        picker.querySelector(`.batch-gap-btn[data-gap="${gap}"]`)?.click();
        set($('batchLimit'), per);
        set($('batchPause'), rest);
        paint();
      });
      row.append(b);
    }
    speed.append(row);
    gapRow.before(speed);
    const sum = mk('p', 'ui2-speed-sum');
    sum.id = 'ui2SpeedSum';
    gapRow.after(sum);
    const more = mk('details', 'ui2-speed-more');
    more.id = 'ui2SpeedMore';
    more.innerHTML = '<summary>More options (poster, follow-up, vary gap, test DM)</summary><div></div>';
    const box = more.querySelector('div');
    for (const id of ['batchLimit', 'batchPause']) {
      const r = $(id)?.closest('.bm-row');
      if (r) box.append(r);
    }
    const custom = mk('button', 'ui2-custom-gap', 'Custom wait…');
    custom.type = 'button';
    custom.addEventListener('click', () => picker.querySelector('.batch-gap-btn[data-gap="custom"]')?.click());
    box.append(custom);
    for (const id of ['batchPauseCustom', 'batchEachRow', 'batchChips', 'batchRandomRow']) if ($(id)) box.append($(id));
    const test = [...picker.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Test DM');
    if (test) box.append(test);
    sum.after(more);
    for (const el of [gapRow, $('batchLimit'), $('batchPause')])
      el?.addEventListener('click', () => setTimeout(paint));
    for (const id of ['batchLimit', 'batchPause', 'batchGap']) $(id)?.addEventListener('change', paint);
  }
  function paint() {
    const per = $('batchLimit')?.value,
      rest = $('batchPause'),
      gapBtn = document.querySelector('#donorBatchPicker .batch-gap-btn[aria-pressed="true"]');
    const gap = gapBtn?.dataset.gap;
    for (const b of document.querySelectorAll('.ui2-speed-btn')) {
      const p = PRESETS.find((x) => x[0] === b.dataset.speed);
      b.setAttribute('aria-pressed', String(String(p[2]) === gap && p[3] === per && p[4] === rest?.value));
    }
    const sum = $('ui2SpeedSum');
    if (sum && rest) {
      const restText = rest.selectedOptions[0]?.textContent || '';
      const text = per + ' per batch, then rest ' + restText.replace(/…$/, '');
      if (sum.textContent !== text) sum.textContent = text;
    }
  }
  function relabel() {
    const picker = $('donorBatchPicker');
    if (!picker) return;
    build(picker);
    for (const [id, text] of Object.entries(LABELS)) {
      const l = picker.querySelector('label[for="' + id + '"]');
      if (l && l.textContent !== text) l.textContent = text;
    }
    const start = $('batchStart');
    const title = picker.querySelector('h2');
    if (start && start.textContent === 'Save gap') start.textContent = 'Save speed';
    const speedOnly = start && start.textContent === 'Save speed';
    if (title) {
      const want = speedOnly ? 'DM speed' : 'Send DMs';
      if (title.textContent !== want) title.textContent = want;
    }
    picker.toggleAttribute('data-ui2-speed-only', !!speedOnly);
    paint();
  }
  new MutationObserver(relabel).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  relabel();
})();

/* 3. Computer: Back (left), DM ★ Important (middle), Options (right) holding Gap, Test DM, Auto, Poster and
   "Send with follow-up" (V4 page 40). Below 900px the controls go back where they were. */
(() => {
  const wide = matchMedia('(min-width: 900px)');
  const IDS = ['donorPace', 'donorTest'];
  const LABELS = ['donorAuto', 'donorRowPoster'];
  let moved = [];
  let follow = null;
  function nodes(bar) {
    const out = IDS.map((id) => document.getElementById(id));
    for (const id of LABELS) out.push(document.querySelector('label[for="' + id + '"]'));
    return out.filter((n) => n && bar.contains(n));
  }
  function build(bar) {
    if (document.getElementById('ui2Options')) return;
    const box = document.createElement('details');
    box.id = 'ui2Options';
    box.className = 'ui2-options';
    box.innerHTML =
      '<summary aria-label="Options">Options ▾</summary><div class="ui2-options-panel"></div>';
    const panel = box.querySelector('div');
    moved = nodes(bar).map((n) => [n, [...bar.children].indexOf(n)]);
    for (const [n] of moved) panel.append(n);
    const fu = document.getElementById('donorFollowUpOpt');
    if (fu) {
      follow = [fu, fu.parentElement, fu.nextSibling];
      panel.append(fu);
    }
    bar.append(box);
    box.addEventListener('keydown', (e) => e.key === 'Escape' && (box.open = false));
    document.addEventListener('pointerdown', (e) => {
      if (box.open && !box.contains(e.target)) box.open = false;
    });
  }
  function restore(bar) {
    const box = document.getElementById('ui2Options');
    if (!box) return;
    for (const [n, i] of moved.sort((a, b) => a[1] - b[1]))
      bar.insertBefore(n, bar.children[i] || null);
    if (follow) follow[1].insertBefore(follow[0], follow[2]);
    follow = null;
    box.remove();
    moved = [];
  }
  function sync() {
    const bar = document.querySelector('.donor-bottom');
    if (!bar) return;
    if (wide.matches) build(bar);
    else restore(bar);
  }
  wide.addEventListener('change', sync);
  new MutationObserver(sync).observe(document.body, { childList: true, subtree: true });
  sync();
})();

/* 4. DM messages page (PDF page 25): one row Edit, Copy, ⋯, Back. Next, Regenerate, Test, Bold, Italic and
   Base message live inside ⋯ and press the real buttons. */
(() => {
  const mk = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  function proxy(label, sel) {
    const b = mk('button', 'tool ui2-proxy', label);
    b.type = 'button';
    b.dataset.ui2Proxy = sel;
    b.addEventListener('click', () => document.querySelector(sel)?.click());
    return b;
  }
  function bank() {
    const box = document.querySelector('#donorMessages .bank-actions');
    if (!box) return;
    let more = box.querySelector('#ui2BankMore');
    if (!more) {
      more = mk('details', 'ui2-bank-more');
      more.id = 'ui2BankMore';
      more.innerHTML = '<summary aria-label="More: Next, Regenerate, Test, Bold, Italic, Base message">⋯</summary><div></div>';
      box.append(more);
      document.addEventListener('pointerdown', (e) => {
        if (more.open && !more.contains(e.target)) more.open = false;
      });
    }
    const panel = more.querySelector(':scope > div');
    if (!panel.querySelector('[data-ui2-proxy]')) {
      if (document.querySelector('#donorMessages .bank-next-arrow'))
        panel.append(proxy('Next ›', '#donorMessages .bank-next-arrow'));
      if (document.querySelector('#donorMessages .bank-gen-icon'))
        panel.append(proxy('↻ Regenerate', '#donorMessages .bank-gen-icon'));
    }
    for (const t of box.querySelectorAll(':scope > button.tool')) {
      const x = t.textContent.trim();
      if (x === 'Edit' || x === 'Done' || x === 'Copy') {
        t.style.setProperty('order', x === 'Copy' ? '2' : '1', 'important');
        continue;
      }
      panel.append(t);
    }
    const back = [...box.querySelectorAll('.bank-pagination button')].find((b) => /Back/.test(b.textContent));
    if (back) {
      box.querySelectorAll('.ui2-bank-back').forEach((o) => o !== back && o.remove());
      back.classList.add('ui2-bank-back');
      box.append(back);
    }
    if (!box.nextElementSibling?.classList.contains('ui2-bank-hint')) {
      const hint = mk('p', 'ui2-bank-hint', 'Base message · Test · Bold/Italic live inside ⋯');
      box.after(hint);
    }
  }
  new MutationObserver(bank).observe(document.body, { childList: true, subtree: true });
  bank();
})();

/* 5. Settings: grouped under four headings, with one line of help under the two switches that decide who gets DMs. */
(() => {
  function mk(text) {
    const h = document.createElement('div');
    h.className = 'ui2-set-head';
    h.textContent = text;
    return h;
  }
  function help(input, text) {
    const t = input?.closest('label')?.querySelector('.t');
    if (t && !t.querySelector('small')) {
      const s = document.createElement('small');
      s.textContent = text;
      t.append(s);
    }
  }
  function group() {
    const body = document.querySelector('#set .body');
    if (!body || body.querySelector('.ui2-set-head')) return;
    const rowOf = (id) => document.getElementById(id)?.closest('.row, label.row');
    const first = body.querySelector(':scope > .row, :scope > label.row');
    const spots = [
      [first, 'Look'],
      [rowOf('swDm'), 'Sending safety'],
      [rowOf('openMemory'), 'Tools'],
      [rowOf('waOut'), 'WhatsApp'],
    ];
    for (const [row, name] of spots) if (row) row.before(mk(name));
    help(document.getElementById('swDm'), 'Turn on only when you want the app to DM by itself');
    help(document.getElementById('swNew'), 'New donors get a DM automatically');
  }
  new MutationObserver(group).observe(document.body, { childList: true, subtree: true });
  group();
})();

/* 6. Stop DMs only shows while DMs are going out. "Resume DMs" and "Change resume" always stay visible. */
(() => {
  function sync() {
    const toggle = document.getElementById('donorToggle');
    const note = document.querySelector('#donorProgress > span');
    if (!toggle || !note) return;
    const idle = /^Idle/i.test(note.textContent.trim()) && toggle.textContent.trim() === 'Stop DMs';
    toggle.toggleAttribute('data-ui2-idle', idle);
  }
  new MutationObserver(sync).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  sync();
})();

/* 7. Home (PDF pages 1-9, 13). Phone: one bottom bar (Message, Donors, Chat, More) and a bottom sheet for the rest.
   Tablet: message and send list side by side. Computer: one top bar, today's message beside the send list,
   and the chat as one slim bar with quick chips. Every button below presses an existing control. */
(() => {
  const $ = (id) => document.getElementById(id);
  const press = (el) => () => el()?.click();
  const band = () => (innerWidth >= 900 ? 'desk' : innerWidth >= 700 ? 'tab' : 'phone');
  const mk = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  };

  /* Status pieces move to the top bar on a computer, to one line on a tablet, to two rows on a phone. */
  function placeStatus() {
    const row = document.querySelector('.ui2-status-row');
    const bar = document.querySelector('.app > .brandbar');
    const wa = $('whatsappConnection'),
      chip = $('leftChip'),
      live = $('live');
    if (!row || !bar || !wa || !chip || !live) return false;
    const b = band();
    if (b === 'desk') {
      const brand = bar.querySelector('.brand');
      if (wa.parentElement !== bar) brand.after(wa);
      if (live.parentElement !== bar) wa.after(live);
      const notes = $('donorNotesShortcut');
      if (chip.parentElement !== bar && notes) bar.insertBefore(chip, notes);
    } else {
      if (wa.parentElement !== row) row.prepend(wa);
      if (chip.parentElement !== row) wa.after(chip);
      if (b === 'tab' && live.parentElement !== row) row.append(live);
      if (b === 'phone' && live.previousElementSibling !== row) row.after(live);
    }
    document.body.dataset.ui2Band = b;
    return true;
  }
  /* "Rs. 25,000 left ✎" once, whether or not the app already wrote "left". */
  function markChip() {
    const chip = $('leftChip');
    if (chip) chip.dataset.ui2Left = /left/i.test(chip.textContent) ? '1' : '0';
  }

  /* Phone and tablet bottom bar. */
  function tabs() {
    const foot = document.querySelector('.app > .foot');
    if (!foot || $('ui2Tabs')) return;
    const nav = mk('nav', 'ui2-tabs');
    nav.id = 'ui2Tabs';
    nav.setAttribute('aria-label', 'Main');
    const items = [
      ['message', '✉', 'Message', () => (typeof Nav !== 'undefined' ? Nav.go('') : null)],
      ['donors', '♥', 'Donors', press(() => $('openDonors'))],
      ['chat', '✎', 'Chat', press(() => $('chatOpen'))],
      ['more', '⋯', 'More', () => sheet()],
    ];
    for (const [key, icon, label, fn] of items) {
      const b = mk('button', 'ui2-tab', `<span aria-hidden="true">${icon}</span>${label}`);
      b.type = 'button';
      b.dataset.tab = key;
      b.addEventListener('click', fn);
      nav.append(b);
    }
    foot.append(nav);
    paintTabs();
  }
  function paintTabs() {
    const path = typeof Nav !== 'undefined' ? Nav.path() : '';
    const on = path.startsWith('donors') ? 'donors' : path === 'chat' ? 'chat' : path ? '' : 'message';
    for (const b of document.querySelectorAll('.ui2-tab'))
      b.setAttribute('aria-current', String(b.dataset.tab === on));
  }

  /* More: a bottom sheet in thumb reach (page 2). */
  function sheet() {
    let d = $('ui2Sheet');
    if (!d) {
      d = mk('dialog', 'ui2-sheet');
      d.id = 'ui2Sheet';
      d.setAttribute('aria-label', 'More');
      d.innerHTML =
        '<div class="ui2-sheet-grip" aria-hidden="true"></div><div class="ui2-sheet-grid"></div><div class="ui2-sheet-extra"></div>';
      d.addEventListener('click', (e) => e.target === d && d.close());
      d.addEventListener('close', () => {
        const pick = d.querySelector('.case-pick');
        const home = document.querySelector('#mainNavMore .compact-nav-panel');
        if (pick && home) home.append(pick);
      });
      document.body.append(d);
    }
    const grid = d.querySelector('.ui2-sheet-grid');
    const extra = d.querySelector('.ui2-sheet-extra');
    grid.textContent = '';
    extra.textContent = '';
    const tile = (title, sub, fn) => {
      const b = mk('button', 'ui2-tile', `<b></b>${sub ? '<small></small>' : ''}`);
      b.type = 'button';
      b.querySelector('b').textContent = title;
      if (sub) b.querySelector('small').textContent = sub;
      b.addEventListener('click', () => {
        d.close();
        fn();
      });
      grid.append(b);
      return b;
    };
    const amount = ($('leftChip')?.textContent || 'Rs.').trim().replace(/\s*left$/i, '');
    tile(amount + ' left', 'change amount', press(() => $('leftChip')));
    const pick = document.querySelector('.case-pick');
    if (pick) {
      const sel = pick.querySelector('select');
      const t = mk('div', 'ui2-tile ui2-case', '<b>Case</b><small></small>');
      const name = () =>
        (t.querySelector('small').textContent =
          (sel?.selectedOptions[0]?.textContent || 'Current case').trim() + ' ▾');
      name();
      sel?.addEventListener('change', name);
      t.append(pick);
      grid.append(t);
    }
    tile('Reply', 'chat shortcuts', press(() => document.querySelector('.reply-open')));
    tile('Notes', '', press(() => $('donorNotesShortcut')));
    tile('Report', 'right-now board', press(() => document.querySelector('.report-open')));
    tile('Settings', '', press(() => $('gear')));
    const resume = document.querySelector('.resume-open');
    if (resume) {
      const r = mk('button', 'ui2-sheet-link', 'Resume messages');
      r.type = 'button';
      r.addEventListener('click', () => {
        d.close();
        resume.click();
      });
      extra.append(r);
    }
    d.showModal();
  }

  /* Send list: one line per group; timers and the single-group choice sit under the list (V4 page 7). */
  function sendList() {
    const box = document.querySelector('.group-send');
    const two = box?.querySelector('.group-two');
    const drop = $('dropFree'),
      tm = $('timerMain'),
      tf = $('timerFree');
    if (!two || !drop || !tm || !tf || $('ui2GroupMore')) return;
    const more = mk('div', 'ui2-group-more');
    more.id = 'ui2GroupMore';
    const later = mk('button', 'ui2-later', '◷ Later');
    later.type = 'button';
    later.id = 'ui2Later';
    later.setAttribute('aria-expanded', 'false');
    later.setAttribute('aria-controls', 'ui2LaterPanel');
    const wrap = mk('div', 'group-drop-wrap ui2-choose');
    const choose = mk('button', 'ui2-choose-btn', '▾ Choose group');
    choose.type = 'button';
    choose.setAttribute('aria-haspopup', 'true');
    choose.setAttribute('aria-expanded', 'false');
    choose.addEventListener('click', () => {
      $('btnFreePick')?.click();
      choose.setAttribute('aria-expanded', String(!drop.hidden));
    });
    wrap.append(choose, drop);
    more.append(later, wrap);
    const panel = mk('div', 'ui2-later-panel');
    panel.id = 'ui2LaterPanel';
    panel.hidden = true;
    for (const [row, name] of [
      [tm, 'GiveLife'],
      [tf, 'All freelance'],
    ]) {
      const line = mk('div', 'ui2-later-line', '<span></span>');
      line.querySelector('span').textContent = name;
      line.append(row);
      panel.append(line);
    }
    two.after(more, panel);
    const timers = () => [...document.querySelectorAll('.gb-timer')];
    later.addEventListener('click', () => {
      const open = panel.hidden;
      for (const t of timers()) if ((t.getAttribute('aria-expanded') === 'true') !== open) t.click();
      panel.hidden = !open;
      later.setAttribute('aria-expanded', String(open));
    });
    const paint = () => {
      const due = timers()
        .filter((t) => t.classList.contains('is-pending'))
        .map((t) => t.textContent.trim());
      const text = due.length ? '◷ Later · ' + due.join(', ') : '◷ Later';
      if (later.textContent !== text) later.textContent = text;
      if (!panel.hidden && tm.hidden && tf.hidden) {
        panel.hidden = true;
        later.setAttribute('aria-expanded', 'false');
      }
    };
    new MutationObserver(paint).observe(box, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['class', 'hidden'],
    });
    paint();
  }

  /* Computer: today's message with its style choices and keyboard letters; chat becomes a slim bar. */
  function desk() {
    const card = $('card'),
      tools = card?.querySelector('.tools');
    const talk = document.querySelector('#main-workspace .talk');
    const form = $('cmdForm'),
      log = $('log');
    if (!card || !tools || !talk || !form || !log || $('ui2Styles')) return;
    const styles = mk('div', 'ui2-styles');
    styles.id = 'ui2Styles';
    styles.setAttribute('role', 'group');
    styles.setAttribute('aria-label', 'Write a new message in another style');
    for (const [key, label] of [
      ['ur_en', 'Urdu + English'],
      ['ur_en_more', 'More Trigger'],
      ['en', 'English'],
      ['en_more', 'English Trigger'],
    ]) {
      const b = mk('button', '', label);
      b.type = 'button';
      b.dataset.style = key;
      b.title = 'Write a new message: ' + label;
      b.addEventListener('click', () => {
        Nav.go('preview');
        setTimeout(() => document.querySelector(`.focus-styles [data-style="${key}"]`)?.click(), 250);
      });
      styles.append(b);
    }
    tools.after(styles);
    const poster = $('previewChangePoster');
    const overflow = tools.querySelector('.overflow-tools > div');
    if (poster && overflow) overflow.prepend(poster);
    const reply = mk('button', 'ui2-last-reply');
    reply.type = 'button';
    reply.id = 'ui2LastReply';
    reply.hidden = true;
    reply.title = 'Open the full chat';
    reply.addEventListener('click', () => $('chatExpand')?.click());
    const chips = mk('div', 'ui2-chips ui2-desk-chips');
    talk.append(reply, chips);
    addChips(chips, $('cmd'), ['Amount left…', 'Send all', 'New wording']);
    const last = () => {
      const bots = log.querySelectorAll('.e.bot');
      const text = bots.length > 1 ? bots[bots.length - 1].textContent.trim().replace(/\s+/g, ' ') : '';
      reply.hidden = !text;
      reply.textContent = text.length > 150 ? text.slice(0, 149) + '…' : text;
    };
    new MutationObserver(last).observe(log, { childList: true, subtree: true, characterData: true });
    last();
  }
  function placeholder() {
    const cmd = $('cmd');
    if (!cmd) return;
    if (band() === 'desk') {
      if (!cmd.dataset.ui2Ph) cmd.dataset.ui2Ph = cmd.placeholder;
      cmd.placeholder = 'Tell the app what changed…';
    } else if (cmd.dataset.ui2Ph) cmd.placeholder = cmd.dataset.ui2Ph;
  }

  /* Quick chips fill the box; nothing is sent until the send arrow is pressed. */
  const CHIP_TEXT = {
    'Amount left…': 'Amount left is Rs. ',
    'Send all': 'Send all',
    'New wording': 'New wording',
    'Send to GiveLife': 'Send to GiveLife',
  };
  function addChips(box, input, names) {
    for (const name of names) {
      const b = mk('button', 'ui2-chip', '');
      b.type = 'button';
      b.textContent = name;
      b.addEventListener('click', () => {
        if (name === 'Show message') {
          $('histClose')?.click();
          setTimeout(() => (typeof Nav !== 'undefined' ? Nav.go('preview') : null), 50);
          return;
        }
        if (!input) return;
        input.value = CHIP_TEXT[name];
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
      });
      box.append(b);
    }
  }
  function chatChips() {
    const form = $('histForm');
    if (!form || $('ui2HistChips')) return;
    const chips = mk('div', 'ui2-chips ui2-hist-chips');
    chips.id = 'ui2HistChips';
    chips.setAttribute('aria-label', 'Quick commands');
    addChips(chips, $('histCmd'), [
      'Amount left…',
      'Send all',
      'New wording',
      'Send to GiveLife',
      'Show message',
    ]);
    form.before(chips);
  }

  const run = () => {
    tabs();
    sendList();
    desk();
    chatChips();
    markChip();
    if (!document.body.dataset.ui2Band) placeStatus();
  };
  const relayout = () => {
    placeStatus();
    placeholder();
  };
  run();
  relayout();
  new MutationObserver(run).observe(document.body, { childList: true, subtree: true, characterData: true });
  for (const q of ['(min-width: 900px)', '(min-width: 700px)'])
    matchMedia(q).addEventListener('change', relayout);
  addEventListener('studio-navigate', paintTabs);
  addEventListener('popstate', paintTabs);
  addEventListener('hashchange', paintTabs);
})();

/* 8. Message reader and editor (PDF pages 10-14).
   One bottom row: Copy, Edit (Done while editing), ⋯ and Back; Save Base, Test and Next wording live inside ⋯.
   While editing, bold and italic show as bold and italic (no stars), with ONE small floating bar: B I ♥ Dua ×.
   The live editor writes WhatsApp text (*bold*, _italic_) back into the real box, so saving is unchanged. */
(() => {
  const $ = (id) => document.getElementById(id);
  function dock() {
    const screen = $('messageFocus');
    const bar = screen?.querySelector('.ui2-reader-dock');
    const more = screen?.querySelector('.focus-rail-more');
    if (!bar || !more || bar.dataset.ui2Row) return;
    const panel = more.querySelector(':scope > div');
    for (const id of ['focusNext', 'focusTest', 'focusSave']) {
      const b = $(id);
      if (b && panel) panel.prepend(b);
    }
    const sum = more.querySelector('summary');
    sum.textContent = '⋯';
    sum.setAttribute('aria-label', 'More: Save Base, Test, Next wording');
    for (const id of ['focusCopy', 'focusEdit']) if ($(id)) bar.append($(id));
    bar.append(more);
    if ($('focusBack')) bar.append($('focusBack'));
    const hint = document.createElement('p');
    hint.className = 'ui2-reader-hint';
    hint.textContent = 'Save Base · Test · Next wording live inside ⋯';
    bar.after(hint);
    bar.dataset.ui2Row = '1';
  }

  /* WhatsApp text <-> simple HTML for the live editor. */
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  function toHtml(text) {
    return String(text)
      .split('\n')
      .map((line) => {
        let h = esc(line)
          .replace(/(^|[^\p{L}\p{N}*])\*(\S(?:[^*\n]*\S)?)\*(?=$|[^\p{L}\p{N}*])/gu, '$1<b>$2</b>')
          .replace(/(^|[^\p{L}\p{N}_])_(\S(?:[^_\n]*\S)?)_(?=$|[^\p{L}\p{N}_])/gu, '$1<i>$2</i>');
        return '<div>' + (h || '<br>') + '</div>';
      })
      .join('');
  }
  function wrap(inner, mark) {
    const lead = inner.match(/^\s*/)[0],
      tail = inner.match(/\s*$/)[0],
      core = inner.trim();
    return core ? lead + mark + core + mark + tail : inner;
  }
  function inline(node) {
    let out = '';
    for (const n of node.childNodes) {
      if (n.nodeType === 3) out += n.nodeValue.replace(/ /g, ' ');
      else if (n.nodeName === 'BR') out += '\n';
      else if (/^(B|STRONG)$/.test(n.nodeName)) out += wrap(inline(n), '*');
      else if (/^(I|EM)$/.test(n.nodeName)) out += wrap(inline(n), '_');
      else if (/^(DIV|P)$/.test(n.nodeName)) out += (out && !out.endsWith('\n') ? '\n' : '') + block(n);
      else out += inline(n);
    }
    return out;
  }
  function block(div) {
    const t = inline(div);
    return t === '\n' ? '' : t.replace(/\n$/, '');
  }
  function toText(root) {
    const parts = [];
    let loose = '';
    for (const n of root.childNodes) {
      if (/^(DIV|P)$/.test(n.nodeName)) {
        if (loose) parts.push(loose), (loose = '');
        parts.push(block(n));
      } else if (n.nodeName === 'BR') {
        parts.push(loose);
        loose = '';
      } else loose += n.nodeType === 3 ? n.nodeValue : inline({ childNodes: [n] });
    }
    if (loose) parts.push(loose);
    return parts.join('\n');
  }

  function live() {
    const box = $('focusText'),
      shown = $('focusFormatted');
    if (!box || !shown || $('ui2Live')) return;
    const ed = document.createElement('div');
    ed.id = 'ui2Live';
    ed.className = 'ui2-live';
    ed.contentEditable = 'true';
    ed.spellcheck = true;
    ed.setAttribute('role', 'textbox');
    ed.setAttribute('aria-multiline', 'true');
    ed.setAttribute('aria-label', 'Edit WhatsApp message');
    ed.hidden = true;
    box.after(ed);
    const tools = document.createElement('div');
    tools.className = 'ui2-float';
    tools.id = 'ui2Float';
    tools.setAttribute('role', 'toolbar');
    tools.setAttribute('aria-label', 'Text style');
    tools.hidden = true;
    tools.innerHTML =
      '<button type="button" data-cmd="bold" aria-label="Bold"><b>B</b></button>' +
      '<button type="button" data-cmd="italic" aria-label="Italic"><i>I</i></button>' +
      '<button type="button" data-ins="💔" aria-label="Heart">♥</button>' +
      '<button type="button" data-ins="🤲" aria-label="Dua">Dua</button>' +
      '<button type="button" data-done aria-label="Done editing">×</button>';
    ed.before(tools);
    let pushing = false;
    const push = () => {
      const text = toText(ed);
      if (box.value === text) return;
      box.value = text;
      pushing = true;
      box.dispatchEvent(new Event('input', { bubbles: true }));
      pushing = false;
    };
    ed.addEventListener('input', push);
    ed.addEventListener('paste', (e) => {
      e.preventDefault();
      document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
    });
    tools.addEventListener('mousedown', (e) => e.preventDefault());
    tools.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.hasAttribute('data-done')) {
        push();
        $('focusEdit')?.click();
        return;
      }
      ed.focus();
      if (b.dataset.cmd) document.execCommand(b.dataset.cmd);
      else document.execCommand('insertText', false, b.dataset.ins);
      push();
    });
    /* Follow the real editor: when it opens, the live one takes its place. */
    const sync = () => {
      const on = !box.hidden;
      if (on && ed.hidden) {
        ed.innerHTML = toHtml(box.value);
        ed.style.fontSize = box.style.fontSize || '';
        ed.hidden = false;
        tools.hidden = false;
        box.classList.add('ui2-under');
        ed.focus({ preventScroll: true });
      } else if (!on && !ed.hidden) {
        ed.hidden = true;
        tools.hidden = true;
        box.classList.remove('ui2-under');
      }
    };
    new MutationObserver(sync).observe(box, { attributes: true, attributeFilter: ['hidden'] });
    /* Text put into the real box by other buttons (new style, undo) shows up in the live editor too. */
    box.addEventListener('input', () => {
      if (!ed.hidden && !pushing && toText(ed) !== box.value) ed.innerHTML = toHtml(box.value);
    });
    sync();
  }
  const run = () => {
    dock();
    live();
  };
  run();
  new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
})();

/* 9. Donors (PDF pages 15-23, V4 page 40). Same tab words on phone and computer, search as an icon on a phone,
   "+ Add" opens Add numbers first, DM ★ Important shows how many, and while DMs go out the bar is ONE amber
   "Stop DMs · 3 of 7 sent". All buttons are the existing ones, moved or relabelled. */
(() => {
  const $ = (id) => document.getElementById(id);
  const wide = () => innerWidth >= 900;
  const setText = (n, t) => n && n.textContent !== t && (n.textContent = t);
  function tabs() {
    for (const b of document.querySelectorAll('.donor-tabs [data-tab]')) {
      const name = b.querySelector('.tab-name');
      if (!name) continue;
      const tab = b.dataset.tab;
      if (tab === 'important') setText(name.querySelector('.tab-word'), wide() ? 'Important' : 'Star');
      else {
        const t = { all: 'All', top: 'Top', donated: 'Donated', not_contacted: 'Not messaged', volunteers: 'Volunteers' }[tab];
        if (t) setText(name, t);
      }
    }
  }
  function head() {
    const h = document.querySelector('.donor-head'),
      nav = $('donorNavMore'),
      add = $('donorAdd');
    if (!h || !nav || !add) return;
    const panel = nav.querySelector('.compact-nav-panel');
    const sum = nav.querySelector('summary');
    setText(sum, '+ Add');
    nav.classList.add('ui2-add-menu');
    const numbers = $('donorNumbers'),
      bulk = $('donorBulk');
    if (panel && numbers && panel.firstElementChild !== numbers) panel.prepend(numbers);
    if (panel && add.parentElement !== panel) numbers ? numbers.after(add) : panel.prepend(add);
    setText(add, 'Add one donor');
    if (panel && bulk && add.nextElementSibling !== bulk) add.after(bulk);
    const msgs = document.querySelector('.donor-message-tablist');
    if (msgs && msgs.nextElementSibling !== nav) h.insertBefore(msgs, nav);
    setText($('donorMessagesTab'), wide() ? 'Messages' : 'Msgs');
    if (!$('ui2DonorSearch')) {
      const s = document.createElement('button');
      s.type = 'button';
      s.id = 'ui2DonorSearch';
      s.className = 'ui2-donor-search';
      s.setAttribute('aria-label', 'Search donors');
      s.setAttribute('aria-expanded', 'false');
      s.textContent = '⌕';
      s.addEventListener('click', () => {
        const shell = document.querySelector('.donor-shell');
        const on = shell.toggleAttribute('data-ui2-search');
        s.setAttribute('aria-expanded', String(on));
        if (on) $('donorSearch')?.focus();
      });
      h.insertBefore(s, msgs || nav);
    }
  }
  function bottom() {
    const bar = document.querySelector('.donor-bottom'),
      dm = $('donorSendImportant'),
      toggle = $('donorToggle'),
      prog = $('donorProgress');
    if (!bar || !dm || !toggle || !prog) return;
    const count = document.querySelector('.donor-tabs [data-tab="important"] .tab-count')?.textContent.trim();
    const n = /Important/.test(dm.textContent) && count ? count : '';
    if (dm.dataset.ui2Count !== n) dm.dataset.ui2Count = n;
    const running = prog.dataset.active === 'true' && !prog.hidden && toggle.textContent.trim() === 'Stop DMs';
    bar.toggleAttribute('data-ui2-running', running);
    const m = (prog.querySelector(':scope > span')?.textContent || '').match(/(\d+) of (\d+) sent/);
    const sent = running && m ? m[1] + ' of ' + m[2] + ' sent' : '';
    if (toggle.dataset.ui2Sent !== sent) toggle.dataset.ui2Sent = sent;
  }
  const run = () => {
    tabs();
    head();
    bottom();
  };
  run();
  new MutationObserver(run).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['data-active', 'hidden'],
  });
  addEventListener('resize', run);
})();

/* 10. Chat, Notes, Settings, Report, Keyboard shortcuts, WhatsApp and Group finder (PDF pages 26-32). */
(() => {
  const $ = (id) => document.getElementById(id);
  const setText = (n, t) => n && n.textContent !== t && (n.textContent = t);
  const mk = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

  /* Notes: Lock and Full always at the top; Checklist, List, Red, B, I in one bar above the keyboard. */
  function notes() {
    const tools = $('notesTools'),
      ed = $('notesEditor');
    if (!tools || !ed) return;
    setText($('notesFullscreen'), 'Full');
    for (const b of tools.querySelectorAll('button')) {
      if (b.textContent.trim() === 'Checklist') setText(b, '☑ Checklist');
      if (b.textContent.trim() === 'Bullets') setText(b, '• List');
    }
    if (tools.querySelector('.ui2-note-b')) return;
    for (const [cmd, label, cls] of [
      ['bold', 'B', 'ui2-note-b'],
      ['italic', 'I', 'ui2-note-i'],
    ]) {
      const b = mk('button', cls, label);
      b.type = 'button';
      b.setAttribute('aria-label', cmd === 'bold' ? 'Bold' : 'Italic');
      b.addEventListener('mousedown', (e) => e.preventDefault());
      b.addEventListener('click', () => {
        ed.focus();
        document.execCommand(cmd);
        ed.dispatchEvent(new Event('input', { bubbles: true }));
      });
      tools.append(b);
    }
  }

  /* Settings: Look / Sending safety / Tools / WhatsApp, Appearance as one choice, neutral Done at the bottom. */
  function settings() {
    const body = document.querySelector('#set .body');
    if (!body || !body.querySelector('.ui2-set-head')) return;
    const heads = [...body.querySelectorAll('.ui2-set-head')];
    const tools = heads.find((h) => h.textContent === 'Tools');
    const wa = heads.find((h) => h.textContent === 'WhatsApp');
    const posterRow = [...body.querySelectorAll(':scope > .row')].find((r) => /^Poster/.test(r.textContent.trim()));
    if (tools && posterRow && tools.nextElementSibling !== posterRow) tools.after(posterRow);
    const ai = body.querySelector(':scope > details.advanced');
    if (ai && wa && ai.nextElementSibling !== wa) wa.before(ai);
    for (const r of body.querySelectorAll(':scope > .row')) {
      const t = r.textContent.trim();
      const btn = r.querySelector('button, a');
      if (/^Poster/.test(t)) setText(btn, 'Change');
      if (/^University group finder/.test(t)) {
        setText(btn, 'Open');
        if (btn && btn.getAttribute('href') === '/group-finder') btn.setAttribute('href', '/new/group-finder');
      }
      if (/^Case plan/.test(t)) setText(btn, 'Open');
      if (/^Appearance/.test(t) && !r.querySelector('.ui2-look')) {
        const seg = [...r.querySelectorAll('button')];
        const sel = mk('select', 'ui2-look');
        sel.setAttribute('aria-label', 'Appearance');
        for (const b of seg) sel.append(new Option(b.textContent.trim() + ' ▾', b.textContent.trim()));
        const sync = () => {
          const on = seg.find((b) => b.getAttribute('aria-pressed') === 'true' || b.classList.contains('on'));
          if (on) sel.value = on.textContent.trim();
        };
        sel.addEventListener('change', () => seg.find((b) => b.textContent.trim() === sel.value)?.click());
        seg[0]?.parentElement.after(sel);
        sync();
        for (const b of seg) new MutationObserver(sync).observe(b, { attributes: true });
      }
    }
    const done = $('setCloseBottom');
    if (done) {
      setText(done, 'Done');
      done.classList.add('ui2-done');
    }
  }

  /* Report: Right now first, then the three Auto rows: name, "6 groups · 0 sent", ON/OFF. Tap a name for its settings. */
  function report() {
    for (const card of document.querySelectorAll('.auto-card')) {
      const dl = card.querySelector('.auto-stats');
      if (!dl) continue;
      const dt = [...dl.querySelectorAll('dt')].map((x) => x.textContent.trim());
      const dd = [...dl.querySelectorAll('dd')].map((x) => x.textContent.trim());
      const i = dt.indexOf('sent');
      const line = (dd[0] || '0') + ' ' + (dt[0] || '') + ' · ' + (i >= 0 ? dd[i] : '0') + ' sent';
      let sub = card.querySelector('.ui2-auto-sub');
      if (!sub) {
        sub = mk('small', 'ui2-auto-sub');
        card.querySelector('.auto-head h4')?.after(sub);
        const h = card.querySelector('.auto-head h4');
        const edit = card.querySelector('.auto-edit');
        if (h && edit) {
          h.tabIndex = 0;
          h.setAttribute('role', 'button');
          h.title = 'Edit settings';
          h.addEventListener('click', () => edit.click());
          h.addEventListener('keydown', (e) => e.key === 'Enter' && edit.click());
        }
      }
      setText(sub, line);
    }
  }

  /* Keyboard shortcuts: the five used every day first, the rest folded. */
  function keys() {
    const dl = document.querySelector('#keyboardDialog dl');
    if (!dl || dl.dataset.ui2) return;
    const rows = [...dl.children];
    const by = (t) => rows.find((r) => r.querySelector('dt')?.textContent.trim() === t);
    const top = ['Edit message', 'New wording', 'Copy message', 'Show / hide message', 'Focus chat'].map(by).filter(Boolean);
    const head = mk('p', 'ui2-keys-head', 'MOST USED');
    dl.before(head);
    for (const r of top) dl.append(r);
    const rest = rows.filter((r) => !top.includes(r));
    const more = mk('details', 'ui2-keys-more');
    more.innerHTML = '<summary>All shortcuts (group / DM, send, scroll, close)</summary>';
    const dl2 = mk('dl');
    for (const r of rest) dl2.append(r);
    more.append(dl2);
    dl.after(more);
    for (const r of top) {
      const kbd = r.querySelector('dd kbd');
      if (kbd && r.querySelector('dt').textContent.trim() === 'Focus chat') {
        r.querySelector('dd').replaceChildren(kbd);
      }
    }
    dl.dataset.ui2 = '1';
  }

  /* WhatsApp: one short green line when connected; the full steps only when something is wrong. */
  function whatsapp() {
    const d = $('whatsappDialog'),
      h = $('waHeading');
    if (!d || !h) return;
    setText(d.querySelector('h2'), 'WhatsApp');
    const ok = /is connected/i.test(h.textContent);
    d.toggleAttribute('data-ui2-ok', ok);
    let line = d.querySelector('.ui2-wa-line');
    if (!line) {
      line = mk('p', 'ui2-wa-line');
      d.querySelector('.connect-state')?.after(line);
    }
    const detail = ($('waDetail')?.textContent || '').replace(/^Ready to send from/i, 'ready from').replace(/\.$/, '');
    setText(line, '✓ Connected · ' + (detail || 'ready'));
  }

  /* Chat: the old bottom Back goes (the top Back stays), chips sit above the box. */
  function chat() {
    const ret = document.querySelector('#hist .chat-return');
    if (ret) ret.classList.add('ui2-chat-return');
  }

  /* Group finder: Back returns to /new, and the main actions sit in a bottom bar. */
  function finder() {
    if (!document.body.classList.contains('ui2-gf')) return;
    const back = document.querySelector('header.top a.back');
    if (back && back.getAttribute('href') === '/') back.setAttribute('href', '/new');
    if ($('ui2GfBar')) return;
    const imp = $('importOpen'),
      find = $('findGroups');
    if (!imp || !find || !back) return;
    const bar = mk('nav', 'ui2-gf-bar');
    bar.id = 'ui2GfBar';
    bar.setAttribute('aria-label', 'Group finder actions');
    const b = mk('a', 'ui2-gf-back', '←');
    b.href = '/new';
    b.setAttribute('aria-label', 'Back');
    bar.append(b, imp, find);
    document.body.append(bar);
    const empty = $('empty');
    if (empty && !empty.querySelector('.ui2-gf-tip')) {
      const tip = mk('p', 'ui2-gf-tip', 'Tap Find groups below to start.');
      empty.append(tip);
    }
  }

  const run = () => {
    notes();
    settings();
    report();
    keys();
    whatsapp();
    chat();
    finder();
  };
  run();
  new MutationObserver(run).observe(document.body, { childList: true, subtree: true, characterData: true });
})();
