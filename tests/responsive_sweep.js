/* Responsive sweep. Paste into the console of the running studio (logged in) or inject it.
   sweep(routes, widths) opens each route in same-origin iframes of every width, in parallel, and lists
   layout faults: sideways scroll, controls past the screen edge, clipped text, controls overlapping each
   other, controls too small to tap or oversized for their label. It only reads; it clicks nothing. */
window.sweep = async function sweep(
  routes = [''],
  widths = [280, 320, 360, 390, 430, 540, 768, 1024, 1440],
  wait = 3500,
  cssHref = window.__cssHref || '',
) {
  const out = [];
  const holder = document.createElement('div');
  holder.style.cssText = 'position:fixed;left:-20000px;top:0;width:1px;height:1px;overflow:hidden';
  document.body.append(holder);
  const audit = (w, route, width, rootSel) => {
    const d = w.document,
      vw = w.innerWidth,
      faults = [];
    const note = (kind, el, extra = '') =>
      faults.push(
        `${route || 'main'}@${width} ${kind} ${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${
          el.className && typeof el.className === 'string'
            ? '.' + el.className.trim().split(/\s+/)[0]
            : ''
        } ${extra}`.trim(),
      );
    if (d.documentElement.scrollWidth > vw + 1)
      faults.push(
        `${route || 'main'}@${width} SIDEWAYS-SCROLL page ${d.documentElement.scrollWidth}>${vw}`,
      );
    const visible = (el) =>
      el.checkVisibility({ checkVisibilityCSS: true }) && el.getBoundingClientRect().width > 0;
    const scrollsX = (el) => {
      for (let p = el.parentElement; p && p !== d.body; p = p.parentElement) {
        const o = w.getComputedStyle(p).overflowX;
        if (
          (o === 'auto' || o === 'scroll' || o === 'hidden') &&
          p.getBoundingClientRect().width > 0
        )
          return true;
      }
      return false;
    };
    const CONTROL =
      'button,a[href],input:not([type=hidden]),select,textarea,summary,[role=button],[role=tab]';
    const root = (rootSel && d.querySelector(rootSel)) || d.body;
    const everyControl = [...root.querySelectorAll(CONTROL)].filter(visible);
    const controls = everyControl;
    for (const el of root.querySelectorAll('*')) {
      if (
        !visible(el) ||
        el.closest('svg') ||
        el.closest('[aria-hidden=true]') ||
        el.closest('.sr-only')
      )
        continue;
      const r = el.getBoundingClientRect(),
        s = w.getComputedStyle(el);
      if (s.position === 'fixed' && (r.right > vw + 1 || r.left < -1))
        note('OFF-SCREEN', el, `${Math.round(r.left)}..${Math.round(r.right)}`);
      else if (
        !scrollsX(el) &&
        s.position !== 'fixed' &&
        (r.right > vw + 1 || r.left < -1) &&
        everyControl.includes(el) &&
        !el.closest('[inert]')
      )
        note('OFF-SCREEN', el, `${Math.round(r.left)}..${Math.round(r.right)}`);
      const clip =
        /hidden|clip/.test(s.overflowX) &&
        el.scrollWidth > el.clientWidth + 2 &&
        s.textOverflow !== 'ellipsis';
      if (clip && el.children.length === 0 && (el.textContent || '').trim())
        note('TEXT-CUT', el, `"${el.textContent.trim().slice(0, 24)}"`);
    }
    for (const el of controls) {
      const r = el.getBoundingClientRect();
      const label = (el.getAttribute('aria-label') || el.textContent || '').trim();
      if (el.type === 'checkbox' || el.type === 'radio' || el.closest('label')) continue;
      if (r.height < 28 || r.width < 28) {
        if (!(r.width < 28 && r.height >= 28 && !label))
          note('TOO-SMALL', el, `${Math.round(r.width)}x${Math.round(r.height)}`);
      }
      if (!label && (r.width > 70 || r.height > 70) && el.tagName === 'BUTTON')
        note('OVERSIZED-ICON', el, `${Math.round(r.width)}x${Math.round(r.height)}`);
      if (
        label &&
        label.length < 24 &&
        r.height > 2.6 * parseFloat(w.getComputedStyle(el).fontSize) * 1.4 &&
        r.width < 140 &&
        el.tagName !== 'TEXTAREA'
      )
        note(
          'TALL-WRAP',
          el,
          `"${label.slice(0, 20)}" ${Math.round(r.width)}x${Math.round(r.height)}`,
        );
    }
    // the part of a control that is really on screen: cut by every scrolling or clipping ancestor
    const shown = (el) => {
      let r = el.getBoundingClientRect(),
        box = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
      for (let p = el.parentElement; p && p !== d.documentElement; p = p.parentElement) {
        const s = w.getComputedStyle(p);
        if (/(auto|scroll|hidden|clip)/.test(s.overflowX + s.overflowY)) {
          const c = p.getBoundingClientRect();
          box = {
            left: Math.max(box.left, c.left),
            top: Math.max(box.top, c.top),
            right: Math.min(box.right, c.right),
            bottom: Math.min(box.bottom, c.bottom),
          };
        }
      }
      return box.right - box.left > 2 && box.bottom - box.top > 2 ? box : null;
    };
    const boxes = new Map(controls.map((el) => [el, shown(el)]));
    for (let i = 0; i < controls.length; i++)
      for (let j = i + 1; j < controls.length; j++) {
        const a = controls[i],
          b = controls[j];
        if (a.contains(b) || b.contains(a)) continue;
        const A = boxes.get(a),
          B = boxes.get(b);
        if (!A || !B) continue;
        const ox = Math.min(A.right, B.right) - Math.max(A.left, B.left),
          oy = Math.min(A.bottom, B.bottom) - Math.max(A.top, B.top);
        const small = Math.min(
          (A.right - A.left) * (A.bottom - A.top),
          (B.right - B.left) * (B.bottom - B.top),
        );
        // a small control sitting inside a big one is a split button (main + timer), not a collision
        if (ox > 4 && oy > 4 && ox * oy > 60 && ox * oy < 0.9 * small) {
          const layer = (el) => {
            for (let p = el; p && p !== d.body; p = p.parentElement)
              if (/^(fixed|sticky)$/.test(w.getComputedStyle(p).position)) return p;
            return null;
          };
          const fa = layer(a),
            fb = layer(b);
          if (
            fa !== fb ||
            w.getComputedStyle(a).position === 'absolute' ||
            w.getComputedStyle(b).position === 'absolute'
          )
            continue; // docked bars and overlays are by design
          note(
            'OVERLAP',
            a,
            `with ${b.tagName.toLowerCase()}${b.id ? '#' + b.id : ''} ${Math.round(ox)}x${Math.round(oy)}`,
          );
        }
      }
    return faults;
  };
  for (const entry of routes) {
    const [route, rootSel] = Array.isArray(entry) ? entry : [entry, ''];
    const frames = widths.map((width) => {
      const f = document.createElement('iframe');
      f.style.cssText = `position:absolute;left:0;top:0;width:${width}px;height:820px;border:0`;
      f.src = (window.__sweepBase || location.pathname) + '#/' + route;
      holder.append(f);
      return [f, width];
    });
    for (
      let i = 0;
      i < 40 &&
      !frames.every(
        ([f]) => f.contentDocument?.head && f.contentDocument.readyState === 'complete',
      );
      i++
    )
      await new Promise((r) => setTimeout(r, 250));
    await new Promise((r) => setTimeout(r, wait));
    if (window.__stripCss) {
      // show the page as it was before the fix: remove that stylesheet from every frame
      for (const [f] of frames)
        f.contentDocument
          .querySelectorAll('link[href*="' + window.__stripCss + '"]')
          .forEach((l) => l.remove());
      await new Promise((r) => setTimeout(r, 400));
    }
    if (cssHref) {
      // try a stylesheet that is not deployed yet, in every frame, before auditing
      for (const [f] of frames) {
        const l = f.contentDocument.createElement('link');
        l.rel = 'stylesheet';
        l.href = cssHref + '?' + Date.now();
        f.contentDocument.head.append(l);
      }
      await new Promise((r) => setTimeout(r, 900));
    }
    for (const [f, width] of frames) {
      try {
        out.push(...audit(f.contentWindow, route, width, rootSel));
      } catch (e) {
        out.push(`${route}@${width} AUDIT-ERROR ${e.message}`);
      }
      f.remove();
    }
  }
  holder.remove();
  return out;
};

/* Short summary: one line per distinct fault, with a count. */
window.sweepSummary = (faults) => {
  const m = new Map();
  for (const l of faults) {
    const k = l.replace(/\s+\d+x\d+$/, '').replace(/ -?\d+\.\.-?\d+/, '');
    const e = m.get(k) || { n: 0, line: l };
    e.n++;
    m.set(k, e);
  }
  return [...m.values()].map((e) => e.line + (e.n > 1 ? ' (x' + e.n + ')' : ''));
};
