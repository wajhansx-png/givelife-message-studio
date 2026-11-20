/* Comfort helpers for screens built after page load. Reuses the live controls and their handlers. */
(() => {
  const phone = matchMedia('(max-width:899px)');

  /* Accessibility: dialog headers/footers are not page landmarks; long previews must be keyboard-reachable. */
  let queued = 0;
  // Native scrollIntoView must account for sticky modal headers and action bars.
  const insetBars = new WeakSet();
  const insetObserver = new ResizeObserver((entries) => {
    for (const { target } of entries) {
      const css = getComputedStyle(target);
      if (!['sticky', 'fixed'].includes(css.position)) continue;
      const dialog = target.closest('dialog');
      let scroller = target.parentElement;
      while (
        scroller &&
        scroller !== dialog &&
        !['auto', 'scroll'].includes(getComputedStyle(scroller).overflowY)
      )
        scroller = scroller.parentElement;
      if (!scroller) continue;
      const edge = css.bottom !== 'auto' ? 'bottom' : 'top';
      scroller.style.setProperty('scroll-padding-' + edge, target.offsetHeight + 8 + 'px');
    }
  });
  function normalise() {
    queued = 0;
    document
      .querySelectorAll(
        'dialog header:not([role]),dialog footer:not([role]),#messageFocus header:not([role]),#messageFocus footer:not([role])',
      )
      .forEach((e) => e.setAttribute('role', 'group'));
    document
      .querySelectorAll(
        'dialog .batch-foot,dialog .donor-form-actions,dialog .dialog-actions,dialog>header,dialog>.head',
      )
      .forEach((bar) => {
        if (!insetBars.has(bar)) {
          insetBars.add(bar);
          insetObserver.observe(bar);
        }
      });
    document.querySelectorAll('.bank-preview:not([tabindex])').forEach((e) => {
      e.tabIndex = 0;
      if (!e.hasAttribute('aria-label')) e.setAttribute('aria-label', 'Message preview');
    });
  }
  new MutationObserver((records) => {
    if (
      !queued &&
      records.some(({ addedNodes }) =>
        [...addedNodes].some(
          (node) => node.nodeType === Node.ELEMENT_NODE && !node.closest('#donorRows'),
        ),
      )
    )
      queued = setTimeout(normalise, 120);
  }).observe(document.body, { childList: true, subtree: true });
  normalise();

  /* Donors: Messages lives in the top nav. On phones Test DM and the poster switch move into More,
    so the bottom bar is a single row: Back · Stop · DM ★ · DM all. */
  function placeDonorControls() {
    const head = document.querySelector('.donor-head'),
      more = document.getElementById('donorNavMore'),
      bottom = document.querySelector('.donor-bottom');
    const tabs = document.querySelector('.donor-message-tablist'),
      test = document.getElementById('donorTest'),
      poster = document.querySelector('.donor-poster-toggle'),
      toggle = document.getElementById('donorToggle');
    if (!head || !more || !bottom || !tabs) return;
    if (tabs.parentElement !== head)
      head.insertBefore(tabs, document.getElementById('donorAdd') || more);
    const panel = more.querySelector('.compact-nav-panel');
    if (phone.matches && panel) {
      /* More keeps only Bulk message. Test DM lives in the Send DMs setup (More options) and the
         poster choice is the Attach poster switch there; the bottom-bar switch stays hidden. */
      const setup = document.querySelector('#donorBatchPicker #batchChips');
      if (test) (setup || panel).append(test);
      if (poster) bottom.append(poster);
    } else if (toggle) {
      if (test) bottom.insertBefore(test, toggle);
      if (poster) toggle.after(poster);
    }
  }
  placeDonorControls();
  phone.addEventListener('change', placeDonorControls);

  /* Donor Messages reader: progress from "Message n of N", → for Next on desktop, swipe left for Next on phones. */
  const box = document.getElementById('donorMessages');
  const nextBtn = () => box?.querySelector('[data-bank-nav=next]:not(:disabled)');
  function decorateReader() {
    if (!box) return;
    const head = box.querySelector('.bank-heading'),
      title = box.querySelector('.bank-current');
    if (!head || !title) return;
    const m = /(\d+)\s+of\s+(\d+)/.exec(title.textContent || '');
    let bar = box.querySelector(':scope > .bank-progress');
    if (!bar) {
      bar = document.createElement('div');
      bar.className = 'bank-progress';
      bar.setAttribute('aria-hidden', 'true');
      bar.append(document.createElement('i'));
      head.after(bar);
    }
    bar.firstChild.style.width = m ? Math.round((+m[1] / +m[2]) * 100) + '%' : '0%';
    const n = nextBtn();
    if (n && !n.title) n.title = 'Next message (→)';
    fitBankPreview();
  }
  /* Keep long captions readable; the reading surface handles scrolling. */
  function fitBankPreview() {
    const p = box?.querySelector('.bank-detail .bank-preview');
    if (!p || p.closest('[hidden]') || !p.clientHeight) return;
    p.style.setProperty('line-height', '1.4', 'important');
    /* the whole message shows without scrolling: the largest size from 14px down to 11px that fits its box
       (a message too long even at 11px keeps 11px and scrolls, as before) */
    const card = p.closest('.bank-detail'),
      fits = (size) => {
        p.style.setProperty('font-size', size + 'px', 'important');
        return !card || card.scrollHeight <= card.clientHeight + 1;
      };
    p.classList.remove('bank-tight');
    card?.classList.remove('bank-tight-card');
    p.style.setProperty('line-height', '1.4', 'important');
    let size = 14;
    while (!fits(size) && size > 11) size -= 0.5;
    if (!fits(size)) {
      /* still too tall at 11px (a very long message on a short phone): tighter lines and smaller gaps, last */
      p.classList.add('bank-tight');
      card?.classList.add('bank-tight-card');
      p.style.setProperty('line-height', '1.25', 'important');
      fits(size);
    }
  }
  addEventListener('resize', () => requestAnimationFrame(fitBankPreview));
  if (box) {
    new MutationObserver(() => requestAnimationFrame(decorateReader)).observe(box, {
      childList: true,
    });
    decorateReader();
  }
  const readerOpen = () =>
    document.getElementById('donorsPage')?.dataset.panel === 'messages' &&
    document.getElementById('donorsPage')?.open;
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' || e.altKey || e.ctrlKey || e.metaKey || !readerOpen()) return;
    if (e.target.closest?.('input,textarea,select,[contenteditable=true]')) return;
    const n = nextBtn();
    if (n) {
      e.preventDefault();
      n.click();
    }
  });
  let touch = null;
  box?.addEventListener(
    'touchstart',
    (e) => {
      if (e.target.closest('.bank-preview') && e.touches.length === 1)
        touch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      else touch = null;
    },
    { passive: true },
  );
  box?.addEventListener(
    'touchend',
    (e) => {
      if (!touch) return;
      const t = e.changedTouches[0],
        dx = t.clientX - touch.x,
        dy = t.clientY - touch.y;
      touch = null;
      if (dx < -70 && Math.abs(dy) < 45 && !getSelection()?.toString()) {
        const n = nextBtn();
        if (n) n.click();
      }
    },
    { passive: true },
  );
})();

