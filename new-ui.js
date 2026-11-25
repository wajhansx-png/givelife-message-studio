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
// Row rendering does not change the chrome, menus or other screens these helpers manage.
function ui2Observe(run, options) {
  new MutationObserver((records) => {
    const rows = document.getElementById('donorRows');
    if (!rows || records.some(({ target }) => !rows.contains(target))) run();
  }).observe(document.body, { childList: true, subtree: true, ...options });
}
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
  ui2Observe(ui2Frame(run));
})();

/* 1. The home screen shows the message above the send controls without opening the reader. */

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
  ui2Observe(ui2Frame(relabel), {
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
  ui2Observe(ui2Frame(sync));
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
        '<summary aria-label="More: Next, Regenerate, Test, Bold, Italic, Base message">More</summary><div></div>';
      box.append(more);
    }
    const panel = more.querySelector(':scope > div');
    /* One small message navigation row, using the existing buttons' handlers. */
    const previous = box.querySelector('[data-bank-nav="previous"]');
    const next = box.querySelector('[data-bank-nav="next"]');
    const hasVersions = previous && next && (!previous.disabled || !next.disabled);
    if (hasVersions && !box.previousElementSibling?.classList.contains('ui2-bank-nav')) {
      const nav = mk('div', 'ui2-bank-nav');
      nav.append(
        proxy('‹ Previous', '#donorMessages [data-bank-nav="previous"]'),
        proxy('↻ Regenerate', '#donorMessages .bank-gen-icon'),
        proxy('Next ›', '#donorMessages .bank-next-arrow'),
      );
      box.before(nav);
    } else if (
      !hasVersions &&
      !panel.querySelector('[data-ui2-proxy]') &&
      document.querySelector('#donorMessages .bank-gen-icon')
    ) {
      panel.append(proxy('Generate 20 versions', '#donorMessages .bank-gen-icon'));
    }
    const controls = box.parentElement.querySelectorAll(
      '.ui2-bank-nav [data-ui2-proxy], #ui2BankMore [data-ui2-proxy]',
    );
    for (const button of controls) {
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
      const hint = mk('p', 'ui2-bank-hint', 'Base message · Test · Bold/Italic live inside More');
      box.after(hint);
    }
  }
  document.addEventListener('pointerdown', (event) => {
    const more = document.querySelector('#donorMessages #ui2BankMore[open]');
    if (more && !more.contains(event.target)) more.open = false;
  });
  ui2Observe(ui2Frame(bank));
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
  ui2Observe(ui2Frame(group));
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
  ui2Observe(ui2Frame(sync), {
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

  /* Keep WhatsApp, the amount and Auto together at every width. */
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
      if (live.parentElement !== row) row.append(live);
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
    /* One matched set on a 24-grid: even 1.6 line, rounded ends, and a soft second tone (class "d") for depth. */
    const ico = (d) =>
      `<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
    const ICONS = {
      case: ico(
        '<path class="d" d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1.2"/><path d="m9 14 2 2 4-4.2"/>',
      ),
      message: ico(
        '<rect class="d" x="2.5" y="4.5" width="19" height="15" rx="3"/><path d="m21.5 8-8.3 5.2a2 2 0 0 1-2.4 0L2.5 8"/>',
      ),
      donors: ico(
        '<path class="d" d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7z"/>',
      ),
      chat: ico(
        '<path class="d" d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/><path d="M8.5 10.5h7M8.5 13.5h4.5"/>',
      ),
      notes: ico(
        '<path class="d" d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4M9 13h6M9 17h6"/>',
      ),
      report: ico(
        '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><rect class="d" x="7" y="12" width="3" height="5" rx="1"/><rect class="d" x="12" y="6" width="3" height="11" rx="1"/><rect class="d" x="17" y="9" width="3" height="8" rx="1"/>',
      ),
      settings: ico(
        '<path d="M3 6h9M18 6h3M3 12h3M12 12h9M3 18h11M20 18h1"/><circle class="d" cx="15" cy="6" r="2.4"/><circle class="d" cx="9" cy="12" r="2.4"/><circle class="d" cx="17" cy="18" r="2.4"/>',
      ),
      giki: ico(
        '<path class="d" d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M21 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
      ),
      thanks: ico(
        '<path class="d" d="M20 12v9H4v-9"/><path d="M2 7h20v5H2zM12 22V7"/><path d="M12 7H7.5a2.5 2.5 0 1 1 0-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 1 0 0-5C13 2 12 7 12 7z"/>',
      ),
      more: ico(
        '<circle cx="5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/>',
      ),
    };
    const items = [
      /* Notes first: on the phone it takes Case's place (Case stays in More) */
      ['notes', ICONS.notes, 'Notes', press(() => $('donorNotesShortcut'))],
      ['case', ICONS.case, 'Case', () => (typeof Nav !== 'undefined' ? Nav.go('case') : null)],
      [
        'message',
        ICONS.message,
        'Message',
        () => {
          if (document.body.dataset.view === 'dm')
            document.querySelector('[data-view-button="group"]')?.click();
          if (typeof Nav !== 'undefined') Nav.go('');
        },
      ],
      /* Computer only (the phone shows Giki 1 and Giki 2 as two small buttons above the bar) */
      ['giki', ICONS.giki, 'Giki 1', () => (location.href = '/giki')],
      ['giki2', ICONS.giki, 'Giki 2', () => (location.href = '/giki2')],
      ['donors', ICONS.donors, 'Donors', press(() => $('openDonors'))],
      ['thanks', ICONS.thanks, 'Thank donors', () => window.DonorThanks?.open?.()],
      ['chat', ICONS.chat, 'Chat', press(() => $('chatOpen'))],
      /* Computer only (the phone keeps these in More): every top-bar option is also one clear button here. */
      ['report', ICONS.report, 'Report', press(() => document.querySelector('.report-open'))],
      ['settings', ICONS.settings, 'Settings', press(() => $('gear'))],
      ['more', ICONS.more, 'More', () => sheet()],
    ];
    for (const [key, icon, label, fn] of items) {
      const b = mk('button', 'ui2-tab', '');
      b.type = 'button';
      b.dataset.tab = key;
      b.innerHTML = icon + '<span></span>';
      b.lastChild.textContent = label;
      b.addEventListener('click', () => sideSwitch(key, fn));
      nav.append(b);
    }
    /* Phone and tablet: Giki 1 and Giki 2 are in More (fewer buttons on every screen); the computer menu keeps them. */
    foot.append(nav);
    paintTabs();
    paintSide();
  }
  function paintTabs() {
    const path = typeof Nav !== 'undefined' ? Nav.path() : '';
    const report = document.querySelector('dialog.report-dialog')?.open;
    const on = report
      ? 'report'
      : path === 'case'
        ? 'case'
        : path.startsWith('donors')
          ? 'donors'
          : path === 'chat'
            ? 'chat'
            : path === 'notes'
              ? 'notes'
              : path.startsWith('settings')
                ? 'settings'
                : path
                  ? ''
                  : 'message';
    for (const b of document.querySelectorAll('.ui2-tab')) {
      const current = String(b.dataset.tab === on);
      if (b.getAttribute('aria-current') !== current) b.setAttribute('aria-current', current);
    }
  }

  /* Desktop: the left menu stays beside Case, Donors, Chat and Report (only Notes covers it). Those pages sit to the
     right of the menu (--ui2-side). A modal page puts its backdrop over the menu, so a click on that strip is handed to
     the menu button under it, and a menu button first closes the page that is open, then opens its own. */
  const SIDE_PAGES = { case: '#casePage', donors: '#donorsPage', chat: '#hist', report: 'dialog.report-dialog' };
  const sideFoot = () => document.querySelector('.app > .foot');
  function paintSide() {
    const f = sideFoot();
    const w = ui2Wide.matches && f ? Math.round(f.getBoundingClientRect().width) : 0;
    document.documentElement.style.setProperty('--ui2-side', w + 'px');
  }
  const sideOpen = () =>
    Object.entries(SIDE_PAGES)
      .filter(([, q]) => document.querySelector(q)?.open)
      .map(([k]) => k);
  function sideSwitch(key, fn) {
    const open = ui2Wide.matches ? sideOpen() : [];
    if (!open.length) return fn();
    if (open.length === 1 && open[0] === key) return; // already there
    /* Go home first, so closing a page never sends the address back to the page before it. */
    if (typeof Nav !== 'undefined') Nav.go('');
    for (const k of open) {
      if (k === 'case') $('casePage')?.close('route');
      else if (k === 'donors') window.DonorHub?.hide();
      else if (k === 'chat' && typeof closeChat === 'function') closeChat();
      else document.querySelector(SIDE_PAGES[k])?.close();
    }
    setTimeout(fn, 80);
  }
  document.addEventListener(
    'click',
    (e) => {
      const d = e.target;
      if (!ui2Wide.matches || !(d instanceof HTMLDialogElement) || !d.matches(Object.values(SIDE_PAGES).join(',')))
        return;
      const f = sideFoot();
      if (!f || e.clientX >= f.getBoundingClientRect().right) return;
      const hit = [...f.querySelectorAll('button')].find((b) => {
        const r = b.getBoundingClientRect();
        return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      });
      if (!hit) return;
      e.preventDefault();
      e.stopPropagation();
      hit.click();
    },
    true,
  );
  addEventListener('resize', paintSide);
  ui2Wide.addEventListener('change', paintSide);
  new MutationObserver(() => {
    paintTabs();
    paintSide();
  }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open'] });

  /* Start a new case: its name and the amount needed. The old case is saved first. Important and Top donors stay
     the same (keep_lists); donated and DM-sent marks start fresh. */
  function newCase() {
    let d = $('ui2NewCase');
    if (!d) {
      d = mk('dialog', 'ui2-sheet ui2-newcase');
      d.id = 'ui2NewCase';
      d.setAttribute('aria-label', 'Start a new case');
      d.innerHTML =
        '<div class="ui2-sheet-grip" aria-hidden="true"></div><button type="button" class="ui2-sheet-x" aria-label="Close">✕</button>' +
        '<form class="ui2-nc" novalidate><h2>Start a new case</h2>' +
        '<label for="ui2NcName">Case name</label><input id="ui2NcName" type="text" maxlength="60" autocomplete="off" placeholder="For example the child\'s name">' +
        '<label for="ui2NcLeft">Amount needed (Rs.)</label><input id="ui2NcLeft" type="text" inputmode="numeric" autocomplete="off" placeholder="For example 50000">' +
        '<p class="ui2-nc-note"></p><p class="ui2-nc-err" role="alert"></p>' +
        '<div class="ui2-nc-bar"><button type="button" class="ui2-nc-cancel">Cancel</button><button type="submit" class="ui2-nc-go">Start new case</button></div></form>';
      const form = d.querySelector('form'),
        err = d.querySelector('.ui2-nc-err'),
        go = d.querySelector('.ui2-nc-go');
      d.querySelector('.ui2-sheet-x').addEventListener('click', () => d.close());
      d.querySelector('.ui2-nc-cancel').addEventListener('click', () => d.close());
      d.addEventListener('click', (e) => e.target === d && d.close());
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = $('ui2NcName').value.trim(),
          left = Number(String($('ui2NcLeft').value).replace(/[^\d.]/g, ''));
        err.textContent = '';
        if (!name || name.length > 60) return void (err.textContent = 'Write the case name (up to 60 letters).');
        if (!Number.isFinite(left) || left <= 0 || left > 100000000)
          return void (err.textContent = 'Write how much money is needed, for example 50000.');
        go.disabled = true;
        go.textContent = 'Starting…';
        try {
          const r = await post('/cases', { action: 'new', name, left, keep_lists: true }),
            j = await r.json().catch(() => ({}));
          if (!r.ok) throw Error(j.error || 'Could not start the new case.');
          location.reload();
        } catch (x) {
          err.textContent = x.message;
          go.disabled = false;
          go.textContent = 'Start new case';
        }
      });
      document.body.append(d);
    }
    const current =
      ($('caseSelect')?.selectedOptions[0]?.textContent || 'The current case').replace(/ · done ✓$/, '').trim();
    d.querySelector('.ui2-nc-note').textContent =
      '"' + current + '" is saved first and stays in the case list. Important and Top donors stay the same. Donated and DM-sent marks start fresh.';
    $('ui2NcName').value = '';
    $('ui2NcLeft').value = '';
    d.querySelector('.ui2-nc-err').textContent = '';
    d.showModal();
    $('ui2NcName').focus({ preventScroll: true });
  }
  /* The old "＋ New case from zero…" choice asks three browser pop-ups and clears the stars; here it opens the form. */
  $('caseSelect')?.addEventListener(
    'change',
    (e) => {
      if (e.target.value !== '__new') return;
      e.stopImmediatePropagation();
      if (typeof loadCases === 'function') loadCases();
      newCase();
    },
    true,
  );

  /* More: a bottom sheet in thumb reach (page 2). */
  function sheet() {
    let d = $('ui2Sheet');
    if (!d) {
      d = mk('dialog', 'ui2-sheet');
      d.id = 'ui2Sheet';
      d.setAttribute('aria-label', 'More');
      d.innerHTML =
        '<div class="ui2-sheet-grip" aria-hidden="true"></div><button type="button" class="ui2-sheet-x" aria-label="Close">✕</button><div class="ui2-sheet-grid"></div><div class="ui2-sheet-extra"></div>';
      d.querySelector('.ui2-sheet-x').addEventListener('click', () => d.close());
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
    /* One list, rare things on top and the most used at the bottom, next to the thumb:
       Settings · Report · Reply, then the case, then Giki 1 · Giki 2. Notes is a tab, so it is not shown twice. */
    tile(
      'Settings',
      '',
      press(() => $('gear')),
    ).dataset.dup = '1';
    tile(
      'Report',
      'right-now board',
      press(() => document.querySelector('.report-open')),
    ).dataset.dup = '1';
    tile(
      'Reply',
      'chat shortcuts',
      press(() => document.querySelector('.reply-open')),
    );
    tile(
      amount + ' left',
      'change amount',
      press(() => $('leftChip')),
    ).dataset.gap = '1';
    tile('New case', 'Important & Top stay', newCase);
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
    tile('Case page', 'run the whole case', () => Nav.go('case'));
    /* The Giki pages (each with its own list and WhatsApp). On a computer they are in the left menu (data-dup). */
    const giki = tile('Giki 1', 'own list and WhatsApp', () => (location.href = '/giki'));
    giki.id = 'ui2GikiTile';
    giki.classList.add('ui2-tile-giki');
    giki.dataset.dup = '1';
    giki.dataset.gap = '1';
    const giki2 = tile('Giki 2', 'own list and WhatsApp', () => (location.href = '/giki2'));
    giki2.id = 'ui2Giki2Tile';
    giki2.classList.add('ui2-tile-giki');
    giki2.dataset.dup = '1';
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
    /* the most used rows (Giki 1 · Giki 2) are at the bottom: on a short phone the list opens scrolled to them */
    if (d.scrollHeight > d.clientHeight) d.scrollTop = d.scrollHeight;
  }

  /* Keep the primary destination and the three daily controls together at every width. */
  function sendList() {
    const box = document.querySelector('.group-send');
    const two = box?.querySelector('.group-two');
    const main = $('btnGivelife');
    const test = two?.querySelector('.test-row');
    const free = $('btnFree')?.closest('.grp-card');
    const all = $('sendAll')?.closest('.send-row');
    const drop = $('dropFree');
    const choose = $('btnFreePick');
    const mainTimes = $('timerMain');
    const freeTimes = $('timerFree');
    if (
      !two ||
      !main ||
      !test ||
      !free ||
      !all ||
      !drop ||
      !choose ||
      !mainTimes ||
      !freeTimes ||
      $('ui2GroupMore')
    )
      return;

    const name = main.querySelector('.gb-name');
    name.replaceChild(document.createTextNode('Send to GiveLife'), name.firstChild);
    main.querySelector('.gb-go').hidden = true;
    test.querySelector('.gb-go').hidden = true;

    const more = mk('div', 'ui2-group-more');
    more.id = 'ui2GroupMore';
    const groups = mk('div', 'ui2-other-groups');
    groups.id = 'ui2OtherGroups';
    groups.setAttribute('role', 'group');
    groups.setAttribute('aria-label', 'Other group sends');
    const panel = mk('div', 'ui2-later-panel');
    panel.id = 'ui2LaterPanel';
    panel.setAttribute('role', 'group');
    panel.setAttribute('aria-label', 'Schedule group sends');
    const disclosure = (label, id, region) => {
      const button = mk('button', 'ui2-dock-tool', label);
      button.type = 'button';
      button.id = id;
      button.setAttribute('aria-controls', region.id);
      button.setAttribute('aria-expanded', 'false');
      return button;
    };
    /* One quiet button opens both: the other groups and the Timer (fewer buttons on the screen). */
    const other = disclosure('Timer & groups', 'ui2GroupPicker', groups);
    const timer = disclosure('Timer', 'ui2Later', panel);
    other.setAttribute('aria-label', 'Timer & groups');
    other.setAttribute('aria-haspopup', 'true');
    timer.hidden = true; /* kept for the keyboard and old links; the Timer is inside Timer & groups */
    const choices = [
      [other, groups],
      [timer, panel],
    ];
    const show = (current) => {
      for (const [button, region] of choices) {
        const open = button === current || (current === other && region === panel);
        region.hidden = !open;
        button.setAttribute('aria-expanded', String(open));
      }
      /* the two parts of the menu stack above the send buttons: the groups sit on top of the Timer */
      box.style.setProperty('--ui2-later-h', panel.hidden ? '0px' : panel.offsetHeight + 12 + 'px');
      if (current !== other && !drop.hidden) {
        drop.hidden = true;
        choose.setAttribute('aria-expanded', 'false');
      }
    };
    for (const [button, region] of choices) {
      button.addEventListener('click', (event) => {
        const open = region.hidden;
        show(open ? button : null);
        if (open && event.detail === 0) region.querySelector('button:not([disabled])')?.focus();
      });
    }

    const wrap = mk('div', 'group-drop-wrap ui2-choose');
    choose.className = 'ui2-choose-btn';
    choose.textContent = 'Choose group';
    choose.setAttribute('aria-label', 'Choose group');
    choose.setAttribute('aria-controls', drop.id);
    choose.addEventListener('click', () => {
      if (!drop.hidden) requestAnimationFrame(() => drop.scrollIntoView({ block: 'nearest' }));
    });
    wrap.append(choose, drop);
    groups.append(free, all, wrap);
    const emptyTestRow = test.parentElement;
    more.append(other, timer, test);
    emptyTestRow.remove();

    for (const [row, label] of [
      [mainTimes, 'GiveLife'],
      [freeTimes, 'All freelance'],
    ]) {
      const line = mk('div', 'ui2-later-line');
      const title = mk('span', '', label);
      row.hidden = false;
      line.append(title, row);
      panel.append(line);
    }
    two.before(groups, panel);
    two.after(more);
    show(null);
    document.addEventListener('click', (event) => {
      if (!box.contains(event.target) && (!groups.hidden || !panel.hidden)) show(null);
    });
    box.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      if (!drop.hidden) {
        drop.hidden = true;
        choose.setAttribute('aria-expanded', 'false');
        choose.focus();
      } else {
        const active = choices.find(([, region]) => !region.hidden);
        if (!active) return;
        show(null);
        (active[0].hidden ? other : active[0]).focus();
      }
      event.preventDefault();
      event.stopPropagation();
    });
    const paint = () => {
      const pending = [mainTimes, freeTimes].some((row) => row.querySelector('.is-pending'));
      timer.toggleAttribute('data-scheduled', pending);
      timer.title = pending ? 'A group send is scheduled' : 'Schedule a group send';
    };
    new MutationObserver(paint).observe(panel, {
      subtree: true,
      attributes: true,
      attributeFilter: ['class'],
    });
    paint();
    // opened straight on the message page (#/preview, a refresh there): the card sits inside it, outside .app, for now
    (box.closest('.app') || document.querySelector('.app'))?.classList.add('ui2-message-home');
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
    for (const [key, label, hint] of [
      ['ur', 'Urdu + English', 'Write a new message: Urdu + English'],
      ['en', 'English', 'Write a new message: English'],
      [
        'trigger',
        'Trigger',
        'Makes the message on screen stronger, in its own language.',
      ],
      [
        'fix',
        'Style fix',
        'Same words in your style: bold and italic lines, and anything missing added. Nothing new is written.',
      ],
    ]) {
      const b = mk('button', '', label);
      b.type = 'button';
      b.dataset.style = key;
      if (key !== 'fix')
        b.setAttribute('aria-pressed', 'false'); /* Style fix is an action, not a choice */
      b.title = hint;
      b.addEventListener('click', () => {
        Nav.go('preview');
        setTimeout(
          () =>
            document
              .querySelector(
                key === 'fix'
                  ? '#focusStyleFix'
                  : key === 'trigger'
                    ? '.focus-styles [data-trigger]'
                    : `.focus-styles [data-lang="${key}"]`,
              )
              ?.click(),
          250,
        );
      });
      styles.append(b);
    }
    /* The reader tells us what it last wrote, so the chips here show the same choice. */
    addEventListener('message-style-state', (e) => {
      const { lang, trigger } = e.detail || {};
      for (const b of styles.children)
        if (b.dataset.style !== 'fix')
          b.setAttribute(
            'aria-pressed',
            String(b.dataset.style === 'trigger' ? !!lang && trigger : b.dataset.style === lang),
          );
    });
    const poster = $('previewChangePoster');
    const overflow = tools.querySelector('.overflow-tools > div');
    if (overflow) {
      const copy = $('copy');
      copy.textContent = 'Copy';
      overflow.parentElement.before(copy);
      overflow.prepend($('fresh'));
      if (poster) overflow.prepend(poster);
      overflow.append(styles);
    }
    if ($('openCase')) $('openCase').style.display = ''; // More → Case page exists on /new only
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
    'Amount left': 'Amount left is Rs. ',
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
    addChips(chips, $('histCmd'), ['Amount left', 'New wording', 'Send all']);
    form.before(chips);
    /* Money left sits in the chat header (tap = type a new amount) */
    const head = document.querySelector('#hist > header'),
      left = $('leftChip');
    if (head && left) {
      const m = mk('button', 'ui2-hist-left', '');
      m.type = 'button';
      m.id = 'ui2HistLeft';
      const sync = () => (m.textContent = left.textContent.trim());
      sync();
      new MutationObserver(sync).observe(left, { childList: true, subtree: true, characterData: true });
      m.addEventListener('click', () => chips.firstChild?.click());
      head.append(m);
    }
    /* Keyboard open: the chat fits the space above it and the newest reply stays in view */
    const vv = window.visualViewport,
      hist = $('hist'),
      log = $('histLog');
    if (vv && hist) {
      const fit = () => {
        hist.style.setProperty('--ui2-hist-vvh', Math.round(vv.height) + 'px');
        const kb = innerHeight - vv.height > 120;
        if (kb !== hist.classList.contains('ui2-kb')) {
          hist.classList.toggle('ui2-kb', kb);
          if (kb && log) log.scrollTop = log.scrollHeight;
        }
      };
      vv.addEventListener('resize', fit);
      fit();
    }
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
  ui2Observe(ui2Frame(run), {
    characterData: true,
  });
  for (const q of ['(min-width: 900px)', '(min-width: 700px)'])
    matchMedia(q).addEventListener('change', relayout);
  addEventListener('studio-navigate', paintTabs);
  addEventListener('popstate', paintTabs);
  addEventListener('hashchange', paintTabs);
})();

/* 8. Message reader and editor (PDF pages 10-14).
   One bottom row: Test (group message) or Copy (DM message), Edit (Done while editing), ⋯ and Back; the other one, Save Base and Next wording live inside ⋯.
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
    for (const id of ['focusNext', 'focusTest', 'focusCopy', 'focusSave']) {
      const b = $(id);
      if (b && panel) panel.prepend(b);
    }
    const sum = more.querySelector('summary');
    sum.textContent = 'More';
    /* Minimal reader (owner's pick): the message fills the screen at full width; one thin row under it with
       ‹ 1 of 5 › (a quick swipe on the message does the same) and 📎 files; then Edit | Copy | Test | More | Back.
       More holds Rewrite (Urdu + English, English, Trigger, Style fix), New versions, Save Base and the files.
       The real buttons are moved, never rebuilt. */
    /* Owner's layout: Copy, Edit, Save base and ⋯ More sit on the message (bottom right). The bottom row is
       Generate · Test · Back (Back right-most, under the thumb). The real buttons are moved, never rebuilt. */
    const tools = document.createElement('div');
    tools.id = 'ui2MsgTools';
    tools.className = 'ui2-msgtools';
    tools.setAttribute('role', 'group');
    tools.setAttribute('aria-label', 'Message tools');
    for (const id of ['focusCopy', 'focusEdit']) if ($(id)) tools.append($(id));
    tools.append(more);
    $('focusFormatted')?.after(tools);
    /* ⋯ More closes with a tap outside it (that tap does nothing else) or with Esc */
    document.addEventListener(
      'click',
      (e) => {
        if (!more.open || more.contains(e.target) || e.target.closest?.('dialog[open]')) return; // a dialog opened from More works
        more.open = false;
        e.preventDefault();
        e.stopPropagation();
      },
      true,
    );
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && more.open) more.open = false;
    });
    if ($('focusTest')) bar.append($('focusTest'));
    /* More opens upward; when there is no room above (a short message on a computer) it opens downward */
    more.addEventListener('toggle', () => {
      if (!more.open) return;
      const list = more.querySelector(':scope > div');
      more.dataset.down = '0';
      requestAnimationFrame(() => {
        if (list && list.getBoundingClientRect().top < 8) more.dataset.down = '1';
      });
    });
    if ($('focusBack')) {
      bar.append($('focusBack'));
      $('focusBack').setAttribute('aria-label', 'Back');
    }
    /* the More sheet covers the More button: a clear Done closes it (tapping outside or Esc still works) */
    const sheet = more?.querySelector(':scope > div');
    if (sheet && !sheet.querySelector('.ui2-more-done')) {
      const done = document.createElement('button');
      done.type = 'button';
      done.className = 'ui2-more-done';
      done.textContent = 'Done';
      done.addEventListener('click', () => {
        more.open = false;
        more.querySelector('summary')?.focus({ preventScroll: true });
      });
      sheet.prepend(done);
    }
    /* a short note above the rewrite row: what was written, or why it was not (the status line is hidden on phones) */
    if (!$('ui2Note')) {
      const n = document.createElement('div');
      n.id = 'ui2Note';
      n.className = 'ui2-note';
      n.setAttribute('role', 'status');
      n.hidden = true;
      screen.append(n);
      addEventListener('message-note', (e) => {
        const { text, error } = e.detail || {};
        if (!text) return;
        n.textContent = text;
        n.dataset.error = error ? '1' : '';
        n.hidden = false;
        clearTimeout(n._t);
        n._t = setTimeout(() => (n.hidden = true), error ? 8000 : 3500);
      });
      n.addEventListener('click', () => (n.hidden = true));
    }
    const rw = document.createElement('div'); // English · Urdu + English · Trigger · Style fix, one tap each
    rw.id = 'ui2RewriteRow';
    rw.className = 'ui2-rewrite-row';
    rw.setAttribute('role', 'group');
    rw.setAttribute('aria-label', 'Rewrite the message');
    const styles = screen.querySelector('.focus-styles');
    if (styles) rw.append(styles);
    if ($('focusStyleFix')) rw.append($('focusStyleFix'));
    if (panel && !panel.dataset.ui2Top) {
      panel.dataset.ui2Top = '1';
      /* More keeps only the files list and Manual messages. Next version, Save Base, Generate and Replace are
         already on the screen (‹ ›, 💾, Generate), so their real buttons wait here, hidden, for those to press. */
      let keep = $('ui2Keep');
      if (!keep) {
        keep = document.createElement('span');
        keep.id = 'ui2Keep';
        keep.hidden = true;
        screen.append(keep);
      }
      for (const id of ['focusNext', 'focusSave', 'focusRetry', 'focusRegenerate']) if ($(id)) keep.append($(id));
    }
    const paper = $('focusFormatted')?.parentElement;
    if (paper && !$('ui2Swipe')) {
      const sw = document.createElement('div');
      sw.id = 'ui2Swipe';
      sw.className = 'ui2-swipe';
      sw.innerHTML =
        '<button type="button" class="ui2-swipe-prev" aria-label="Previous version">‹</button>' +
        '<span class="ui2-ver" aria-live="polite">Original</span>' +
        '<button type="button" class="ui2-swipe-next" aria-label="Next version">›</button>' +
        '<span class="ui2-swipe-gap"></span>' +
        '<button type="button" class="ui2-gen-btn" aria-label="Write 5 new versions" title="Delete the old versions and write 5 new ones"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg><span class="ui2-gen-w">Generate</span></button>' +
        '<button type="button" class="ui2-base-btn" title="Make the message you see the base message. New versions are written from it.">Save base</button>' +
        '<button type="button" class="ui2-files-btn" aria-label="Files that go with the message">📎<span class="ui2-files-w"> Files</span></button>';
      bar.before(sw);
      sw.after(rw);
      bar.prepend(sw.querySelector('.ui2-gen-btn')); // bottom row: Generate · Test · Back
      const baseBtn = sw.querySelector('.ui2-base-btn'); // Save base: a small 💾 on the message
      baseBtn.setAttribute('aria-label', 'Save base');
      baseBtn.innerHTML =
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>';
      tools.insertBefore(baseBtn, more);
      let navAt = 0; // a version change slides; any other new text (a rewrite, Generate) fades in instead
      /* ‹ ›: the next / previous version slides in from that side, like a swipe */
      const go = (dir) => {
        navAt = Date.now();
        return Promise.resolve(window.focusVersionStep ? window.focusVersionStep(dir) : $('focusNext')?.click()).then(
          (changed) => {
            if (!changed) return;
            slide(dir * 28, 0);
            void msg.offsetWidth;
            slide(0, 200);
          }
        );
      };
      baseBtn.onclick = () => $('focusSave')?.click();
      /* Write 5 new versions: presses the real Generate button; it waits while versions are being written */
      const writeBtn = bar.querySelector('.ui2-gen-btn');
      // ✦ = replace: the old versions are deleted and a fresh 5 are written from the base message
      writeBtn.onclick = () => ($('focusRegenerate') || $('focusRetry'))?.click();
      if ($('focusRetry')) {
        /* While 5 versions are being written the sparkle becomes the live count: 0/5, 1/5 … 5/5 */
        const icon = writeBtn.innerHTML;
        const sync = () => {
          const busy = $('focusRetry').disabled;
          writeBtn.disabled = busy;
          writeBtn.dataset.busy = busy ? '1' : '';
          const count = busy ? $('focusState')?.querySelector('.fx-count')?.textContent || '0/5' : '';
          if (busy) {
            if (writeBtn.textContent !== count) writeBtn.textContent = count;
            writeBtn.setAttribute('aria-label', 'Writing versions ' + count.replace('/', ' of '));
          } else if (writeBtn.dataset.count) {
            writeBtn.innerHTML = icon;
            writeBtn.setAttribute('aria-label', 'Write 5 new versions');
          }
          writeBtn.dataset.count = count;
        };
        sync();
        new MutationObserver(sync).observe($('focusRetry'), { attributes: true, attributeFilter: ['disabled'] });
        if ($('focusState'))
          new MutationObserver(sync).observe($('focusState'), { childList: true, subtree: true, characterData: true });
      }
      sw.querySelector('.ui2-swipe-prev').onclick = () => go(-1);
      sw.querySelector('.ui2-swipe-next').onclick = () => go(1);
      sw.querySelector('.ui2-files-btn').onclick = () => {
        more.open = true;
        requestAnimationFrame(() => $('ui2ReaderExtras')?.scrollIntoView({ block: 'nearest' }));
      };
      const ver = sw.querySelector('.ui2-ver');
      const verBox = document.createElement('span'); // "4 of 10" with "or swipe the message" under it (phone, tablet)
      verBox.className = 'ui2-ver-box';
      ver.before(verBox);
      const hint = document.createElement('small');
      hint.className = 'ui2-swipe-hint';
      hint.textContent = 'or swipe the message';
      verBox.append(ver, hint);
      /* a new, unsaved text: the middle of the pill is a yellow "✓ Save" button; after it, "Saved" for a moment */
      let savedT = 0,
        askedAt = 0; // Save was tapped: "✓ Saved" shows when the text really is saved (after the confirm box)
      const saveDraft = () => {
        if (sw.dataset.draft !== '1') return;
        askedAt = Date.now();
        baseBtn.click();
      };
      const savedNow = () => {
        sw.dataset.saved = '1';
        clearTimeout(savedT);
        savedT = setTimeout(() => {
          sw.dataset.saved = '';
          paintDots();
        }, 1400);
      };
      // the confirm box closed: a save finishes within moments; after that a cleared draft is not a save (‹ › went back)
      $('focusBaseDialog')?.addEventListener('close', () => setTimeout(() => (askedAt = 0), 3000));
      verBox.addEventListener('click', saveDraft);
      verBox.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          saveDraft();
        }
      });
      /* minimal: ‹ 1/5 › sits inside the message (bottom left, next to the small icons), so there is one row less;
         a new, unsaved text turns the pill yellow ("Not saved") */
      tools.prepend(sw);
      const paintDots = () => {
        const v = $('focusVersion'),
          n = Number(v?.dataset.n || 0),
          i = Number(v?.dataset.i || 0);
        // phones: a short label, so it never runs into the › arrow ("1/5", "Base +5")
        const narrow = matchMedia('(max-width: 480px)').matches,
          tiny = matchMedia('(max-width: 380px)').matches;
        const draft = v?.dataset.draft === '1'; // a button wrote it: not saved, never called "Base"
        if (!draft && sw.dataset.draft === '1' && askedAt && Date.now() - askedAt < 120000) {
          askedAt = 0;
          if ((Number(v?.dataset.i || 0) || 0) === 0) savedNow(); // it became the base: say so where the finger is
        }
        sw.dataset.draft = draft ? '1' : ''; // a new text: the white "Save" capsule (tap to save)
        if (draft) {
          verBox.setAttribute('role', 'button');
          verBox.tabIndex = 0;
          verBox.setAttribute('aria-label', 'Not saved. Save this text');
        } else {
          verBox.removeAttribute('role');
          verBox.removeAttribute('tabindex');
          verBox.removeAttribute('aria-label');
        }
        ver.textContent = draft
          ? 'Save'
          : sw.dataset.saved === '1'
            ? 'Saved'
            : i
            ? i + '/' + n
            : n && !tiny
              ? 'Base +' + n
              : 'Base'; // a short label: it sits in a small pill inside the message
        baseBtn.dataset.pending = i || draft ? '1' : ''; // Save base makes what is showing the base
      };
      paintDots();
      if ($('focusVersion'))
        new MutationObserver(paintDots).observe($('focusVersion'), {
          attributes: true,
          attributeFilter: ['data-n', 'data-i', 'data-draft'],
        });
      /* swipe the message sideways: it follows the finger; past 60px (or a quick flick) it slides out and the next /
         previous version slides in. With no versions yet, the swipe makes them. */
      const msg = $('focusFormatted');
      /* the message box fills the space the phone really shows (it shrinks when the keyboard opens) */
      const vv = window.visualViewport;
      const fitVv = () => {
        screen.style.setProperty('--ui2-vvh', Math.round(vv ? vv.height : innerHeight) + 'px');
        // the keyboard opened or closed: the message measures its size again for the new height
        requestAnimationFrame(() => window.focusFit?.(true));
      };
      fitVv();
      (vv || window).addEventListener('resize', fitVv);
      const still = matchMedia('(prefers-reduced-motion: reduce)');
      let start = null,
        gen = 0; // each swipe gets a number: a newer swipe cancels the animation of an older one
      const slide = (x, ms) => {
        msg.style.transition = ms && !still.matches ? 'transform ' + ms + 'ms cubic-bezier(.2,.8,.2,1), opacity ' + ms + 'ms ease' : x ? 'none' : '';
        msg.style.transform = x ? 'translate3d(' + x + 'px,0,0)' : '';
        msg.style.opacity = x ? String(Math.max(0.35, 1 - Math.abs(x) / 400)) : '';
      };
      /* any other new text (a rewrite, Trigger, Generate, Done) fades in, so the change is seen and never jumps */
      new MutationObserver(() => {
        if (still.matches || Date.now() - navAt < 1200 || !msg.textContent.trim()) return;
        msg.animate?.([{ opacity: 0.25 }, { opacity: 1 }], { duration: 260, easing: 'ease-out' });
      }).observe(msg, { childList: true, characterData: true, subtree: true });
      paper.addEventListener('pointerdown', (e) => {
        if (!$('focusText')?.hidden || e.target.closest('button, a, summary, details, textarea, [contenteditable="true"]')) return;
        if (matchMedia('(min-width: 900px)').matches) return; // the computer: Previous / Next buttons, no swipe
        gen++; // a swipe made while the last one is still sliding takes over at once
        slide(0, 0);
        start = { x: e.clientX, y: e.clientY, t: Date.now(), dx: 0, side: false };
      });
      paper.addEventListener('pointermove', (e) => {
        if (!start) return;
        const dx = e.clientX - start.x,
          dy = e.clientY - start.y;
        if (!start.side) {
          if (Math.abs(dy) > 12 && Math.abs(dy) > Math.abs(dx)) return (start = null); // reading: a vertical scroll
          if (Math.abs(dx) < 6) return;
          start.side = true;
          paper.setPointerCapture?.(e.pointerId);
        }
        start.dx = dx;
        /* one paint per frame while the finger moves */
        if (!start.raf)
          start.raf = requestAnimationFrame(() => {
            if (start) {
              start.raf = 0;
              slide(start.dx, 0);
            }
          });
      });
      /* Let go past 40px (or a quick flick): the next / previous version shows AT ONCE and slides in from the side the
         finger came from. It does not wait for the old one to slide out or for the server. */
      const finish = () => {
        if (!start) return;
        const { dx, t, side, raf } = start;
        if (raf) cancelAnimationFrame(raf);
        start = null;
        if (!side) return;
        const flick = Math.abs(dx) > 20 && Date.now() - t < 300;
        if (Math.abs(dx) < 40 && !flick) return slide(0, 160);
        const mine = ++gen,
          w = paper.clientWidth || 360,
          dir = dx < 0 ? 1 : -1;
        navAt = Date.now();
        Promise.resolve(window.focusVersionStep ? window.focusVersionStep(dir, true) : false).then((changed) => {
          if (mine !== gen) return; // a newer swipe took over
          slide(changed ? dir * w * 0.3 : dx, 0);
          void msg.offsetWidth;
          slide(0, 170);
        });
      };
      paper.addEventListener('pointerup', finish);
      paper.addEventListener('pointercancel', () => {
        if (start?.side) slide(0, 180);
        start = null;
      });
    }
    bar.dataset.ui2Row = '1';
    dockKind();
  }
  /* Test and Copy stay in the bottom row for a group and for a DM message alike. */
  function dockKind() {
    const screen = $('messageFocus');
    const bar = screen?.querySelector('.ui2-reader-dock');
    if (!bar || !bar.dataset.ui2Row) return;
    const tools = $('ui2MsgTools');
    for (const id of ['focusEdit', 'focusCopy']) {
      const b = $(id);
      if (b && tools && b.parentElement !== tools) tools.prepend(b);
    }
    const test = $('focusTest');
    if (test && test.parentElement !== bar) bar.insertBefore(test, $('focusBack'));
    screen.querySelector('.focus-rail-more > summary')?.setAttribute('aria-label', 'More: rewrite, new versions, Save Base and files');
  }
  addEventListener('reader-kind', dockKind);

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
      } else loose += n.nodeType === 3 ? n.nodeValue.replace(/\u00a0/g, ' ') : inline({ childNodes: [n] });
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
      '<button type="button" data-ins="🤲" aria-label="Dua">Dua</button>';
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
    /* Paste = the text exactly as copied. The caret may sit inside an old bold / italic line (an emptied bold line
       keeps its <b>), and plain insertText would then be bold too (the whole message came out *wrapped*). So the
       caret is first lifted OUT of every <b> / <i> (splitting them around it), then the text goes in. */
    const isMark = (n) => n && n !== ed && /^(B|I|STRONG|EM)$/.test(n.nodeName);
    function liftCaretOutOfMarks() {
      const sel = getSelection();
      if (!sel.rangeCount) return;
      const range = sel.getRangeAt(0);
      let node = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
      const chain = [];
      for (let n = node; n && n !== ed; n = n.parentElement) if (isMark(n)) chain.push(n); // innermost first
      for (const f of chain) {
        const tail = document.createRange();
        tail.setStart(range.startContainer, range.startOffset);
        tail.setEnd(f, f.childNodes.length);
        const rest = tail.extractContents();
        if (rest.textContent !== '') {
          const copy = f.cloneNode(false);
          copy.append(rest);
          f.after(copy); // what was after the caret stays formatted
        }
        const empty = f.textContent === '';
        range.setStartAfter(f);
        range.collapse(true);
        if (empty) f.remove();
      }
      sel.removeAllRanges();
      sel.addRange(range);
      for (const cmd of ['bold', 'italic']) if (document.queryCommandState(cmd)) document.execCommand(cmd);
    }
    ed.addEventListener('paste', (e) => {
      e.preventDefault();
      let text = e.clipboardData.getData('text/plain') || '';
      if (!text) {
        // some apps copy only HTML: take its words, a line break for each <br> and block
        const html = e.clipboardData.getData('text/html');
        if (html)
          text = new DOMParser()
            .parseFromString(html.replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|li|h[1-6])>/gi, '</$1>\n'), 'text/html')
            .body.textContent.replace(/\n{3,}/g, '\n\n').replace(/\n+$/, '');
      }
      text = text.replace(/\r\n?/g, '\n');
      if (!text) return;
      const sel = getSelection();
      if (!sel.rangeCount || !ed.contains(sel.anchorNode)) return;
      if (!sel.isCollapsed) document.execCommand('delete'); // pasting over a selection replaces it
      liftCaretOutOfMarks();
      document.execCommand('insertText', false, text);
      push();
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
  ui2Observe(ui2Frame(run));
})();

/* 9. Donors (PDF pages 15-23, V4 page 40). Same tab words on phone and computer, search as an icon on a phone,
   "+ Add" opens Add numbers first, DM ★ Important shows how many, and while DMs go out the bar is ONE amber
   "Stop DMs · 3 of 7 sent". All buttons are the existing ones, moved or relabelled. */
(() => {
  const $ = (id) => document.getElementById(id);
  const wide = () => ui2Wide.matches;
  const setText = (n, t) => n && n.textContent !== t && (n.textContent = t);
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
    /* Phone: the menu is one "More" button at the end of the tabs row; computer: the "+ Add" button in the header. */
    setText(sum, phone ? 'More' : '+ Add');
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
    /* Phone: search icon and "More" end the tabs row; the hide / deselect chips live inside "More". Computer: back in the header. */
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
    head();
    bottom();
  };
  run();
  ui2Observe(ui2Frame(run), {
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

  /* Notes (calm writer): only the text on the page. The top row is just ← and a full-screen icon. The tool bar
     (Normal / Title / Heading, B I U, list, checklist, colour) appears only while text is selected. */
  const NOTE_COLORS = [
    ['Default', '#ededed'],
    ['Red', '#f4a4ad'],
    ['Orange', '#fdba74'],
    ['Yellow', '#fde047'],
    ['Green', '#86efac'],
    ['Blue', '#93c5fd'],
    ['Purple', '#c4b5fd'],
  ];
  function notes() {
    const tools = $('notesTools'),
      ed = $('notesEditor'),
      page = $('foundationNotes');
    if (!tools || !ed || !page) return;
    const full = $('notesFullscreen');
    if (full && !full.getAttribute('aria-label')) full.setAttribute('aria-label', 'Full screen');
    if (tools.querySelector('#ui2NoteStyle')) return;
    const keep = (b) => b.addEventListener('mousedown', (e) => e.preventDefault());
    const changed = () => ed.dispatchEvent(new Event('input', { bubbles: true }));
    let saved = null;
    const remember = () => {
      const sel = getSelection();
      if (sel.rangeCount && ed.contains(sel.anchorNode)) saved = sel.getRangeAt(0).cloneRange();
    };
    const restore = () => {
      ed.focus({ preventScroll: true });
      if (!saved) return;
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(saved);
    };
    const style = mk('select', 'ui2-note-style');
    style.id = 'ui2NoteStyle';
    style.setAttribute('aria-label', 'Text style');
    for (const [v, t] of [
      ['p', 'Normal'],
      ['h1', 'Title'],
      ['h2', 'Heading'],
    ])
      style.append(new Option(t, v));
    style.addEventListener('change', () => {
      restore();
      document.execCommand('formatBlock', false, style.value);
      changed();
      remember();
    });
    const sep = () => mk('span', 'ui2-note-sep');
    const marks = [];
    for (const [cmd, html, label] of [
      ['bold', '<b>B</b>', 'Bold'],
      ['italic', '<i>I</i>', 'Italic'],
      ['underline', '<u>U</u>', 'Underline'],
    ]) {
      const b = mk('button', 'ui2-note-' + cmd, '');
      b.type = 'button';
      b.innerHTML = html;
      b.setAttribute('aria-label', label);
      b.title = label;
      keep(b);
      b.addEventListener('click', () => {
        restore();
        document.execCommand(cmd);
        changed();
        remember();
      });
      marks.push(b);
    }
    const lists = [...tools.querySelectorAll('button')].filter((b) => b.id !== 'notesRed');
    for (const b of lists) {
      if (b.id === 'notesChecklist') b.textContent = '☑';
      else {
        b.textContent = '•≡';
        b.setAttribute('aria-label', 'Bulleted list');
      }
    }
    /* Colour: one button, a row of seven colours opens above the bar */
    const swatches = mk('div', 'ui2-note-swatches');
    swatches.hidden = true;
    swatches.setAttribute('role', 'group');
    swatches.setAttribute('aria-label', 'Text colour');
    const color = mk('button', 'ui2-note-color', '');
    color.type = 'button';
    color.setAttribute('aria-label', 'Text colour');
    color.title = 'Colour';
    keep(color);
    color.addEventListener('click', () => {
      swatches.hidden = !swatches.hidden;
      color.setAttribute('aria-expanded', String(!swatches.hidden));
    });
    for (const [name, hex] of NOTE_COLORS) {
      const c = mk('button', 'ui2-note-swatch', '');
      c.type = 'button';
      c.style.setProperty('--c', hex);
      c.setAttribute('aria-label', name);
      c.title = name;
      keep(c);
      c.addEventListener('click', () => {
        restore();
        document.execCommand('foreColor', false, hex);
        changed();
        remember();
        swatches.hidden = true;
        color.setAttribute('aria-expanded', 'false');
      });
      swatches.append(c);
    }
    const red = $('notesRed');
    if (red) red.hidden = true;
    tools.replaceChildren(swatches, style, sep(), ...marks, sep(), ...lists, color);
    if (red) tools.append(red);
    /* Show the bar only while text is selected in the note */
    let hideTimer = 0;
    const show = (on) => {
      page.toggleAttribute('data-ui2-sel', on);
      if (!on) {
        swatches.hidden = true;
        color.setAttribute('aria-expanded', 'false');
      }
    };
    document.addEventListener('selectionchange', () => {
      const sel = getSelection();
      const on = sel.rangeCount > 0 && !sel.isCollapsed && ed.contains(sel.anchorNode);
      clearTimeout(hideTimer);
      if (on) {
        remember();
        const n = sel.anchorNode.nodeType === 3 ? sel.anchorNode.parentElement : sel.anchorNode;
        const blk = n.closest('h1,h2,h3,li,p,div');
        style.value = blk && /^H[12]$/.test(blk.tagName) ? blk.tagName.toLowerCase() : 'p';
        show(true);
      } else
        hideTimer = setTimeout(() => {
          if (!tools.contains(document.activeElement)) show(false);
        }, 300);
    });
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
      /* Minimal text: "4/15 · next 10:00", "6/20 · check WhatsApp", nothing at all when there is nothing to say. */
      const num = (k) => Number(dd[dt.indexOf(k)]) || 0,
        sent = num('sent'),
        total = Number(card.dataset.progressTotal) || sent + num('left'),
        at = dd[dt.indexOf('next')],
        isGroup = card.dataset.control === 'group',
        run = card.dataset.state === 'ON' || card.dataset.state === 'STOPPING',
        bits = [];
      if (sent || total) bits.push(isGroup ? sent + ' sent' : sent + '/' + total + ' sent');
      if (run && at && at !== '—') bits.push('next ' + at);
      if (card.dataset.alert === '1') bits.push('check WhatsApp');
      setText(sub, bits.join(' · '));
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
  ui2Observe(ui2Frame(run), {
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
  function row(id, regen, next, mini) {
    const r = document.createElement('div');
    r.className = 'ui2-gnav' + (mini ? ' ui2-gmini' : '');
    r.id = id;
    const a = mk('ui2-gbtn', 'Regenerate', REGEN, regen),
      b = mk('ui2-gbtn ui2-gnext', 'Next', NEXT, next);
    if (mini)
      for (const x of [a, b]) {
        x.setAttribute('aria-label', x.textContent); /* the word stays for screen readers and tests */
        x.title = x.textContent;
      }
    r.append(a, b);
    return r;
  }
  /* Main screen: two small buttons sit inside the message, bottom right (thumb side): Rewrite opens the message page
     with every tool (Copy, Edit, Save base, ⋯, English, Urdu + English, Trigger, Style fix, Generate), and ‹ 2/6 ›
     steps through the saved versions (#ui2VerNav, added by the versions block below). */
  function main() {
    const chat = $('chat'),
      card = $('card');
    if (!chat || !card || $('ui2GnavMain')) return;
    card.classList.add('ui2-has-mini');
    const r = document.createElement('div');
    r.className = 'ui2-gnav ui2-gmini ui2-inmsg';
    r.id = 'ui2GnavMain';
    const PEN =
      '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>';
    const rw = mk('ui2-gbtn ui2-rewrite', 'Rewrite', PEN, () => {
      if (typeof Nav !== 'undefined') Nav.go('preview');
    });
    rw.title = 'Rewrite: English, Urdu + English, Trigger, Style fix, Generate, Copy, Edit';
    r.append(rw);
    const ver = $('ui2VerNav');
    if (ver) r.append(ver);
    $('groupPreview')?.after(r);
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
  /* Reader (the page a message opens): "Also send:" PDF / Video under the message.
     Group message: attach the PDF and the video here (Add / Change) and tick which ones go; they follow the poster and
     caption of every group post, Auto too (every 45 minutes). They are the case's files, stored once.
     DM message: the same two ticks only; they take those same files and follow each donor's DM (poster + caption). */
  function readerExtras() {
    const nav = $('ui2GnavReader');
    if (!nav || $('ui2ReaderExtras')) return;
    const mk = (tag, cls, text) => {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text != null) n.textContent = text;
      return n;
    };
    const box = mk('div', 'ui2-rx');
    box.id = 'ui2ReaderExtras';
    box.setAttribute('role', 'group');
    const rxLabel = mk('span', 'ui2-rx-label', 'Sends in this order');
    const items = {};
    let order = ['poster', 'video', 'pdf']; // 1st, 2nd, 3rd after the case message (kept on the server)
    const ORD = ['1st', '2nd', '3rd'];
    let uploading = false;
    const msg = mk('p', 'ui2-rx-msg', '');
    msg.setAttribute('role', 'status');
    for (const [kind, name, accept] of [
      ['pdf', 'PDF', 'application/pdf'],
      ['video', 'Video', 'video/mp4'],
      ['poster', 'Poster', 'image/jpeg,image/png,image/webp'], // the AFTER poster: its own picture
    ]) {
      const item = mk('div', 'ui2-rx-item');
      item.dataset.kind = kind;
      const lab = mk('label', 'ui2-rx-chip');
      const cb = mk('input');
      cb.type = 'checkbox';
      cb.id = 'ui2Rx-' + kind;
      cb.addEventListener('change', () => change(kind, cb.checked));
      const meta = mk('small', 'ui2-rx-meta', '');
      const th = mk('span', 'ui2-rx-th');
      lab.append(cb, mk('span', 'ui2-rx-name', name), meta);
      const file = mk('input');
      file.type = 'file';
      file.accept = accept;
      file.hidden = true;
      file.id = 'ui2RxFile-' + kind;
      const add = mk('label', 'ui2-rx-add');
      add.htmlFor = file.id;
      const addWord = mk('span', '', 'Add');
      add.append(addWord);
      add.title = 'Attach the ' + name + ' (the case file for every group post and every DM)';
      file.addEventListener('change', async () => {
        const f = file.files[0];
        file.value = '';
        if (!f || uploading) return;
        if (f.size > 15_000_000) return void (msg.textContent = 'Choose a ' + name + ' under 15 MB.');
        uploading = true;
        msg.textContent = '';
        const it = items[kind];
        it.item.dataset.up = '1';
        it.item.setAttribute('aria-busy', 'true');
        for (const x of Object.values(items)) x.cb.disabled = true;
        // Live percentage: the bar fills behind the word as the bytes go up; "Saving" while the server checks the file.
        const show = (sent, total, phase) => {
          const pct = total ? Math.min(99, Math.floor((sent / total) * 100)) : 0;
          it.item.style.setProperty('--p', (phase === 'saving' ? 100 : pct) + '%');
          it.add.textContent = phase === 'saving' ? 'Saving' : pct + '%';
        };
        try {
          const d = await uploadFile(
            '/group-extras-file',
            f,
            { 'X-Extra-Kind': kind, 'X-File-Name': encodeURIComponent(f.name) },
            show,
          );
          take(d);
          dispatchEvent(new CustomEvent('group-extras-changed'));
        } catch (e) {
          msg.textContent = e.message;
          load();
        } finally {
          uploading = false;
          it.item.removeAttribute('data-up');
          it.item.removeAttribute('aria-busy');
          it.item.style.removeProperty('--p');
          paint();
        }
      });
      const rank = mk('span', 'ui2-rx-rank', '');
      const up = mk('button', 'ui2-rx-up', '↑');
      up.type = 'button';
      up.id = 'ui2RxUp-' + kind;
      up.title = 'Send this one earlier';
      up.addEventListener('click', () => moveUp(kind));
      item.append(rank, th, lab, add, up, file);
      box.append(item);
      items[kind] = { item, cb, add: addWord, file: add, lab, meta, th, rank, up };
    }
    /* Which file carries the message text (same setting as in Poster): only shown once a video is attached */
    const textRow = mk('div', 'ui2-rx-text');
    textRow.id = 'ui2RxText';
    textRow.setAttribute('role', 'group');
    textRow.setAttribute('aria-label', 'Text goes on');
    textRow.append(mk('span', 'ui2-rx-text-label', 'Text goes on:'));
    /* Group and DM each keep their own choice (the group message view sets the groups, the DM view the DMs) */
    let setupAll = {};
    let posterKind = 'image';
    const profile = () => (isDm() ? 'dm' : 'group');
    const mine = () => setupAll[profile()] || { text_on: 'video', poster: true };
    async function saveSetup(field, value) {
      msg.textContent = '';
      try {
        // the text choice is one for groups and DMs together; the PDF / video / poster ticks stay per place
        const r = await post('/group-extras', field === 'text_on' ? { action: 'text_on', value } : { action: 'setup', profile: profile(), field, value }),
          d = await r.json().catch(() => ({}));
        if (!r.ok) throw Error(d.error || 'Could not save that.');
        take(d);
        dispatchEvent(new CustomEvent('group-extras-changed'));
      } catch (e) {
        msg.textContent = e.message;
        load();
      }
    }
    for (const [v, label] of [
      ['video', 'Video'],
      ['poster', 'Poster'],
    ]) {
      const b = mk('button', 'ui2-rx-text-b', label);
      b.type = 'button';
      b.dataset.v = v;
      b.id = 'ui2RxText-' + v;
      b.addEventListener('click', () => saveSetup('text_on', v));
      textRow.append(b);
    }
    /* "Order: 1. Video + text  2. Poster  3. PDF": what WhatsApp will get, in order, updated on every tick or tap.
       It follows the server (group_extras.lead / to_send / after_items, DonorDelivery._after_kinds): when the text
       goes on the video the case poster is not sent; the ticked Poster is the after poster. */
    const orderLine = mk('p', 'ui2-rx-order', '');
    orderLine.id = 'ui2RxOrder';
    orderLine.setAttribute('aria-live', 'polite');
    /* Top of the list: the case message itself (its poster or video is changed here), then which file carries
       its text. Then 1st / 2nd / 3rd: the files in the order they are sent. */
    const caseRow = mk('div', 'ui2-rx-case');
    caseRow.id = 'ui2RxCase';
    const caseWord = mk('span', 'ui2-rx-casew', 'Case message');
    const caseNote = mk('small', 'ui2-rx-casen', '');
    const caseTop = $('focusPoster');
    if (caseTop) {
      caseTop.textContent = 'Change';
      caseTop.title = 'Change the case poster or video';
      caseTop.setAttribute('aria-label', 'Change the case poster or video');
    }
    caseRow.append(caseWord, caseNote);
    if (caseTop) caseRow.append(caseTop);
    box.prepend(rxLabel, caseRow, textRow, orderLine);
    box.append(msg);
    /* The attached files live inside More (a row each: preview, name, tick, Add / Change), so the reader grows by
       nothing. A small preview chip for each ATTACHED and ticked file shows under the message. */
    const panel = document.querySelector('#messageFocus .focus-rail-more > div');
    if (panel) panel.prepend(box);
    else nav.after(box);
    const chips = mk('div', 'ui2-att');
    chips.id = 'ui2AttChips';
    chips.setAttribute('aria-label', 'Attached files');
    document.querySelector('#messageFocus .ui2-reader-dock')?.before(chips);
    const thumbs = {}; // the blob URL of the saved poster / video, fetched once per saved file (the promise is cached)
    const preview = (kind, name) => {
      if (kind === 'pdf') return Promise.resolve('');
      const t = thumbs[kind];
      if (t && t.name === name) return t.promise;
      t?.promise.then((u) => u && URL.revokeObjectURL(u));
      const promise = fetch('/group-extras-media/' + kind, { cache: 'no-store' })
        .then((r) => (r.ok ? r.blob() : null))
        .then((b) => (b ? URL.createObjectURL(b) : ''))
        .catch(() => '');
      thumbs[kind] = { name, promise };
      return promise;
    };
    const picture = (kind, url) => {
      if (kind === 'pdf' || !url) return mk('span', 'ui2-att-th ui2-att-' + kind, kind === 'pdf' ? 'PDF' : kind === 'video' ? '▶' : '');
      const el = mk(kind === 'video' ? 'video' : 'img', 'ui2-att-th');
      if (kind === 'video') {
        el.muted = true;
        el.preload = 'metadata';
        el.playsInline = true;
        el.src = url + '#t=0.1';
      } else {
        el.src = url;
        el.alt = '';
      }
      return el;
    };
    $('messageFocus')?.classList.add('ui2-has-rx');
    const have = { pdf: false, video: false, poster: false },
      names = { pdf: '', video: '', poster: '' },
      sizes = { pdf: 0, video: 0, poster: 0 },
      groupOn = { pdf: false, video: false, poster: false };
    let dmOn = { pdf: false, video: false };
    try {
      dmOn = {
        pdf: localStorage.getItem('givelife-dm-pdf') === '1',
        video: localStorage.getItem('givelife-dm-video') === '1',
      };
    } catch (e) {}
    const isDm = () => $('messageFocus')?.dataset.kind === 'dm';
    const paint = () => {
      const dm = isDm();
      box.dataset.dm = dm ? '1' : '0';
      box.title = dm
        ? 'Also sent after each donor DM (poster and caption first). They use the PDF and video added on the group message.'
        : 'Also sent after the poster and caption in every group post, Auto too';
      box.setAttribute('aria-label', box.title);
      for (const k of ['pdf', 'video', 'poster']) {
        const it = items[k];
        // a group message can tick only what is attached; a DM tick is checked when ticked (a missing file is refused)
        it.cb.disabled = uploading || (!dm && !have[k]);
        it.item.dataset.off = have[k] ? '0' : '1';
        // the DM poster tick is kept on the server (pdf / video DM ticks are kept by the Donors page)
        const dmTick = k === 'poster' ? !!(setupAll.dm && setupAll.dm.poster) : dmOn[k];
        it.cb.checked = !!(have[k] && (dm ? dmTick : groupOn[k]));
        if (!it.item.dataset.up) it.add.textContent = have[k] ? 'Change' : 'Add';
        it.item.title = have[k] ? names[k] : '';
        it.meta.textContent = have[k]
          ? (names[k] || '') + (sizes[k] ? ' · ' + (sizes[k] >= 1024 ? (sizes[k] / 1024).toFixed(1) + ' MB' : sizes[k] + ' KB') : '')
          : 'Not attached';
        const stamp = have[k] ? names[k] || k : '';
        if (it.th.dataset.k !== stamp) {
          it.th.dataset.k = stamp;
          it.th.replaceChildren(have[k] ? picture(k, '') : mk('span', 'ui2-att-th ui2-att-none', '+'));
          if (have[k])
            preview(k, names[k]).then((url) => {
              if (url && it.th.dataset.k === stamp) it.th.replaceChildren(picture(k, url));
            });
        }
        it.file.hidden = dm; // DMs only tick: the files are attached on the group message
      }
      const shown = ['pdf', 'video', 'poster'].filter((k) => have[k] && items[k].cb.checked);
      const fb = document.querySelector('#ui2Swipe .ui2-files-btn');
      if (fb) {
        // the words go away on a narrow phone (the 📎 stays) so Save base fits the same thin row
        const words = shown.length ? ' ' + shown.length + (shown.length === 1 ? ' file' : ' files') : ' Add files';
        if (fb.dataset.words !== words) {
          fb.dataset.words = words;
          fb.replaceChildren('📎', Object.assign(document.createElement('span'), { className: 'ui2-files-w', textContent: words }));
        }
      }
      const sig = shown.map((k) => k + ':' + names[k]).join('|');
      if (chips.dataset.sig !== sig) {
        chips.dataset.sig = sig;
        chips.hidden = !shown.length;
        chips.replaceChildren();
        for (const k of shown) {
          const c = mk('div', 'ui2-att-chip');
          const slot = mk('span', 'ui2-att-slot');
          slot.append(picture(k, ''));
          preview(k, names[k]).then((url) => url && slot.replaceChildren(picture(k, url)));
          const x = mk('button', 'ui2-att-x', '✕');
          x.type = 'button';
          x.setAttribute('aria-label', 'Stop sending ' + (k === 'pdf' ? 'the PDF' : 'the ' + k));
          x.onclick = () => change(k, false);
          c.append(slot, mk('span', 'ui2-att-name', names[k] || k), x);
          chips.append(c);
        }
      }
      textRow.hidden = !have.video;
      $('messageFocus')?.classList.toggle('ui2-has-rx-text', have.video);
      const m = mine();
      for (const b of textRow.querySelectorAll('button'))
        b.setAttribute('aria-pressed', String(b.dataset.v === m.text_on));
      textRow.title = dm ? 'For DMs' : 'For group posts';
      const led = m.text_on === 'video' && have.video && (dm || groupOn.video);
      const noPicture = !led && posterKind !== 'image'; // the Poster is a picture only: without one nothing goes out
      orderLine.dataset.warn = noPicture ? '1' : '0';
      orderLine.textContent = noPicture
        ? 'Nothing will be sent: there is no Poster picture. Upload a picture in Poster.'
        : '';
      caseNote.textContent = led ? 'Video + text' : 'Poster + text';
      // the files in the owner's order; a video that carries the text goes with the case, not after it
      const now = [...box.querySelectorAll('.ui2-rx-item')].map((e) => e.dataset.kind).join();
      if (now !== order.join()) for (const k of order) box.insertBefore(items[k].item, msg);
      order.forEach((k, i) => {
        const it = items[k];
        it.rank.textContent = ORD[i];
        it.up.hidden = false;
        it.up.style.visibility = i ? '' : 'hidden';
        it.up.disabled = !i || uploading;
        it.up.setAttribute('aria-label', 'Send the ' + (k === 'pdf' ? 'PDF' : k) + ' earlier');
        it.item.dataset.led = k === 'video' && led && it.cb.checked ? '1' : '0';
      });
    };
    const take = (v) => {
      for (const k of ['pdf', 'video', 'poster']) {
        have[k] = !!(v[k] && v[k].has);
        names[k] = have[k] ? String(v[k].name || '') : '';
        sizes[k] = have[k] ? Number(v[k].kb) || 0 : 0;
        groupOn[k] = !!(have[k] && v[k].on);
      }
      setupAll = v.setup || {};
      posterKind = v.poster_kind || 'image';
      if (Array.isArray(v.order) && v.order.length === 3) order = v.order.slice();
      paint();
    };
    const load = async () => {
      try {
        const r = await fetch('/group-extras');
        if (r.ok) take(await r.json());
      } catch (e) {}
    };
    async function moveUp(kind) {
      msg.textContent = '';
      try {
        const r = await post('/group-extras', { action: 'move_up', kind }),
          d = await r.json().catch(() => ({}));
        if (!r.ok) throw Error(d.error || 'Could not move that.');
        take(d);
        dispatchEvent(new CustomEvent('group-extras-changed'));
      } catch (e) {
        msg.textContent = e.message;
        load();
      }
    }
    async function change(kind, on) {
      msg.textContent = '';
      if (isDm()) {
        if (on && !have[kind]) {
          items[kind].cb.checked = false;
          msg.textContent =
            'No ' +
            (kind === 'pdf' ? 'PDF' : kind === 'poster' ? 'poster' : 'video') +
            ' yet. Attach it on the group message first.';
          return;
        }
        if (kind === 'poster') return void saveSetup('poster', on); // DMs' own poster tick
        // donors.js remembers the tick and applies it to a running Auto-DM
        dispatchEvent(new CustomEvent('dm-extra-request', { detail: { kind, on } }));
        return;
      }
      try {
        const r = await post('/group-extras', { action: 'toggle', kind, on }),
          d = await r.json().catch(() => ({}));
        if (!r.ok) throw Error(d.error || 'Could not save that.');
        take(d);
        dispatchEvent(new CustomEvent('group-extras-changed'));
      } catch (e) {
        msg.textContent = e.message;
        load();
      }
    }
    addEventListener('dm-extras-changed', (e) => {
      dmOn = { pdf: !!e.detail.pdf, video: !!e.detail.video };
      paint();
    });
    addEventListener('group-extras-changed', load);
    addEventListener('reader-kind', paint);
    addEventListener('focus', load);
    load();
  }
  const run = () => {
    main();
    reader();
    readerExtras();
  };
  run();
  ui2Observe(ui2Frame(run));
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
  ui2Observe(ui2Frame(run));
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
  ui2Observe(run, {});
  ui2Wide.addEventListener('change', run);
  arrange();
})();

/* Message home, every width: the whole message shows without scrolling. Mini read: 12.5px on a phone or tablet and
   14px on a computer; a long message on a short screen steps down (never under 11px). Only if it still cannot fit
   (very small old phones) does the text scroll inside its card, and the buttons under it stay put. */
(() => {
  const wide = matchMedia('(min-width: 900px)');
  let busy = false;
  const fit = () => {
    const app = document.querySelector('.app.ui2-message-home'),
      card = document.getElementById('card'),
      chat = document.getElementById('chat'),
      msg = document.getElementById('groupPreview');
    if (busy || !app || !card || !chat || !msg) return;
    if (msg.isContentEditable) return; // never re-size text that is being edited
    busy = true;
    try {
      const send = document.querySelector('.ui2-message-home .group-send');
      const room = wide.matches
        ? () => {
            const td = document.getElementById('ui2Today'),
              sf = document.getElementById('ui2SendFiles'),
              under = td && !td.classList.contains('is-side') && td.getClientRects().length ? td.getBoundingClientRect().bottom : 0,
              files = sf?.getClientRects().length ? sf.getBoundingClientRect().bottom : 0;
            return window.innerHeight - Math.max(card.getBoundingClientRect().bottom, send?.getBoundingClientRect().bottom || 0, under, files) - 16;
          }
        : () => chat.clientHeight - chat.scrollHeight + 2; // 2px for rounding
      app.classList.remove('ui2-msg-scroll');
      let size = wide.matches ? 14 : 12.5; // mini read: one look, the eyes do not travel down
      app.style.setProperty('--home-msg-size', size + 'px');
      while (room() < 0 && size > 11) {
        size -= 0.5;
        app.style.setProperty('--home-msg-size', size + 'px');
      }
      app.classList.toggle('ui2-msg-scroll', room() < 0);
    } finally {
      busy = false;
    }
  };
  let queued = 0;
  const later = () => {
    cancelAnimationFrame(queued);
    queued = requestAnimationFrame(fit);
  };
  addEventListener('resize', later);
  wide.addEventListener('change', later);
  const watch = () => {
    const msg = document.getElementById('groupPreview'),
      chat = document.getElementById('chat');
    if (!msg || !chat) return setTimeout(watch, 500);
    new MutationObserver(later).observe(msg, { childList: true, subtree: true, characterData: true });
    if (typeof ResizeObserver === 'function') new ResizeObserver(later).observe(chat); // the box changed size: fit again
    later();
    /* the page is still settling while it opens (fonts, the send buttons moving in): measure again when it is calm */
    document.fonts?.ready?.then(later);
    for (const ms of [600, 1500, 3000]) setTimeout(later, ms);
  };
  watch();
})();

/* Desktop Message home: ‹ › under the message, centred, icons only: previous / next saved version in the message box
   (base → 1 → 2 … → base). Send then sends the version on screen first (same as the reader). Edit always edits the
   base message. */
(() => {
  const $ = (id) => document.getElementById(id);
  let list = [],
    index = 0,
    nav = null,
    sent = { source: false, items: [] },
    row = null;
  const take = (d) => {
    list = [d.source, ...(d.items || [])].filter((t) => typeof t === 'string' && t.trim());
    sent = d.sent && typeof d.sent === 'object' ? d.sent : { source: false, items: [] };
  };
  /* the language of a version, for the small tag under its number (Roman Urdu words = Urdu + English) */
  const lang = (t) => {
    const hits = (String(t).toLowerCase().match(/\b(hai|hain|ki|ka|ke|ko|aur|se|nahi|bachi|bacha|madad|zindagi|sirf|apni|apna|abhi|kar|karein|dua)\b/g) || []).length;
    return hits >= 4 ? 'Urdu+Eng' : 'English';
  };
  /* Computer: the versions as one row above the message (Base · 1 · 2 …), one click to any; a green dot = already
     sent to the GiveLife group, so the same words do not go twice */
  const drawRow = () => {
    if (!row) return;
    row.hidden = list.length < 2;
    const chips = list.map((t, i) => {
      const was = i ? sent.items?.[i - 1] : sent.source;
      return (
        '<button type="button" class="ui2-vr-chip' + (i === index ? ' is-on' : '') + (was ? ' is-sent' : '') +
        '" data-i="' + i + '" aria-pressed="' + (i === index) + '" title="' +
        (i ? 'Version ' + i : 'Base message') + (was ? ' · already sent to GiveLife' : '') + '"><b>' +
        (i ? i : 'Base') + '</b><small>' + lang(t) + '</small></button>'
      );
    });
    row.innerHTML = '<div class="ui2-vr-seg" role="group" aria-label="Versions">' + chips.join('') + '</div><span class="ui2-vr-keys">← → keys</span>';
  };
  const svg = (d) =>
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + d + '"/></svg>';
  const showing = () => index > 0 && list[index];
  const label = () => {
    if (!nav) return;
    const n = Math.max(0, list.length - 1),
      where = index > 0 ? 'Version ' + index + ' of ' + n : n ? 'Base message (' + n + ' versions)' : 'Base message';
    nav.dataset.i = String(index);
    nav.title = where;
    const count = nav.querySelector('.ui2-ver-count');
    if (count) count.textContent = list.length > 1 ? index + 1 + '/' + list.length : '';
    for (const [b, word] of [
      [nav.firstChild, 'Previous version'],
      [nav.lastChild, 'Next version'],
    ]) {
      b.setAttribute('aria-label', word + ' · now: ' + where);
      b.title = word;
    }
    window.focusShownVersion = showing() || '';
    drawRow();
  };
  const draw = (text) => {
    $('groupPreview').innerHTML = window
      .waFormat(text)
      .split('\n')
      .map((l) => '<div class="wa-line' + (l ? (/^[ \t]*[—–─_-]{3,}[ \t]*$/.test(l) ? ' rule' : '') : ' blank') + '">' + (l || '<br>') + '</div>')
      .join('');
  };
  const reset = () => {
    index = 0;
    label();
  };
  let stepping = false;
  async function step(dir, b) {
    const msg = $('groupPreview');
    if (stepping || !msg || msg.isContentEditable) return; // never replace text that is being edited
    stepping = true;
    try {
      await go(dir, b);
    } finally {
      stepping = false;
    }
  }
  async function go(dir, b) {
    if (index === 0) {
      try {
        take(await (await fetch('/focus-bank?kind=group')).json());
      } catch (e) {
        list = [];
      }
    }
    if (list.length < 2) {
      b.title = 'No versions yet';
      b.dataset.empty = '1';
      setTimeout(() => (delete b.dataset.empty, label()), 1600);
      return;
    }
    index = (index + dir + list.length) % list.length;
    if (index === 0) window.paint?.('group');
    else draw(list[index]);
    label();
    dispatchEvent(new Event('resize')); // the message box fits the new text
  }
  function add() {
    const tools = document.querySelector('#card .tools');
    if (!tools || $('homeNext') || typeof window.paint !== 'function') return !!$('homeNext');
    nav = document.createElement('div');
    nav.id = 'ui2VerNav';
    nav.className = 'ui2-ver-nav';
    nav.setAttribute('role', 'group');
    nav.setAttribute('aria-label', 'Versions');
    for (const [id, d, dir] of [
      ['homePrev', 'm15 6-6 6 6 6', -1],
      ['homeNext', 'm9 6 6 6-6 6', 1],
    ]) {
      const b = document.createElement('button');
      b.type = 'button';
      b.id = id;
      b.className = 'ui2-ver-btn';
      b.innerHTML = svg(d);
      b.addEventListener('click', () => step(dir, b));
      nav.append(b);
      if (dir < 0) nav.append(Object.assign(document.createElement('span'), { className: 'ui2-ver-count' }));
    }
    /* ‹ 2/6 › lives inside the message (main screen, every width), next to Rewrite */
    const home = $('ui2GnavMain');
    (home || tools).append(nav);
    row = document.createElement('div');
    row.id = 'ui2VerRow';
    row.className = 'ui2-ver-row';
    row.hidden = true;
    row.addEventListener('click', (e) => {
      const c = e.target.closest('.ui2-vr-chip');
      if (!c || stepping || $('groupPreview')?.isContentEditable) return;
      const i = Number(c.dataset.i);
      if (i === index) return;
      index = i;
      if (i === 0) window.paint?.('group');
      else draw(list[i]);
      label();
      dispatchEvent(new Event('resize'));
    });
    $('card')?.before(row);
    /* computer: ← → change the version (not while typing, not on another page) */
    addEventListener('keydown', (e) => {
      if ((e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') || e.altKey || e.ctrlKey || e.metaKey) return;
      if (!matchMedia('(min-width: 900px)').matches || !row || row.hidden || !row.offsetParent) return;
      if (e.target.closest?.('input, textarea, select, [contenteditable="true"], [role="menu"], [role="listbox"], [role="radiogroup"], [role="slider"], [role="tablist"]')) return;
      if ($('messageFocus')?.getClientRects().length) return; // the message page is open: it has its own keys
      e.preventDefault();
      step(e.key === 'ArrowLeft' ? -1 : 1, e.key === 'ArrowLeft' ? $('homePrev') : $('homeNext'));
    });
    label();
    /* the count (2/6) is known before the first press; it is read again when the owner comes back from another page */
    const count = async () => {
      if (index > 0) return;
      try {
        const d = await (await fetch('/focus-bank?kind=group')).json();
        if (index > 0) return;
        take(d);
      } catch (e) {}
      label();
    };
    count();
    addEventListener('hashchange', () => (label(), count())); // back from another page: Send still matches the version on screen
    // a send to the GiveLife group finished ("Sent just now"): the green dots follow at once
    const lastMain = document.querySelector('.group-send [data-last-group="main"]');
    let lastSeen = lastMain?.textContent;
    if (lastMain)
      new MutationObserver(() => {
        if (lastMain.textContent === lastSeen) return; // the same words repainted: nothing new was sent
        lastSeen = lastMain.textContent;
        if (/just now/.test(lastSeen)) count(); // only a fresh send, not the minutes ticking
      }).observe(lastMain, { childList: true, characterData: true, subtree: true });
    /* the DM screen shows the DM message: the Group version view ends (Copy and Send then use the DM text) */
    new MutationObserver(() => {
      if (document.body.dataset.view === 'dm' && index > 0) window.paint('group');
    }).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });
    /* the app redraws the base message (a save, a new draft): the version view ends there */
    const paint = window.paint;
    window.paint = (k) => {
      paint(k);
      if (k === 'group' && index > 0) reset();
    };
    $('edit')?.addEventListener(
      'click',
      () => {
        if (index > 0) window.paint('group');
      },
      true,
    );
    $('copy')?.addEventListener(
      'click',
      (e) => {
        const text = showing();
        if (!text) return; // the base message: the app's own Copy
        e.stopImmediatePropagation();
        e.preventDefault();
        navigator.clipboard.writeText(text).then(
          () => window.dispatchEvent(new CustomEvent('ui2-copied')),
          () => {},
        );
      },
      true,
    );
    return true;
  }
  if (!add()) {
    const t = setInterval(() => add() && clearInterval(t), 400);
    setTimeout(() => clearInterval(t), 20000);
  }
})();

/* Desktop side menu: a Hide button folds it to a slim strip of icons (remembered); Show opens it again. */
(() => {
  const KEY = 'givelife-rail-min';
  function add() {
    const tabs = document.getElementById('ui2Tabs'),
      app = document.querySelector('.app');
    if (!tabs || !app) return false;
    if (document.getElementById('ui2RailHide')) return true;
    const b = document.createElement('button');
    b.type = 'button';
    b.id = 'ui2RailHide';
    b.className = 'ui2-rail-hide';
    const paint = () => {
      const min = app.classList.contains('ui2-rail-min');
      b.innerHTML = '<span aria-hidden="true">' + (min ? '»' : '«') + '</span><b>' + (min ? 'Show' : 'Hide') + '</b>';
      b.setAttribute('aria-label', min ? 'Show the menu' : 'Hide the menu');
      b.title = min ? 'Show the menu' : 'Hide the menu';
      b.setAttribute('aria-expanded', String(!min));
    };
    let min = false;
    try {
      min = localStorage.getItem(KEY) === '1';
    } catch (e) {}
    app.classList.toggle('ui2-rail-min', min);
    b.addEventListener('click', () => {
      const on = !app.classList.contains('ui2-rail-min');
      app.classList.toggle('ui2-rail-min', on);
      try {
        localStorage.setItem(KEY, on ? '1' : '0');
      } catch (e) {}
      paint();
      dispatchEvent(new Event('resize')); // the message box re-fits the new width
    });
    paint();
    tabs.prepend(b);
    /* a folded menu still names each place when the mouse rests on it */
    for (const t of tabs.querySelectorAll('.ui2-tab')) if (!t.title) t.title = t.textContent.trim();
    return true;
  }
  if (!add()) {
    const t = setInterval(() => add() && clearInterval(t), 400);
    setTimeout(() => clearInterval(t), 20000);
  }
})();

/* Desktop Message home: Copy and Edit are small icons inside the message box (bottom right), like ChatGPT / Claude.
   The real buttons are moved, never rebuilt; on a phone they go back to the row under the message. */
(() => {
  const $ = (id) => document.getElementById(id);
  const wide = matchMedia('(min-width: 900px)');
  let box = null;
  const mark = (b) => {
    const t = b.textContent.trim();
    b.dataset.state = /^(Done|Copied)/i.test(t) ? 'done' : '';
    b.setAttribute('aria-label', b.id === 'edit' ? (t === 'Done' ? 'Done editing' : 'Edit message') : t === 'Copied' ? 'Copied' : 'Copy message');
  };
  function place() {
    const chat = $('chat'),
      tools = document.querySelector('#card .tools'),
      edit = $('edit'),
      copy = $('copy'),
      more = document.querySelector('#card .overflow-tools');
    if (!chat || !tools || !edit || !copy) return false;
    if (!box) {
      box = document.createElement('div');
      box.id = 'ui2MsgActions';
      box.className = 'ui2-msg-actions';
      for (const b of [copy, edit]) {
        mark(b);
        new MutationObserver(() => mark(b)).observe(b, { childList: true, characterData: true, subtree: true });
      }
    }
    if (wide.matches) {
      if (box.parentElement !== chat) chat.append(box);
      if (copy.parentElement !== box) box.append(copy, edit);
      if (more && more.parentElement !== box) box.append(more);
    } else if (edit.parentElement === box) {
      tools.prepend(edit, copy);
      const verNav = tools.querySelector('#ui2VerNav');
      if (more) verNav ? verNav.before(more) : tools.append(more);
      box.remove();
    }
    return true;
  }
  let tick = 0;
  const copied = () => {
    const c = $('copy');
    if (!c) return;
    c.dataset.state = 'done';
    c.setAttribute('aria-label', 'Copied');
    clearTimeout(tick);
    tick = setTimeout(() => mark(c), 1400);
  };
  addEventListener('ui2-copied', copied);
  document.addEventListener('click', (e) => {
    if (e.target.closest?.('#copy') && e.target.closest('#ui2MsgActions'))
      setTimeout(copied, 120); // a short ✓ (never reads the clipboard: that would ask the owner for permission)
  });
  wide.addEventListener('change', place);
  if (!place()) {
    const t = setInterval(() => place() && clearInterval(t), 400);
    setTimeout(() => clearInterval(t), 20000);
  }
})();

/* Phone: a short message sits in the exact middle of its card (see responsive.css). .ui2-short means there is room to
   spare above and below it, so the strip kept for the refresh and next buttons is not needed. */
(() => {
  const FOOT = 50; // px kept at the bottom of the card for the buttons (same value as responsive.css)
  let queued = 0;
  function fit() {
    queued = 0;
    const chat = document.getElementById('chat');
    const msg = document.getElementById('groupPreview');
    if (!chat || !msg) return;
    const short = matchMedia('(max-width: 899px)').matches && msg.offsetHeight + 2 * FOOT <= chat.clientHeight;
    if (chat.classList.contains('ui2-short') !== short) chat.classList.toggle('ui2-short', short);
  }
  const soon = () => queued || (queued = requestAnimationFrame(fit));
  function start() {
    const chat = document.getElementById('chat');
    const msg = document.getElementById('groupPreview');
    if (!chat || !msg) return setTimeout(start, 300);
    if (typeof ResizeObserver === 'function') {
      const ro = new ResizeObserver(soon);
      ro.observe(chat);
      ro.observe(msg);
    }
    new MutationObserver(soon).observe(msg, { childList: true, subtree: true, characterData: true });
    addEventListener('resize', soon);
    soon();
  }
  start();
})();

/* Computer, main Message screen (owner picks 6 and 9 + reactions):
   - "Sends in this order": the case message (poster or video + text), then the files 1st / 2nd / 3rd, on or off.
   - Today: when the Test group, the GiveLife group and the other groups last got it, and what is scheduled.
   - Send to GiveLife waits 5 s with Undo before it starts (every width). */
(() => {
  const $ = (id) => document.getElementById(id);
  const ORD = ['1st', '2nd', '3rd'],
    NAME = { poster: 'Poster', video: 'Video', pdf: 'PDF' },
    ICON = { poster: '🖼', video: '▶', pdf: '📄' };
  let files = null,
    today = null;
  async function loadFiles() {
    if (!files) return;
    try {
      const r = await fetch('/group-extras');
      if (!r.ok) return;
      const v = await r.json();
      const order = Array.isArray(v.order) && v.order.length === 3 ? v.order : ['poster', 'video', 'pdf'];
      const led = v.text_on === 'video' && v.video?.has && v.video?.on;
      const tiles = ['<span class="ui2-sf-lbl">Sends in this order</span>'];
      tiles.push('<span class="ui2-sf-tile is-case"><span class="ui2-sf-ic">' + (led ? '▶' : '🖼') + '</span><span><b>Case</b><small>' + (led ? 'Video + text' : 'Poster + text') + '</small></span></span>');
      order.forEach((k, i) => {
        if (k === 'video' && led) return; // the video carries the text: it is the case message above
        const f = v[k] || {},
          state = !f.has ? 'none yet' : f.on ? 'on' : 'off';
        tiles.push('<span class="ui2-sf-tile' + (f.has && f.on ? '' : ' is-off') + '" title="' + NAME[k] + ': ' + state + '"><span class="ui2-sf-ic">' + ICON[k] + '</span><span><b>' + ORD[i] + ' ' + NAME[k] + '</b><small>' + state + '</small></span></span>');
      });
      tiles.push('<button type="button" class="ui2-sf-change">Change</button>');
      files.innerHTML = tiles.join('');
    } catch (e) {}
  }
  function paintToday() {
    if (!today) return;
    const t = typeof groupTimers === 'object' && groupTimers ? groupTimers : {},
      now = Date.now() / 1000,
      clock = (s) => (typeof clockText === 'function' ? clockText(s) : new Date(s * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })),
      due = [['main', 'GiveLife'], ['free', 'Other groups']].filter(([k]) => t[k] && t[k].due_at > now).map(([k, w]) => w + ' at ' + clock(t[k].due_at));
    const sch = today.querySelector('.ui2-td-sch');
    sch.textContent = due.length ? due.join(' · ') : 'Nothing scheduled';
    sch.classList.toggle('is-set', !!due.length);
    if (typeof paintGroupTimes === 'function') paintGroupTimes(); // fills the "Sent 5 min ago" lines
  }
  /* beside the message on a wide screen; under the send line on a smaller computer */
  function place() {
    const card = $('card');
    if (!today || !card) return;
    const wide = matchMedia('(min-width: 1280px)').matches && !!card.getClientRects().length;
    today.classList.toggle('is-side', wide);
    if (!wide) {
      today.style.top = today.style.left = '';
      today.hidden = false;
      return;
    }
    // the column moved left to make room: measure once it has
    requestAnimationFrame(() => {
      const par = today.offsetParent || card.parentElement,
        pr = par.getBoundingClientRect(),
        cr = card.getBoundingClientRect();
      today.style.top = Math.round(cr.top - pr.top - par.clientTop + par.scrollTop) + 'px';
      today.style.left = Math.round(cr.right + 24 - pr.left - par.clientLeft) + 'px';
      today.hidden = cr.right + 24 + 260 > window.innerWidth - 12; // never over the edge
    });
  }
  function add() {
    const card = $('card'),
      rail = document.querySelector('.ui2-message-home .action-rail') || document.querySelector('.ui2-message-home .group-send')?.parentElement;
    if (!card || !rail || typeof sendGroup !== 'function') return false;
    if ($('ui2SendFiles')) return true;
    files = document.createElement('div');
    files.id = 'ui2SendFiles';
    files.className = 'ui2-send-files';
    files.addEventListener('click', (e) => {
      if (!e.target.closest('.ui2-sf-change')) return;
      if (typeof Nav !== 'undefined') Nav.go('preview');
      setTimeout(() => {
        const more = document.querySelector('#messageFocus .focus-rail-more');
        if (more) more.open = true;
      }, 450);
    });
    rail.after(files); // under the send line: the send line stays right under the message
    today = document.createElement('aside');
    today.id = 'ui2Today';
    today.className = 'ui2-today';
    today.setAttribute('aria-label', 'Today');
    today.innerHTML =
      '<div class="ui2-td-t">Today</div>' +
      '<div class="ui2-td-row"><span>Test group</span><span data-last-group="test">Checking…</span></div>' +
      '<div class="ui2-td-row"><span>GiveLife group</span><span data-last-group="main">Checking…</span></div>' +
      '<div class="ui2-td-row"><span>Other groups</span><span data-last-group="free">Checking…</span></div>' +
      '<div class="ui2-td-row"><span>Scheduled</span><span class="ui2-td-sch">Nothing scheduled</span></div>';
    files.after(today);
    loadFiles();
    paintToday();
    place();
    addEventListener('group-extras-changed', loadFiles);
    addEventListener('focus', loadFiles);
    addEventListener('resize', place);
    if (typeof ResizeObserver === 'function') {
      const ro = new ResizeObserver(place);
      for (const el of [card, files, $('ui2VerRow')]) if (el) ro.observe(el); // the row above appearing moves the card
    }
    for (const ms of [600, 1500, 3000]) setTimeout(place, ms);
    // the timer buttons change when a send is scheduled or done: the Today line follows
    const timers = document.querySelectorAll('.gb-timer');
    timers.forEach((b) => new MutationObserver(paintToday).observe(b, { attributes: true, childList: true, characterData: true, subtree: true }));
    setInterval(paintToday, 30000);
    return true;
  }
  if (!add()) {
    const t = setInterval(() => add() && clearInterval(t), 400);
    setTimeout(() => clearInterval(t), 20000);
  }

  /* Send to GiveLife: 5 s to undo (Gmail style) instead of an "are you sure" box. Tap again = Undo. A send that is
     already running keeps its own tap-to-stop. */
  const btn = $('btnGivelife');
  if (!btn) return;
  let timer = 0,
    tick = 0,
    left = 0,
    go = false;
  const cover = document.createElement('span');
  cover.className = 'ui2-undo';
  cover.hidden = true;
  btn.append(cover);
  const stop = () => {
    clearTimeout(timer);
    clearInterval(tick);
    timer = 0;
    cover.hidden = true;
    btn.classList.remove('is-undo');
  };
  btn.addEventListener(
    'click',
    (e) => {
      if (go) return; // the real send, after the 5 s
      if (typeof stops !== 'undefined' && stops.has && stops.has('main')) return; // a running send: tap = stop
      e.preventDefault();
      e.stopImmediatePropagation();
      if (timer) {
        stop(); // Undo
        cover.hidden = false;
        cover.textContent = 'Not sent';
        setTimeout(() => !timer && (cover.hidden = true), 1200);
        return;
      }
      left = 5;
      btn.classList.add('is-undo');
      cover.hidden = false;
      cover.innerHTML = '<i class="ui2-undo-bar"></i><span>Sending in ' + left + '…</span><b>Undo</b>';
      tick = setInterval(() => {
        left -= 1;
        const s = cover.querySelector('span');
        if (s && left > 0) s.textContent = 'Sending in ' + left + '…';
      }, 1000);
      timer = setTimeout(() => {
        stop();
        go = true;
        try {
          btn.click();
        } finally {
          go = false;
        }
      }, 5000);
    },
    true,
  );
})();
