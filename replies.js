/* Auto replies: the owner's own written replies for chats where someone sends a picture or says done/donated. */
(() => {
  const make = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const dlg = make('dialog', 'donor-form-dialog replies-dialog');
  dlg.setAttribute('aria-label', 'Auto replies');
  dlg.innerHTML =
    '<h2>Reply</h2><p style="margin:0 0 6px;font-size:13px;opacity:.75">When someone sends a picture or says done / donated, every reply below goes to them as its own message. WhatsApp is checked every minute.</p><label style="display:flex;align-items:center;gap:10px;margin:8px 0;font-weight:600"><input type="checkbox" id="repEnabled" style="width:20px;height:20px;min-height:0;flex:none"> Turn ON</label><div id="repList"></div><p id="repNote" role="status"></p><div class="donor-form-actions"><button type="button" id="repAdd">+ Add another reply</button><button type="button" id="repClose">Close</button><button type="button" class="primary" id="repSave">Save</button></div>';
  document.body.append(dlg);
  const $ = (id) => document.getElementById(id);
  const row = (text) => {
    const box = make('div', 'rep-row');
    box.style.cssText = 'display:flex;gap:8px;align-items:flex-start;margin:6px 0';
    const ta = make('textarea', '');
    ta.style.flex = '1';
    ta.rows = 2;
    ta.maxLength = 1000;
    ta.placeholder = 'Write a reply, e.g. JazakAllah, we will confirm and update you soon. 🤲';
    ta.value = text || '';
    const rm = make('button', 'tool', 'Remove');
    rm.type = 'button';
    rm.onclick = () => box.remove();
    box.append(ta, rm);
    $('repList').append(box);
  };
  const note = (t, bad) => {
    $('repNote').textContent = t;
    $('repNote').style.color = bad ? 'var(--red)' : '';
  };
  async function load() {
    try {
      const r = await fetch('/reply-setup');
      const d = await r.json();
      $('repEnabled').checked = !!d.enabled;
      $('repList').textContent = '';
      const saved = d.replies && d.replies.length ? d.replies : [];
      (saved.length >= 2 ? saved : [...saved, '', ''].slice(0, 2)).forEach(row);
      note(
        d.autopilot ? '' : 'Auto is off. Replies are saved but only sent while Auto is on.',
        false,
      );
    } catch (e) {
      note('Could not load your replies.', true);
    }
  }
  $('repAdd').onclick = () => row('');
  $('repEnabled').onchange = () => $('repSave').click();
  $('repClose').onclick = () => dlg.close();
  $('repSave').onclick = async () => {
    const replies = [...dlg.querySelectorAll('textarea')]
      .map((t) => t.value.trim())
      .filter(Boolean);
    $('repSave').disabled = true;
    try {
      const r = await fetch('/reply-setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: $('repEnabled').checked, replies }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error || 'Could not save.');
      note(
        'Saved ' +
          d.replies.length +
          ' repl' +
          (d.replies.length === 1 ? 'y' : 'ies') +
          (d.enabled ? ' · on' : ' · off'),
        false,
      );
    } catch (e) {
      note(e.message, true);
    } finally {
      $('repSave').disabled = false;
    }
  };
  const open = () => {
    load();
    dlg.showModal();
  };
  /* The Reply button lives in the header More menu (and the old message tools menu as a fallback). */
  const place = () => {
    const panel =
      document.querySelector('#mainNavMore .compact-nav-panel') ||
      document.querySelector('.overflow-tools>div');
    if (!panel || panel.querySelector('.reply-open')) return !!panel;
    const b = make('button', 'tool reply-open', 'Reply');
    b.type = 'button';
    b.onclick = open;
    panel.append(b);
    return true;
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', place);
  else place();
  window.AutoReplies = { open };
})();
