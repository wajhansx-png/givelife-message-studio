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

/* 2. DM speed dialog: plain words. Every option stays visible. */
(() => {
  const LABELS = {
    batchCount: 'How many people',
    batchLimit: 'DMs in each batch',
    batchPause: 'Rest between batches',
  };
  function relabel() {
    const picker = document.getElementById('donorBatchPicker');
    if (!picker) return;
    for (const [id, text] of Object.entries(LABELS)) {
      const l = picker.querySelector('label[for="' + id + '"]');
      if (l && l.textContent !== text) l.textContent = text;
    }
    const start = document.getElementById('batchStart');
    const title = picker.querySelector('h2');
    const speedOnly = start && start.textContent === 'Save gap';
    if (speedOnly) start.textContent = 'Save speed';
    if (title) {
      const want = start && start.textContent === 'Save speed' ? 'DM speed' : 'Send DMs';
      if (title.textContent !== want) title.textContent = want;
    }
  }
  new MutationObserver(relabel).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  relabel();
})();

/* 3. Computer: Gap, Test DM, Auto and Poster move into one Options menu (left); Back stays on the right. */
(() => {
  const wide = matchMedia('(min-width: 900px)');
  const IDS = ['donorPace', 'donorTest'];
  const LABELS = ['donorAuto', 'donorRowPoster'];
  let moved = [];
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
      '<summary aria-label="Options">Options</summary><div class="ui2-options-panel"></div>';
    const panel = box.querySelector('div');
    moved = nodes(bar).map((n) => [n, [...bar.children].indexOf(n)]);
    for (const [n] of moved) panel.append(n);
    bar.prepend(box);
    box.addEventListener('keydown', (e) => e.key === 'Escape' && (box.open = false));
  }
  function restore(bar) {
    const box = document.getElementById('ui2Options');
    if (!box) return;
    for (const [n, i] of moved.sort((a, b) => a[1] - b[1]))
      bar.insertBefore(n, bar.children[i] || null);
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

/* 4. Phone: big Regenerate and Next buttons on the DM messages page. They press the real round buttons. */
(() => {
  const press = (sel) => () => document.querySelector(sel)?.click();
  function big(id, label, sel) {
    const b = document.createElement('button');
    b.type = 'button';
    b.id = id;
    b.className = 'ui2-big';
    b.textContent = label;
    b.addEventListener('click', press(sel));
    return b;
  }
  function bank() {
    const box = document.querySelector('#donorMessages .bank-actions');
    if (
      !box ||
      box.querySelector('#ui2BankNext') ||
      !document.querySelector('#donorMessages .bank-next-arrow')
    )
      return;
    box.prepend(big('ui2BankNext', 'Next ›', '#donorMessages .bank-next-arrow'));
    box.prepend(big('ui2BankGen', '↻ Regenerate', '#donorMessages .bank-gen-icon'));
    for (const t of box.querySelectorAll('button.tool')) {
      const x = t.textContent.trim();
      if (x === 'Test') t.classList.add('ui2-test');
      const n = { Edit: 1, Copy: 2, Test: 3, B: 4, I: 5, 'Base message': 6 }[x] ?? 7;
      t.style.setProperty('order', String(n), 'important');
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
    help(document.getElementById('swDm'), 'Auto may send DMs by itself while it is on.');
    help(document.getElementById('swNew'), 'Auto also DMs people who are new.');
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
