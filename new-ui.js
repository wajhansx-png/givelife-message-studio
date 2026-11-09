/* Redesign helpers, loaded only at /new. They move or relabel existing controls; nothing here sends anything. */

/* 1. Phone and computer: open straight into the message with its buttons and the send list (the reader). Back goes to the main screen. */
(() => {
  if (location.hash.replace('#', '') !== '') return;
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

/* 4. Phone: big Regenerate and Next buttons in the thumb zone. They press the real round buttons, so nothing new can go wrong. */
(() => {
  const phone = matchMedia('(max-width: 899px)');
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
  function reader() {
    const rail = document.querySelector('#messageFocus .focus-rail');
    if (!rail || rail.querySelector('#ui2Next')) return;
    rail.prepend(big('ui2Next', 'Next ›', '#focusNextArrow'));
    rail.prepend(big('ui2Regen', '↻ Regenerate', '#focusGenIcon'));
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
  /* Save Base lives in the reader's More menu on a phone so the bottom bar stays short; it goes back on a computer. */
  function moveSave() {
    const save = document.getElementById('focusSave');
    const panel = document.querySelector('#messageFocus details.focus-rail-more > div');
    const rail = document.querySelector('#messageFocus .focus-rail');
    if (!save || !panel || !rail) return;
    if (phone.matches && save.parentElement !== panel) panel.prepend(save);
    else if (!phone.matches && save.parentElement === panel)
      rail.insertBefore(save, document.getElementById('focusTest'));
  }
  const run = () => {
    reader();
    bank();
    moveSave();
  };
  phone.addEventListener('change', run);
  new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
  run();
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
