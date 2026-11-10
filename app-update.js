/* If the server has been updated since this page loaded, say so: a tab left open keeps running old code. */
(() => {
  let first = null,
    shown = false;
  function show() {
    shown = true;
    const bar = document.createElement('div');
    bar.id = 'updateBar';
    bar.setAttribute('role', 'status');
    bar.setAttribute('popover', 'manual'); // top layer: above open dialogs too
    bar.style.cssText =
      'position:fixed;inset:max(8px,env(safe-area-inset-top)) 8px auto 8px;margin:0 auto;max-width:420px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 8px 8px 16px;border:1px solid #3b82f6;border-radius:14px;background:#10203f;color:#fff;font:600 14px system-ui,sans-serif;box-shadow:0 8px 24px #0008;z-index:2147483647';
    const text = document.createElement('span');
    text.textContent = 'New version ready';
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Refresh';
    button.style.cssText =
      'min-height:40px;padding:0 18px;border:0;border-radius:10px;background:#2f6fe8;color:#fff;font:700 14px system-ui,sans-serif;cursor:pointer';
    button.onclick = () => location.reload();
    bar.append(text, button);
    document.body.append(bar);
    try {
      bar.showPopover();
    } catch (_) {}
  }
  async function check() {
    if (shown) return;
    try {
      const response = await fetch('/health', { cache: 'no-store' });
      const version = (await response.json()).version;
      if (!version || version === 'local') return;
      if (first === null) first = version;
      else if (version !== first) show();
    } catch (_) {}
  }
  check();
  setInterval(check, 60000);
  document.addEventListener('visibilitychange', () => document.hidden || check());
})();
