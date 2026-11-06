/* Comfort helpers for screens built after page load. Reuses the live controls and their handlers. */
(() => {
  const phone = matchMedia('(max-width:899px)'),
    still = matchMedia('(prefers-reduced-motion: reduce)');

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
  new MutationObserver(() => {
    if (!queued) queued = setTimeout(normalise, 120);
  }).observe(document.body, { childList: true, subtree: true });
  normalise();

  /* Smooth screen changes: a short fade-and-rise whenever a screen, tab or message appears. */
  function enter(el) {
    if (!el || still.matches || el.classList.contains('cmf-enter')) return;
    el.classList.add('cmf-enter');
    el.addEventListener('animationend', () => el.classList.remove('cmf-enter'), { once: true });
  }
  const shown = (el) => (el.tagName === 'DIALOG' ? el.open : !el.hidden);
  new MutationObserver((records) => {
    for (const r of records) {
      const el = r.target;
      /* Only whole screens: page dialogs and the message editor. Small dialogs and ordinary hidden toggles never animate the page. */
      const screen =
        (el.tagName === 'DIALOG' &&
          !el.matches('.memory-dialog,.keyboard-dialog,#feedbackDialog')) ||
        el.id === 'messageFocus';
      if (!screen || r.attributeName !== (el.tagName === 'DIALOG' ? 'open' : 'hidden')) continue;
      if (shown(el)) enter(el);
      else if (
        !document.querySelector('dialog[open]:not(.memory-dialog):not(.keyboard-dialog)') &&
        document.getElementById('messageFocus')?.hidden !== false
      )
        enter(document.getElementById('main-workspace'));
    }
  }).observe(document.body, {
    attributes: true,
    attributeFilter: ['open', 'hidden'],
    subtree: true,
  });
  document.addEventListener(
    'click',
    (e) => {
      const t = e.target.closest(
        '.donor-tabs [role=tab],#donorMessagesTab,[data-bank-nav],.bank-back,.bank-back-bottom,[data-view-button]',
      );
      if (!t) return;
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          if (t.matches('[data-bank-nav]'))
            enter(document.querySelector('#donorMessages .bank-detail'));
          else if (t.matches('#donorMessagesTab')) enter(document.getElementById('donorMessages'));
          else if (t.matches('[data-view-button]')) enter(document.getElementById('card'));
          else enter(document.getElementById('donorTable'));
        }),
      );
    },
    true,
  );

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
      const setup = document.querySelector('#donorBatchPicker .batch-options');
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
  }
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
  for (const ev of ['fullscreenchange', 'webkitfullscreenchange']) document.addEventListener(ev, paint);
  document.addEventListener('fullscreenerror', () => say('This browser did not allow full screen.'));
  window.NativeFS = { supported: can, isOn, toggle };
  paint();
  (document.querySelector('.brandbar') || document.body).append(btn);
  document.body.append(note);
  /* Keyboard: keep the field being typed in on screen once the keyboard has resized the view. */
  addEventListener('focusin', (e) => {
    const t = e.target;
    if (t?.matches?.('input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable=true]'))
      setTimeout(() => {
        if (document.activeElement === t) t.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }, 320);
  });
})();
