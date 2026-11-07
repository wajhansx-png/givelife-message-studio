/* Donor data never contains a phone number in this client. IDs go to the server. */
(() => {
  const el = (id) => document.getElementById(id),
    make = (tag, cls, text) => {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text != null) n.textContent = text;
      return n;
    };
  const page = make('dialog', 'donor-page');
  page.id = 'donorsPage';
  page.setAttribute('aria-label', 'Donor Hub');
  page.innerHTML = `<div class="donor-shell"><header class="donor-head"><div class="donor-title"><h1>Donors <span class="donor-count" id="donorTotal"></span></h1></div><span class="donor-total"><small>Total donated</small> <strong id="donorTotalAmount">PKR 0</strong></span><span class="donor-total"><small>Normal total</small> <strong id="donorNormalTotal">PKR 0</strong></span><span class="donor-message-tablist" role="tablist" aria-label="Message bank"><button role="tab" class="donor-msgs" id="donorMessagesTab" data-tab="messages" aria-selected="false" aria-label="Messages">Messages</button></span><button class="donor-bulk" id="donorBulk">Bulk message</button><button class="donor-add" id="donorAdd">+ Add</button></header><div class="donor-toolbar"><div class="donor-tabs" role="tablist" aria-label="Donor filters"><button role="tab" data-tab="all" aria-selected="true">All</button><button role="tab" data-tab="important" aria-selected="false">★ Important</button><button role="tab" data-tab="top" aria-selected="false">Top donors</button><button role="tab" data-tab="donated" aria-selected="false">Donated</button><button role="tab" data-tab="not_contacted" aria-selected="false">Not contacted</button><button role="tab" data-tab="volunteers" aria-selected="false">Volunteers</button></div><input class="donor-search" id="donorSearch" name="donor_search" type="search" autocomplete="off" placeholder="Search donors…" aria-label="Search donor names or private numbers"></div><div id="donorHideRow" class="hide-row" hidden><button type="button" id="donorHideSent" class="hide-chip"></button><button type="button" id="donorDeselectAll" class="hide-chip deselect-chip">Deselect all</button></div><div id="donorNotice" class="donor-notice" role="status" aria-live="polite"></div><div class="donor-table" id="donorTable" role="region" aria-label="Donor list" tabindex="0"><div class="donor-columns" aria-hidden="false"><span>★</span><span>Name</span><span>DM</span><span>Status</span><span>PKR</span><span><button type="button" class="donor-expand-btn" id="donorExpand" aria-label="Expand to full screen" title="Expand to full screen">⤢</button></span></div><div id="donorRows"></div></div><section id="donorMessages" class="donor-messages" aria-label="DM wording bank" hidden></section><section id="donorVolunteers" class="donor-volunteers" aria-label="Volunteers" hidden></section><div class="donor-progress" id="donorProgress" hidden><button type="button" class="dp-hide" id="donorProgressHide" aria-label="Hide sending details" title="Hide">Hide ⌄</button><span></span><div class="dp-facts" id="donorProgressFacts" aria-label="Batch plan"></div><button id="donorContinue" hidden>Restart</button><button id="donorEditBatch" title="Edit future sends without pausing the running batch">Edit settings</button><button id="donorStop">Pause</button></div><button type="button" class="dp-show" id="donorProgressShow" hidden aria-label="Show sending details" title="Show sending details">⌃ DM sending status</button><details id="donorBatchList" class="batch-list" hidden><summary id="donorBatchSummary"></summary><div class="batch-cols"><section><h3>Sent</h3><ol id="batchSent"></ol></section><section><h3>Next</h3><ol id="batchNext"></ol></section></div><p id="batchOther"></p></details><footer class="donor-bottom"><button type="button" class="donor-back-bottom back-action" id="donorMainBottom" aria-label="Back to main screen">← Back</button><button type="button" class="donor-gap" id="donorPace">Gap: 4 min ▾</button><input id="donorGap" type="hidden" value="240"><button type="button" class="donor-mini" id="donorTest" title="Send one clearly marked test DM to your own WhatsApp">Test DM</button><button type="button" class="donor-mini" id="donorToggle" title="Stop all DMs. Press again to resume everything.">Stop DMs</button><label class="donor-poster-toggle" for="donorRowPoster" title="Attach the poster to the single-tap DM button beside each donor"><input type="checkbox" id="donorRowPoster" checked> Poster on DM</label><span class="donor-message-info">Saved DM · Important first</span><button class="send-important" id="donorSendImportant">DM ★ Important</button><button class="send-donors" id="donorSendAll">DM all</button></footer></div>`;
  document.body.append(page);
  /* The Hide / Deselect chips live in the top bar, so showing them never pushes the donor list down. */
  page.querySelector('.donor-head').insertBefore(
    page.querySelector('#donorHideRow'),
    page.querySelector('.donor-message-tablist'),
  );

  /* Batch DM count, shown on its own at the right side of the donor list. */
  const dmBadge = make('div', 'donor-dm-badge');
  dmBadge.id = 'donorDmBadge';
  dmBadge.hidden = true;
  dmBadge.setAttribute('role', 'status');
  page.querySelector('.donor-shell').append(dmBadge);
  /* Follow-up: ON by default once a follow-up message is saved (the owner can switch it off; the choice is remembered). */
  let followUpOn = false;
  try {
    const stored = localStorage.getItem('givelife-follow-up');
    if (stored !== null) followUpOn = stored === '1';
    else
      api('/donor-messages')
        .then((d) => {
          if (stored === null && d && String(d.follow_up || '').trim()) setFollowUp(true, false);
        })
        .catch(() => {});
  } catch (e) {}
  function setFollowUp(on, remember = true) {
    followUpOn = !!on;
    if (el('donorFollowUp')) el('donorFollowUp').checked = followUpOn;
    if (el('batchFollowUp')) el('batchFollowUp').checked = followUpOn;
    if (remember)
      try {
        localStorage.setItem('givelife-follow-up', followUpOn ? '1' : '0');
      } catch (e) {}
  }
  /* ---- fullscreen expand ---- */
  {
    const btn = page.querySelector('#donorExpand');
    function updateExpandBtn(expanded) {
      btn.textContent = expanded ? '⤡' : '⤢';
      btn.setAttribute('aria-label', expanded ? 'Exit full screen' : 'Expand to full screen');
      btn.setAttribute('title', expanded ? 'Exit full screen' : 'Expand to full screen');
      page.classList.toggle('donor-expanded', expanded);
    }
    function tryNativeFS(enter) {
      try {
        // The Donors page is its own top layer, so it is the element that goes full screen.
        if (enter && !window.NativeFS?.isOn()) window.NativeFS?.toggle();
        else if (!enter && window.NativeFS?.isOn()) window.NativeFS.toggle();
      } catch (e) {}
    }
    /* The button floats over the list's top-right corner, so it shows on phones too (the header row is hidden there). */
    {
      const table = page.querySelector('#donorTable'),
        wrap = document.createElement('div');
      wrap.className = 'donor-table-wrap';
      table.parentNode.insertBefore(wrap, table);
      wrap.append(table, btn);
      /* On phones the full-screen icon sits in the header beside the title, not floating over the list. */
      const headMq = matchMedia('(max-width:700px)');
      const placeExpand = () => {
        const title = page.querySelector('.donor-title');
        if (headMq.matches && title) title.append(btn);
        else wrap.append(btn);
      };
      placeExpand();
      headMq.addEventListener('change', placeExpand);
      const opt = make('label', 'donor-fu-opt'),
        box = make('input');
      box.type = 'checkbox';
      box.id = 'donorFollowUp';
      box.name = 'send_follow_up';
      box.onchange = () => setFollowUp(box.checked);
      opt.id = 'donorFollowUpOpt';
      opt.append(box, make('span', '', 'Send with follow-up'));
      box.checked = followUpOn;
      wrap.prepend(opt);
    }
    {
    }
    /* Real browser full screen (browser bar hidden); where a phone browser can't, the list still fills the page. */
    btn.onclick = () => {
      const entering = !page.classList.contains('donor-expanded');
      updateExpandBtn(entering);
      tryNativeFS(entering);
    };
    document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && page.classList.contains('donor-expanded')) updateExpandBtn(false); });
  }

  let msgSub = 'dm'; /* Messages sub-tab: 'dm' versions or 'follow' up */
  const resumeStatus = make('div', 'donor-resume-status');
  resumeStatus.id = 'donorResumeStatus';
  resumeStatus.hidden = true;
  resumeStatus.innerHTML =
    '<span role="status" aria-live="polite"></span><div class="donor-resume-actions"><button type="button" class="primary" id="donorResumeNowInline">Resume now</button><button type="button" id="donorResumeAtInline">At a time…</button><button type="button" id="donorResumeCancel">Stop scheduled resume</button></div>';
  page
    .querySelector('.donor-shell')
    .insertBefore(resumeStatus, page.querySelector('.donor-bottom'));
  const resumeDialog = make('dialog', 'donor-form-dialog donor-resume-dialog');
  resumeDialog.id = 'donorResumeDialog';
  resumeDialog.setAttribute('aria-labelledby', 'donorResumeTitle');
  resumeDialog.innerHTML = `<h2 id="donorResumeTitle">Resume donor DMs</h2><p>Continue your saved automatic setup: same audience, gaps, batches, pauses and poster. People already handled are skipped.</p><div class="donor-resume-choices"><button type="button" class="primary" id="donorResumeNow">Resume now</button><button type="button" id="donorResumeSchedule">Resume at a time</button></div><form id="donorResumeClock" hidden><label for="donorResumeDate">Date (Pakistan)</label><input type="date" id="donorResumeDate" required><label for="donorResumeTime">Time (PKT)</label><input type="time" id="donorResumeTime" required step="60"><p>Pakistan time (UTC+5). The saved setup runs on the server when it is available; you can close the app.</p><div class="donor-form-actions"><button type="submit" class="primary" id="donorResumeSave">Schedule resume</button></div></form><p id="donorResumeNote" role="status" aria-live="polite"></p><div class="donor-form-actions"><button type="button" id="donorResumeClose">Cancel</button></div>`;
  document.body.append(resumeDialog);
  const volTiming = make('dialog', 'donor-form-dialog volunteer-timing-dialog');
  volTiming.id = 'volTimingDialog';
  volTiming.setAttribute('aria-labelledby', 'volTimingTitle');
  volTiming.innerHTML = `<h2 id="volTimingTitle">DM all volunteers</h2><p id="volTimingAudience"></p><form id="volTimingForm"><label for="volStartDelay">Start sending</label><select id="volStartDelay" name="delay_seconds"><option value="0">Send now</option><option value="300">In 5 minutes</option><option value="600">In 10 minutes</option><option value="900">In 15 minutes</option><option value="1800">In 30 minutes</option><option value="3600">In 1 hour</option><option value="7200">In 2 hours</option></select><p id="volTimingPlan" role="status"></p><p>Your message and poster choice will be queued on the server. You can close the app. Sending starts when the server is available.</p><p id="volTimingNote" role="status" aria-live="polite"></p><div class="donor-form-actions"><button type="button" id="volTimingCancel">Cancel</button><button type="submit" class="primary" id="volTimingStart">Send now</button></div></form>`;
  document.body.append(volTiming);
  let volSendPlan = null,
    volTimingPending = false;
  function volunteerDelaySeconds(raw) {
    if (!/^(0|300|600|900|1800|3600|7200)$/.test(String(raw)))
      throw Error('Choose when to start sending.');
    return Number(raw);
  }
  function paintVolunteerTiming() {
    const delay = volunteerDelaySeconds(el('volStartDelay').value);
    el('volTimingStart').textContent = delay ? 'Schedule DMs' : 'Send now';
    el('volTimingPlan').textContent =
      (delay ? 'First DM in ' + delay / 60 + ' minutes. ' : 'First DM now. ') +
      'Then one DM every 3 minutes.';
  }
  function openVolunteerTiming(text, poster) {
    if (volTimingPending) return;
    if (!text.trim()) {
      notice('Write the message for volunteers first.', true);
      el('volMessage')?.focus();
      return;
    }
    volSendPlan = { text, poster, request_id: 'v' + requestId() };
    el('volStartDelay').value = '0';
    el('volTimingNote').textContent = '';
    el('volTimingAudience').textContent =
      'Send to the volunteers still waiting in your list (' + vols.items.length + ' total).';
    paintVolunteerTiming();
    if (!volTiming.open) volTiming.showModal();
    el('volStartDelay').focus();
  }
  el('volStartDelay').onchange = paintVolunteerTiming;
  el('volTimingCancel').onclick = () => volTiming.close();
  el('volTimingForm').onsubmit = async (e) => {
    e.preventDefault();
    if (volTimingPending || !volSendPlan) return;
    volTimingPending = true;
    el('volTimingStart').disabled = true;
    el('volStartDelay').disabled = true;
    el('volTimingNote').textContent = 'Saving your send…';
    try {
      const plan = volSendPlan,
        delay = volunteerDelaySeconds(el('volStartDelay').value);
      await api('/volunteers', { action: 'message', text: plan.text });
      const result = await api('/volunteers', {
        action: 'send_all',
        request_id: plan.request_id,
        poster: plan.poster,
        gap_seconds: 180,
        delay_seconds: delay,
      });
      volTiming.close();
      await loadVolunteers();
      if (tab === 'volunteers') showVolunteers(true);
      notice(result.reply);
    } catch (error) {
      el('volTimingNote').textContent = error.message;
    } finally {
      volTimingPending = false;
      el('volTimingStart').disabled = false;
      el('volStartDelay').disabled = false;
    }
  };
  let resumePending = false;
  function openResumeChoice() {
    el('donorResumeClock').hidden = true;
    el('donorResumeNote').textContent = '';
    if (!resumeDialog.open) resumeDialog.showModal();
    el('donorResumeNow').focus({ preventScroll: true });
  }
  function paintDMControl(st) {
    const pending = st.resume?.state === 'Pending';
    el('donorToggle').dataset.paused = String(!!st.paused);
    el('donorToggle').textContent = pending
      ? 'Change resume'
      : st.paused
        ? 'Resume DMs'
        : 'Stop DMs';
    const attention = ['Failed', 'Uncertain'].includes(st.resume?.state),
      paused = !!st.paused;
    resumeStatus.hidden = !pending && !attention && !paused;
    /* The status owns a full-width footer row; it never shares a button cell. */
    const bottomRow = page.querySelector('.donor-bottom');
    if (bottomRow && resumeStatus.parentElement !== bottomRow)
      bottomRow.prepend(resumeStatus);
    /* Folded: the panel shows as a small pill until tapped open again (remembered). */
    let folded = false;
    try {
      folded = localStorage.getItem('givelife-resume-folded') === '1';
    } catch (e) {}
    resumeStatus.classList.toggle('rs-folded', folded && !attention);
    if (!resumeStatus.querySelector('.rs-fold')) {
      const fold = make('button', 'rs-fold', 'Hide ⌄');
      fold.type = 'button';
      fold.setAttribute('aria-label', 'Hide the resume panel');
      const pill = make('button', 'rs-pill', '⏸ DMs paused · Show');
      pill.type = 'button';
      pill.setAttribute('aria-label', 'Show the resume panel');
      const set = (v) => {
        try {
          localStorage.setItem('givelife-resume-folded', v ? '1' : '0');
        } catch (e) {}
        resumeStatus.classList.toggle('rs-folded', v);
      };
      fold.onclick = () => set(true);
      pill.onclick = () => set(false);
      resumeStatus.append(fold, pill);
    }
    resumeStatus.dataset.state = pending ? 'scheduled' : attention ? 'attention' : 'paused';
    resumeStatus.querySelector('span').textContent = pending
      ? 'DMs paused · Resume at ' + st.resume.label
      : attention
        ? 'Resume needs attention: ' + (st.resume?.error || '')
        : 'DMs paused';
    el('donorResumeNowInline').hidden = attention || !(pending || paused);
    el('donorResumeAtInline').hidden = attention || !(pending || paused);
    el('donorResumeAtInline').textContent = pending ? 'Change time' : 'At a time…';
    el('donorResumeCancel').hidden = !pending;
  }
  function resumeClockValue(date, time) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time))
      throw Error('Choose both a date and a clock time.');
    const stamp = Date.parse(date + 'T' + time + ':00+05:00');
    if (!Number.isFinite(stamp) || stamp <= Date.now())
      throw Error('Choose a future time in Pakistan time (PKT).');
    return date + 'T' + time;
  }
  async function submitResume(when) {
    if (resumePending) return;
    resumePending = true;
    for (const id of ['donorResumeNow', 'donorResumeSchedule', 'donorResumeSave'])
      el(id).disabled = true;
    el('donorResumeNote').textContent = when
      ? 'Saving your resume time…'
      : 'Resuming your saved setup…';
    try {
      const r = await api(
        '/donor-delivery',
        when
          ? { resume_at: when, request_id: requestId() }
          : { resume: true, request_id: requestId() },
      );
      resumeDialog.close();
      notice(r.reply);
      await syncToggle();
      await poll();
    } catch (e) {
      el('donorResumeNote').textContent = e.message;
      if (!resumeDialog.open) notice(e.message, true);
    } finally {
      resumePending = false;
      for (const id of ['donorResumeNow', 'donorResumeSchedule', 'donorResumeSave'])
        el(id).disabled = false;
    }
  }
  el('donorResumeNow').onclick = () => submitResume();
  el('donorResumeClose').onclick = () => resumeDialog.close();
  el('donorResumeSchedule').onclick = () => {
    const next = new Date(Date.now() + 5 * 60000 + 5 * 3600000).toISOString();
    el('donorResumeDate').value = next.slice(0, 10);
    el('donorResumeDate').min = new Date(Date.now() + 5 * 3600000).toISOString().slice(0, 10);
    el('donorResumeTime').value = next.slice(11, 16);
    el('donorResumeClock').hidden = false;
    el('donorResumeDate').focus();
  };
  el('donorResumeClock').onsubmit = (e) => {
    e.preventDefault();
    try {
      submitResume(resumeClockValue(el('donorResumeDate').value, el('donorResumeTime').value));
    } catch (error) {
      el('donorResumeNote').textContent = error.message;
      el('donorResumeTime').focus();
    }
  };
  el('donorResumeNowInline').onclick = () => submitResume();
  el('donorResumeAtInline').onclick = () => {
    openResumeChoice();
    el('donorResumeSchedule').click();
  };
  el('donorResumeCancel').onclick = async () => {
    el('donorResumeCancel').disabled = true;
    try {
      const r = await api('/donor-delivery', { stop: true });
      notice(r.reply);
      await syncToggle();
      await poll();
    } catch (e) {
      notice(e.message, true);
    } finally {
      el('donorResumeCancel').disabled = false;
    }
  };
  const add = make('dialog', 'donor-form-dialog');
  add.id = 'donorAddDialog';
  add.setAttribute('aria-label', 'Add donor');
  add.innerHTML = `<h2>Add donor</h2><form id="donorAddForm"><label for="donorNewName">Name or saved label</label><input id="donorNewName" name="donor_name" aria-describedby="donorAddNote" maxlength="120" placeholder="Ali Donor or D25" autocomplete="off"><label for="donorNewPhone">Phone number (optional)</label><input id="donorNewPhone" name="donor_phone" aria-describedby="donorAddNote" type="password" inputmode="tel" autocomplete="off" placeholder="Optional. Country code, or Pakistani 03 number"><p id="donorAddNote" role="status"></p><div class="donor-form-actions"><button type="button" id="donorAddCancel">Cancel</button><button type="submit" class="primary" id="donorAddSave">Add donor</button></div></form><details><summary>Import verified contacts</summary><button type="button" id="donorImport">Choose contacts file</button><input type="file" id="donorImportFile" accept="application/json,.json" hidden></details>`;
  document.body.append(add);
  const poster = make('dialog', 'poster-dialog');
  poster.id = 'posterDialog';
  poster.setAttribute('aria-label', 'Change DM poster');
  poster.innerHTML = `<h2>Poster · groups and DMs</h2><img width="320" height="400" id="posterCurrent" alt="Current campaign poster"><video id="posterCurrentVideo" controls playsinline preload="metadata" aria-label="Saved campaign video" hidden></video><label class="poster-choose" for="posterFile">Choose new poster (picture or MP4 video)</label><input type="file" id="posterFile" accept="image/*,video/mp4,video/quicktime" hidden><p id="posterNote" role="status" aria-live="polite"></p><div id="posterProgress" class="poster-save-progress" hidden><div id="posterProgressTrack" class="poster-save-track" role="progressbar" aria-label="Poster upload progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><span id="posterProgressFill"></span></div><span id="posterProgressText" role="status" aria-live="polite"></span></div><div class="donor-form-actions"><button id="posterClose" type="button">Cancel</button><button id="posterSave" type="button" class="primary" disabled>Save poster</button></div>`;
  document.body.append(poster);
  const launch = make('button', 'primary donor-launch donor-launch-foot', 'Donors');
  launch.type = 'button';
  launch.id = 'openDonors';
  launch.setAttribute('aria-label', 'Open Donors');
  /* Keep Donors at the bottom centre on every screen size. */
  document.querySelector('.foot')?.insertBefore(launch, document.getElementById('keyboardHelp'));
  const settings = document.querySelector('#set .body');
  if (settings) {
    const row = make('div', 'row');
    const text = make('div', 't');
    text.append(make('b', '', 'Poster'));
    const b = make('button', 'tool', 'Change poster');
    b.type = 'button';
    b.onclick = openPoster;
    row.append(text, b);
    settings.prepend(row);
  }
  const tools = document.querySelector('.overflow-tools>div');
  if (tools) {
    const b = make('button', 'tool', 'Change poster');
    b.type = 'button';
    b.onclick = openPoster;
    tools.append(b);
  }
  let vols = { items: [], message: '', delivery: null },
    volPoll = 0,
    volDockObserver = null;
  let drawEpoch = 0;
  const DRAW_CHUNK = 40;
  let tab = 'all',
    data = { items: [], counts: {} },
    searchTimer,
    sendPending = false,
    pollTimer,
    posterData = null,
    posterUrl = null,
    posterSaving = false,
    noticeTimer;
  let singlePosterOn = true;
  try {
    singlePosterOn = sessionStorage.getItem('givelife-donor-row-poster') !== '0';
  } catch (e) {}
  let allDonors = [],
    loaded = false,
    loadPromise = null,
    bankData = null,
    bankPage = 10;
  const rowQueues = new Map(),
    rowVersions = new Map(),
    confirmedRows = new Map(),
    amountTimers = new Map();
  let pickerScope = null;
  const bankEdits = new Map();
  try {
    for (const [id, text] of JSON.parse(sessionStorage.getItem('givelife-bank-edits') || '[]'))
      if (typeof id === 'string' && typeof text === 'string') bankEdits.set(id, text);
  } catch (e) {}
  function keepBankEdits() {
    try {
      sessionStorage.setItem('givelife-bank-edits', JSON.stringify([...bankEdits]));
    } catch (e) {}
  }
  const requestId = () => crypto.randomUUID();
  let filterEpoch = 0;
  function cancelAmount(id) {
    clearTimeout(amountTimers.get(id));
    amountTimers.delete(id);
  }
  /* Cached once and updated on resize: reading sizes during a DOM change forces a full page layout. */
  const narrow560 = { matches: false },
    narrow700 = { matches: false };
  for (const [flag, q] of [[narrow560, '(max-width:559.98px)'], [narrow700, '(max-width:699.98px)']]) {
    const mq = matchMedia(q);
    flag.matches = mq.matches;
    mq.addEventListener('change', (e) => (flag.matches = e.matches));
  }
  function updateCounts() {
    const counts = {
      all: allDonors.length,
      top: 0,
      important: 0,
      donated: 0,
      not_contacted: 0,
      donated_amount: 0,
    };
    for (const d of allDonors) {
      if (d.top_donor) counts.top++;
      if (d.important) counts.important++;
      if (d.donated) {
        counts.donated++;
        counts.donated_amount += Number(d.amount) || 0;
      } else if (!d.dm_sent) counts.not_contacted++;
    }
    data.counts = counts;
    el('donorTotal').textContent = counts.all;
    el('donorTotalAmount').textContent = 'PKR ' + counts.donated_amount.toLocaleString('en-PK');
    const labels = {
      all: 'All',
      important: '★ Important',
      top: 'Top donors',
      donated: 'Donated',
      // matchMedia, not innerWidth: reading innerWidth right after a DOM change forces a full page layout.
      not_contacted: narrow560.matches ? 'Not DMed' : 'Not contacted',
      volunteers: narrow700.matches ? 'Helpers' : 'Volunteers',
      messages: 'Messages',
    };
    counts.volunteers = vols.items.length;
    for (const b of page.querySelectorAll('[data-tab]')) {
      paintTab(b, labels[b.dataset.tab], counts[b.dataset.tab]);
      b.setAttribute('aria-selected', String(tab === b.dataset.tab));
      // setAttribute (only on change), not .tabIndex: the property forces a synchronous style recalc per tab.
      const ti = b.dataset.tab === 'messages' || tab === b.dataset.tab ? '0' : '-1';
      if (b.getAttribute('tabindex') !== ti) b.setAttribute('tabindex', ti);
      b.setAttribute(
        'aria-label',
        {
          all: 'All donors',
          important: 'Important donors',
          top: 'Top donors',
          donated: 'Donated donors',
          not_contacted: 'Not contacted donors',
          volunteers: 'Volunteers',
          messages: 'Messages',
        }[b.dataset.tab] + (b.dataset.tab === 'messages' ? '' : ' (' + counts[b.dataset.tab] + ')'),
      );
    }
  }
  function paintTab(b, label, count) {
    if (b.dataset.tab === 'messages') {
      b.textContent = label;
      return;
    }
    let name = b.querySelector('.tab-name'),
      n = b.querySelector('.tab-count');
    if (!name) {
      b.textContent = '';
      name = make('span', 'tab-name');
      n = make('span', 'tab-count');
      b.append(name, n);
    }
    name.textContent = '';
    if (label.startsWith('★ ')) {
      name.append('★ ', make('span', 'tab-word', label.slice(2)));
    } else name.textContent = label;
    n.textContent = count == null ? '' : count;
  }
  function paintRow(d) {
    const row = [...el('donorRows').children].find((n) => n.dataset.donorId === d.id);
    if (!row) return;
    row.dataset.important = !!d.important;
    row.dataset.donated = !!d.donated;
    row.dataset.sent = !!d.dm_sent;
    row.dataset.count = d.sent_count || 0;
    const star = row.querySelector('.donor-star');
    star.textContent = d.important ? '★' : '☆';
    star.setAttribute('aria-pressed', !!d.important);
    star.setAttribute(
      'aria-label',
      (d.important ? 'Remove Important from ' : 'Make Important: ') + d.name,
    );
    row.querySelector('.donor-name').textContent = d.name;
    {
      const ident = row.querySelector('.donor-identity');
      let tag = ident?.querySelector('.donor-normal-tag');
      if (d.normal_amount > 0) {
        if (!tag && ident) {
          tag = document.createElement('small');
          tag.className = 'donor-normal-tag';
          ident.append(tag);
        }
        if (tag) tag.textContent = 'Usually Rs. ' + Number(d.normal_amount).toLocaleString('en-PK');
      } else tag?.remove();
      const ni = row.querySelector('.donor-normal');
      if (ni && document.activeElement !== ni) ni.value = d.normal_amount || '';
    }
    const status = row.querySelector('.donor-status');
    status.textContent = d.donated ? 'Donated ✓' : 'Not donated';
    status.setAttribute('aria-pressed', !!d.donated);
    status.setAttribute('aria-label', 'Mark ' + d.name + (d.donated ? ' Not donated' : ' Donated'));
    const amount = row.querySelector('.donor-amount');
    if (document.activeElement !== amount) amount.value = d.amount || '';
    paintDelivery(row, d.delivery || 'Not contacted');
  }
  /* Top donors: highest known total first, then more records, then the saved manual order. */
  function topCmp(a, b) {
    return (
      (b.known_total || 0) - (a.known_total || 0) ||
      (b.activity || 0) - (a.activity || 0) ||
      (a.top_order ?? Number.MAX_SAFE_INTEGER) - (b.top_order ?? Number.MAX_SAFE_INTEGER) ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
    );
  }
  /* Sort = the server's sending order: Important first, not-yet-sent before sent, sent sink in the order sent; the top row is always next. */
  function applyFilters() {
    page.dataset.panel = tab;
    el('donorMessagesTab').tabIndex = 0;
    const epoch = ++filterEpoch;
    updateCounts();
    el('donorTable').hidden = tab === 'messages' || tab === 'volunteers';
    if (el('donorFollowUpOpt')) el('donorFollowUpOpt').hidden = tab === 'messages' || tab === 'volunteers';
    el('donorMessages').hidden = tab !== 'messages';
    el('donorVolunteers').hidden = tab !== 'volunteers';
    if (tab === 'volunteers') {
      showVolunteers();
      return;
    }
    if (tab === 'messages') {
      showMessages();
      return;
    }
    for (const [flag, field, rank] of [
      ['important', 'important_order', 'important_rank'],
      ['top_donor', 'top_order', 'top_rank'],
    ])
      allDonors
        .filter((d) => d[flag])
        .sort(
          field === 'top_order'
            ? topCmp
            : (a, b) => (a[field] ?? Number.MAX_SAFE_INTEGER) - (b[field] ?? Number.MAX_SAFE_INTEGER),
        )
        .forEach((d, i) => (d[rank] = i + 1));
    el('donorSendImportant').textContent = tab === 'top' ? 'DM Top donors' : 'DM ★ Important';
    el('donorSendImportant').dataset.short = tab === 'top' ? 'DM Top donors' : 'DM ★ Important';
    const q = el('donorSearch').value.trim().toLocaleLowerCase();
    data.items = allDonors
      .filter(
        (d) =>
          (tab === 'all' ||
            (tab === 'important' && d.important) ||
            (tab === 'top' && d.top_donor) ||
            (tab === 'donated' && d.donated) ||
            (tab === 'not_contacted' && !d.donated && !d.dm_sent)) &&
          !(tab === 'important' && hideSent && d.dm_sent && !q) &&
          (!q ||
            d.name.toLocaleLowerCase().includes(q) ||
            (d.notes || '').toLocaleLowerCase().includes(q)),
      )
      .sort(
        (a, b) =>
          (tab === 'top' ? topCmp(a, b) : 0) ||
          Number(b.important) - Number(a.important) ||
          // Top is an owner-controlled priority, not a receipt requirement.
          (tab === 'all' ? Number(!!b.top_donor) - Number(!!a.top_donor) : 0) ||
          (tab === 'all' && a.top_donor && b.top_donor
            ? (a.top_order ?? Number.MAX_SAFE_INTEGER) - (b.top_order ?? Number.MAX_SAFE_INTEGER)
            : 0) ||
          Number(!!a.dm_sent) - Number(!!b.dm_sent) ||
          (a.dm_sent ? (a.last_sent_at || 0) - (b.last_sent_at || 0) : 0) ||
          (a.important_order ?? Number.MAX_SAFE_INTEGER) - (b.important_order ?? Number.MAX_SAFE_INTEGER) ||
          0 ||
          Number(!!a.dm_sent) - Number(!!b.dm_sent) ||
          (a.dm_sent ? (a.last_sent_at || 0) - (b.last_sent_at || 0) : 0) ||
          a.name.localeCompare(b.name),
      );
    draw();
    paintHideRow();
    if (q && /^[+\d ()-]+$/.test(q) && q.replace(/\D/g, '').length >= 4)
      api('/donors?tab=' + tab + '&q=' + encodeURIComponent(q))
        .then((r) => {
          if (filterEpoch !== epoch) return;
          data.items = r.items.map((d) => allDonors.find((x) => x.id === d.id) || d);
          draw();
        })
        .catch((e) => notice(e.message, true));
  }
  let hideSent = (() => {
    try {
      return localStorage.getItem('givelife-hide-contacted') !== '0';
    } catch (e) {
      return true;
    }
  })();
  function paintHideRow() {
    const box = el('donorHideRow');
    if (!box) return;
    const n = allDonors.filter((d) => d.important && d.dm_sent).length;
    const starred = allDonors.filter((d) => d.important).length;
    box.hidden = tab !== 'important' || !starred;
    if (box.hidden) return;
    el('donorHideSent').hidden = !n;
    el('donorHideSent').textContent = hideSent
      ? n + ' contacted hidden · Show'
      : 'Showing contacted · Hide';
    el('donorHideSent').setAttribute('aria-pressed', String(!hideSent));
    el('donorDeselectAll').textContent = 'Deselect all ' + starred;
  }
  const picker = make('dialog', 'donor-form-dialog batch-dialog');
  picker.setAttribute('aria-label', 'Donor batch settings');
  picker.innerHTML = `<h2>Send DMs</h2><form id="donorBatchForm">
<div id="batchResume" hidden>
  <p id="batchResumeText" class="batch-hint"></p>
  <label class="batch-fresh"><input type="checkbox" id="batchFresh"> Start from the beginning</label>
</div>
<div class="bm-grid2">
  <div class="bm-row"><label for="batchCount">People</label>
  <input id="batchCount" name="count" type="number" min="1" max="1000" inputmode="numeric" required></div>
  <div class="bm-row"><label for="batchLimit">Per batch</label>
  <select id="batchLimit" name="batch_size"><option value="5">5</option><option value="10">10</option><option value="15">15</option><option value="20" selected>20</option></select></div>
<div class="bm-row"><label for="batchPause">Rest</label>
<select id="batchPause" name="pause"><option value="20">20 min</option><option value="30">30 min</option><option value="60">1 hour</option><option value="custom">Custom…</option><option value="each">Different each…</option></select></div>
</div>
<p id="batchAudience" class="batch-hint"></p>
<div class="bm-row bm-gap"><label id="batchGapLabel">Wait between DMs</label>
<div class="batch-gap-row" role="group" aria-labelledby="batchGapLabel">
  <button type="button" class="batch-gap-btn" data-gap="2">2 min</button>
  <button type="button" class="batch-gap-btn" data-gap="4">4 min</button>
  <button type="button" class="batch-gap-btn" data-gap="6">6 min</button>
  <button type="button" class="batch-gap-btn" data-gap="8">8 min</button>
  <button type="button" class="batch-gap-btn" data-gap="custom">Custom</button>
</div></div>
<div id="batchGapCustom" class="bm-custom" hidden>
  <input id="batchGap" name="gap_value" type="number" min="1" max="600" inputmode="numeric" value="4" aria-label="Custom gap">
  <select id="batchGapUnit" name="gap_unit" aria-label="Gap unit"><option value="60">minutes</option><option value="1">seconds</option></select>
</div>
<small id="batchGapNote" class="batch-hint" hidden>Under 1 minute can get a number restricted by WhatsApp.</small>

<input id="batchPauseCustom" type="number" min="1" max="1440" inputmode="numeric" placeholder="Minutes" aria-label="Custom minutes between batches" hidden>
<div id="batchEachRow" class="bm-row" hidden><label for="batchEach">Rest after each batch (minutes, e.g. 20, 30, 60)</label>
<input id="batchEach" name="each" type="text" inputmode="text" placeholder="20, 30, 60" autocomplete="off"></div>
<div id="batchRandomRow" class="bm-jit" hidden>
  <div><label for="batchJMin">Shorter by up to (s)</label><input id="batchJMin" type="number" min="0" max="300" inputmode="numeric" value="10"></div>
  <div><label for="batchJMax">Longer by up to (s)</label><input id="batchJMax" type="number" min="0" max="600" inputmode="numeric" value="15"></div>
</div>
<div class="bm-chips" id="batchChips">
  <label class="bm-chip"><input type="checkbox" id="batchPoster" checked><span>Poster</span></label>
  <label class="bm-chip"><input type="checkbox" id="batchFollowUp"><span>Follow-up</span></label>
  <label class="bm-chip"><input type="checkbox" id="batchIncl"><span>Include contacted</span></label>
  <label class="bm-chip"><input type="checkbox" id="batchRandom"><span>Vary gap</span></label>
</div>
<div class="batch-foot">
  <p id="batchPlan" class="batch-plan" role="status" aria-live="polite"></p>
  <div class="donor-form-actions">
    <button type="button" id="batchCancel">Cancel</button>
    <button type="submit" class="primary" id="batchStart">Start sending</button>
  </div>
</div>
</form>`;
  picker.id = 'donorBatchPicker';
  document.body.append(picker);
  let editingJob = null;
  let batchBody = {},
    lastJob = null,
    seenSent = null;
  function batchAvailable() {
    const scope = pickerScope,
      incl = el('batchIncl').checked;
    return allDonors.filter(
      (d) =>
        (scope === 'important' ? d.important : scope === 'top' ? d.top_donor : true) &&
        (incl || !d.dm_sent),
    ).length;
  }
  function batchPauses() {
    const each = (el('batchPause').value === 'each' ? el('batchEach').value : '')
      .split(/[,\s]+/)
      .filter(Boolean)
      .map(Number);
    if (each.length) {
      if (each.some((n) => !Number.isFinite(n) || n < 1 || n > 1440)) return null;
      return each.map((n) => n * 60);
    }
    const v = el('batchPause').value;
    const m = v === 'custom' ? Number(el('batchPauseCustom').value) : Number(v);
    if (!Number.isFinite(m) || m < 1 || m > 1440) return null;
    return [m * 60];
  }
  function paintAudience() {
    const scope = pickerScope;
    el('batchPauseCustom').hidden = el('batchPause').value !== 'custom';
    el('batchEachRow').hidden = el('batchPause').value !== 'each';
    el('batchRandomRow').hidden = !el('batchRandom').checked;
    const free = batchAvailable();
    const hidden = allDonors.filter(
      (d) =>
        (scope === 'important' ? d.important : scope === 'top' ? d.top_donor : true) && d.dm_sent,
    ).length;
    el('batchAudience').textContent = !scope
      ? ''
      : free +
        ' not contacted yet' +
        (!el('batchIncl').checked && hidden
          ? ' · ' + hidden + ' already contacted are left out'
          : '');
    const empty = !!scope && free === 0 && !editingJob;
    el('batchStart').disabled = empty;
    const count = Number(el('batchCount').value) || 0,
      per = Math.max(1, Math.min(20, Number(el('batchLimit').value) || 20)),
      gap = gapSecs() / 60 || 4,
      pauses = batchPauses();
    const plan = el('batchPlan');
    if (!scope) {
      plan.textContent = '';
      return;
    }
    if (!count || !pauses) {
      plan.textContent = empty
        ? 'Everyone here was already contacted. Tick “Include already-contacted people” in More options to send again.'
        : !pauses
          ? 'Check the pause between batches.'
          : '';
      return;
    }
    const batches = Math.ceil(count / per);
    let secs = (count - 1) * gap * 60;
    for (let i = 0; i < batches - 1; i++) secs += pauses[Math.min(i, pauses.length - 1)];
    /* No long summary line in the modal: it lives in Start's tooltip. Only warnings show as text. */
    plan.textContent = '';
    el('batchStart').title =
      'Send to ' +
      count +
      (count === 1 ? ' person' : ' people') +
      '. Wait ' +
      gapText(gapSecs()) +
      ' between each. Poster ' +
      (el('batchPoster').checked ? 'on' : 'off') +
      '. Done by about ' +
      clock(new Date(Date.now() + secs * 1000)) +
      (batches > 1 ? ' (' + batches + ' batches, with rests)' : '') +
      '. Runs even if the app is closed.';
  }
  let pickerEpoch = 0;
  /* Gap = number + unit (minutes or seconds). Stored as seconds everywhere else. */
  const gapSecs = () => Number(el('batchGap').value) * Number(el('batchGapUnit').value);
  const gapText = (s) => (s < 60 ? Math.round(s) + ' sec' : s / 60 + ' min');
  function setGap(s) {
    const whole = s % 60 === 0;
    el('batchGapUnit').value = whole ? '60' : '1';
    el('batchGap').value = whole ? s / 60 : s;
    highlightGapBtn();
  }
  async function openBatchPicker(scope) {
    editingJob = null;
    el('batchIncl').disabled=false;el('batchFresh').disabled=false;
    const epoch = ++pickerEpoch,
      path = Nav.path();
    pickerScope = scope;
    el('batchFresh').checked = false;
    el('batchResume').hidden = true;
    try {
      lastJob = await api('/donor-delivery');
    } catch (e) {
      lastJob = null;
    }
    if (epoch !== pickerEpoch || path !== Nav.path() || !page.open) return;
    const left = scope && lastJob && lastJob.scope === scope ? lastJob.resumable || 0 : 0;
    el('batchResume').hidden = !left;
    if (left)
      el('batchResumeText').textContent =
        'Your last batch stopped. ' +
        left +
        ' people are still waiting; the ones already sent will be skipped.';
    customGap = false;
    el('batchFollowUp').checked = followUpOn;
    el('batchPoster').checked = el('donorRowPoster') ? el('donorRowPoster').checked : true;
    setGap(Math.max(5, Math.min(600, Number(el('donorGap').value) || 240)));
    el('batchIncl').checked = false;
    el('batchCount').value = scope ? Math.min(1000, batchAvailable()) || '' : '';
    el('batchCount').disabled = !scope;
    paintAudience();
    highlightGapBtn();
    el('batchStart').textContent = scope ? (left ? 'Continue' : 'Start sending') : 'Save gap';
    picker.showModal();
    el('batchStart').focus({ preventScroll: true });
  }
  el('donorPace').onclick = () => openBatchPicker(null);
  el('batchLimit').oninput = paintAudience;
  el('batchLimit').onchange = paintAudience;
  el('batchCancel').onclick = () => picker.close();
  let customGap = false;
  function highlightGapBtn() {
    const v = String(el('batchGap').value),
      min = el('batchGapUnit').value === '60',
      preset = min && ['2', '4', '6', '8'].includes(v),
      custom = customGap || !preset;
    for (const b of picker.querySelectorAll('.batch-gap-btn'))
      b.setAttribute(
        'aria-pressed',
        String(b.dataset.gap === 'custom' ? custom : !custom && b.dataset.gap === v),
      );
    el('batchGapCustom').hidden = !custom;
    el('batchGapNote').hidden = !(gapSecs() > 0 && gapSecs() < 60);
  }
  for (const b of picker.querySelectorAll('.batch-gap-btn'))
    b.onclick = () => {
      if (b.dataset.gap === 'custom') {
        customGap = true;
        highlightGapBtn();
        el('batchGap').focus();
        el('batchGap').select();
      } else {
        customGap = false;
        el('batchGapUnit').value = '60';
        el('batchGap').value = b.dataset.gap;
        highlightGapBtn();
      }
      paintAudience();
    };
  for (const id of [
    'batchCount',
    'batchGap',
    'batchLimit',
    'batchEach',
    'batchPauseCustom',
    'batchJMin',
    'batchJMax',
  ])
    el(id).oninput =
      id === 'batchGap'
        ? () => {
            highlightGapBtn();
            paintAudience();
          }
        : paintAudience;
  el('batchGapUnit').onchange = () => {
    highlightGapBtn();
    paintAudience();
  };
  el('batchFollowUp').onchange = () => setFollowUp(el('batchFollowUp').checked);
  el('batchPoster').onchange = () => {
    /* One poster choice for the app: the switch here also sets the single-tap DM poster. */
    if (!editingJob && el('donorRowPoster') && el('donorRowPoster').checked !== el('batchPoster').checked) {
      el('donorRowPoster').checked = el('batchPoster').checked;
      el('donorRowPoster').dispatchEvent(new Event('change'));
    }
    paintAudience();
  };
  for (const id of ['batchPause', 'batchRandom', 'batchIncl'])
    el(id).onchange = () => {
      if (id === 'batchIncl' && pickerScope)
        el('batchCount').value = Math.min(1000, batchAvailable()) || '';
      paintAudience();
    };
  el('donorHideSent').onclick = () => {
    hideSent = !hideSent;
    try {
      localStorage.setItem('givelife-hide-contacted', hideSent ? '1' : '0');
    } catch (e) {}
    applyFilters();
  };
  el('donorDeselectAll').onclick = async () => {
    const starred = allDonors.filter((d) => d.important).length;
    if (!starred || !confirm('Remove the star from all ' + starred + ' Important donors?')) return;
    el('donorDeselectAll').disabled = true;
    try {
      const r = await api('/donors', { action: 'clear_important' });
      await refresh(true);
      notice(r.reply);
    } catch (e) {
      notice(e.message, true);
    } finally {
      el('donorDeselectAll').disabled = false;
    }
  };
  el('donorBatchForm').onsubmit = async (e) => {
    e.preventDefault();
    const secs = gapSecs(),
      per = Number(el('batchLimit').value);
    if (!(secs >= 5 && secs <= 600)) {
      el('batchGap').focus();
      el('batchPlan').textContent = 'Choose a gap from 5 seconds to 10 minutes.';
      return;
    }
    el('donorGap').value = secs;
    el('donorPace').textContent = 'Gap: ' + gapText(secs) + ' ▾';
    if (!pickerScope) {
      picker.close();
      return;
    }
    const count = Number(el('batchCount').value),
      pauses = batchPauses();
    if (!(count >= 1 && count <= 1000) || !(per >= 1 && per <= 20) || !pauses) {
      paintAudience();
      return;
    }
    const body = {
      chunk: per,
      limit: count,
      rests: pauses,
      skip_contacted: !el('batchIncl').checked,
      poster: el('batchPoster').checked,
    };
    if (el('batchRandom').checked) {
      const lo = Number(el('batchJMin').value) || 0,
        hi = Number(el('batchJMax').value) || 0;
      body.jitter = { min: -Math.abs(lo), max: Math.abs(hi) };
    }
    if (editingJob) {
      const button=el('batchStart');button.disabled=true;
      try {
        const result=await api('/donor-delivery',{configure:editingJob,settings:{gap_seconds:secs,chunk:per,rests:pauses,poster:body.poster,jitter:body.jitter||null}});
        editingJob=null;picker.close();notice(result.reply);await poll();
      } catch(error) { el('batchPlan').textContent=error.message; }
      finally {button.disabled=false;}
      return;
    }
    batchBody = body;
    picker.close();
    send(pickerScope, undefined, per, el('batchFresh').checked);
  };
  let bankRegenerating = false,
    bankGenerationTimer = null;
  const bankSaves = new Set();
  /* One short status. The full reason (with the AI's detail) shows when the status is tapped. */
  function bankGenerationDetail() {
    const g = bankData?.generation;
    return g && g.state !== 'Generating' && g.state !== 'Ready' && g.error ? g.error : '';
  }
  function bankGenerationLabel() {
    const g = bankData?.generation;
    if (!g) return '';
    if (g.state === 'Generating') return `Generating · ${g.ready}/${g.target} saved`;
    if (g.state === 'Ready') return `${g.ready} ready`;
    if (!g.error) return '';
    const missing = Math.max(0, g.target - g.ready);
    return `${g.ready} ready · ${missing} need review ⓘ`;
  }
  function wireStatus(node) {
    const detail = bankGenerationDetail();
    node.title = detail;
    node.tabIndex = detail ? 0 : -1;
    node.onclick = () => {
      if (!detail) return;
      const open = node.dataset.open === '1';
      node.dataset.open = open ? '' : '1';
      node.textContent = open ? bankGenerationLabel() : detail;
    };
    node.onkeydown = (e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), node.onclick());
  }
  function queueBankGenerationPoll() {
    clearTimeout(bankGenerationTimer);
    if (!page.open || tab !== 'messages' || bankData?.generation?.state !== 'Generating') return;
    bankGenerationTimer = setTimeout(async () => {
      try {
        const fresh = await api('/donor-messages');
        if (!page.open || tab !== 'messages') return;
        const changed = JSON.stringify(fresh.generation) !== JSON.stringify(bankData?.generation);
        bankData = fresh;
        const editing = el('donorMessages').querySelector('textarea:not([hidden])');
        if (changed && !editing && !bankEdits.size) showMessages();
        else {
          const state = el('donorMessages').querySelector('.bank-generation-state');
          if (state) state.textContent = bankGenerationLabel();
          syncBankControls();
        }
      } catch (e) {
        const state = el('donorMessages').querySelector('.bank-generation-state');
        if (state)
          state.textContent = 'Connection interrupted. Saved versions are safe; checking again.';
      } finally {
        queueBankGenerationPoll();
      }
    }, 1500);
  }

  async function showMessages(force = false) {
    if (!bankData || force) {
      el('donorMessages').textContent = 'Loading saved message variants…';
      try {
        bankData = await api('/donor-messages');
      } catch (e) {
        el('donorMessages').textContent = e.message;
        return;
      }
    }
    if (tab !== 'messages') return;
    const box = el('donorMessages');
    box.textContent = '';
    const head = make('div', 'bank-heading');
    head.append(
      make('span', '', bankData.items.length + ' wording variants · same facts · editable'),
    );
    const regen = make('button', 'tool bank-regenerate', bankData.items.length > 1 ? 'Regenerate 20' : 'Generate 20 versions');
    regen.onclick = async () => {
      if (bankRegenerating || bankSaves.size) return;
      const master = bankData.items[0];
      if (!master) {
        notice('Save Message 1 before regenerating.', true);
        return;
      }
      if (
        [...bankEdits.keys()].some((id) => id !== master.id) &&
        !confirm('Unsaved edits to other versions will be replaced. Continue?')
      )
        return;
      bankRegenerating = true;
      syncBankControls();
      try {
        // Saving Message 1 first avoids generating from yesterday's hidden origin.
        if (bankEdits.has(master.id)) {
          const text = bankEdits.get(master.id);
          await api('/donor-messages', { id: master.id, text });
          master.text = text;
          bankEdits.delete(master.id);
          keepBankEdits();
        }
        bankData = await api('/donor-messages', { action: 'regenerate' });
        bankEdits.clear();
        keepBankEdits();
        showMessages();
        notice(
          'Generating in the background. Message 1 is preserved; accepted versions save automatically.',
        );
      } catch (e) {
        notice(e.message, true);
        showMessages();
      } finally {
        bankRegenerating = false;
        syncBankControls();
      }
    };
    box.append(head);
    {
      const fuWrap = make('div', 'bank-followup'),
        tabs = make('div', 'bank-subtabs'),
        fuPanel = make('div', 'bank-followup-panel'),
        fuText = make('textarea'),
        fuSave = make('button', 'tool', 'Save follow-up'),
        fuNote = make(
          'small',
          '',
          'Sent as a separate message after the poster DM, only when "Send with follow-up" is ticked. {name} becomes e.g. "Sohaib Bhai".',
        );
      tabs.setAttribute('role', 'tablist');
      tabs.setAttribute('aria-label', 'Message type');
      box.dataset.sub = msgSub;
      for (const [id, label] of [
        ['dm', 'DM messages'],
        ['follow', 'Follow-up'],
      ]) {
        const t = make('button', '', label);
        t.type = 'button';
        t.setAttribute('role', 'tab');
        t.dataset.sub = id;
        t.setAttribute('aria-selected', String(msgSub === id));
        t.onclick = () => {
          msgSub = id;
          box.dataset.sub = id;
          tabs.querySelectorAll('button').forEach((x) => x.setAttribute('aria-selected', String(x.dataset.sub === id)));
          if (id === 'follow') fuText.focus({ preventScroll: true });
        };
        tabs.append(t);
      }
      fuSave.type = 'button';
      fuText.name = 'follow_up_text';
      fuText.maxLength = 2000;
      fuText.rows = 4;
      fuText.placeholder = '{name}, please do consider helping.';
      fuText.value = bankData.follow_up || '';
      fuSave.onclick = async () => {
        fuSave.disabled = true;
        try {
          const r = await api('/donor-messages', { action: 'follow_up', text: fuText.value });
          bankData.follow_up = r.follow_up;
          notice(r.reply);
        } catch (e) {
          notice(e.message, true);
        } finally {
          fuSave.disabled = false;
        }
      };
      fuPanel.append(fuText, fuNote, fuSave);
      fuWrap.append(tabs, fuPanel);
      box.prepend(fuWrap);
    }
    const generationState = make('span', 'bank-generation-state', bankGenerationLabel());
    generationState.setAttribute('role', 'status');
    wireStatus(generationState);
    head.append(generationState);
    queueBankGenerationPoll();
    let selected;
    try {
      selected = sessionStorage.getItem('givelife-bank-selected');
    } catch (e) {}
    const savedIndex = bankData.items.findIndex((item) => item.id === selected);
    if (savedIndex >= 0) bankPage = Math.max(bankPage, savedIndex + 1);
    const items = bankData.items.slice(0, bankPage);
    if (!items.some((item) => item.id === selected)) selected = items[0]?.id;
    const currentIndex = bankData.items.findIndex((item) => item.id === selected);
    const mobileTitle = make(
      'strong',
      'bank-current',
      currentIndex < 0
        ? 'Messages'
        : 'Message ' + (currentIndex + 1) + ' of ' + bankData.items.length,
    );
    head.prepend(mobileTitle);
    const info = make('span', 'bank-top-info', 'Edit Message 1 to update all regenerated wordings');
    head.append(info);
    const grid = make('div', 'bank-workspace'),
      picker = make('nav', 'bank-picker'),
      actions = make('aside', 'bank-actions');
    picker.setAttribute('aria-label', 'Saved DM messages');
    actions.setAttribute('aria-label', 'Message actions');
    picker.append(make('h2', 'bank-picker-title', 'Saved DM versions'));
    for (const [i, item] of items.entries()) {
      const pick = make('button', '', 'Message ' + (i + 1));
      pick.type = 'button';
      pick.setAttribute('aria-pressed', String(item.id === selected));
      pick.dataset.bankId = item.id;
      pick.onclick = () => {
        try {
          sessionStorage.setItem('givelife-bank-selected', item.id);
        } catch (e) {}
        showMessages();
      };
      pick.onkeydown = (e) => {
        const buttons = [...picker.querySelectorAll('[data-bank-id]')],
          index = buttons.indexOf(pick);
        let next;
        if (e.key === 'ArrowDown' || e.key === 'ArrowRight') next = (index + 1) % buttons.length;
        else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft')
          next = (index + buttons.length - 1) % buttons.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = buttons.length - 1;
        if (next !== undefined) {
          e.preventDefault();
          buttons[next].click();
          [...box.querySelectorAll('[data-bank-id]')]
            .find((b) => b.dataset.bankId === buttons[next].dataset.bankId)
            ?.focus({ preventScroll: true });
        }
      };
      picker.append(pick);
    }
    if (bankPage < bankData.items.length) {
      const more = make('button', 'tool', 'Show 10 more');
      more.onclick = () => {
        bankPage += 10;
        showMessages();
      };
      picker.append(more);
    }
    const index = items.findIndex((item) => item.id === selected),
      item = items[index];
    if (item) {
      const card = make('article', 'bank-message bank-detail'),
        title = make('header', '');
      card.dataset.bankDetail = item.id;
      title.append(make('strong', '', 'Message ' + (index + 1)));
      const preview = make('div', 'bank-preview');
      paintBankPreview(preview, item.text);
      const edit = make('textarea', '');
      edit.value = bankEdits.get(item.id) ?? item.text;
      edit.hidden = !bankEdits.has(item.id);
      preview.hidden = !edit.hidden;
      edit.oninput = () => {
        bankEdits.set(item.id, edit.value);
        keepBankEdits();
      };
      edit.setAttribute('aria-label', 'Edit message ' + (index + 1));
      edit.name = 'message_' + item.id;
      const button = make('button', 'tool', edit.hidden ? 'Edit' : 'Save');
      button.type = 'button';
      button.dataset.bankSaveId = item.id;
      button.onclick = async () => {
        if (bankRegenerating || bankSaves.has(item.id)) return;
        if (edit.hidden) {
          /* The editor looks exactly like the message it replaces: same font, size and spacing. */
          const look = getComputedStyle(preview);
          for (const prop of ['font-family', 'font-size', 'line-height', 'letter-spacing', 'padding'])
            edit.style.setProperty(prop, look.getPropertyValue(prop), 'important');
          edit.hidden = false;
          preview.hidden = true;
          button.textContent = 'Save';
          edit.focus({ preventScroll: true });
        } else {
          const submitted = edit.value;
          bankSaves.add(item.id);
          syncBankControls();
          try {
            await api('/donor-messages', { id: item.id, text: submitted });
            item.text = submitted;
            const latest = bankEdits.get(item.id) ?? edit.value;
            if (latest === submitted) bankEdits.delete(item.id);
            keepBankEdits();
            const active = [...box.querySelectorAll('[data-bank-detail]')].find(
              (node) => node.dataset.bankDetail === item.id,
            );
            if (active && !bankEdits.has(item.id)) {
              active.querySelector('textarea').hidden = true;
              const shown = active.querySelector('.bank-preview');
              shown.hidden = false;
              paintBankPreview(shown, submitted);
            }
            notice(
              bankEdits.has(item.id)
                ? 'Saved. Your newer edits are still unsaved.'
                : 'Message saved.',
            );
          } catch (e) {
            notice(e.message, true);
          } finally {
            bankSaves.delete(item.id);
            syncBankControls();
            fitBankPreview();
          }
        }
      };
      actions.append(button);
      for (const [mark, label] of [['*', 'B'], ['_', 'I']]) {
        const f = make('button', 'tool bank-format', label);
        f.type = 'button';
        f.setAttribute('aria-label', mark === '*' ? 'Bold' : 'Italic');
        f.onmousedown = (e) => e.preventDefault();
        f.onclick = () => {
          if (edit.hidden) button.click();
          wrapMark(edit, mark);
          bankEdits.set(item.id, edit.value);
          keepBankEdits();
        };
        actions.append(f);
      }
      const copy = make('button', 'tool bank-copy', 'Copy');
      copy.type = 'button';
      copy.onclick = async () => {
        try {
          await navigator.clipboard.writeText(bankEdits.get(item.id) ?? item.text);
          notice('Message copied.');
        } catch (e) {
          notice('Select the text and copy it.', true);
        }
      };
      actions.append(copy);
      card.append(title, preview, edit);
      grid.append(card);
    }
    if (!item)
      grid.append(
        make('p', 'donor-empty', 'No saved messages yet. Use Regenerate to create them.'),
      );
    const nav = make('nav', 'bank-pagination');
    nav.setAttribute('aria-label', 'Message navigation');
    const backBottom = make('button', 'bank-back-bottom back-action', '← Back');
    backBottom.type = 'button';
    backBottom.setAttribute('aria-label', 'Back to donors');
    backBottom.onclick = () => selectDonorTab('all');
    const position = bankData.items.findIndex((entry) => entry.id === selected);
    for (const [step, label] of [
      [-1, 'Previous'],
      [1, 'Next'],
    ]) {
      const b = make('button', step === 1 ? 'primary' : '', label);
      b.type = 'button';
      b.dataset.bankNav = step === 1 ? 'next' : 'previous';
      b.setAttribute('aria-label', step === 1 ? 'Next message' : 'Previous message');
      b.disabled = position < 0 || position + step < 0 || position + step >= bankData.items.length;
      b.onclick = () => {
        const target = position + step;
        bankPage = Math.max(bankPage, target + 1);
        try {
          sessionStorage.setItem('givelife-bank-selected', bankData.items[target].id);
        } catch (e) {}
        showMessages();
        [...box.querySelectorAll('[data-bank-nav]')]
          .find((node) => node.dataset.bankNav === b.dataset.bankNav)
          ?.focus({ preventScroll: true });
      };
      if (step === 1) {
        const count = make(
          'span',
          '',
          position < 0 ? '0 / 0' : position + 1 + ' / ' + bankData.items.length,
        );
        count.setAttribute('aria-live', 'polite');
        nav.append(count);
      }
      nav.append(b);
    }
    const baseBtn = make('button', 'tool bank-base', 'Base message');
    baseBtn.type = 'button';
    baseBtn.onclick = openBaseMessage;
    const testBtn = make('button', 'tool bank-test', 'Test');
    testBtn.type = 'button';
    testBtn.onclick = async () => {
      testBtn.disabled = true;
      try {
        const r = await api('/donor-messages', { action: 'test', poster: singlePosterOn });
        notice(r.reply);
      } catch (e) {
        notice(e.message, true);
      } finally {
        testBtn.disabled = false;
      }
    };
    // Keep Generate 20 in the visible action area on phones as well as desktop.
    // Progress is derived from the saved backend generation, never a fake timer.
    const regenProgress = make('span', 'bank-regenerate-progress', bankGenerationLabel());
    regenProgress.setAttribute('role', 'status');
    nav.insertBefore(backBottom, nav.firstChild);
    actions.append(baseBtn, testBtn, regen, regenProgress, nav);
    grid.append(actions, picker);
    {
      const cardEl = grid.querySelector('.bank-detail');
      if (cardEl) {
        const arrow = make('button', 'bank-next-arrow', '›');
        arrow.type = 'button';
        arrow.title = 'Next message';
        arrow.setAttribute('aria-label', 'Next message');
        arrow.onclick = () => box.querySelector('[data-bank-nav=next]')?.click();
        const gen = make('button', 'bank-gen-icon', '↻');
        gen.type = 'button';
        gen.title = 'Regenerate versions';
        gen.setAttribute('aria-label', 'Regenerate versions');
        gen.onclick = () => box.querySelector('.bank-regenerate')?.click();
        cardEl.append(arrow, gen);
      }
    }
    box.append(grid);
    syncBankControls();
    if (typeof ResizeObserver !== 'undefined') {
      bankFitObserver?.disconnect();
      bankFitObserver = new ResizeObserver(() => fitBankPreview());
      bankFitObserver.observe(grid);
      const fitTarget = grid.querySelector('.bank-detail');
      if (fitTarget) bankFitObserver.observe(fitTarget);
    }
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => fitBankPreview());
  }
  function syncBankControls() {
    const box = el('donorMessages');
    for (const b of box.querySelectorAll('.bank-regenerate')) {
      const generating = bankData?.generation?.state === 'Generating';
      b.disabled = bankRegenerating || bankSaves.size > 0 || generating;
      b.textContent = generating
        ? 'Generating 20…'
        : (bankData?.items?.length || 0) > 1
          ? 'Regenerate 20 versions'
          : 'Generate 20 versions';
    }
    const progress = box.querySelector('.bank-regenerate-progress');
    if (progress) progress.textContent = bankGenerationLabel();
    for (const b of box.querySelectorAll('[data-bank-save-id]')) {
      b.disabled = bankRegenerating || bankSaves.has(b.dataset.bankSaveId);
      const input = box.querySelector('.bank-detail textarea');
      if (!input) continue;
      input.disabled = bankRegenerating;
      b.textContent = bankSaves.has(b.dataset.bankSaveId)
        ? 'Saving…'
        : input.hidden
          ? 'Edit'
          : 'Save';
    }
  }
  let bankFitObserver;
  function paintBankPreview(preview, text) {
    if (window.waFormat)
      preview.innerHTML = window
        .waFormat(text)
        .split('\n')
        .map(
          (line) =>
            '<div class="bank-line' + (line ? '' : ' blank') + '">' + (line || '<br>') + '</div>',
        )
        .join('');
    else preview.textContent = text;
  }
  function fitBankPreview(tries = 0) {
    const preview = el('donorMessages').querySelector('.bank-preview');
    if (!preview) return;
    preview.style.removeProperty('font-size');
    if (!preview.clientHeight) {
      if (typeof tries === 'number' && tries < 30 && typeof requestAnimationFrame === 'function')
        requestAnimationFrame(() => fitBankPreview(tries + 1));
      return;
    } /* Reading comfort: the type size stays steady; a long message scrolls inside its card instead of shrinking. */
  }
  document.fonts?.ready.then(() => fitBankPreview());
  async function api(path, body) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 60000);
    try {
      const r = await fetch(path, {
        ...(body === undefined
          ? {}
          : {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
            }),
        signal: controller.signal,
      });
      /* While the app is being updated the server answers with a web page, not data: say so plainly. */
      const d = await r.json().catch(() => {
        throw Error('The app is restarting after an update. Wait a minute, then tap again.');
      });
      if (!r.ok) throw Error(d.error || 'The request could not complete.');
      return d;
    } catch (e) {
      if (e.name === 'AbortError')
        throw Error(
          'Request timed out. The result is not confirmed. Check delivery or saved messages before retrying.',
        );
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }
  let dismissedJob = '';
  try {
    dismissedJob = sessionStorage.getItem('givelife-dismissed-batch') || '';
  } catch (e) {}
  function dismissBatch(key) {
    dismissedJob = key;
    try {
      sessionStorage.setItem('givelife-dismissed-batch', key);
    } catch (e) {}
    el('donorNotice').textContent = '';
    el('donorProgress').hidden = true;
    dmBadge.hidden = true;
    el('donorBatchList').hidden = true;
  }
  function notice(text, error = false, undo) {
    clearTimeout(noticeTimer);
    const n = el('donorNotice');
    n.textContent = '';
    n.dataset.error = error;
    const message = make('span', '', text);
    n.append(message);
    const close = make('button', 'donor-notice-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.onclick = () => {
      n.textContent = '';
    };
    n.append(close);
    if (undo) {
      const b = make('button', '', 'Undo');
      b.onclick = async () => {
        try {
          await api('/donors', { action: 'restore', id: undo });
          await refresh(true);
          notice('Donor restored.');
        } catch (e) {
          notice(e.message, true);
        }
      };
      n.append(b);
    } else if (!error)
      noticeTimer = setTimeout(() => {
        n.textContent = '';
      }, 4000);
  }
  function when(t) {
    if (!t) return 'Not contacted';
    const mins = Math.max(0, Math.floor((Date.now() / 1000 - t) / 60));
    return mins < 1
      ? 'Sent just now'
      : mins < 60
        ? `Sent ${mins}m ago`
        : mins < 1440
          ? `Sent ${Math.floor(mins / 60)}h ago`
          : `Sent ${Math.floor(mins / 1440)}d ago`;
  }
  async function change(id, fields) {
    const donor = allDonors.find((d) => d.id === id);
    if (!donor) return;
    if (fields.donated === false) {
      cancelAmount(id);
      fields = { ...fields, amount: 0 };
      const control = [...(el('donorRows')?.children || [])]
        .find((n) => n.dataset.donorId === id)
        ?.querySelector('.donor-amount');
      if (control) control.value = '';
    }
    const version = (rowVersions.get(id) || 0) + 1;
    rowVersions.set(id, version);
    Object.assign(donor, fields);
    paintRow(donor);
    updateCounts();
    const previous = rowQueues.get(id) || Promise.resolve();
    const pending = previous
      .catch(() => {})
      .then(() =>
        api('/donors', {
          action: 'update',
          id,
          expected_updated_at: confirmedRows.get(id)?.updated_at,
          ...fields,
        }),
      )
      .then((r) => {
        confirmedRows.set(id, { ...r.donor });
        if (rowVersions.get(id) === version) {
          Object.assign(donor, r.donor);
          paintRow(donor);
          updateCounts();
          if (('important' in fields || 'top_donor' in fields) && ['important', 'top'].includes(tab))
            applyFilters();
        }
      })
      .catch((e) => {
        if (rowVersions.get(id) === version && confirmedRows.has(id)) {
          Object.assign(donor, confirmedRows.get(id));
          paintRow(donor);
          updateCounts();
        }
        notice(e.message, true);
      })
      .finally(() => {
        if (rowQueues.get(id) === pending) rowQueues.delete(id);
      });
    rowQueues.set(id, pending);
    return pending;
  }
  function paintDelivery(row, state) {
    const sent = row.dataset.sent === 'true',
      count = Number(row.dataset.count) || (sent ? 1 : 0),
      pending = ['Requesting', 'Sending'].includes(state);
    /* A confirmed DM stays visible as "DM sent" whatever happens to a later attempt. */
    const confirmed = (sent && !pending) || state === 'Sent',
      check = !confirmed && ['Uncertain', 'Skipped'].includes(state);
    row.dataset.delivery = confirmed ? 'Sent' : state;
    if (confirmed) row.dataset.sent = 'true';
    const button = row.querySelector('.donor-dm');
    if (!button) return;
    const times = count > 1 ? ' ×' + count : '';
    button.textContent = pending
      ? '…'
      : confirmed
        ? 'DM sent' + times
        : check
          ? 'Check'
          : state === 'Not sent'
            ? 'Retry'
            : 'DM';
    button.setAttribute('data-mobile-label', confirmed ? 'Sent ✓' + times : button.textContent);
    button.disabled = pending;
    const later =
      sent && ['Uncertain', 'Not sent', 'Skipped'].includes(state)
        ? ' The latest attempt was not confirmed.'
        : '';
    button.title = pending
      ? 'Sending now; waiting for WhatsApp confirmation'
      : confirmed
        ? 'WhatsApp confirmed a DM' +
          (count > 1 ? ' (' + count + ' times)' : '') +
          '.' +
          later +
          ' Click to send again now.'
        : state === 'Skipped'
          ? 'Opted out or blocked. No message was sent.'
          : state === 'Uncertain'
            ? 'Delivery was uncertain. A new click explicitly sends again; no automatic retry.'
            : 'Send saved DM + poster now';
    button.setAttribute(
      'aria-label',
      (pending
        ? 'Sending DM to '
        : confirmed
          ? 'DM sent to '
          : check
            ? 'Check DM status for '
            : 'Send saved DM to ') +
        row.querySelector('.donor-name').textContent +
        (confirmed && !pending ? '. Tap to send again' : ''),
    );
  }
  function draw() {
    const normalTotal = allDonors.reduce((s, d) => s + (Number(d.normal_amount) || 0), 0);
    const nt = el('donorNormalTotal');
    if (nt) nt.textContent = 'PKR ' + normalTotal.toLocaleString('en-PK');
    el('donorTotal').textContent = data.counts.all ?? '';
    el('donorTotalAmount').textContent =
      'PKR ' + Number(data.counts.donated_amount || 0).toLocaleString('en-PK');
    const labels = {
      all: 'All',
      important: '★ Important',
      top: 'Top donors',
      donated: 'Donated',
      not_contacted: narrow560.matches ? 'Not DMed' : 'Not contacted',
      volunteers: narrow700.matches ? 'Helpers' : 'Volunteers',
    };
    for (const b of page.querySelectorAll('[data-tab]')) {
      if (b.dataset.tab === 'messages') {
        b.textContent = 'Messages';
        b.setAttribute('aria-label', 'Messages');
        b.setAttribute('aria-selected', tab === 'messages');
        continue;
      }
      paintTab(
        b,
        labels[b.dataset.tab],
        b.dataset.tab === 'volunteers' ? vols.items.length : data.counts[b.dataset.tab] || 0,
      );
      b.setAttribute(
        'aria-label',
        {
          all: 'All donors',
          important: 'Important donors',
          top: 'Top donors',
          donated: 'Donated donors',
          not_contacted: 'Not contacted donors',
          volunteers: 'Volunteers',
        }[b.dataset.tab] +
          ' (' +
          (b.dataset.tab === 'volunteers' ? vols.items.length : data.counts[b.dataset.tab] || 0) +
          ')',
      );
      b.setAttribute('aria-selected', b.dataset.tab === tab);
    }
    const rows = el('donorRows');
    rows.textContent = '';
    if (!data.items.length) {
      const empty = make('div', 'donor-empty');
      empty.append(
        make(
          'strong',
          '',
          el('donorSearch').value
            ? 'No matching donors'
            : tab === 'important'
              ? 'No Important donors yet'
              : 'No donors in this tab',
        ),
        make(
          'span',
          '',
          tab === 'important'
            ? 'Tap the star beside a donor in All.'
            : 'Add a donor, import contacts, or try another search.',
        ),
      );
      rows.append(empty);
      return;
    }
    const items = data.items,
      epoch = ++drawEpoch;
    let next = 0;
    /* First screenful at once, the rest in the following frames: a tab click answers immediately even with hundreds of donors. */ const paintChunk =
      () => {
        if (epoch !== drawEpoch) return;
        for (const end = Math.min(next + DRAW_CHUNK, items.length); next < end; next++) {
          const d = items[next];
          const row = make('article', 'donor-row');
          row.dataset.donorId = d.id;
          row.dataset.important = !!d.important;
          row.dataset.donated = !!d.donated;
          row.dataset.sent = !!d.dm_sent;
          row.dataset.count = d.sent_count || 0;
          const star = make('button', 'donor-star', d.important ? '★' : '☆');
          star.type = 'button';
          star.setAttribute('aria-pressed', !!d.important);
          star.setAttribute(
            'aria-label',
            (d.important ? 'Remove Important from ' : 'Make Important: ') + d.name,
          );
          star.onclick = () => change(d.id, { important: !d.important });
          const ident = make('div', 'donor-identity');
          ident.onclick = () => star.click();
          ident.append(make('div', 'donor-name', d.name));
          ident.firstChild.dataset.rank =
            tab === 'top' ? d.top_rank || '' : tab === 'important' ? d.important_rank || '' : '';
          {
            const best = make('button', 'donor-top-chip', d.top_donor ? 'Top ✓' : '+ Top');
            best.type = 'button';
            best.setAttribute('aria-pressed', !!d.top_donor);
            best.setAttribute(
              'aria-label',
              (d.top_donor ? 'Remove from Top donors: ' : 'Add to Top donors: ') + d.name,
            );
            best.onclick = async (e) => {
              e.stopPropagation();
              if (d.top_donor) return change(d.id, { top_donor: false });
              if (!d.important) await change(d.id, { important: true });
              await change(d.id, { top_donor: true });
            };
            ident.append(best);
          }
          if (d.normal_amount > 0)
            ident.append(
              make(
                'small',
                'donor-normal-tag',
                'Usually Rs. ' + Number(d.normal_amount).toLocaleString('en-PK'),
              ),
            );
          if (tab === 'top')
            ident.append(
              make(
                'small',
                'donor-known',
                d.known_total
                  ? 'Rs. ' +
                      Number(d.known_total).toLocaleString('en-PK') +
                      (d.activity > 1 ? ' · ' + d.activity + ' records' : '')
                  : 'Unverified',
              ),
            );
          if (d.follow_up_state) {
            row.dataset.fu = d.follow_up_state;
            ident.append(make('small', 'donor-fu', 'Follow-up: ' + d.follow_up_state.toLowerCase()));
          }
          ident.title = d.name + ' · ' + when(d.last_sent_at);
          const status = make('button', 'donor-status', d.donated ? 'Donated ✓' : 'Not donated');
          status.type = 'button';
          status.setAttribute('aria-pressed', !!d.donated);
          status.setAttribute(
            'aria-label',
            'Mark ' + d.name + (d.donated ? ' Not donated' : ' Donated'),
          );
          status.onclick = () => {
            cancelAmount(d.id);
            change(d.id, { donated: !d.donated });
          };
          const amount = make('input', 'donor-amount');
          amount.type = 'number';
          amount.name = 'donated_amount';
          amount.autocomplete = 'off';
          amount.inputMode = 'numeric';
          amount.min = '0';
          amount.max = '100000000';
          amount.step = '1';
          amount.value = d.amount || '';
          amount.placeholder = '—';
          amount.setAttribute('aria-label', 'Donated rupees for ' + d.name);
          const saveAmount = () => {
            cancelAmount(d.id);
            const current = allDonors.find((x) => x.id === d.id);
            if (current)
              change(d.id, {
                amount: Number(amount.value),
                donated: Number(amount.value) > 0 || current.donated,
              });
          };
          amount.onchange = saveAmount;
          amount.oninput = () => {
            cancelAmount(d.id);
            amountTimers.set(d.id, setTimeout(saveAmount, 400));
          };
          const dm = make('button', 'donor-dm', 'DM');
          dm.type = 'button';
          dm.setAttribute('aria-label', 'Send saved DM to ' + d.name);
          dm.onclick = () => send('selected', [d.id]);
          if (d.has_number === false) {
            dm.textContent = 'Add #';
            dm.title = 'Add a number to send DMs';
            dm.setAttribute('aria-label', 'Add a number for ' + d.name);
            dm.onclick = () => {
              more.open = true;
              setTimeout(() => more.querySelector('input[name=donor_phone]')?.focus(), 0);
            };
          }
          const more = make('details', 'donor-more');
          const summary = make('summary', '', '···');
          summary.setAttribute('aria-label', 'Manage ' + d.name);
          let menuBuilt = false;
          const buildMenu = () => {
            if (menuBuilt) return;
            menuBuilt = true;
            const menu = make('div', '');
            menu.setAttribute('role', 'group');
            menu.setAttribute('aria-label', 'Options for ' + d.name);
            const closeMenu = make('button', 'donor-menu-close', 'Close ×');
            closeMenu.type = 'button';
            closeMenu.setAttribute('aria-label', 'Close options for ' + d.name);
            closeMenu.onclick = () => {
              more.open = false;
              summary.focus({ preventScroll: true });
            };
            menu.append(closeMenu);
            const rename = make('div', 'donor-normal-box');
            const rlabel = make('label', '', 'Name');
            const rinput = make('input', 'donor-normal');
            rinput.type = 'text';
            rinput.name = 'donor_name';
            rinput.autocomplete = 'off';
            rinput.maxLength = 60;
            rinput.value = d.name;
            rlabel.append(rinput);
            const rsave = make('button', 'donor-normal-save', 'Save name');
            rsave.type = 'button';
            const saveName = () => {
              const n = rinput.value.trim();
              if (!n) {
                notice('Enter a name.', true);
                rinput.focus();
                return;
              }
              if (n !== d.name) change(d.id, { name: n });
              more.open = false;
            };
            rsave.onclick = saveName;
            rinput.onkeydown = (e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                saveName();
              }
            };
            rename.append(rlabel, rsave);
            // DM greeting is editable: a name is not proof of someone's gender.
            const dmProfile = make('div', 'donor-normal-box donor-dm-profile');
            const dmNameLabel = make('label', '', 'DM first name');
            const dmFirst = make('input', 'donor-normal');
            dmFirst.type = 'text';
            dmFirst.maxLength = 30;
            dmFirst.value = d.dm_name || '';
            dmFirst.placeholder = 'Name, or blank';
            dmNameLabel.append(dmFirst);
            const dmTitleLabel = make('label', '', 'DM greeting');
            const dmTitle = make('select', 'donor-normal');
            for (const [value, title] of [
              ['Brother', 'Bhai'],
              ['Sister', 'Sister'],
              ['Neutral', 'Name only'],
            ]) {
              const option = make('option', '', title);
              option.value = value;
              dmTitle.append(option);
            }
            dmTitle.value = d.dm_salutation || 'Brother';
            dmTitleLabel.append(dmTitle);
            const dmPreview = make('small', '', 'Suggested from contact name; please correct if needed.');
            const dmSave = make('button', 'donor-normal-save', 'Save DM greeting');
            dmSave.type = 'button';
            dmSave.onclick = () => {
              const first = dmFirst.value.trim();
              if (first && !/^[A-Za-z][A-Za-z'-]{1,24}$/.test(first)) {
                notice('Enter one simple first name, or leave it blank.', true);
                dmFirst.focus();
                return;
              }
              change(d.id, { dm_name: first, dm_salutation: dmTitle.value });
              more.open = false;
            };
            dmProfile.append(dmNameLabel, dmTitleLabel, dmPreview, dmSave);
            const normal = make('div', 'donor-normal-box');
            const nlabel = make('label', '', 'Usually donates (Rs.)');
            const ninput = make('input', 'donor-normal');
            ninput.type = 'number';
            ninput.name = 'normal_amount';
            ninput.autocomplete = 'off';
            ninput.inputMode = 'numeric';
            ninput.min = '0';
            ninput.max = '100000000';
            ninput.step = '1';
            ninput.value = d.normal_amount || '';
            ninput.placeholder = 'e.g. 500';
            nlabel.append(ninput);
            const nsave = make('button', 'donor-normal-save', 'Save');
            nsave.type = 'button';
            const saveNormal = () => {
              const raw = ninput.value.trim();
              const v = raw === '' ? 0 : Number(raw);
              if (!Number.isFinite(v) || v < 0 || v > 100000000) {
                notice('Enter a valid amount.', true);
                ninput.focus();
                return;
              }
              change(d.id, { normal_amount: v });
              notice(
                v
                  ? 'Saved. ' +
                      d.name +
                      ' now gets the line for Rs. ' +
                      v.toLocaleString('en-PK') +
                      '.'
                  : 'Cleared. ' + d.name + ' gets the shared message.',
              );
              more.open = false;
            };
            nsave.onclick = saveNormal;
            ninput.onkeydown = (e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                saveNormal();
              }
            };
            normal.append(nlabel, nsave);
            const del = make('button', 'remove', 'Delete donor');
            del.type = 'button';
            del.onclick = async () => {
              del.disabled = true;
              try {
                await api('/donors', { action: 'delete', id: d.id });
                await refresh(true);
                notice('Removed ' + d.name + '.', false, d.id);
              } catch (e) {
                notice(e.message, true);
              } finally {
                del.disabled = false;
              }
            };
            if (d.has_number === false) {
              const nbox = make('div', 'donor-normal-box');
              const nl = make('label', '', 'Add their number');
              const ni = make('input', 'donor-normal');
              ni.type = 'tel';
              ni.name = 'donor_phone';
              ni.autocomplete = 'off';
              ni.inputMode = 'tel';
              ni.placeholder = '03XX XXXXXXX';
              nl.append(ni);
              const ns = make('button', 'donor-normal-save', 'Save');
              ns.type = 'button';
              const saveNum = async () => {
                try {
                  await api('/donors', { action: 'update', id: d.id, phone: ni.value });
                  await refresh(true);
                  notice('Number saved for ' + d.name + '. You can send DMs now.');
                } catch (e) {
                  notice(e.message, true);
                  ni.focus();
                }
              };
              ns.onclick = saveNum;
              ni.onkeydown = (e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  saveNum();
                }
              };
              nbox.append(nl, ns);
              menu.append(nbox);
            }
            // The compact phone row keeps its amount editor under More.
            const donatedBox = make('label', 'donor-menu-amount', 'Donated amount (PKR)');
            const donatedInput = amount.cloneNode();
            donatedInput.className = 'donor-menu-amount-input';
            donatedInput.setAttribute('aria-label', 'Edit donated rupees for ' + d.name);
            donatedInput.onchange = () => {
              amount.value = donatedInput.value;
              saveAmount();
            };
            donatedBox.append(donatedInput);
            const topInMenu = make('button', 'donor-menu-top', d.top_donor ? 'Remove from Top donors' : 'Add to Top donors');
            topInMenu.type = 'button';
            topInMenu.onclick = () => ident.querySelector('.donor-top-chip').click();
            menu.append(rename, dmProfile, normal, donatedBox, topInMenu, del);
            more.append(menu);
          };
          more.ontoggle = () => {
            if (!more.open) return;
            // A phone-sized bottom sheet should never stack on another donor's sheet.
            for (const other of rows.querySelectorAll('.donor-more[open]'))
              if (other !== more) other.open = false;
            buildMenu();
            /* Desktop: the menu never runs off the bottom of the screen; it scrolls inside instead. */
            requestAnimationFrame(() => {
              const m = more.querySelector(':scope > div');
              if (!m || !more.open || innerWidth <= 560) return;
              m.style.maxHeight = '';
              const top = m.getBoundingClientRect().top;
              m.style.maxHeight = Math.max(200, innerHeight - Math.max(top, 8) - 8) + 'px';
              m.style.overflowY = 'auto';
            });
          };
          more.append(summary);
          row.append(star, ident, dm, status, amount, more);
          rows.append(row);
          paintDelivery(row, d.delivery || 'Not contacted');
        }
        if (next < items.length) requestAnimationFrame(paintChunk);
      };
    paintChunk();
  }
  async function refresh(force = false) {
    if (loadPromise) await loadPromise;
    if (!loaded || force) {
      loadPromise = (async () => {
        const fresh = await api('/donors?tab=all');
        const incoming = fresh.items || [];
        allDonors = incoming.map((r) => {
          confirmedRows.set(r.id, { ...r });
          const pending = rowQueues.has(r.id) && allDonors.find((d) => d.id === r.id);
          return pending || r;
        });
        loaded = true;
      })().finally(() => (loadPromise = null));
      try {
        await loadPromise;
      } catch (e) {
        notice(e.message, true);
        return;
      }
    }
    if (tab === 'messages' && bankData) {
      updateCounts();
      return;
    }
    applyFilters();
  }
  const TABS = ['all', 'important', 'top', 'donated', 'not_contacted', 'volunteers', 'messages'];
  function showSelectedTab() {
    page.dataset.panel = tab;
    el('donorMessagesTab').tabIndex = 0;
    for (const b of page.querySelectorAll('[data-tab]')) {
      b.setAttribute('aria-selected', String(tab === b.dataset.tab));
      // setAttribute (only on change), not .tabIndex: the property forces a synchronous style recalc per tab.
      const ti = b.dataset.tab === 'messages' || tab === b.dataset.tab ? '0' : '-1';
      if (b.getAttribute('tabindex') !== ti) b.setAttribute('tabindex', ti);
    }
    el('donorTable').hidden = tab === 'messages' || tab === 'volunteers';
    if (el('donorFollowUpOpt')) el('donorFollowUpOpt').hidden = tab === 'messages' || tab === 'volunteers';
    el('donorMessages').hidden = tab !== 'messages';
    el('donorVolunteers').hidden = tab !== 'volunteers';
    if (tab === 'messages' && !el('donorMessages').textContent)
      el('donorMessages').textContent = 'Loading saved message variants…';
  }
  async function open() {
    loadVolunteers();
    showSelectedTab();
    if (!page.open) page.showModal();
    Nav.go('donors/' + tab);
    el('donorMainBottom').focus({ preventScroll: true });
    if (loaded) applyFilters();
    await refresh(true);
    await poll();
  }
  function close() {
    page.close();
    Nav.leave('donors');
    clearTimeout(pollTimer);
    launch.focus({ preventScroll: true });
  }
  /* The address decides which tab shows, so a refresh or the Back button returns to the same place. */
  function show(name) {
    if (name === 'not_donated') name = 'not_contacted';
    const next = TABS.includes(name) ? name : 'all';
    if (next !== tab) {
      tab = next;
      try {
        sessionStorage.setItem('givelife-donor-tab', tab);
      } catch (e) {}
    }
    return page.open ? (applyFilters(), undefined) : open();
  }
  function hide() {
    clearTimeout(pollTimer);
    if (page.open) page.close();
  }
  page.addEventListener('close', () => {
    clearTimeout(pollTimer);
    Nav.leave('donors');
  });
  async function send(scope, ids, limit = 20, fresh = false) {
    if (sendPending) return;
    sendPending = true;
    document.activeElement?.blur();
    const selected = [...el('donorRows').children].filter((row) =>
      ids?.includes(row.dataset.donorId),
    );
    selected.forEach((row) => paintDelivery(row, 'Requesting'));
    page.querySelectorAll('.send-important,.send-donors').forEach((b) => (b.disabled = true));
    try {
      if (scope === 'selected') {
        const result = await api('/donor-send', {
          id: ids[0],
          request_id: requestId(),
          poster: singlePosterOn,
          ...(followUpOn ? { follow_up: true } : {}),
        });
        if (result.follow_up && result.follow_up !== 'Sent')
          notice('Follow-up ' + result.follow_up.toLowerCase() + '. Check WhatsApp before resending.', true);
        if (result.code === 'SUCCESS') {
          const mine = allDonors.find((x) => x.id === ids[0]);
          if (mine) {
            mine.dm_sent = true;
            mine.sent_count = (mine.sent_count || 0) + 1;
          }
        }
        await refresh(true);
        selected.forEach((row) =>
          paintDelivery(row, result.code === 'SUCCESS' ? 'Sent' : 'Uncertain'),
        );
        if (result.code !== 'SUCCESS') notice(result.reply, true);
        return;
      }
      const gap = Number(el('donorGap').value);
      if (!Number.isFinite(gap) || gap < 5 || gap > 600)
        throw Error('Choose a gap from 5 seconds to 10 minutes.');
      const r = await api('/donor-delivery', {
        scope,
        ids,
        ...(scope === 'selected' ? { limit } : batchBody),
        gap_seconds: gap,
        request_id: requestId(),
        poster: batchBody.poster !== false,
        ...(followUpOn ? { follow_up: true } : {}),
        ...(fresh ? { fresh: true } : {}),
      });
      if (scope !== 'selected') notice(r.reply);
      selected.forEach((row) => paintDelivery(row, 'Sending'));
      await poll();
    } catch (e) {
      if (scope === 'selected') await refresh();
      selected.forEach((row) =>
        paintDelivery(
          row,
          data.items.find((d) => d.id === row.dataset.donorId)?.delivery || 'Not sent',
        ),
      );
      notice(e.message, true);
    } finally {
      sendPending = false;
      page.querySelectorAll('.send-important,.send-donors').forEach((b) => (b.disabled = false));
    }
  }
  function paintBatchList(j) {
    const box = el('donorBatchList');
    const done = (j.receipts || []).filter((r) => r.state === 'Sent'),
      other = (j.receipts || []).filter((r) => r.state !== 'Sent'),
      next = j.waiting || [];
    box.hidden = j.state === 'Idle' || !(done.length || other.length || next.length);
    if (box.hidden) return;
    const fill = (id, items, fmt) => {
      const ol = el(id);
      ol.textContent = '';
      for (const x of items.slice(0, 100)) {
        const li = document.createElement('li');
        li.textContent = fmt(x);
        ol.append(li);
      }
      if (!items.length) {
        const li = document.createElement('li');
        li.className = 'none';
        li.textContent = 'Nobody yet';
        ol.append(li);
      }
    };
    fill('batchSent', done, (r) =>
      r.name +
      (r.time ? ' · ' + clock(new Date(r.time * 1000)) : '') +
      (r.follow_up ? ' · follow-up: ' + r.follow_up.toLowerCase() : ''),
    );
    fill('batchNext', next, (n) => n);
    const nb = j.next_batch_at
      ? ' · next batch ' +
        (j.batch || '') +
        (j.batches ? ' of ' + j.batches : '') +
        ' at ' +
        clock(new Date(j.next_batch_at * 1000)) +
        (j.next_batch_size ? ' (' + j.next_batch_size + ' people)' : '')
      : '';
    el('donorBatchSummary').textContent =
      '✓ ' +
      (j.sent ?? done.length) +
      ' sent · ' +
      (j.pending ?? next.length) +
      ' pending · ' +
      (j.failed || other.length) +
      ' failed' +
      nb;
    el('batchOther').textContent = other.length
      ? 'Not sent or not confirmed: ' +
        other
          .map((r) => r.name + ' (' + r.state.replace('Skipped: ', 'skipped, ').toLowerCase() + ')')
          .join('; ') +
        '. Check these in WhatsApp.'
      : '';
    el('batchOther').hidden = !other.length;
  }
  async function poll() {
    clearTimeout(pollTimer);
    if (!page.open) return;
    try {
      const j = await api('/donor-delivery');
      paintDMControl(j);
      const active = ['Starting', 'Sending', 'Waiting'].includes(j.state);
      el('donorProgress').hidden = j.state === 'Idle';
      el('donorProgress').dataset.active = active;
      el('donorProgress').dataset.error = !!j.error || j.state === 'Nothing sent';
      paintBatchList(j);
      el('donorStop').hidden = !active;
      lastJob = j;
      el('donorContinue').hidden =
        active ||
        !(j.resumable > 0 && ['all', 'important', 'top', 'donated', 'not_donated'].includes(j.scope));
      if (!el('donorContinue').hidden)
        el('donorContinue').textContent = 'Restart (' + j.resumable + ' left)';
      /* Whole-audience total from the donor list itself, so it stays right after an app restart. */
      const inScope = allDonors.filter((d) =>
          j.scope === 'top' ? d.top_donor : j.scope === 'important' ? d.important : j.scope === 'all' ? true : false,
        ),
        /* The count sits outside the list box, in the free space on the right; with no room it joins the green line. */
        shellBox = el('donorTable').getBoundingClientRect(),
        phone = innerWidth - shellBox.right < 190,
        overall =
          phone && inScope.length
            ? inScope.filter((d) => d.dm_sent).length + ' / ' + inScope.length + ' DMed · '
            : '';
      dmBadge.hidden = phone || !active || !inScope.length;
      dmBadge.style.left = Math.round(shellBox.right + 18) + 'px';
      if (!dmBadge.hidden) {
        dmBadge.textContent = '';
        dmBadge.append(
          make('strong', '', inScope.filter((d) => d.dm_sent).length + ' / ' + inScope.length),
          make('small', '', 'DMed'),
        );
      }
      /* The plan at a glance: batches, rest between batches, gap between messages. */
      {
        const facts = el('donorProgressFacts'),
          mins = (sec) => {
            const m = Math.round((Number(sec) || 0) / 60);
            return m >= 60 && m % 60 === 0 ? m / 60 + ' hr' : m + ' min';
          },
          rests = (j.rests && j.rests.length ? j.rests : j.rest_seconds ? [j.rest_seconds] : []).map(mins),
          items = [];
        /* After a restart the batch number can pass the planned count; never show "4 of 2". */
        if (j.batches) {
          const now = Number(j.batch) || 0,
            of = Math.max(Number(j.batches) || 0, now);
          items.push(['Batches', (now ? now + ' of ' : '') + of]);
        }
        if (j.chunk) items.push(['Per batch', j.chunk + ' people']);
        if (j.batches > 1 && rests.length) items.push(['Rest between batches', [...new Set(rests)].join(' / ')]);
        if (j.gap_seconds) items.push(['Gap between messages', j.gap_seconds < 60 ? gapText(j.gap_seconds) : mins(j.gap_seconds)]);
        facts.textContent = '';
        if (items.length) {
          const short = { Batches: 'batch', 'Per batch': 'per batch', 'Rest between batches': 'rest', 'Gap between messages': 'gap' };
          facts.append(
            make(
              'small',
              'dp-plan',
              items
                .map(([k, v]) => (k === 'Batches' ? 'Batch ' + v : k === 'Per batch' ? v.replace(' people', '') + ' per batch' : short[k] + ' ' + v))
                .join(' · '),
            ),
          );
        }
        facts.hidden = !items.length;
      }
      el('donorProgress').querySelector('span').textContent =
        `${j.state}: ${(j.previous_sent || 0) + (j.sent || 0)} of ${j.original_total || j.total || 0} sent` +
        ` · ${j.pending ?? Math.max(0, (j.total || 0) - (j.sent || 0) - (j.skipped || 0) - (j.failed || 0))} left` +
        (j.failed ? ` · ${j.failed} not confirmed` : '') +
        (j.skipped ? ' · ' + j.skipped + ' skipped' : '') +
        (j.current ? ' · ' + j.current : '') +
        (j.next_at ? ' · ' + Math.max(0, Math.ceil(j.next_at - Date.now() / 1000)) + 's' : '') +
        (j.next_batch_at
          ? ' · next batch ' +
            (j.batch || '') +
            (j.batches ? '/' + j.batches : '') +
            ' at ' +
            clock(new Date(j.next_batch_at * 1000))
          : '') +
        (j.error ? ' · ' + j.error : '');
      if (!active && j.error && !j.sent) {
        el('donorBatchList').open = false;
      }
      const terminal = !active && j.state !== 'Idle';
      const jobKey = JSON.stringify([j.id, j.updated_at, j.state, j.sent, j.error, j.receipts]);
      if (terminal) {
        el('donorProgress').hidden = false;
        el('donorBatchList').hidden = true;
        if (jobKey !== dismissedJob) {
          /* An app update restarts the server mid-batch; the batch continues by itself, so this is news, not an error. */
          const restarting = /Starting again by itself/.test(j.error || '');
          const failed = !restarting && (!!j.error || !!j.failed || j.state === 'Nothing sent');
          const reason = (j.receipts || []).find((r) => r.state?.startsWith('Skipped: '));
          const text = restarting
            ? 'The app was updated, so sending restarted. It continues by itself ' +
              (j.sent ? '(' + j.sent + ' already sent, not repeated).' : '(nobody is sent twice).')
            : failed
            ? 'Not sent' +
              (j.sent ? ' to everyone' : '') +
              '. ' +
              (reason
                ? reason.name + ': ' + reason.state.slice(9)
                : j.error || 'Check delivery results.')
            : 'Batch complete · ' +
              (j.sent || 0) +
              ' sent' +
              (j.skipped ? ' · ' + j.skipped + ' skipped' : '');
          notice(text, failed);
          el('donorNotice').querySelector('.donor-notice-close').onclick = () =>
            dismissBatch(jobKey);
          dismissedJob = jobKey;
        }
      } else if (active) {
        el('donorNotice').textContent = '';
      }
      el('donorProgress').querySelector('span').title = 'Tap to see who was sent and who is next';
      /* Folded away, the bar is one small chip: sent / total (e.g. 5/20). */
      {
        const shown = (j.previous_sent || 0) + (j.sent || 0),
          whole = j.original_total || j.total || 0;
        el('donorProgressShow').textContent = '⌃ ' + shown + '/' + whole;
        el('donorProgressShow').setAttribute('aria-label', 'Show sending details: ' + shown + ' of ' + whole + ' sent');
      }
      if (!active && j.state !== 'Idle') await refresh(true);
      if (active && seenSent !== null && j.sent !== seenSent) await refresh(true);
      seenSent = j.sent || 0;
      for (const receipt of j.receipts || []) {
        const row = [...el('donorRows').children].find((n) => n.dataset.donorId === receipt.id);
        if (row) {
          const previous = data.items.find((d) => d.id === receipt.id)?.delivery;
          paintDelivery(
            row,
            previous === 'Sent'
              ? 'Sent'
              : receipt.state === 'Sent'
                ? 'Sent'
                : receipt.state === 'Uncertain'
                  ? 'Uncertain'
                  : receipt.state?.startsWith('Skipped')
                    ? 'Skipped'
                    : receipt.state,
          );
        }
      }
      if (active || j.resume?.state === 'Pending') pollTimer = setTimeout(poll, 1200);
    } catch (e) {
      notice('Could not refresh delivery status. Checking again; no sends were retried.', true);
      if (page.open) pollTimer = setTimeout(poll, 3000);
    }
  }
  /* ---- Volunteers: people who help share the case. A name, a private number, one message you write, and a DM to share it. ---- */
  async function loadVolunteers() {
    try {
      vols = await api('/volunteers');
      updateCounts();
    } catch (e) {
      notice(e.message, true);
    }
  }
  function volState(d) {
    const s = d.delivery;
    return d.dm_sent || s === 'Sent'
      ? 'DM sent'
      : s === 'Uncertain'
        ? 'Check'
        : s === 'Sending' || s === 'Requesting'
          ? 'Sending…'
          : 'DM';
  }
  async function volAct(body, okText) {
    try {
      const r = await api('/volunteers', body);
      await loadVolunteers();
      if (tab === 'volunteers') showVolunteers(true);
      if (okText) notice(okText);
      return r;
    } catch (e) {
      notice(e.message, true);
    }
  }
  function volProgress() {
    const j = vols.delivery,
      box = el('volProgress');
    if (!box) return;
    const active = j && ['Starting', 'Sending', 'Waiting'].includes(j.state);
    box.hidden = !j || !j.total || j.state === 'Idle';
    if (box.hidden) {
      return;
    }
    const scheduled = active && j.hold_until > Date.now() / 1000;
    box.textContent =
      (scheduled
        ? 'Scheduled · first DM at ' +
          new Date(j.hold_until * 1000).toLocaleString('en-PK', {
            timeZone: 'Asia/Karachi',
            day: 'numeric',
            month: 'short',
            hour: 'numeric',
            minute: '2-digit',
          }) +
          ' PKT · '
        : active
          ? 'Sending to volunteers · '
          : 'Last send · ') +
      (j.sent || 0) +
      ' sent · ' +
      Math.max(0, (j.total || 0) - (j.sent || 0) - (j.skipped || 0) - (j.failed || 0)) +
      ' left' +
      (j.error ? ' · ' + j.error : '');
    box.dataset.active = String(!!active);
    clearTimeout(volPoll);
    if (active && tab === 'volunteers')
      volPoll = setTimeout(async () => {
        await loadVolunteers();
        if (tab === 'volunteers') showVolunteers(true);
      }, 5000);
  }
  async function showVolunteers(keepDraft = false) {
    const box = el('donorVolunteers');
    if (!keepDraft || (!vols.items.length && !vols.message)) await loadVolunteers();
    if (tab !== 'volunteers') return;
    const draft =
        keepDraft && box.querySelector('#volMessage')
          ? box.querySelector('#volMessage').value
          : null,
      nm = box.querySelector('#volName')?.value || '',
      ph = box.querySelector('#volPhone')?.value || '';
    box.textContent = '';
    const add = make('form', 'vol-add');
    add.autocomplete = 'off';
    const name = make('input', '');
    name.id = 'volName';
    name.name = 'volunteer_name';
    name.placeholder = 'Volunteer name';
    name.setAttribute('aria-label', 'Volunteer name');
    name.maxLength = 80;
    name.value = nm;
    const phone = make('input', '');
    phone.id = 'volPhone';
    phone.name = 'volunteer_phone';
    phone.type = 'tel';
    phone.inputMode = 'tel';
    phone.placeholder = 'WhatsApp number';
    phone.setAttribute('aria-label', 'Volunteer WhatsApp number');
    phone.value = ph;
    const addBtn = make('button', 'primary', '+ Add volunteer');
    addBtn.type = 'submit';
    add.append(name, phone, addBtn);
    add.onsubmit = async (e) => {
      e.preventDefault();
      addBtn.disabled = true;
      const typed = [name.value, phone.value];
      name.value = '';
      phone.value = '';
      const r = await volAct(
        { action: 'add', name: typed[0], phone: typed[1] },
        'Added ' + typed[0].trim() + '.',
      );
      addBtn.disabled = false;
      const n = el('donorVolunteers').querySelector('#volName'),
        p2 = el('donorVolunteers').querySelector('#volPhone');
      if (!r) {
        n.value = typed[0];
        p2.value = typed[1];
      }
      n?.focus();
    };
    const list = make('div', 'vol-list');
    if (vols.items.length) list.setAttribute('role', 'list');
    if (!vols.items.length) list.append(make('p', 'donor-empty', 'No volunteers yet.'));
    vols.items.forEach((d, i) => {
      const row = make('div', 'vol-row');
      row.setAttribute('role', 'listitem');
      row.dataset.volId = d.id;
      const sent = volState(d) === 'DM sent';
      row.dataset.sent = String(sent);
      const nameEl = make('div', 'vol-name', i + 1 + '. ' + d.name);
      const dm = make('button', 'tool vol-dm', volState(d));
      dm.type = 'button';
      dm.setAttribute('aria-label', 'Send the volunteer message to ' + d.name);
      dm.onclick = () => {
        if (!vols.message.trim()) {
          notice('Write the message for volunteers first (the box below).', true);
          el('donorVolunteers').querySelector('#volMessage')?.focus();
          return;
        }
        volAct(
          {
            action: 'send_one',
            id: d.id,
            request_id: 'v' + crypto.randomUUID().replace(/-/g, ''),
            poster: el('volPoster').checked,
          },
          'Sending to ' + d.name + '…',
        );
      };
      const more = make('details', 'donor-more');
      const summary = make('summary', '', '···');
      summary.setAttribute('aria-label', 'Manage ' + d.name);
      let menuBuilt = false;
      const buildMenu = () => {
        if (menuBuilt) return;
        menuBuilt = true;
        const menu = make('div', '');
        const rename = make('button', '', 'Rename');
        rename.type = 'button';
        rename.onclick = () => {
          const n = prompt('Volunteer name', d.name);
          if (n?.trim()) volAct({ action: 'update', id: d.id, name: n.trim() });
          more.open = false;
        };
        const del = make('button', 'remove', 'Remove');
        del.type = 'button';
        del.onclick = () => {
          if (confirm('Remove ' + d.name + ' from volunteers?'))
            volAct({ action: 'delete', id: d.id }, 'Removed ' + d.name + '.');
          more.open = false;
        };
        menu.append(rename, del);
        more.append(menu);
      };
      more.ontoggle = () => {
        if (more.open) buildMenu();
      };
      more.append(summary);
      row.append(nameEl, dm, more);
      list.append(row);
    });
    const msg = make('div', 'vol-msg');
    const label = make('label', '', 'Message to volunteers (they get it exactly like this)');
    label.htmlFor = 'volMessage';
    const ta = make('textarea', '');
    ta.id = 'volMessage';
    ta.name = 'volunteer_message';
    ta.rows = 6;
    ta.maxLength = 4000;
    ta.placeholder =
      'Assalam o alaikum {name}, please share this case in your groups…  ({name} becomes their name)';
    ta.value = draft ?? vols.message ?? '';
    const poster = make('label', 'vol-check');
    const pc = make('input', '');
    pc.type = 'checkbox';
    pc.id = 'volPoster';
    pc.checked = true;
    poster.append(pc, ' Send the poster with it');
    const save = make('button', 'tool', 'Save message');
    save.type = 'button';
    save.onclick = () => volAct({ action: 'message', text: ta.value }, 'Message saved.');
    msg.append(label, ta, make('div', 'vol-msg-actions'));
    msg.lastChild.append(poster, save);
    const prog = make('div', 'donor-progress vol-progress');
    prog.id = 'volProgress';
    prog.hidden = true;
    prog.setAttribute('role', 'status');
    const foot = make('div', 'vol-foot');
    const all = make('button', 'primary send-donors', 'DM all volunteers');
    all.type = 'button';
    all.disabled = !vols.items.length;
    all.onclick = () => openVolunteerTiming(ta.value, pc.checked);
    const pause = make('button', 'tool', 'Pause');
    pause.type = 'button';
    pause.hidden = !(
      vols.delivery && ['Starting', 'Sending', 'Waiting'].includes(vols.delivery.state)
    );
    pause.onclick = () => volAct({ action: 'stop' }, 'Pausing…');
    const back = make('button', 'tool vol-back', '← Back');
    back.type = 'button';
    back.setAttribute('aria-label', 'Back to main screen');
    back.onclick = close;
    foot.append(pause, all, back);
    box.append(add, list, msg, prog, foot);
    // Account for the real sticky footer when scrolling to a message field.
    const syncVolDock = () => box.style.setProperty('--vol-dock-height', foot.offsetHeight + 'px');
    if (typeof ResizeObserver !== 'undefined') {
      if (!volDockObserver) volDockObserver = new ResizeObserver(entries => {
        for (const entry of entries) box.style.setProperty('--vol-dock-height', entry.target.offsetHeight + 'px');
      });
      volDockObserver.disconnect();
      volDockObserver.observe(foot);
    }
    syncVolDock();
    volProgress();
  }
  function selectDonorTab(next) {
    tab = next;
    el('donorSearch').value = '';
    try {
      sessionStorage.setItem('givelife-donor-search', '');
    } catch (e) {}
    clearTimeout(searchTimer);
    Nav.go('donors/' + next, { replace: true });
    applyFilters();
  }
  launch.onclick = open;
  el('donorMainBottom').onclick = close;
  page.addEventListener('cancel', (e) => {
    e.preventDefault();
    close();
  });
  for (const b of page.querySelectorAll('[data-tab]'))
    b.onclick = () => selectDonorTab(b.dataset.tab);
  page.querySelector('.donor-tabs').addEventListener('keydown', (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    const buttons = [...page.querySelectorAll('.donor-tabs [data-tab]')];
    let i = buttons.indexOf(e.target);
    i =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? buttons.length - 1
          : (i + (e.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
    buttons[i].focus();
    buttons[i].click();
  });
  el('donorSearch').oninput = () => {
    try {
      sessionStorage.setItem('givelife-donor-search', el('donorSearch').value);
    } catch (e) {}
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, 80);
  };
  const syncToggle = async () => {
    try {
      paintDMControl(await api('/donor-delivery'));
    } catch (e) {}
  };
  el('donorTest').onclick = async () => {
    el('donorTest').disabled = true;
    try {
      const r = await api('/donor-delivery', { test: true, poster: singlePosterOn });
      notice(r.reply);
    } catch (e) {
      notice(e.message, true);
    } finally {
      el('donorTest').disabled = false;
    }
  };
  el('donorToggle').onclick = async () => {
    el('donorToggle').disabled = true;
    try {
      const st = await api('/donor-delivery');
      paintDMControl(st);
      if (st.paused) {
        openResumeChoice();
        return;
      }
      const r = await api('/donor-delivery', { stop: true });
      notice(r.reply);
      await syncToggle();
      await poll();
    } catch (e) {
      notice(e.message, true);
    } finally {
      el('donorToggle').disabled = false;
    }
  };
  launch.addEventListener('click', syncToggle);
  window.addEventListener('hashchange', syncToggle);
  el('donorRowPoster').checked = singlePosterOn;
  el('donorRowPoster').onchange = () => {
    singlePosterOn = el('donorRowPoster').checked;
    try {
      sessionStorage.setItem('givelife-donor-row-poster', singlePosterOn ? '1' : '0');
    } catch (e) {}
  };
  el('donorSendAll').onclick = () => openBatchPicker('all');
  el('donorSendImportant').onclick = () => openBatchPicker(tab === 'top' ? 'top' : 'important');
  el('donorContinue').onclick = openResumeChoice;
  el('donorProgress').querySelector('span').onclick = () => {
    const box = el('donorBatchList');
    if (!box.hidden) box.open = !box.open;
  };
  el('donorEditBatch').onclick = async () => {
    const b = el('donorEditBatch');
    b.disabled = true;
    try {
      const job = await api('/donor-delivery').catch(() => ({}));
      if (!['Starting','Sending','Waiting'].includes(job.state)) throw Error('Resume the paused batch first, then edit its settings.');
      await openBatchPicker(job.scope === 'top' || job.scope === 'all' ? job.scope : 'important');
      editingJob=job.id;
      setGap(job.gap_seconds);
      el('batchLimit').value=job.chunk||20;
      el('batchCount').value=job.total||1;el('batchCount').disabled=true;
      el('batchIncl').disabled=true;el('batchFresh').disabled=true;
      el('batchPoster').checked=job.poster!==false;
      el('batchEach').value=(job.rests||[job.rest_seconds||1200]).map(x=>x/60).join(', ');
      el('batchPause').value='each';
      el('batchRandom').checked=!!job.jitter;
      if(job.jitter){el('batchJMin').value=Math.abs(job.jitter.min);el('batchJMax').value=job.jitter.max;}
      paintAudience();
      el('batchStart').textContent='Save changes';
      el('batchPlan').textContent='DMs keep sending while you edit. Changes apply to waiting donors when saved.';
    } catch (e) {
      notice(e.message, true);
    } finally {
      b.disabled = false;
      poll();
    }
  };
  /* Hide the sending bar to a small ⌃ button, and bring it back with one tap (remembered). */
  let progressHidden = false;
  try {
    progressHidden = localStorage.getItem('givelife-progress-hidden') === '1';
  } catch (e) {}
  function paintProgressHidden() {
    el('donorProgress').classList.toggle('dp-collapsed', progressHidden);
    el('donorProgressShow').hidden = !progressHidden || el('donorProgress').hidden;
  }
  for (const [id, hide] of [['donorProgressHide', true], ['donorProgressShow', false]])
    el(id).onclick = () => {
      progressHidden = hide;
      try {
        localStorage.setItem('givelife-progress-hidden', hide ? '1' : '0');
      } catch (e) {}
      paintProgressHidden();
    };
  new MutationObserver(paintProgressHidden).observe(el('donorProgress'), { attributes: true, attributeFilter: ['hidden'] });
  /* Hide sits at the bottom of the box, within thumb reach. */
  el('donorProgress').append(el('donorProgressHide'));
  const foldProgress = () => {
    if (el('donorProgress').hidden || progressHidden) return false;
    progressHidden = true;
    try {
      localStorage.setItem('givelife-progress-hidden', '1');
    } catch (e) {}
    paintProgressHidden();
    return true;
  };
  /* Outside click or Escape closes the progress box (it stays visible as the small chip) and a row's menu. */
  document.addEventListener('pointerdown', (e) => {
    if (!page.open) return;
    const box = el('donorProgress');
    if (!box.hidden && !progressHidden && !box.contains(e.target) && !el('donorProgressShow').contains(e.target) && e.target.closest('dialog') === page)
      foldProgress();
    for (const m of page.querySelectorAll('.donor-more[open]')) if (!m.contains(e.target)) m.open = false;
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented || !page.open || [...document.querySelectorAll('dialog[open]')].some((d) => d !== page)) return;
    const menu = page.querySelector('.donor-more[open]');
    if (menu) {
      menu.open = false;
      menu.querySelector('summary')?.focus({ preventScroll: true });
      e.preventDefault();
    } else if (foldProgress()) e.preventDefault();
  });
  paintProgressHidden();
  /* The sending panel floats above the bottom buttons (and above the paused bar), so the donor list keeps its height. */
  {
    const foot = page.querySelector('.donor-bottom'),
      shell = page.querySelector('.donor-shell'),
      rs = page.querySelector('#donorResumeStatus'),
      heights = new Map(),
      size = (n) => (heights.has(n) ? heights.get(n) : n.offsetHeight),
      sync = () => {
        /* Write only when a value changes: rewriting the same variable re-styles the whole donor screen.
           Sizes come from the ResizeObserver entries, so no extra forced layout. */
        const footPx = (foot ? size(foot) : 72) + 'px',
          rsH = rs ? size(rs) : 0,
          rsPx = rs && rs.parentElement !== foot && !rs.hidden && rsH ? rsH + 8 + 'px' : '0px';
        if (shell.style.getPropertyValue('--donor-foot') !== footPx) shell.style.setProperty('--donor-foot', footPx);
        if (shell.style.getPropertyValue('--donor-rs') !== rsPx) shell.style.setProperty('--donor-rs', rsPx);
      };
    if (typeof ResizeObserver !== 'undefined')
      for (const n of [foot, rs])
        if (n)
          new ResizeObserver((entries) => {
            for (const e of entries) heights.set(e.target, Math.round(e.borderBoxSize?.[0]?.blockSize ?? e.target.offsetHeight));
            sync();
          }).observe(n);
    if (rs) new MutationObserver(() => (heights.delete(rs), sync())).observe(rs, { attributes: true, attributeFilter: ['hidden', 'class'] });
    sync();
  }
  el('donorStop').onclick = async () => {
    try {
      await api('/donor-delivery', { stop: true });
      notice(
        'Paused. A message already in flight may still complete. Tap Resume DMs to choose now or a time.',
      );
      poll();
    } catch (e) {
      notice(e.message, true);
    }
  };
  el('donorAdd').onclick = () => {
    el('donorAddNote').textContent = '';
    add.showModal();
    el('donorNewName').focus();
  };
  el('donorAddCancel').onclick = () => {
    el('donorNewPhone').value = '';
    el('donorNewPhone').removeAttribute('aria-invalid');
    add.close();
  };
  for (const id of ['donorNewName', 'donorNewPhone'])
    el(id).addEventListener('paste', (e) => {
      const text = e.clipboardData?.getData('text') || '';
      const m = text.match(/(?:\+|00)?\d[\d ()-]{6,23}\d/);
      if (m) {
        e.preventDefault();
        el('donorNewPhone').value = m[0];
        const name = (text.slice(0, m.index) + ' ' + text.slice(m.index + m[0].length))
          .trim()
          .replace(/^[,;:\s-]+|[,;:\s-]+$/g, '');
        if (name) el('donorNewName').value = name;
      }
    });
  el('donorAddForm').onsubmit = async (e) => {
    e.preventDefault();
    el('donorAddSave').disabled = true;
    try {
      const r = await api('/donors', {
        action: 'add',
        name: el('donorNewName').value,
        phone: el('donorNewPhone').value,
      });
      el('donorNewPhone').removeAttribute('aria-invalid');
      el('donorNewName').value = '';
      el('donorNewPhone').value = '';
      el('donorNewPhone').removeAttribute('aria-invalid');
      add.close();
      await refresh(true);
      notice(r.reply);
    } catch (e) {
      el('donorAddNote').textContent = e.message;
      el('donorNewPhone').setAttribute('aria-invalid', String(!!el('donorNewPhone').value.trim()));
      (el('donorNewPhone').value.trim() ? el('donorNewPhone') : el('donorNewName')).focus();
    } finally {
      el('donorAddSave').disabled = false;
    }
  };
  el('donorImport').onclick = () => el('donorImportFile').click();
  el('donorImportFile').onchange = async () => {
    const file = el('donorImportFile').files[0];
    if (!file) return;
    try {
      if (file.size > 2000000) throw Error('Choose a contacts JSON file under 2 MB.');
      const parsed = JSON.parse(await file.text());
      const r = await api('/donors', {
        action: 'import',
        records: Array.isArray(parsed) ? parsed : parsed.records,
      });
      el('donorAddNote').textContent = r.reply;
      await refresh(true);
    } catch (e) {
      el('donorAddNote').textContent = e.message;
    } finally {
      el('donorImportFile').value = '';
    }
  };
  function showPosterPreview(blob, mime) {
    if (posterUrl) URL.revokeObjectURL(posterUrl);
    posterUrl = URL.createObjectURL(blob);
    const video = String(mime || '').startsWith('video/');
    el('posterCurrent').hidden = video;
    el('posterCurrentVideo').hidden = !video;
    if (video) {
      el('posterCurrent').removeAttribute('src');
      el('posterCurrentVideo').src = posterUrl;
    } else {
      el('posterCurrentVideo').pause();
      el('posterCurrentVideo').removeAttribute('src');
      el('posterCurrent').src = posterUrl;
    }
  }
  async function loadSavedPoster() {
    const r = await fetch('/dm-poster', { cache: 'no-store' });
    if (!r.ok) throw Error('The saved poster could not load. Upload it again.');
    const blob = await r.blob();
    showPosterPreview(blob, blob.type || r.headers.get('Content-Type'));
  }
  function setPosterProgress(percent, message, state = 'uploading') {
    const value = Math.max(0, Math.min(100, Math.round(percent)));
    el('posterProgress').hidden = false;
    el('posterProgress').dataset.state = state;
    el('posterProgressTrack').setAttribute('aria-valuenow', String(value));
    el('posterProgressFill').style.width = value + '%';
    el('posterProgressText').textContent = message;
    el('posterSave').textContent = state === 'saved' ? 'Saved ✓' : state === 'saving' ? 'Finishing…' : 'Saving ' + value + '%';
  }
  function resetPosterProgress() {
    el('posterProgress').hidden = true;
    el('posterProgress').removeAttribute('data-state');
    el('posterProgressTrack').setAttribute('aria-valuenow', '0');
    el('posterProgressFill').style.width = '0%';
    el('posterProgressText').textContent = '';
    el('posterSave').textContent = 'Save poster';
  }
  // The upload percentage is based on bytes actually sent, not an estimated timer.
  // Reaching 100% means the server confirmed that it saved the poster.
  function uploadPosterWithProgress(data, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', (window.GIVELIFE_API || '') + '/upload-image');
      xhr.timeout = 120000;
      xhr.setRequestHeader('Content-Type', 'application/json');
      const key = localStorage.getItem('givelife-cloud-key');
      if (key) xhr.setRequestHeader('Authorization', 'Bearer ' + key);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0)
          onProgress(Math.min(99, Math.floor((event.loaded / event.total) * 99)), false);
      };
      xhr.upload.onload = () => onProgress(99, true);
      xhr.onload = () => {
        let result;
        try { result = JSON.parse(xhr.responseText); }
        catch (e) { reject(Error('Server response was invalid. Check the saved poster before retrying.')); return; }
        if (xhr.status < 200 || xhr.status >= 300 || result.id !== 'poster') {
          reject(Error(result.error || (xhr.status === 401 ? 'Session expired. Sign in again.' : 'Saving was not confirmed.')));
          return;
        }
        resolve(result);
      };
      xhr.onerror = () => reject(Error('Connection lost. Check the saved poster before retrying.'));
      xhr.ontimeout = () => reject(Error('Save timed out. Check the saved poster before retrying.'));
      try { xhr.send(JSON.stringify({ use: 'dm_poster', data })); }
      catch (e) { reject(Error('Could not start the upload. ' + e.message)); }
    });
  }
  async function openPoster() {
    posterData = null;
    resetPosterProgress();
    el('posterSave').disabled = true;
    el('posterClose').textContent = 'Cancel';
    el('posterNote').textContent = 'Loading saved poster…';
    poster.showModal();
    try {
      await loadSavedPoster();
      if (!posterData) el('posterNote').textContent = '';
    } catch (e) {
      el('posterNote').textContent = e.message;
    }
  }
  function closePoster() {
    if (posterSaving) return;
    poster.close();
    posterData = null;
    if (posterUrl) URL.revokeObjectURL(posterUrl);
    posterUrl = null;
    el('posterCurrentVideo').pause();
  }
  el('posterClose').onclick = closePoster;
  poster.addEventListener('cancel', (event) => {
    if (posterSaving) event.preventDefault();
    else {
      posterData = null;
      if (posterUrl) URL.revokeObjectURL(posterUrl);
      posterUrl = null;
      el('posterCurrentVideo').pause();
    }
  });
  el('posterFile').onchange = async () => {
    if (posterSaving) return;
    const f = el('posterFile').files[0];
    if (!f) return;
    resetPosterProgress();
    posterData = null;
    el('posterSave').disabled = true;
    try {
      if (f.type.startsWith('video/')) {
        if (f.size > 15000000 || !/mp4|quicktime/.test(f.type))
          throw Error('Choose an MP4 video under 15 MB.');
        posterData = await new Promise((ok, no) => {
          const r = new FileReader();
          r.onload = () => ok(r.result);
          r.onerror = () => no(Error('Could not read the video.'));
          r.readAsDataURL(f);
        });
        showPosterPreview(f, f.type);
        el('posterNote').textContent =
          'Video chosen (' +
          Math.round((f.size / 1e6) * 10) / 10 +
          ' MB). Save to send it with every group message and DM.';
        el('posterSave').disabled = false;
        return;
      }
      if (!f.type.startsWith('image/') || f.size > 20000000)
        throw Error('Choose an image under 20 MB, or an MP4 video under 15 MB.');
      const bitmap = await createImageBitmap(f);
      const scale = Math.min(1, 1800 / Math.max(bitmap.width, bitmap.height));
      const c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(bitmap.width * scale));
      c.height = Math.max(1, Math.round(bitmap.height * scale));
      const ctx = c.getContext('2d');
      ctx.fillStyle = 'white';
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(bitmap, 0, 0, c.width, c.height);
      bitmap.close();
      posterData = c.toDataURL('image/jpeg', 0.9);
      if (posterUrl) URL.revokeObjectURL(posterUrl);
      posterUrl = null;
      el('posterCurrentVideo').pause();
      el('posterCurrentVideo').hidden = true;
      el('posterCurrent').hidden = false;
      el('posterCurrent').src = posterData;
      el('posterNote').textContent = 'Preview only. Save to use this poster for future sends.';
      el('posterSave').disabled = false;
    } catch (e) {
      el('posterNote').textContent = e.message;
    } finally {
      el('posterFile').value = '';
    }
  };
  el('posterSave').onclick = async () => {
    if (!posterData || posterSaving) return;
    posterSaving = true;
    el('posterSave').disabled = true;
    el('posterClose').disabled = true;
    el('posterFile').disabled = true;
    const isVideo = posterData.startsWith('data:video/');
    el('posterNote').textContent = '';
    setPosterProgress(0, 'Uploading ' + (isVideo ? 'video' : 'picture') + ' · 0%');
    try {
      await uploadPosterWithProgress(posterData, (percent, uploaded) => {
        setPosterProgress(
          percent,
          uploaded ? 'Upload complete · saving securely…' : 'Uploading · ' + percent + '%',
          uploaded ? 'saving' : 'uploading',
        );
      });
      setPosterProgress(100, 'Saved successfully', 'saved');
      el('posterNote').textContent = isVideo
        ? 'Video saved for groups and DMs.'
        : 'Poster saved for groups and DMs.';
      window.dispatchEvent(new Event('poster-changed'));
      posterData = null;
      // Keep the confirmed 100% visible briefly before closing automatically.
      await new Promise((resolve) => setTimeout(resolve, 650));
      posterSaving = false;
      closePoster();
      notice(isVideo ? 'Video saved for groups and DMs.' : 'Poster saved for groups and DMs.');
    } catch (e) {
      el('posterProgress').dataset.state = 'error';
      el('posterProgressText').textContent = 'Save not confirmed';
      el('posterNote').textContent = e.message;
      el('posterSave').textContent = 'Retry save';
      el('posterSave').disabled = false;
    } finally {
      posterSaving = false;
      el('posterClose').disabled = false;
      el('posterFile').disabled = false;
    }
  };
  const paste = make('dialog', 'donor-form-dialog paste-dialog');
  paste.id = 'donorPasteDialog';
  paste.setAttribute('aria-label', 'Bulk message');
  paste.innerHTML = `<h2>Bulk message</h2><label for="pastePeople" class="paste-step-list">Numbers and names</label><textarea id="pastePeople" name="recipients" rows="5" autocomplete="off" spellcheck="false" placeholder="0300 1234567, Ali
Ayesha, +92 301 1234567" aria-describedby="pasteResult"></textarea><div id="pasteResult" class="paste-result" role="status" aria-live="polite"></div><ol id="pastePlan" class="paste-plan" aria-label="Planned send times" hidden></ol><label for="pasteGap" class="paste-step-time">Gap between DMs</label><select id="pasteGap" class="paste-step-time" name="gap_minutes">${Array.from({ length: 10 }, (_, i) => `<option value="${i + 1}" ${i === 3 ? 'selected' : ''}>${i + 1} minute${i ? 's' : ''}</option>`).join('')}</select><label for="pasteMessage" class="paste-step-time">Your message (optional)</label><textarea id="pasteMessage" class="paste-step-time" rows="3" maxlength="8000" placeholder="Write any message…"></textarea><p class="paste-step-time">{name} uses the pasted name; no name uses Bhai. Leave blank to use saved messages.</p><label class="paste-step-time batch-fresh"><input type="checkbox" id="pastePoster" checked> Attach poster</label><label for="pasteMedia" class="paste-step-time">Attach media</label><input id="pasteMedia" class="paste-step-time" type="file" accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf"><p id="pasteMediaNote" class="paste-step-time" role="status"></p><div class="donor-form-actions"><button type="button" id="pasteCancel">Cancel</button><button type="button" id="pasteBack" class="paste-step-time">← Back</button><button type="button" class="primary paste-step-list" id="pasteNext" disabled>DM all</button><button type="button" class="primary paste-step-time" id="pasteStart" disabled>Start DMs now</button></div>`;
  document.body.append(paste);
  let pasteAttachment = null,
    mediaPending = false;
  el('pasteMedia').onchange = async () => {
    pasteAttachment = null;
    const file = el('pasteMedia').files[0];
    if (!file) {
      el('pasteMediaNote').textContent = 'No extra attachment.';
      return;
    }
    if (file.size > 15000000) {
      el('pasteMedia').value = '';
      el('pasteMediaNote').textContent = 'Choose a file under 15 MB.';
      return;
    }
    mediaPending = true;
    el('pasteStart').disabled = true;
    el('pasteMediaNote').textContent = 'Uploading privately…';
    try {
      const data = await new Promise((ok, no) => {
        const r = new FileReader();
        r.onload = () => ok(r.result);
        r.onerror = () => no(Error('Could not read file.'));
        r.readAsDataURL(file);
      });
      const mime =
        file.type ||
        {
          pdf: 'application/pdf',
          mp4: 'video/mp4',
          jpg: 'image/jpeg',
          jpeg: 'image/jpeg',
          png: 'image/png',
          webp: 'image/webp',
        }[file.name.split('.').pop().toLowerCase()];
      const payload = mime
        ? data.replace(/^data:[^;]*;base64,/, 'data:' + mime + ';base64,')
        : data;
      const result = await api('/upload-image', { use: 'bulk', data: payload });
      pasteAttachment = result.id;
      el('pastePoster').checked = false;
      el('pasteMediaNote').textContent = file.name + ' ready.';
    } catch (e) {
      el('pasteMediaNote').textContent = e.message;
      el('pasteMedia').value = '';
    } finally {
      mediaPending = false;
      el('pasteStart').disabled = !pasteToken || pastePending;
    }
  };
  let pasteTimer,
    pasteEpoch = 0,
    pasteToken = null,
    pastePending = false;
  /* Two steps: 1) paste and check the numbered list, 2) choose the gap and see every send time, then start. */
  function pasteStep(step) {
    paste.dataset.step = step;
    if (step === 'time') el('pasteStart').focus({ preventScroll: true });
  }
  function openPaste() {
    pasteStep('list');
    paste.showModal();
    el('pastePeople').focus({ preventScroll: true });
  }
  el('pasteNext').onclick = () => {
    if (pasteToken) pasteStep('time');
  };
  el('pasteBack').onclick = () => pasteStep('list');
  el('sendMoreDonors').onclick = openPaste;
  el('donorBulk').onclick = openPaste;
  el('pasteCancel').onclick = () => paste.close();
  el('pastePeople').oninput = () => {
    const epoch = ++pasteEpoch;
    clearTimeout(pasteTimer);
    pasteToken = null;
    el('pasteStart').disabled = true;
    el('pasteNext').disabled = true;
    el('pastePeople').removeAttribute('aria-invalid');
    el('pasteResult').textContent = 'Checking names and numbers…';
    if (!el('pastePeople').value.trim()) {
      el('pastePlan').hidden = true;
      el('pasteResult').textContent = '';
      return;
    }
    pasteTimer = setTimeout(async () => {
      try {
        const d = await api('/donor-paste', {
          action: 'preview',
          text: el('pastePeople').value,
          gap_seconds: Number(el('pasteGap').value) * 60,
        });
        if (epoch !== pasteEpoch) return;
        pasteToken = d.token;
        el('pasteResult').textContent =
          d.count +
          ' recipient' +
          (d.count === 1 ? '' : 's') +
          ' ready' +
          (d.duplicates ? ' · ' + d.duplicates + ' duplicate(s) removed' : '') +
          (d.count > 1 ? ' · everyone is scheduled below' : '');
        drawPlan(d);
        el('pasteStart').disabled = pastePending;
        el('pasteNext').disabled = !d.count;
        el('pasteNext').textContent = 'DM all ' + d.count;
      } catch (e) {
        if (epoch !== pasteEpoch) return;
        el('pastePeople').setAttribute('aria-invalid', 'true');
        el('pasteResult').textContent = e.message;
        el('pastePlan').hidden = true;
      }
    }, 400);
  };
  /* Every recipient with the clock time it will go out, shown before anything is sent. */
  function clock(at) {
    return at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  function span(seconds) {
    const m = Math.round(seconds / 60);
    return m < 1
      ? 'now'
      : m < 60
        ? m + ' min'
        : Math.floor(m / 60) + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : '');
  }
  function drawPlan(d) {
    const list = el('pastePlan');
    list.textContent = '';
    const start = Date.now();
    for (const item of d.plan || []) {
      const li = make('li', '');
      li.append(
        make('span', 'plan-n', item.position),
        make('span', 'plan-name', item.name),
        make(
          'span',
          'plan-when',
          item.after_seconds
            ? clock(new Date(start + item.after_seconds * 1000)) +
                ' · in ' +
                span(item.after_seconds)
            : 'Now',
        ),
      );
      list.append(li);
    }
    list.hidden = !(d.plan || []).length;
    if (d.plan?.length > 1) {
      const last = d.plan.at(-1),
        foot = make(
          'li',
          'plan-total',
          'All ' +
            d.plan.length +
            ' done by about ' +
            clock(new Date(start + last.after_seconds * 1000)) +
            ' (about ' +
            span(d.total_seconds) +
            ' after the first)',
        );
      list.append(foot);
    }
  }
  el('pasteGap').onchange = () => {
    if (el('pastePeople').value.trim()) el('pastePeople').oninput();
  };
  el('pasteStart').onclick = async () => {
    if (pastePending || mediaPending || !pasteToken) return;
    pastePending = true;
    el('pasteStart').disabled = true;
    const token = pasteToken;
    pasteToken = null;
    el('pasteResult').textContent = 'Starting your donor batch…';
    try {
      const r = await api('/donor-paste', {
        action: 'start',
        token,
        gap_seconds: Number(el('pasteGap').value) * 60,
        request_id: requestId(),
        poster: !pasteAttachment && el('pastePoster').checked,
        ...(pasteAttachment ? { attachment: pasteAttachment } : {}),
        ...(el('pasteMessage').value.trim() ? { message: el('pasteMessage').value } : {}),
      });
      paste.close();
      pasteAttachment = null;
      el('pasteMedia').value = '';
      el('pastePeople').value = '';
      el('pasteMessage').value = '';
      el('pasteResult').textContent = 'Numbers are hidden in the recipient preview.';
      el('pastePlan').hidden = true;
      el('pastePlan').textContent = '';
      await open();
      notice(r.reply);
    } catch (e) {
      el('pasteResult').textContent =
        e.message +
        ' Check Donors for saved contacts and delivery results. Nothing is retried automatically.';
    } finally {
      pastePending = false;
    }
  };
  try {
    el('donorSearch').value = sessionStorage.getItem('givelife-donor-search') || '';
  } catch (e) {}
  page.querySelector('.donor-tabs').addEventListener('keydown', (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    const tabs = [...e.currentTarget.querySelectorAll('[role=tab]')];
    const index = tabs.indexOf(e.target);
    if (index < 0) return;
    e.preventDefault();
    const next =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? tabs.length - 1
          : (index + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].click();
    tabs[next].focus({ preventScroll: true });
  });
  window.DonorHub = {
    open,
    show,
    hide,
    isOpen: () => page.open,
    refresh,
    openPoster,
    privateChatText: (text) =>
      /\bdonors?\b/i.test(text)
        ? String(text).replace(/(?:\+|00)?\d[\d ()-]{6,23}\d/g, '[number hidden]')
        : text,
  };
  function wrapMark(input, mark) {
    if (input.selectionStart === input.selectionEnd) return input.focus();
    window.waMark.apply(input, mark);
  }

  function openBaseMessage() {
    let d = el('baseMessageDialog');
    if (!d) {
      d = document.createElement('dialog');
      d.id = 'baseMessageDialog';
      d.className = 'base-dialog';
      d.innerHTML = '<form method="dialog"><h2>Base message</h2><p>The 20 versions are written from this. Saving keeps only this message until you press Generate 20 versions.</p><div class="base-tools"><button type="button" data-mark="*" aria-label="Bold"><b>B</b></button><button type="button" data-mark="_" aria-label="Italic"><i>I</i></button></div><textarea id="baseMessageText" rows="14" aria-label="Base message"></textarea><p id="baseMessageNote" role="status"></p><div class="base-actions"><button type="button" id="baseMessageCancel">Cancel</button><button type="button" id="baseMessageSave" class="primary">Save base message</button></div></form>';
      document.body.append(d);
      for (const b of d.querySelectorAll('[data-mark]')) {
        b.onmousedown = (e) => e.preventDefault();
        b.onclick = () => wrapMark(el('baseMessageText'), b.dataset.mark);
      }
      el('baseMessageCancel').onclick = () => d.close();
      el('baseMessageSave').onclick = async () => {
        const text = el('baseMessageText').value.trim();
        if (!text) return;
        const note = el('baseMessageNote');
        if (bankData && bankData.items.length > 1 && !confirm('This replaces all 20 versions with just this base message. Continue?')) return;
        el('baseMessageSave').disabled = true;
        try {
          const r = await api('/donor-messages', { action: 'base', text });
          bankData = null;
          note.textContent = r.reply || 'Saved.';
          await showMessages(true);
          d.close();
        } catch (e) {
          note.textContent = e.message;
        } finally {
          el('baseMessageSave').disabled = false;
        }
      };
    }
    const existing = bankData?.items?.[0]?.text || '';
    el('baseMessageText').value = existing;
    d.showModal();
  }

  document.addEventListener('donors-changed', () => {
    bankData = null;
    if (page.open) {
      refresh(true);
      poll();
      loadVolunteers().then(() => {
        if (tab === 'volunteers') showVolunteers(true);
      });
    }
  });
})();
