/* Redesign helpers, loaded only at /new. Chips only fill the chat box: they never send anything. */
(() => {
  const CHIPS = [
    ['Amount left…', '', 'Amount left, e.g. 25k'],
    ['Send all', 'send all', ''],
    ['New wording', 'new wording', ''],
  ];
  function add(form) {
    if (!form || form.previousElementSibling?.classList.contains('ui2-chips')) return;
    const box = document.createElement('div');
    box.className = 'ui2-chips';
    for (const [label, text, hint] of CHIPS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.addEventListener('click', () => {
        const ta = form.querySelector('textarea');
        if (!ta) return;
        ta.value = text;
        if (hint) ta.placeholder = hint;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.focus();
      });
      box.append(b);
    }
    form.before(box);
  }
  const run = () => ['cmdForm', 'histForm'].forEach((id) => add(document.getElementById(id)));
  run();
  new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
})();

/* On a computer, open straight into the message beside the send list (the reader). Back still goes to the chat. */
(() => {
  if (innerWidth < 900 || location.hash.replace('#', '') !== '') return;
  const go = () => typeof Nav !== 'undefined' && Nav.go('preview');
  if (document.readyState === 'complete') setTimeout(go, 400);
  else addEventListener('load', () => setTimeout(go, 400));
})();
