/* Redesign helpers, loaded only at /new. They move or relabel existing controls; nothing here sends anything. */
/* Speed: every helper below watches the page for changes. Run each at most once per frame, not once per change. */
/* Width checks use media queries: reading innerWidth made the browser re-measure the whole page each time. */
const ui2Wide = matchMedia('(min-width: 900px)');
const ui2Tab = matchMedia('(min-width: 700px)');
const ui2Frame = (fn) => {
  let queued = false;
  return () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      fn();
    });
  };
};
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
  new MutationObserver(ui2Frame(run)).observe(document.body, { childList: true, subtree: true });
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
    more.innerHTML =
      '<summary>More options (poster, follow-up, vary gap, test DM)</summary><div></div>';
    const box = more.querySelector('div');
    for (const id of ['batchLimit', 'batchPause']) {
      const r = $(id)?.closest('.bm-row');
      if (r) box.append(r);
    }
    const custom = mk('button', 'ui2-custom-gap', 'Custom wait…');
    custom.type = 'button';
    custom.addEventListener('click', () =>
      picker.querySelector('.batch-gap-btn[data-gap="custom"]')?.click(),
    );
    box.append(custom);
    for (const id of ['batchPauseCustom', 'batchEachRow', 'batchChips', 'batchRandomRow'])
      if ($(id)) box.append($(id));
    const test = [...picker.querySelectorAll('button')].find(
      (b) => b.textContent.trim() === 'Test DM',
    );
    if (test) box.append(test);
    sum.after(more);
    picker.addEventListener('close', () => (more.open = false));
    for (const el of [gapRow, $('batchLimit'), $('batchPause')])
      el?.addEventListener('click', () => setTimeout(paint));
    for (const id of ['batchLimit', 'batchPause', 'batchGap'])
      $(id)?.addEventListener('change', paint);
  }
  function paint() {
    const per = $('batchLimit')?.value,
      rest = $('batchPause'),
      gapBtn = document.querySelector('#donorBatchPicker .batch-gap-btn[aria-pressed="true"]');
    const gap = gapBtn?.dataset.gap;
    for (const b of document.querySelectorAll('.ui2-speed-btn')) {
      const p = PRESETS.find((x) => x[0] === b.dataset.speed);
      b.setAttribute(
        'aria-pressed',
        String(String(p[2]) === gap && p[3] === per && p[4] === rest?.value),
      );
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
  new MutationObserver(ui2Frame(relabel)).observe(document.body, {
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
  new MutationObserver(ui2Frame(sync)).observe(document.body, { childList: true, subtree: true });
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
      more.innerHTML =
        '<summary aria-label="More: Next, Regenerate, Test, Bold, Italic, Base message">⋯</summary><div></div>';
      box.append(more);
      document.addEventListener('pointerdown', (e) => {
        if (more.open && !more.contains(e.target)) more.open = false;
      });
    }
    const panel = more.querySelector(':scope > div');
    /* Next and Regenerate: one small row right under the message (pressing the real round buttons). */
    if (!box.previousElementSibling?.classList.contains('ui2-bank-nav')) {
      const nav = mk('div', 'ui2-bank-nav');
      if (document.querySelector('#donorMessages .bank-gen-icon'))
        nav.append(proxy('↻ Regenerate', '#donorMessages .bank-gen-icon'));
      if (document.querySelector('#donorMessages .bank-next-arrow'))
        nav.append(proxy('Next ›', '#donorMessages .bank-next-arrow'));
      if (nav.children.length) box.before(nav);
    }
    for (const button of box.parentElement.querySelectorAll('.ui2-bank-nav [data-ui2-proxy]')) {
      const target = document.querySelector(button.dataset.ui2Proxy);
      button.disabled = !target || target.disabled;
    }
    for (const t of box.querySelectorAll(':scope > button.tool')) {
      if (ui2Wide.matches && t.matches('[data-bank-save-id], .bank-copy')) continue;
      const x = t.textContent.trim();
      if (x === 'Edit' || x === 'Done' || x === 'Copy') {
        t.style.setProperty('order', x === 'Copy' ? '2' : '1', 'important');
        continue;
      }
      panel.append(t);
    }
    const back = [...box.querySelectorAll('.bank-pagination button')].find((b) =>
      /Back/.test(b.textContent),
    );
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
  new MutationObserver(ui2Frame(bank)).observe(document.body, { childList: true, subtree: true });
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
  new MutationObserver(ui2Frame(group)).observe(document.body, { childList: true, subtree: true });
  group();
})();

/* 6. Stop DMs only shows while DMs are actually going out (sending, starting or waiting between batches).
   "Resume DMs" and "Change resume" always stay visible. */
(() => {
  function sync() {
    const toggle = document.getElementById('donorToggle');
    const prog = document.getElementById('donorProgress');
    if (!toggle || !prog) return;
    const running = !prog.hidden && prog.dataset.active === 'true';
    const idle = !running && toggle.textContent.trim() === 'Stop DMs';
    toggle.toggleAttribute('data-ui2-idle', idle);
  }
  new MutationObserver(ui2Frame(sync)).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['data-active', 'hidden'],
  });
  sync();
})();

