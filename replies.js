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
    '<h2>Reply</h2><p class="rep-hint">When someone sends a payment picture or says “done”, these go out by themselves (only while Auto is on).</p>' +
    '<label class="rep-switch"><input type="checkbox" id="repEnabled" role="switch"><span>Replies ON</span></label>' +
    '<section class="rep-group"><h3>Saved contacts</h3><small>Numbers already in Donors. Ask them to share the case.</small><div id="repList"></div><button type="button" class="rep-add" id="repAdd">+ Add</button></section>' +
    '<section class="rep-group"><h3>New contacts</h3><small>Numbers not in Donors. Ask them to join GiveLife and share.</small><div id="repNewList"></div><button type="button" class="rep-add" id="repAddNew">+ Add</button></section>' +
    '<p id="repNote" role="status" aria-live="polite"></p><div class="rep-actions"><button type="button" id="repClose">Close</button><button type="button" class="primary" id="repSave">Save</button></div>';
  document.body.append(dlg);
  const $ = (id) => document.getElementById(id);
  let dirty = false;
  dlg.addEventListener('input', () => (dirty = true));
  const row = (text, list = 'repList') => {
    const box = make('div', 'rep-row');
    const ta = make('textarea', '');
    ta.rows = 2;
    ta.maxLength = 1000;
    ta.placeholder =
      list === 'repList'
        ? 'e.g. JazakAllah! Please share this case in your groups. 🤲'
        : 'e.g. JazakAllah! Join GiveLife and share: <group link>';
    ta.value = text || '';
    const rm = make('button', 'tool rep-remove', '✕');
    rm.setAttribute('aria-label', 'Remove this reply');
    rm.type = 'button';
    rm.onclick = () => {
      box.remove();
      dirty = true;
    };
    box.append(ta, rm);
    $(list).append(box);
  };
  const note = (t, bad) => {
    $('repNote').textContent = t;
    $('repNote').style.color = bad ? 'var(--red)' : '';
  };
  async function load() {
    try {
      const r = await fetch('/reply-setup');
      const d = await r.json();
      // Never set up before: start ON, so the owner only has to write the replies and Save.
      $('repEnabled').checked = d.configured ? !!d.enabled : true;
      $('repList').textContent = '';
      $('repNewList').textContent = '';
      (d.replies && d.replies.length ? d.replies : ['']).forEach((t) => row(t, 'repList'));
      (d.new_replies && d.new_replies.length ? d.new_replies : ['']).forEach((t) =>
        row(t, 'repNewList'),
      );
      dirty = false;
      note(d.autopilot ? '' : 'Auto is off. Replies are saved and go out once Auto is on.', false);
    } catch (e) {
      note('Could not load your replies.', true);
    }
  }
  const texts = (list) =>
    [...$(list).querySelectorAll('textarea')].map((t) => t.value.trim()).filter(Boolean);
  async function save(close) {
    $('repSave').disabled = true;
    try {
      const r = await fetch('/reply-setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: $('repEnabled').checked,
          replies: texts('repList'),
          new_replies: texts('repNewList'),
        }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error || 'Could not save.');
      dirty = false;
      note('Saved ✓' + (d.enabled ? ' · replies ON' : ' · replies OFF'), false);
      if (close) setTimeout(() => dlg.open && !dirty && dlg.close(), 700);
    } catch (e) {
      note(e.message, true); // the typed text stays in the boxes
    } finally {
      $('repSave').disabled = false;
    }
  }
  $('repAdd').onclick = () => row('', 'repList');
  $('repAddNew').onclick = () => row('', 'repNewList');
  $('repEnabled').onchange = () => save(false);
  $('repSave').onclick = () => save(true);
  $('repClose').onclick = () => {
    if (dirty && !confirm('Close without saving your changes?')) return;
    dlg.close();
  };
  dlg.addEventListener('cancel', (e) => {
    if (dirty && !confirm('Close without saving your changes?')) e.preventDefault();
  });
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
          '<li><span class="rp-n" aria-hidden="true">' +
          (i + 1) +
          '</span><span class="rp-t">' +
          t +
          '</span><b class="rp-v" id="' +
          id +
          '">…</b><small class="rp-s" id="' +
          id +
          'Sub"></small></li>',
      )
      .join('') +
    '</ol><section id="autoControls" class="auto-controls" aria-label="Auto controls"><h3>Auto</h3><div id="autoCards"></div><p id="autoMsg" class="auto-msg" role="alert"></p></section><button type="button" id="reportClose">Close</button></div>';
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
            ? 'Next: ' +
              (GROUP_NAMES[next.group] || next.group) +
              (next.in ? ' in ' + next.in + ' min' : ' now')
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
      on
        ? localStorage.setItem('givelife-report-open', '1')
        : localStorage.removeItem('givelife-report-open');
    } catch (e) {}
  };
  async function fillExtra() {
    try {
      const d = await (await fetch('/report')).json(),
        r = d.replies || {},
        list = d.resumes || [],
        last = list[0];
      put(
        'reportReplies',
        (r.today || 0) + ' today',
        (r.total || 0) + ' in total' + (r.on ? '' : ' · Reply is off'),
      );
      put(
        'reportResumes',
        list.length ? String(list.length) : 'None',
        last
          ? 'Latest: ' + last.what + ' · ' + last.when + (last.state ? ' · ' + last.state : '')
          : '',
      );
    } catch (e) {
      put('reportReplies', 'Unavailable', '');
      put('reportResumes', 'Unavailable', '');
    }
  }
  /* ---- Auto: Group Auto, DM Important Donors, Important Donors Auto. Each card only talks to /auto-controls;
     the server runs everything, so closing the browser changes nothing. ---- */
  const cards = {};
  let autoTimer = 0,
    autoBusy = false;
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const autoSay = (text) => ($('autoMsg').textContent = text || '');
  async function autoCall(body) {
    const r = await fetch('/auto-controls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(d.error || 'That did not work. Nothing was changed.');
    return d;
  }
  function buildCard(c) {
    const card = el('article', 'auto-card'),
      head = el('div', 'auto-head'),
      sw = el('button', 'auto-switch'),
      stats = el('dl', 'auto-stats'),
      note = el('p', 'auto-note'),
      edit = el('button', 'auto-edit', 'Edit Settings'),
      form = el('form', 'auto-form');
    card.dataset.control = c.id;
    head.append(el('h4', '', c.title), sw);
    sw.type = edit.type = 'button';
    sw.setAttribute('role', 'switch');
    sw.setAttribute('aria-label', c.title);
    for (const [k, label] of [
      ['recipients', 'Recipients'],
      ['sent', 'Sent'],
      ['pending', 'Pending'],
      ['next', 'Next send'],
    ]) {
      const row = el('div');
      row.append(el('dt', '', label), el('dd', '', '—'));
      row.dataset.stat = k;
      stats.append(row);
    }
    form.hidden = true;
    form.append(el('p', 'auto-error'));
    card.append(head, stats, note, edit, form);
    cards[c.id] = { card, sw, stats, note, edit, form, fields: c.fields, filled: false };
    sw.onclick = () => toggle(c.id);
    edit.onclick = () => {
      form.hidden = !form.hidden;
      if (!form.hidden) fillForm(c.id);
    };
    form.onsubmit = (e) => {
      e.preventDefault();
      saveForm(c.id);
    };
    $('autoCards').append(card);
  }
  function fillForm(id) {
    const x = cards[id],
      view = x.last;
    x.form.replaceChildren(el('p', 'auto-error'));
    for (const f of x.fields) {
      const label = el('label'),
        text = el('span', '', f.label);
      let input;
      if (f.type === 'select') {
        input = el('select');
        for (const o of f.options) input.append(new Option(o.replace('_', ' '), o));
      } else {
        input = el('input');
        input.type = f.type === 'check' ? 'checkbox' : 'number';
        if (f.type === 'number') {
          input.min = f.min;
          input.max = f.max;
          input.step = 'any';
        }
      }
      input.name = f.key;
      const value = view.settings[f.key];
      if (f.type === 'check') input.checked = !!value;
      else input.value = value == null ? '' : value;
      label.className = f.type === 'check' ? 'auto-check' : '';
      label.append(...(f.type === 'check' ? [input, text] : [text, input]));
      x.form.append(label);
    }
    const save = el('button', 'auto-save', 'Save'),
      cancel = el('button', '', 'Cancel');
    save.type = 'submit';
    cancel.type = 'button';
    cancel.onclick = () => (x.form.hidden = true);
    x.form.append(save, cancel);
  }
  async function saveForm(id) {
    const x = cards[id],
      settings = {};
    for (const f of x.fields) {
      const input = x.form.elements[f.key];
      if (!input) continue;
      settings[f.key] =
        f.type === 'check'
          ? input.checked
          : f.type === 'number'
            ? input.value === ''
              ? null
              : Number(input.value)
            : input.value;
    }
    try {
      x.form.querySelector('.auto-error').textContent = '';
      paint(await autoCall({ control: id, settings }));
      x.form.hidden = true;
      autoSay(
        'Saved. Active sends use the new settings from the next send; nothing was restarted.',
      );
    } catch (e) {
      x.form.querySelector('.auto-error').textContent = e.message;
    }
  }
  async function toggle(id) {
    const x = cards[id];
    if (autoBusy) return;
    const turningOn = !x.last.on && x.last.state !== 'STOPPING';
    if (turningOn && id !== 'group') {
      const s = x.last.settings,
        what =
          id === 'important'
            ? 'up to ' + s.count + ' Important donors, ' + s.gap_minutes + ' minutes apart'
            : 'your ' +
              (s.scope || 'important').replace('_', ' ') +
              ' donors the way you usually send';
      if (!confirm('Switch ' + x.last.title + ' ON? It will DM ' + what + '.')) return;
    }
    autoBusy = true;
    x.sw.disabled = true;
    autoSay('');
    try {
      paint(await autoCall({ control: id, on: turningOn }));
    } catch (e) {
      autoSay(e.message);
    } finally {
      autoBusy = false;
      x.sw.disabled = false;
    }
  }
  function paint(view) {
    for (const c of Object.values(view.controls || {})) {
      if (!cards[c.id]) buildCard(c);
      const x = cards[c.id];
      x.last = c;
      x.sw.textContent = c.state === 'STOPPING' ? 'STOPPING' : c.on ? 'ON' : 'OFF';
      x.sw.setAttribute('aria-checked', c.on ? 'true' : 'false');
      x.card.dataset.state = c.state;
      const v = {
        recipients: c.recipients,
        sent: c.sent,
        pending: c.pending,
        next: c.next_at ? clock(c.next_at) : '—',
      };
      for (const row of x.stats.children) row.lastChild.textContent = v[row.dataset.stat];
      x.note.textContent = c.note || '';
    }
  }
  async function autoRefresh() {
    try {
      paint(await (await fetch('/auto-controls')).json());
    } catch (e) {
      autoSay('Auto controls are unavailable right now. Nothing was changed.');
    }
  }
  const open = () => {
    fill();
    fillExtra();
    autoRefresh();
    clearInterval(autoTimer);
    autoTimer = setInterval(() => {
      if (dlg.open && !document.hidden) autoRefresh();
    }, 2500);
    if (!dlg.open) dlg.showModal();
    remember(true);
  };
  dlg.addEventListener('close', () => {
    clearInterval(autoTimer);
    remember(false);
  });
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
    if (at === '') return (note.textContent = 'Pick a time first, or press Resume now.');
    note.textContent = 'Working…';
    for (const b of dlg.querySelectorAll('button')) b.disabled = true;
    try {
      const r = await fetch('/schedule-resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ which: $('rgWhich').value, at: at || '' }),
        }),
        d = await r
          .json()
          .catch(() => ({ error: 'The app is restarting. Try again in a minute.' }));
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

/* Phone main screen: Chat | Group messages | Donors along the bottom (the top copy is hidden by CSS). */
(() => {
  const place = () => {
    const foot = document.querySelector('.app > .foot'),
      top = document.querySelector('.brandbar .seg button');
    if (!foot || !top || foot.querySelector('#navGroups')) return;
    const b = document.createElement('button');
    b.type = 'button';
    b.id = 'navGroups';
    b.className = 'ghost';
    b.textContent = 'Group messages';
    b.onclick = () => top.click();
    const donors = foot.querySelector('#openDonors');
    donors ? donors.before(b) : foot.append(b);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', place);
  else place();
})();
