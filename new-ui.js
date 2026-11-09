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

/* 1. Computer: open straight into the message beside the send list (the reader). Back still goes to the chat. */
(() => {
  if (innerWidth < 900 || location.hash.replace('#', '') !== '') return;
  const go = () => typeof Nav !== 'undefined' && Nav.go('preview');
  if (document.readyState === 'complete') setTimeout(go, 400);
  else addEventListener('load', () => setTimeout(go, 400));
})();

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