/* 7. Home (PDF pages 1-9, 13). Phone: one bottom bar (Message, Donors, Chat, More) and a bottom sheet for the rest.
   Tablet: message and send list side by side. Computer: one top bar, today's message beside the send list,
   and the chat as one slim bar with quick chips. Every button below presses an existing control. */
(() => {
  const $ = (id) => document.getElementById(id);
  const press = (el) => () => el()?.click();
  const band = () => (ui2Wide.matches ? 'desk' : ui2Tab.matches ? 'tab' : 'phone');
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
    const ico = (d) =>
      `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
    const ICONS = {
      message: ico('<path d="M4 5h16v11H9l-5 4z"/>'),
      donors: ico(
        '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.4A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
      ),
      chat: ico(
        '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.7A8 8 0 1 1 21 12z"/><path d="M9 11h6M9 14h4"/>',
      ),
      notes: ico('<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>'),
      report: ico('<path d="M5 20V10M12 20V4M19 20v-7"/>'),
      settings: ico(
        '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
      ),
      more: ico(
        '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
      ),
    };
    const items = [
      ['message', ICONS.message, 'Message', () => (typeof Nav !== 'undefined' ? Nav.go('') : null)],
      ['donors', ICONS.donors, 'Donors', press(() => $('openDonors'))],
      ['chat', ICONS.chat, 'Chat', press(() => $('chatOpen'))],
      /* Computer only (the phone keeps these in More): every top-bar option is also one clear button here. */
      ['notes', ICONS.notes, 'Notes', press(() => $('donorNotesShortcut'))],
      ['report', ICONS.report, 'Report', press(() => document.querySelector('.report-open'))],
      ['settings', ICONS.settings, 'Settings', press(() => $('gear'))],
      ['more', ICONS.more, 'More', () => sheet()],
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
    const on = path.startsWith('donors')
      ? 'donors'
      : path === 'chat'
        ? 'chat'
        : path === 'notes'
          ? 'notes'
          : path
            ? ''
            : 'message';
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
    tile(
      amount + ' left',
      'change amount',
      press(() => $('leftChip')),
    );
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
    tile(
      'Reply',
      'chat shortcuts',
      press(() => document.querySelector('.reply-open')),
    );
    /* On a computer these three are already buttons in the bottom bar, so they are not shown twice. */
    tile(
      'Notes',
      '',
      press(() => $('donorNotesShortcut')),
    ).dataset.dup = '1';
    tile(
      'Report',
      'right-now board',
      press(() => document.querySelector('.report-open')),
    ).dataset.dup = '1';
    tile(
      'Settings',
      '',
      press(() => $('gear')),
    ).dataset.dup = '1';
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
    const later = mk('button', 'ui2-later', 'Later');
    later.type = 'button';
    later.id = 'ui2Later';
    later.setAttribute('aria-expanded', 'false');
    later.setAttribute('aria-controls', 'ui2LaterPanel');
    const wrap = mk('div', 'group-drop-wrap ui2-choose');
    const choose = mk('button', 'ui2-choose-btn', 'Choose group');
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
      for (const t of timers())
        if ((t.getAttribute('aria-expanded') === 'true') !== open) t.click();
      panel.hidden = !open;
      later.setAttribute('aria-expanded', String(open));
    });
    const paint = () => {
      const due = timers()
        .filter((t) => t.classList.contains('is-pending'))
        .map((t) => t.textContent.trim());
      const text = due.length ? 'Later · ' + due.join(', ') : 'Later';
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
        setTimeout(
          () => document.querySelector(`.focus-styles [data-style="${key}"]`)?.click(),
          250,
        );
      });
      styles.append(b);
    }
    tools.after(styles);
    const poster = $('previewChangePoster');
    const overflow = tools.querySelector('.overflow-tools > div');
    if (poster && overflow) overflow.prepend(poster);
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

  /* Computer: Chat is its own screen, opened from the top bar. */
  function topChat() {
    const bar = document.querySelector('.app > .brandbar'),
      notes = $('donorNotesShortcut');
    if (!bar || !notes || $('ui2TopChat')) return;
    const b = mk('button', 'ui2-top-chat', 'Chat');
    b.type = 'button';
    b.id = 'ui2TopChat';
    b.addEventListener('click', () => $('chatOpen')?.click());
    bar.insertBefore(b, notes);
  }

  const run = () => {
    topChat();
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
  new MutationObserver(ui2Frame(run)).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
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
      else if (/^(DIV|P)$/.test(n.nodeName))
        out += (out && !out.endsWith('\n') ? '\n' : '') + block(n);
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
        if (loose) (parts.push(loose), (loose = ''));
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
  new MutationObserver(ui2Frame(run)).observe(document.body, { childList: true, subtree: true });
})();

/* 9. Donors (PDF pages 15-23, V4 page 40). Same tab words on phone and computer, search as an icon on a phone,
   "+ Add" opens Add numbers first, DM ★ Important shows how many, and while DMs go out the bar is ONE amber
   "Stop DMs · 3 of 7 sent". All buttons are the existing ones, moved or relabelled. */
(() => {
  const $ = (id) => document.getElementById(id);
  const wide = () => ui2Wide.matches;
  const setText = (n, t) => n && n.textContent !== t && (n.textContent = t);
  function tabs() {
    for (const b of document.querySelectorAll('.donor-tabs [data-tab]')) {
      const name = b.querySelector('.tab-name');
      if (!name) continue;
      const tab = b.dataset.tab;
      if (tab === 'important')
        setText(name.querySelector('.tab-word'), wide() ? 'Important' : 'Star');
      else {
        const t = {
          all: 'All',
          top: 'Top',
          donated: 'Donated',
          not_contacted: 'Not messaged',
          volunteers: 'Volunteers',
        }[tab];
        if (t) setText(name, t);
      }
    }
    /* The tab you are on is always in view: the row scrolls to it when the tab changes (and when the screen opens). */
    const strip = document.querySelector('.donor-tabs'),
      sel = strip?.querySelector('[aria-selected="true"]');
    if (strip && sel) {
      /* Again whenever the tab or the row's size changes (labels settle, buttons step aside), never while you scroll it. */
      const key = [sel.dataset.tab, strip.scrollWidth, strip.clientWidth].join(':');
      const r = sel.getBoundingClientRect(),
        box = strip.getBoundingClientRect();
      if (strip.dataset.ui2Sel !== key && box.width && r.width) {
        strip.dataset.ui2Sel = key;
        strip.scrollLeft += r.left + r.width / 2 - (box.left + box.width / 2);
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
    const phone = !wide(),
      bar = document.querySelector('.donor-toolbar'),
      hide = $('donorHideRow');
    /* Phone: the menu is one "⋯" button at the end of the tabs row; computer: the "+ Add" button in the header. */
    setText(sum, phone ? '⋯' : '+ Add');
    sum.setAttribute('aria-label', phone ? 'More: add donors and list options' : 'Add donors');
    nav.classList.add('ui2-add-menu');
    const numbers = $('donorNumbers'),
      bulk = $('donorBulk');
    if (panel && numbers && panel.firstElementChild !== numbers) panel.prepend(numbers);
    if (panel && add.parentElement !== panel) numbers ? numbers.after(add) : panel.prepend(add);
    setText(add, 'Add one donor');
    if (panel && bulk && add.nextElementSibling !== bulk) add.after(bulk);
    const msgs = document.querySelector('.donor-message-tablist');
    if (msgs && nav.parentElement === h && msgs.nextElementSibling !== nav)
      h.insertBefore(msgs, nav);
    setText($('donorMessagesTab'), wide() ? 'Messages' : 'Msgs');
    if (!$('ui2DonorSearch')) {
      const s = document.createElement('button');
      s.type = 'button';
      s.id = 'ui2DonorSearch';
      s.className = 'ui2-donor-search';
      s.setAttribute('aria-label', 'Search donors');
      s.setAttribute('aria-expanded', 'false');
      s.textContent = '⌕';
      const shell = document.querySelector('.donor-shell'),
        input = $('donorSearch');
      const close = () => {
        shell.removeAttribute('data-ui2-search');
        s.setAttribute('aria-expanded', 'false');
      };
      const clear = () => {
        if (!input?.value) return;
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      /* Keep focus in the field while the button is pressed, so the field's blur never reopens it. */
      s.addEventListener('mousedown', (e) => e.preventDefault());
      s.addEventListener('click', () => {
        const on = !shell.hasAttribute('data-ui2-search');
        if (on) {
          shell.setAttribute('data-ui2-search', '');
          s.setAttribute('aria-expanded', 'true');
          input?.focus();
        } else {
          clear();
          close();
        }
      });
      input?.addEventListener('blur', () => {
        if (!input.value.trim()) close();
      });
      input?.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        e.preventDefault();
        clear();
        close();
        input.blur();
      });
      (nav.parentElement === h ? h : bar)?.insertBefore(
        s,
        nav.parentElement === h ? msgs || nav : nav,
      );
    }
    /* Phone: search icon and "⋯" end the tabs row; the hide / deselect chips live inside "⋯". Computer: back in the header. */
    const search = $('ui2DonorSearch');
    if (phone && bar) {
      if (search.parentElement !== bar) bar.append(search);
      if (nav.parentElement !== bar) bar.append(nav);
      if (hide && panel && hide.parentElement !== panel) panel.append(hide);
    } else if (!phone) {
      if (hide && hide.parentElement !== h) h.insertBefore(hide, msgs);
      if (search.parentElement !== h) h.insertBefore(search, msgs || null);
      if (nav.parentElement !== h) h.append(nav);
    }
  }
  function bottom() {
    const bar = document.querySelector('.donor-bottom'),
      dm = $('donorSendImportant'),
      toggle = $('donorToggle'),
      prog = $('donorProgress');
    if (!bar || !dm || !toggle || !prog) return;
    const count = document
      .querySelector('.donor-tabs [data-tab="important"] .tab-count')
      ?.textContent.trim();
    const n = /Important/.test(dm.textContent) && count ? count : '';
    if (dm.dataset.ui2Count !== n) dm.dataset.ui2Count = n;
    const running =
      prog.dataset.active === 'true' && !prog.hidden && toggle.textContent.trim() === 'Stop DMs';
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
  new MutationObserver(ui2Frame(run)).observe(document.body, {
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
    const posterRow = [...body.querySelectorAll(':scope > .row')].find((r) =>
      /^Poster/.test(r.textContent.trim()),
    );
    if (tools && posterRow && tools.nextElementSibling !== posterRow) tools.after(posterRow);
    const ai = body.querySelector(':scope > details.advanced');
    if (ai && wa && ai.nextElementSibling !== wa) wa.before(ai);
    for (const r of body.querySelectorAll(':scope > .row')) {
      const t = r.textContent.trim();
      const btn = r.querySelector('button, a');
      if (/^Poster/.test(t)) setText(btn, 'Change');
      if (/^University group finder/.test(t)) {
        setText(btn, 'Open');
        if (btn && btn.getAttribute('href') === '/group-finder')
          btn.setAttribute('href', '/new/group-finder');
      }
      if (/^Case plan/.test(t)) setText(btn, 'Open');
      if (/^Appearance/.test(t) && !r.querySelector('.ui2-look')) {
        const seg = [...r.querySelectorAll('button')];
        const sel = mk('select', 'ui2-look');
        sel.setAttribute('aria-label', 'Appearance');
        for (const b of seg)
          sel.append(new Option(b.textContent.trim() + ' ▾', b.textContent.trim()));
        const sync = () => {
          const on = seg.find(
            (b) => b.getAttribute('aria-pressed') === 'true' || b.classList.contains('on'),
          );
          if (on) sel.value = on.textContent.trim();
        };
        sel.addEventListener('change', () =>
          seg.find((b) => b.textContent.trim() === sel.value)?.click(),
        );
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
    const top = ['Edit message', 'New wording', 'Copy message', 'Show / hide message', 'Focus chat']
      .map(by)
      .filter(Boolean);
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
    const detail = ($('waDetail')?.textContent || '')
      .replace(/^Ready to send from/i, 'ready from')
      .replace(/\.$/, '');
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
  new MutationObserver(ui2Frame(run)).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
})();

/* Back/Forward and dialog closing are owned by the shared Nav controller. */

/* 15. Phone: tapping anywhere on the Auto row switches Auto (the switch itself still works as before). */
document.addEventListener('click', (e) => {
  const live = e.target.closest?.('#live');
  if (!live || e.target.closest('#auto') || ui2Wide.matches) return;
  document.getElementById('auto')?.click();
});

/* 16. Group message: Regenerate and Next sit right under the message, like on the DM messages screen.
   Main screen: Next = the app's next saved wording (New), Regenerate = opens the reader and makes 5 new versions.
   Reader: Next version / Generate 5 Versions. Every button presses the real existing control. */
(() => {
  const $ = (id) => document.getElementById(id);
  const mk = (cls, label, svg, fn, id) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = cls;
    if (id) b.id = id;
    b.innerHTML = svg + '<span></span>';
    b.lastChild.textContent = label;
    b.addEventListener('click', fn);
    return b;
  };
  const REGEN =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/></svg>';
  const NEXT =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
  function row(id, regen, next) {
    const r = document.createElement('div');
    r.className = 'ui2-gnav';
    r.id = id;
    r.append(
      mk('ui2-gbtn', 'Regenerate', REGEN, regen),
      mk('ui2-gbtn ui2-gnext', 'Next', NEXT, next),
    );
    return r;
  }
  function main() {
    const card = $('card');
    if (!card || $('ui2GnavMain')) return;
    card.after(
      row(
        'ui2GnavMain',
        () => {
          if (typeof Nav !== 'undefined') Nav.go('preview');
          let tries = 0;
          const go = setInterval(() => {
            const b = $('focusRetry');
            if (++tries > 40 || (b && !$('messageFocus').hidden && !b.disabled)) {
              clearInterval(go);
              if (tries <= 40) b.click();
            }
          }, 100);
        },
        () => $('fresh')?.click(),
      ),
    );
  }
  function reader() {
    const bar = document.querySelector('#messageFocus .ui2-reader-dock');
    if (!bar || $('ui2GnavReader')) return;
    bar.before(
      row(
        'ui2GnavReader',
        () => $('focusRetry')?.click(),
        () => $('focusNext')?.click(),
      ),
    );
  }
  const run = () => {
    main();
    reader();
  };
  run();
  new MutationObserver(ui2Frame(run)).observe(document.body, { childList: true, subtree: true });
})();

/* 17. Phone: a Msgs button in the donors bottom bar on every tab (it presses the real Msgs control). */
(() => {
  const ICON =
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.7A8 8 0 1 1 21 12z"/><path d="M9 11h6M9 14h4"/></svg>';
  function proxy() {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ui2-msgs-bottom';
    b.setAttribute('aria-label', 'DM messages');
    b.innerHTML = ICON + '<span>Msgs</span>';
    b.addEventListener('click', () => document.getElementById('donorMessagesTab')?.click());
    return b;
  }
  function run() {
    for (const bar of document.querySelectorAll('#donorsPage .donor-bottom, #donorsPage .vol-foot'))
      if (!bar.querySelector(':scope > .ui2-msgs-bottom')) bar.append(proxy());
  }
  run();
  new MutationObserver(ui2Frame(run)).observe(document.body, { childList: true, subtree: true });
})();

/* The shared header's Add action follows the selected directory tab. */
document.addEventListener(
  'click',
  (event) => {
    if (
      !event.target.closest?.('#donorNavMore > summary') ||
      document.getElementById('donorsPage')?.dataset.panel !== 'volunteers'
    )
      return;
    event.preventDefault();
    event.stopImmediatePropagation();
    document.querySelector('.vol-add-panel > summary')?.click();
  },
  true,
);

/* Desktop DM bank: navigation in the dock, quiet editing/copy icons around the message.
   The original controls keep their handlers; phone/tablet DOM and layout stay as before. */
(() => {
  const COPY =
    '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4"/></svg>';
  const PENCIL =
    '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14z"/></svg>';
  const SAVE =
    '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>';
  function make(cls, label, content, selector) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = cls;
    button.setAttribute('aria-label', label);
    button.title = label;
    button.innerHTML = content;
    button.onclick = () => document.querySelector(selector)?.click();
    return button;
  }
  function arrange() {
    const root = document.getElementById('donorMessages');
    if (!root) return;
    if (!ui2Wide.matches) {
      root.querySelectorAll('.ui2-desktop-msg-control').forEach((e) => e.remove());
      root.querySelector('.bank-detail')?.classList.remove('ui2-desktop-editing');
      return;
    }
    const card = root.querySelector('.bank-detail'),
      preview = card?.querySelector('.bank-preview');
    const actions = root.querySelector('.bank-actions'),
      original = root.querySelector('[data-bank-save-id]');
    if (!card || !preview || !actions || !original) return;
    if (!actions.querySelector('.ui2-desktop-regenerate')) {
      actions.append(
        make(
          'ui2-desktop-msg-control ui2-desktop-regenerate',
          'Regenerate',
          '↻ Regenerate',
          '#donorMessages .bank-gen-icon',
        ),
        make(
          'ui2-desktop-msg-control ui2-desktop-next',
          'Next message',
          'Next ›',
          '#donorMessages [data-bank-nav="next"]',
        ),
      );
    }
    actions.querySelector('.ui2-desktop-regenerate').disabled =
      !!root.querySelector('.bank-regenerate')?.disabled;
    actions.querySelector('.ui2-desktop-next').disabled =
      !!root.querySelector('[data-bank-nav="next"]')?.disabled;
    let edit = card.querySelector('.ui2-desktop-edit');
    if (!edit)
      edit = make(
        'ui2-desktop-msg-control ui2-desktop-edit',
        'Edit message',
        PENCIL,
        '#donorMessages [data-bank-save-id]',
      );
    const editing = !card.querySelector('textarea').hidden;
    card.classList.toggle('ui2-desktop-editing', editing);
    const host = editing ? card : preview;
    if (edit.parentElement !== host) host.append(edit);
    const label = editing ? 'Save message' : 'Edit message';
    if (edit.getAttribute('aria-label') !== label) {
      edit.setAttribute('aria-label', label);
      edit.title = label;
      edit.innerHTML = editing ? SAVE : PENCIL;
    }
    edit.disabled = original.disabled;
    let copy = card.querySelector('.ui2-desktop-copy');
    if (!copy) {
      copy = make(
        'ui2-desktop-msg-control ui2-desktop-copy',
        'Copy message',
        COPY,
        '#donorMessages .bank-copy',
      );
      card.append(copy);
    }
    copy.hidden = editing;
  }
  const run = ui2Frame(arrange);
  new MutationObserver(run).observe(document.body, {
    childList: true,
    subtree: true,
  });
  ui2Wide.addEventListener('change', run);
  arrange();
})();
