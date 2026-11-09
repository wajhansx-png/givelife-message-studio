/* Redesign helpers, loaded only at /new. They move or relabel existing controls; nothing here sends anything. */

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
