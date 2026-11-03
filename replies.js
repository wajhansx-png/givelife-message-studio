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
    const rm = make('button', 'tool rep-remove', '✕');
    rm.setAttribute('aria-label', 'Remove this reply');
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

/* Report: a quick two-line view of what is happening right now (groups, then DMs). */
(() => {
  const GROUP_NAMES = {
    main: 'GiveLife',
    community: 'Upwork Community',
    fiverr: 'Fiverr Course',
    upwork: 'Upwork Course',
    uet: 'Fiverr UET',
    toprated: 'Top Rated',
  };
  const dlg = document.createElement('dialog');
  dlg.className = 'report-dialog';
  dlg.setAttribute('aria-label', 'Report');
  dlg.innerHTML =
    '<div class="report-card"><h2>Right now</h2><p class="report-line" id="reportGroups">Loading…</p><p class="report-line" id="reportDms"></p><button type="button" id="reportClose">Close</button></div>';
  document.body.append(dlg);
  const $ = (id) => document.getElementById(id);
  const clock = (sec) =>
    new Date(sec * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  async function fill() {
    $('reportGroups').textContent = 'Loading…';
    $('reportDms').textContent = '';
    try {
      const d = await (await fetch('/autopilot')).json(),
        st = d.status || {},
        t = st.today || {},
        next = (st.next || [])[0];
      $('reportGroups').textContent =
        '👥 Groups: ' +
        (t.posts || 0) +
        ' posts today' +
        (next ? ' · next ' + (GROUP_NAMES[next.group] || next.group) + (next.in ? ' in ' + next.in + ' min' : ' now') : '') +
        (d.on ? '' : ' · Auto is OFF');
    } catch (e) {
      $('reportGroups').textContent = '👥 Groups: status unavailable right now.';
    }
    try {
      const j = await (await fetch('/donor-delivery')).json(),
        active = ['Starting', 'Sending', 'Waiting'].includes(j.state),
        sent = (j.previous_sent || 0) + (j.sent || 0),
        total = j.original_total || j.total || 0;
      $('reportDms').textContent = active
        ? '💬 DMs: ' +
          sent +
          ' / ' +
          total +
          ' sent · ' +
          Math.max(0, total - sent) +
          ' left' +
          (j.next_batch_at ? ' · next batch at ' + clock(j.next_batch_at) : j.next_at ? ' · next in ' + Math.max(0, Math.ceil(j.next_at - Date.now() / 1000)) + 's' : '')
        : '💬 DMs: not sending right now' + (sent ? ' · last batch ' + sent + ' / ' + total + ' sent' : '');
    } catch (e) {
      $('reportDms').textContent = '💬 DMs: status unavailable right now.';
    }
  }
  const open = () => {
    fill();
    dlg.showModal();
  };
  $('reportClose').onclick = () => dlg.close();
  dlg.addEventListener('click', (e) => {
    if (e.target === dlg) dlg.close();
  });
  const place = () => {
    const bar = document.querySelector('.brandbar');
    if (bar && !bar.querySelector('.report-open')) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'report-open';
      b.title = 'Report';
      b.setAttribute('aria-label', 'Report');
      b.textContent = '📊 Report';
      b.onclick = open;
      const more = bar.querySelector('#mainNavMore');
      more ? bar.insertBefore(b, more) : bar.append(b);
    }
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', place);
  else place();
  window.GiveLifeReport = { open };
})();
