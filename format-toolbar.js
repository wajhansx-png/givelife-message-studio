/* WhatsApp Bold / Italic for the message editors.
   One pure function (toggle) does all the text work, so the selection toolbar, the editor buttons and the
   base-message dialog behave identically. The toolbar appears right under selected text in the Group and DM
   editors, the DM version editors, the base-message dialog and the volunteer message. */
(function (root) {
  const WORD = /[\p{L}\p{N}]/u;
  const isWord = (ch) => !!ch && WORD.test(ch);
  /* Complete same-mark pairs inside a line are removed before wrapping, so a selection that already
     holds *bold* never becomes the broken *a *b* c*. */
  const stripPairs = (text, mark) => {
    const m = mark.replace(/[*_~]/g, '\\$&');
    return text.replace(new RegExp(m + '(\\S(?:[^' + m + '\\n]*\\S)?)' + m, 'g'), '$1');
  };
  const wrapped = (core, mark) => core.length >= 3 && core[0] === mark && core.at(-1) === mark;

  /* toggle(value, start, end, mark) -> {changed, value, from, to, text, start, end}
     from..to is the exact range of the OLD value that text replaces; start..end is the selection to keep. */
  function toggle(value, start, end, mark) {
    value = String(value);
    if (mark !== '*' && mark !== '_') return { changed: false, value, start, end };
    start = Math.max(0, Math.min(start, value.length));
    end = Math.max(0, Math.min(end, value.length));
    if (start > end) [start, end] = [end, start];
    if (start === end) return { changed: false, value, start, end };
    /* Markers must touch the text, and WhatsApp ignores them inside a word: take the whole word. */
    while (start > 0 && isWord(value[start - 1]) && isWord(value[start])) start--;
    while (end < value.length && isWord(value[end - 1]) && isWord(value[end])) end++;
    const lines = value.slice(start, end).split('\n');
    const parts = lines.map((line) => {
      const lead = line.match(/^\s*/)[0];
      const core = line.slice(lead.length).replace(/\s+$/, '');
      return { lead, core, tail: line.slice(lead.length + core.length) };
    });
    const live = parts.filter((p) => p.core);
    if (!live.length) return { changed: false, value, start, end };
    /* Markers sitting just outside the selection (the inside of *bold* was selected) are removed. */
    if (live.length === 1) {
      const p = live[0],
        at = value.indexOf(p.core, start),
        before = at - 1,
        after = at + p.core.length;
      if (
        parts.length === 1 &&
        value[before] === mark &&
        value[after] === mark &&
        !wrapped(p.core, mark) &&
        !isWord(value[before - 1]) &&
        !isWord(value[after + 1])
      ) {
        return {
          changed: true,
          value: value.slice(0, before) + p.core + value.slice(after + 1),
          from: before,
          to: after + 1,
          text: p.core,
          start: before,
          end: before + p.core.length,
        };
      }
    }
    const off = live.every((p) => wrapped(p.core, mark));
    const next = parts.map((p) =>
      !p.core
        ? p.lead + p.tail
        : p.lead + (off ? p.core.slice(1, -1) : mark + stripPairs(p.core, mark) + mark) + p.tail,
    );
    const text = next.join('\n');
    const first = parts.findIndex((p) => p.core);
    const lastIdx = parts.length - 1 - [...parts].reverse().findIndex((p) => p.core);
    const offset = (i) =>
      next.slice(0, i).reduce((n, l) => n + l.length + 1, 0) + (parts[i].lead || '').length;
    const selStart = start + offset(first);
    const selEnd =
      start +
      offset(lastIdx) +
      (off ? parts[lastIdx].core.length - 2 : stripPairs(parts[lastIdx].core, mark).length + 2);
    return {
      changed: true,
      value: value.slice(0, start) + text + value.slice(end),
      from: start,
      to: end,
      text,
      start: selStart,
      end: selEnd,
    };
  }

  /* The line around a position (used by the editor buttons when nothing is selected). */
  function lineBounds(value, pos) {
    const a = value.lastIndexOf('\n', pos - 1) + 1;
    let z = value.indexOf('\n', pos);
    if (z < 0) z = value.length;
    return [a, z];
  }

  /* Apply to a real textarea. execCommand keeps the browser's undo history and fires the normal input
     event (so saving, dirty-tracking and version editing all see it); setRangeText is the fallback. */
  function apply(ta, mark, opts = {}) {
    let a = ta.selectionStart,
      z = ta.selectionEnd;
    if (a === z && opts.lineIfEmpty) [a, z] = lineBounds(ta.value, a);
    const r = toggle(ta.value, a, z, mark);
    if (!r.changed) return false;
    ta.focus({ preventScroll: true });
    ta.setSelectionRange(r.from, r.to);
    let done = false;
    try {
      done = !!document.execCommand && document.execCommand('insertText', false, r.text);
    } catch (e) {
      done = false;
    }
    if (!done || ta.value !== r.value) {
      ta.value = r.value;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
    ta.setSelectionRange(r.start, r.end);
    return true;
  }

  root.waMark = { toggle, apply, lineBounds };
  if (typeof module !== 'undefined') module.exports = root.waMark;
  if (typeof document === 'undefined') return;

  /* ---- the tiny toolbar under the selection ---- */
  const TARGETS = '#focusText, #baseMessageText, .bank-detail textarea, #volMessage';
  const bar = document.createElement('div');
  bar.id = 'waMarkBar';
  bar.setAttribute('role', 'toolbar');
  bar.setAttribute('aria-label', 'Text formatting');
  bar.hidden = true;
  bar.innerHTML =
    '<button type="button" data-wa-mark="*" aria-label="Bold selected text" title="Bold"><b>B</b></button>' +
    '<button type="button" data-wa-mark="_" aria-label="Italic selected text" title="Italic"><i>I</i></button>';
  let current = null,
    pointerDown = false,
    frame = 0;

  /* Where a character index sits on screen: a hidden copy of the textarea's text is measured. */
  function pointAt(ta, index) {
    const cs = getComputedStyle(ta),
      mirror = document.createElement('div');
    for (const prop of [
      'boxSizing',
      'width',
      'paddingTop',
      'paddingRight',
      'paddingBottom',
      'paddingLeft',
      'borderTopWidth',
      'borderRightWidth',
      'borderBottomWidth',
      'borderLeftWidth',
      'fontFamily',
      'fontSize',
      'fontWeight',
      'fontStyle',
      'lineHeight',
      'letterSpacing',
      'textTransform',
      'textIndent',
      'tabSize',
      'direction',
      'textAlign',
    ])
      mirror.style[prop] = cs[prop];
    mirror.style.cssText +=
      ';position:fixed;visibility:hidden;top:0;left:-9999px;white-space:pre-wrap;overflow-wrap:break-word;overflow:hidden;height:auto';
    mirror.textContent = ta.value.slice(0, index);
    const mark = document.createElement('span');
    mark.textContent = ta.value.slice(index) || '.';
    mirror.append(mark);
    document.body.append(mirror);
    const box = ta.getBoundingClientRect(),
      m = mirror.getBoundingClientRect(),
      s = mark.getBoundingClientRect(),
      line = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.35;
    const point = {
      x: box.left + (s.left - m.left) - ta.scrollLeft,
      bottom: box.top + (s.top - m.top) - ta.scrollTop + Math.min(line, s.height || line),
      line,
    };
    mirror.remove();
    return point;
  }

  function hide() {
    bar.hidden = true;
    current = null;
  }

  function place() {
    frame = 0;
    const ta = document.activeElement;
    if (
      pointerDown ||
      !ta ||
      ta.tagName !== 'TEXTAREA' ||
      !ta.matches(TARGETS) ||
      ta.hidden ||
      ta.disabled ||
      ta.readOnly ||
      ta.selectionStart === ta.selectionEnd ||
      !ta.value.slice(ta.selectionStart, ta.selectionEnd).trim()
    )
      return hide();
    current = ta;
    const end = pointAt(ta, ta.selectionEnd),
      start = pointAt(ta, ta.selectionStart),
      oneLine = Math.abs(start.bottom - end.bottom) < 4,
      vv = window.visualViewport,
      view = {
        left: vv ? vv.offsetLeft : 0,
        top: vv ? vv.offsetTop : 0,
        width: vv ? vv.width : innerWidth,
        height: vv ? vv.height : innerHeight,
      };
    /* A modal dialog makes everything outside it unclickable, so the bar lives inside it while it is open. */
    const host = ta.closest('dialog') || document.body;
    if (bar.parentNode !== host) host.append(bar);
    bar.hidden = false;
    const w = bar.offsetWidth,
      h = bar.offsetHeight,
      anchorX = oneLine ? (start.x + end.x) / 2 : end.x;
    let left = anchorX - w / 2,
      top = end.bottom + 8;
    left = Math.max(view.left + 8, Math.min(left, view.left + view.width - w - 8));
    /* No room below (keyboard or screen edge): sit just above the selection instead of off screen. */
    if (top + h > view.top + view.height - 4)
      top = Math.max(view.top + 4, start.bottom - start.line - h - 6);
    bar.style.left = Math.round(left) + 'px';
    bar.style.top = Math.round(top) + 'px';
    /* If the host has its own transform, fixed positions are relative to it: measure and correct. */
    const got = bar.getBoundingClientRect();
    if (Math.abs(got.left - left) > 1 || Math.abs(got.top - top) > 1) {
      bar.style.left = Math.round(left - (got.left - left)) + 'px';
      bar.style.top = Math.round(top - (got.top - top)) + 'px';
    }
  }

  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(place);
  };

  document.addEventListener('selectionchange', schedule);
  /* Some browsers only report a textarea's selection through select / input, not selectionchange. */
  document.addEventListener('select', schedule, true);
  document.addEventListener('input', schedule, true);
  document.addEventListener('pointerdown', (e) => {
    if (bar.contains(e.target)) return;
    pointerDown = !!e.target.closest?.(TARGETS);
    if (!pointerDown) hide();
    else bar.hidden = true;
  });
  document.addEventListener('pointerup', () => {
    if (pointerDown) {
      pointerDown = false;
      schedule();
    }
  });
  document.addEventListener('pointercancel', () => {
    pointerDown = false;
    schedule();
  });
  document.addEventListener('keyup', schedule);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !bar.hidden) hide();
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && current && !bar.hidden) {
      const k = e.key.toLowerCase();
      if (k === 'b' || k === 'i') {
        e.preventDefault();
        apply(current, k === 'b' ? '*' : '_');
      }
    }
  });
  document.addEventListener('scroll', schedule, true);
  addEventListener('resize', schedule);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', schedule);
    window.visualViewport.addEventListener('scroll', schedule);
  }
  document.addEventListener('focusout', (e) => {
    if (e.target === current) setTimeout(() => document.activeElement !== current && hide(), 0);
  });
  /* Pressing the buttons must not take the selection away from the text. */
  bar.addEventListener('pointerdown', (e) => e.preventDefault());
  bar.addEventListener('mousedown', (e) => e.preventDefault());
  bar.addEventListener('click', (e) => {
    const b = e.target.closest('[data-wa-mark]');
    if (b && current && apply(current, b.dataset.waMark)) schedule();
  });
  document.body.append(bar);
})(typeof window !== 'undefined' ? window : globalThis);
