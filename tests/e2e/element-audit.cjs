/* Read-only geometry audit. It scrolls controls into view, never activates them. */
async function auditElements(page, rootSelector) {
  return page.locator(rootSelector).evaluate((root, rootSelector) => {
    const viewport = { width: innerWidth, height: innerHeight };
    const controls = [
      ...root.querySelectorAll(
        'button,a[href],input:not([type=hidden]),textarea,select,summary,[role=button],[role=tab],[contenteditable=true]',
      ),
    ].filter(
      (el) =>
        el.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true }) &&
        el.getBoundingClientRect().width > 0,
    );
    const failures = [],
      records = [];
    for (const el of controls) {
      // Bring controls in scrolling dialogs, toolbars and lists into view first.
      if (el.matches('a.skip, a.skip-link')) el.focus({ preventScroll: true });
      el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
      const rect = el.getBoundingClientRect(),
        style = getComputedStyle(el);
      const label = el.labels?.[0] || el.closest('label');
      const target = /checkbox|radio/.test(el.type) && label ? label : el;
      const hit = target.getBoundingClientRect();
      const inline = el.matches('a') && style.display === 'inline';
      const name =
        el.getAttribute('aria-label') ||
        el.getAttribute('title') ||
        el.textContent.trim() ||
        label?.textContent.trim() ||
        el.getAttribute('placeholder') ||
        el.id;
      const record = {
        element: el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + [...el.classList].join('.'),
        name: String(name || '').slice(0, 100),
        x: +rect.x.toFixed(1),
        y: +rect.y.toFixed(1),
        width: +rect.width.toFixed(1),
        height: +rect.height.toFixed(1),
        targetWidth: +hit.width.toFixed(1),
        targetHeight: +hit.height.toFixed(1),
        disabled: !!el.disabled,
        issues: [],
      };
      if (rect.left < -1 || rect.right > innerWidth + 1) record.issues.push('horizontal-clipping');
      // WCAG 2.2 AA minimum. Primary phone controls have separate 44px tests.
      // Inline links and native inputs using a larger label are handled explicitly.
      if (!inline && !el.disabled && (hit.width < 23.5 || hit.height < 23.5))
        record.issues.push('target-under-24px');
      if (!el.disabled) {
        const left = Math.max(rect.left, 0),
          right = Math.min(rect.right, innerWidth);
        const top = Math.max(rect.top, 0),
          bottom = Math.min(rect.bottom, innerHeight);
        let reachable = false;
        if (right > left && bottom > top) {
          const points = [
            [(left + right) / 2, (top + bottom) / 2],
            [left + 2, top + 2],
            [right - 2, top + 2],
            [left + 2, bottom - 2],
            [right - 2, bottom - 2],
          ];
          reachable = points.some(([x, y]) => {
            const at = document.elementFromPoint(x, y);
            return (
              at === el ||
              el.contains(at) ||
              (target !== el && (at === target || target.contains(at)))
            );
          });
        }
        if (!reachable) record.issues.push('covered-or-unreachable');
      }
      if (
        el.matches('button,summary,[role=tab]') &&
        style.fontSize !== '0px' &&
        el.scrollWidth > el.clientWidth + 2
      )
        record.issues.push('control-label-overflow');
      records.push(record);
      if (el.matches('a.skip, a.skip-link')) el.blur();
      if (record.issues.length) failures.push(record);
    }
    // Inspect every rendered element, not only a hand-picked control list.
    let layoutElements = 0;
    for (const el of [root, ...root.querySelectorAll('*')]) {
      if (!el.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true })) continue;
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      const css = getComputedStyle(el);
      if (rect.width <= 2 && rect.height <= 2 && (css.clip !== 'auto' || css.clipPath !== 'none'))
        continue;
      layoutElements++;
      if (rect.left < -1 || rect.right > innerWidth + 1) {
        let scrolling = false;
        for (
          let parent = el.parentElement;
          parent && root.contains(parent);
          parent = parent.parentElement
        ) {
          const pc = getComputedStyle(parent);
          if (
            ['auto', 'scroll'].includes(pc.overflowX) &&
            parent.scrollWidth > parent.clientWidth
          ) {
            scrolling = true;
            break;
          }
        }
        if (!scrolling)
          failures.push({
            element: el.id ? '#' + el.id : el.tagName.toLowerCase(),
            name: (el.textContent || '').trim().slice(0, 60),
            x: +rect.left.toFixed(1),
            right: +rect.right.toFixed(1),
            issues: ['element-horizontal-clipping'],
          });
      }
    }
    const pageOverflow = document.documentElement.scrollWidth > innerWidth + 1;
    if (pageOverflow) failures.push({ element: 'html', issues: ['page-horizontal-overflow'] });
    return {
      viewport,
      root: rootSelector,
      controls: records.length,
      layoutElements,
      records,
      failures,
      pageOverflow,
    };
  }, rootSelector);
}
module.exports = { auditElements };
