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

/* Report: four numbered facts about what is happening right now, one short line each. */
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
    '<div class="report-card"><h2>Right now</h2><ol class="report-list">' +
    [
      ['Groups', 'reportGroups'],
      ['DMs', 'reportDms'],
      ['Replies', 'reportReplies'],
      ['Resumes', 'reportResumes'],
    ]
      .map(
        ([t, id], i) =>
          '<li><span class="rp-n" aria-hidden="true">' + (i + 1) + '</span><span class="rp-t">' + t +
          '</span><b class="rp-v" id="' + id + '">…</b><small class="rp-s" id="' + id + 'Sub"></small></li>',
      )
      .join('') +
    '</ol><button type="button" id="reportClose">Close</button></div>';
  document.body.append(dlg);
  const $ = (id) => document.getElementById(id);
  const clock = (sec) =>
    new Date(sec * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const put = (id, value, sub) => {
    $(id).textContent = value;
    $(id + 'Sub').textContent = sub || '';
  };
  async function fill() {
    for (const id of ['reportGroups', 'reportDms', 'reportReplies', 'reportResumes']) put(id, '…');
    try {
      const d = await (await fetch('/autopilot')).json(),
        st = d.status || {},
        t = st.today || {},
        next = (st.next || [])[0];
      put(
        'reportGroups',
        (t.posts || 0) + ' today',
        !d.on
          ? 'Auto is off'
          : next
            ? 'Next: ' + (GROUP_NAMES[next.group] || next.group) + (next.in ? ' in ' + next.in + ' min' : ' now')
            : 'Nothing due',
      );
    } catch (e) {
      put('reportGroups', 'Unavailable', 'Try again in a moment');
    }
    try {
      const j = await (await fetch('/donor-delivery')).json(),
        active = ['Starting', 'Sending', 'Waiting'].includes(j.state),
        sent = (j.previous_sent || 0) + (j.sent || 0),
        total = j.original_total || j.total || 0;
      if (active)
        put(
          'reportDms',
          sent + ' / ' + total,
          Math.max(0, total - sent) +
            ' left' +
            (j.next_batch_at
              ? ' · next batch ' + clock(j.next_batch_at)
              : j.next_at
                ? ' · next in ' + Math.max(0, Math.ceil(j.next_at - Date.now() / 1000)) + 's'
                : ''),
        );
      else put('reportDms', 'Idle', sent ? 'Last batch: ' + sent + ' of ' + total + ' sent' : '');
    } catch (e) {
      put('reportDms', 'Unavailable', 'Try again in a moment');
    }
  }
  const remember = (on) => {
    try {
      on ? localStorage.setItem('givelife-report-open', '1') : localStorage.removeItem('givelife-report-open');
    } catch (e) {}
  };
  async function fillExtra() {
    try {
      const d = await (await fetch('/report')).json(),
        r = d.replies || {},
        list = d.resumes || [],
        last = list[0];
      put('reportReplies', (r.today || 0) + ' today', (r.total || 0) + ' in total' + (r.on ? '' : ' · Reply is off'));
      put(
        'reportResumes',
        list.length ? String(list.length) : 'None',
        last ? 'Latest: ' + last.what + ' · ' + last.when + (last.state ? ' · ' + last.state : '') : '',
      );
    } catch (e) {
      put('reportReplies', 'Unavailable', '');
      put('reportResumes', 'Unavailable', '');
    }
  }
  const open = () => {
    fill();
    fillExtra();
    if (!dlg.open) dlg.showModal();
    remember(true);
  };
  dlg.addEventListener('close', () => remember(false));
  /* Reopening the app returns to the Report if it was open. */
  try {
    if (localStorage.getItem('givelife-report-open') === '1') setTimeout(open, 600);
  } catch (e) {}
  $('reportClose').onclick = () => {
    remember(false);
    dlg.close();
  };
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
      b.textContent = 'Report';
      b.onclick = open;
      const more = bar.querySelector('#mainNavMore');
      more ? bar.insertBefore(b, more) : bar.append(b);
    }
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', place);
  else place();
  window.GiveLifeReport = { open };
})();

/* Resume messages: pick GiveLife or Freelance, then resume now or at a Pakistan time. */
(() => {
  const dlg = document.createElement('dialog');
  dlg.className = 'resume-groups-dialog';
  dlg.setAttribute('aria-label', 'Resume messages');
  dlg.innerHTML =
    '<h2>Resume messages</h2><label for="rgWhich">Which groups?</label><select id="rgWhich"><option value="main">GiveLife</option><option value="free">All freelance groups</option><option value="all">All 6 groups</option></select><label for="rgTime">Resume at (Pakistan time, optional)</label><input id="rgTime" type="time" step="60"><p id="rgNote" role="status"></p><div class="rg-actions"><button type="button" id="rgCancel">Cancel</button><button type="button" id="rgAt">Resume at time</button><button type="button" id="rgNow" class="primary">Resume now</button></div>';
  document.body.append(dlg);
  const $ = (id) => document.getElementById(id);
  async function go(at) {
    const note = $('rgNote');
    if (at === '' ) return (note.textContent = 'Pick a time first, or press Resume now.');
    note.textContent = 'Working…';
    for (const b of dlg.querySelectorAll('button')) b.disabled = true;
    try {
      const r = await fetch('/schedule-resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ which: $('rgWhich').value, at: at || '' }),
        }),
        d = await r.json().catch(() => ({ error: 'The app is restarting. Try again in a minute.' }));
      if (!r.ok) throw Error(d.error || 'Could not resume.');
      note.textContent = '✓ ' + d.message;
      setTimeout(() => dlg.open && dlg.close(), 1600);
    } catch (e) {
      note.textContent = e.message;
    } finally {
      for (const b of dlg.querySelectorAll('button')) b.disabled = false;
    }
  }
  $('rgNow').onclick = () => go(null);
  $('rgAt').onclick = () => go($('rgTime').value);
  $('rgCancel').onclick = () => dlg.close();
  const open = () => {
    $('rgNote').textContent = '';
    dlg.showModal();
  };
  const place = () => {
    const panel = document.querySelector('#mainNavMore .compact-nav-panel');
    if (!panel || panel.querySelector('.resume-open')) return;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tool resume-open';
    b.textContent = 'Resume messages';
    b.onclick = open;
    panel.append(b);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', place);
  else place();
})();