/* Full screen: one button, only on a user tap (browsers refuse otherwise). The whole page goes full screen, so it stays on while
   the app moves between screens. Where a browser cannot (e.g. iPhone Safari) the button is hidden; nothing is faked. */
(() => {
  const root = document.documentElement,
    can = !!(root.requestFullscreen || root.webkitRequestFullscreen),
    isOn = () => !!(document.fullscreenElement || document.webkitFullscreenElement),
    btn = document.createElement('button'),
    note = document.createElement('div');
  let timer = 0;
  btn.type = 'button';
  btn.id = 'fsToggle';
  btn.className = 'fs-toggle';
  btn.hidden = !can;
  note.className = 'fs-note';
  note.setAttribute('role', 'status');
  const say = (t) => {
    note.textContent = t;
    note.classList.add('on');
    clearTimeout(timer);
    timer = setTimeout(() => note.classList.remove('on'), 3500);
  };
  const paint = () => {
    const on = isOn();
    btn.dataset.on = on;
    btn.setAttribute('aria-label', on ? 'Exit full screen' : 'Enter full screen');
    btn.title = on ? 'Exit full screen' : 'Full screen';
    btn.innerHTML = on
      ? '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      : '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  };
  async function toggle() {
    try {
      if (isOn()) await (document.exitFullscreen || document.webkitExitFullscreen).call(document);
      else if (root.requestFullscreen) await root.requestFullscreen({ navigationUI: 'hide' });
      else root.webkitRequestFullscreen();
    } catch (e) {
      say('This browser did not allow full screen.');
    }
    paint();
  }
  btn.onclick = toggle;
  for (const ev of ['fullscreenchange', 'webkitfullscreenchange'])
    document.addEventListener(ev, paint);
  document.addEventListener('fullscreenerror', () =>
    say('This browser did not allow full screen.'),
  );
  window.NativeFS = { supported: can, isOn, toggle };
  paint();
  (document.querySelector('.brandbar') || document.body).append(btn);
  document.body.append(note);
  /* Keyboard: keep the field being typed in on screen once the keyboard has resized the view. */
  addEventListener('focusin', (e) => {
    const t = e.target;
    if (
      t?.matches?.(
        'input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable=true]',
      )
    )
      setTimeout(() => {
        if (document.activeElement === t)
          t.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }, 320);
  });
})();
