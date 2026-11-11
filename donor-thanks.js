/* Completion proof, its attached caption, and an optional independent message. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'donorThanksDialog';
  dialog.setAttribute('aria-labelledby', 'thanksTitle');
  dialog.innerHTML = `<header><div class="thanks-head-row"><h2 id="thanksTitle" tabindex="-1" autofocus>Thank donors</h2><div class="thanks-media"><button type="button" class="thanks-attach" id="thanksAttachImg">+ Image</button><button type="button" class="thanks-attach" id="thanksAttachVid">+ Video</button></div></div><small id="thanksContext"></small></header>
  <div class="thanks-body"><section class="thanks-compose">
    <div class="thanks-picker" hidden><select id="thanksMediaSelect" aria-label="Attachment"></select><button type="button" id="thanksRemove" class="thanks-remove">Remove</button></div><div class="thanks-list" id="thanksList"></div>
    <input id="thanksFile" type="file" aria-label="Attach file" accept="image/jpeg,image/png,image/webp,video/mp4" multiple hidden>
    <section class="thanks-msg">
      <label for="thanksMessage">Message</label><textarea id="thanksMessage" aria-describedby="thanksNameHint" maxlength="4000" rows="2" placeholder="Optional extra message…"></textarea>
      <small id="thanksNameHint">{name} = name + Bhai/Sister</small>
    </section>
    <section class="thanks-timing">
      <div class="thanks-grid">
        <div class="thanks-opt" data-k="gap"><label><select aria-label="Gap" id="thanksGapSel"></select></label><div class="thanks-custom" hidden><label>min<input id="thanksGap" type="number" min="0" max="1440" inputmode="numeric"></label><label>sec<input id="thanksGapSec" type="number" min="0" max="59" inputmode="numeric"></label></div></div>
        <div class="thanks-opt" data-k="vary"><label><select aria-label="Variation" id="thanksVarySel"></select></label><div class="thanks-custom" hidden><label>sec<input id="thanksVary" type="number" min="0" max="300" inputmode="numeric"></label></div></div>
        <div class="thanks-opt" data-k="batch"><label><select aria-label="Batch size" id="thanksBatchSel"></select></label><div class="thanks-custom" hidden><label>donors<input id="thanksBatch" type="number" min="1" max="100" inputmode="numeric"></label></div></div>
        <div class="thanks-opt" data-k="rest"><label><select aria-label="Rest" id="thanksRestSel"></select></label><div class="thanks-custom" hidden><label>min<input id="thanksRest" type="number" min="0" max="1440" inputmode="numeric"></label><label>sec<input id="thanksRestSec" type="number" min="0" max="59" inputmode="numeric"></label></div></div>
      </div></section>
  </section></div>
  <p id="thanksStatus" role="status" aria-live="polite"></p><footer><button type="button" id="thanksSave">Save</button><button type="button" id="thanksTest" title="Send this to the GiveLife test group only">Test</button><div class="thanks-start"><span id="thanksStartLabel">Start</span><button type="button" role="switch" id="thanksSwitch" aria-checked="false" aria-label="Start sending the thank-you updates"><i></i></button></div><button type="button" id="thanksClose" aria-label="Close Thank donors">Back</button></footer>`;
  document.body.append(dialog);
  const $ = (id) => dialog.querySelector('#' + id);
  const scrollArea = dialog.querySelector('.thanks-body');
  let visibilityFrame = 0;
  function keepFocusedFieldVisible() {
    cancelAnimationFrame(visibilityFrame);
    visibilityFrame = requestAnimationFrame(() => {
      const field = document.activeElement;
      if (
        !dialog.open ||
        !scrollArea.contains(field) ||
        !field.matches('textarea, input:not([type="file"])')
      )
        return;
      const bounds = field.getBoundingClientRect();
      const area = scrollArea.getBoundingClientRect();
      if (bounds.bottom > area.bottom - 6)
        scrollArea.scrollTop += bounds.bottom - area.bottom + 6;
      else if (bounds.top < area.top + 6)
        scrollArea.scrollTop -= area.top - bounds.top + 6;
    });
  }
  dialog.addEventListener('focusin', keepFocusedFieldVisible);
  window.visualViewport?.addEventListener('resize', keepFocusedFieldVisible);
  if (window.ResizeObserver) new ResizeObserver(keepFocusedFieldVisible).observe(scrollArea);
  let state,
    selectedMedia = 0,
    viewVersion = 0,
    busy = false,
    starting = false,
    stopping = false,
    actionVersion = 0,
    poll;
  async function api(action, body = {}) {
    const response = await fetch(
      '/donor-thanks',
      action
        ? {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, ...body }),
          }
        : {},
    );
    const result = await response.json();
    if (!response.ok)
      throw Error(result.error || 'Could not save this update. Your text is still here.');
    return result;
  }
  const note = (text, level = 'info') => {
    $('thanksStatus').textContent = text;
    $('thanksStatus').dataset.level = level;
  };
  function controls() {
    dialog.dataset.hasMedia = String(!!state?.media.length);
    dialog.dataset.hasMessage = String(!!$('thanksMessage').value.trim());
    for (const field of dialog.querySelectorAll('input,textarea'))
      field.disabled = busy || state?.on;
    for (const sel of dialog.querySelectorAll('select')) sel.disabled = busy || state?.on;
    $('thanksSave').disabled = busy || state?.on;
    $('thanksTest').disabled =
      busy || !state || (!state.media.length && !$('thanksMessage').value.trim());
    const on = !stopping && (!!state?.on || starting);
    dialog.dataset.phase = stopping ? 'stopping' : starting ? 'starting' : on ? 'running' : 'idle';
    $('thanksSwitch').setAttribute('aria-checked', String(on));
    $('thanksSwitch').setAttribute('aria-label', stopping ? 'Stopping thank-you updates' : starting ? 'Starting thank-you updates' : on ? 'Stop sending thank-you updates' : 'Start sending thank-you updates');
    $('thanksSwitch').setAttribute('aria-busy', String(starting || stopping));
    $('thanksSwitch').disabled =
      busy ||
      !state ||
      (!on &&
        (state.left > 0 ||
          (!state.media.length && !$('thanksMessage').value.trim()) ||
          state.pending === 0));
    $('thanksStartLabel').textContent = stopping ? 'Stopping…' : starting ? 'Starting…' : on ? 'Stop' : 'Start';
    for (const b of dialog.querySelectorAll('.thanks-remove, .thanks-attach'))
      b.disabled =
        busy ||
        state?.on ||
        (b.classList.contains('thanks-attach') && state?.media.length >= MAX_MEDIA);
  }
  /* Any number of images and videos (up to 8), each with its own optional "+ Caption"; sent in this order. */
  const MAX_MEDIA = 8;
  function renderList() {
    const list = $('thanksList');
    list.replaceChildren();
    selectedMedia = Math.min(selectedMedia, Math.max(0, (state?.media.length || 0) - 1));
    const picker = $('thanksMediaSelect');
    picker.replaceChildren();
    picker.parentElement.hidden = !state?.media.length;
    picker.onchange = () => {
      selectedMedia = Number(picker.value);
      for (const [index, item] of [...list.children].entries())
        item.hidden = index !== selectedMedia;
    };
    state?.media.forEach((m, i) => {
      const item = document.createElement('div');
      item.className = 'thanks-item';
      item.hidden = i !== selectedMedia;
      const option = new Option(i + 1 + '. ' + m.filename, String(i));
      picker.add(option);
      picker.value = String(selectedMedia);
      const name = document.createElement('span');
      name.className = 'thanks-name';
      name.textContent = m.filename;
      name.title = m.filename;
      const more = document.createElement('div');
      more.className = 'thanks-capd';
      const captionLabel = document.createElement('span');
      captionLabel.className = 'thanks-field-label';
      captionLabel.textContent = 'Caption';
      const box = document.createElement('textarea');
      box.maxLength = 4000;
      box.rows = 2;
      box.placeholder = 'Caption (optional)';
      box.value = m.caption || '';
      box.setAttribute('aria-label', 'Caption for ' + m.filename);
      box.addEventListener('input', () => {
        m.caption = box.value;
        note('Unsaved changes');
      });
      more.append(captionLabel, box);
      item.append(name, more);
      list.append(item);
    });
    $('thanksRemove').onclick = () => {
      state.media.splice(selectedMedia, 1);
      renderList();
      note('Attachment removed. Save to keep this change.');
    };
    controls();
  }
  const preview = renderList;
  function audience() {
    $('thanksContext').textContent =
      `${state.case_name} · ${state.sent} sent · ${state.pending} waiting` +
      (state.left > 0 ? ' · Finish case to send' : '');
  }
  function fill() {
    $('thanksMessage').value = state.message;
    const c = state.settings;
    $('thanksGap').value = c.gap_minutes;
    $('thanksGapSec').value = c.gap_seconds || 0;
    $('thanksVary').value = c.vary_seconds || 0;
    $('thanksBatch').value = c.batch_size;
    $('thanksRest').value = c.rest_minutes;
    $('thanksRestSec').value = c.rest_seconds || 0;
    for (const k of Object.keys(OPTS)) syncOpt(k, false);
    audience();
    preview();
  }
  const num = (id) => Number($(id).value) || 0;
  /* Timing: a dropdown of common choices per setting; "Custom…" shows the exact minute / second boxes. */
  const OPTS = {
    gap: [10, 20, 30, 60, 120, 180, 300, 600, 900, 1800],
    vary: [0, 5, 10, 15, 30, 60, 120],
    batch: [5, 10, 15, 20, 30, 50],
    rest: [60, 120, 300, 600, 1200, 1800, 3600, 7200],
  };
  // Short visible labels keep all four timing settings readable on a phone.
  const words = (k, v) =>
    k === 'batch'
      ? String(v)
      : v < 60
        ? v + 's'
        : Math.floor(v / 60) + 'm' + (v % 60 ? ' ' + (v % 60) + 's' : '');
  const BOXES = {
    gap: () => num('thanksGap') * 60 + num('thanksGapSec'),
    vary: () => num('thanksVary'),
    batch: () => num('thanksBatch'),
    rest: () => num('thanksRest') * 60 + num('thanksRestSec'),
  };
  const WRITE = {
    gap: (v) => (($('thanksGap').value = Math.floor(v / 60)), ($('thanksGapSec').value = v % 60)),
    vary: (v) => ($('thanksVary').value = v),
    batch: (v) => ($('thanksBatch').value = v),
    rest: (v) => (
      ($('thanksRest').value = Math.floor(v / 60)),
      ($('thanksRestSec').value = v % 60)
    ),
  };
  function syncOpt(k, keepCustom) {
    const sel = $('thanks' + k[0].toUpperCase() + k.slice(1) + 'Sel'),
      box = dialog.querySelector(`[data-k="${k}"] .thanks-custom`),
      v = BOXES[k]();
    sel.value = OPTS[k].includes(v) && !(keepCustom && !box.hidden) ? String(v) : 'custom';
    box.hidden = sel.value !== 'custom';
  }
  for (const k of Object.keys(OPTS)) {
    const sel = $('thanks' + k[0].toUpperCase() + k.slice(1) + 'Sel');
    const label = {gap: 'Gap', vary: 'Vary', batch: 'Batch', rest: 'Rest'}[k];
    for (const v of OPTS[k]) sel.append(new Option(label + ': ' + (k === 'vary' && v ? '±' : '') + words(k, v), v));
    sel.append(new Option(label + ': Custom…', 'custom'));
    sel.addEventListener('change', () => {
      const box = dialog.querySelector(`[data-k="${k}"] .thanks-custom`);
      if (sel.value === 'custom') {
        box.hidden = false; // "Custom…" opens the exact boxes, whatever the current value is
        box.querySelector('input')?.focus();
        return;
      }
      WRITE[k](Number(sel.value));
      box.hidden = true;
    });
    for (const input of dialog.querySelectorAll(`[data-k="${k}"] input`))
      input.addEventListener('input', () => syncOpt(k, true));
  }
  async function save() {
    state = await api('save', {
      case_id: state.case_id,
      revision: state.revision,
      media: state.media.map((m) => ({ id: m.id, filename: m.filename, caption: m.caption || '' })),
      message: $('thanksMessage').value,
    });
    const settings = {
      gap_minutes: num('thanksGap'),
      gap_seconds: num('thanksGapSec'),
      vary_seconds: num('thanksVary'),
      batch_size: num('thanksBatch'),
      rest_minutes: num('thanksRest'),
      rest_seconds: num('thanksRestSec'),
    };
    if (Object.entries(settings).some(([key, value]) => state.settings[key] !== value))
      state = await api('settings', { case_id: state.case_id, settings });
    fill();
  }
  async function action(task, start = false, stop = false) {
    if (busy) return;
    actionVersion++;
    starting = start;
    stopping = stop;
    busy = true;
    controls();
    if (stop) note('Stopping…', 'warning');
    try {
      await task();
    } catch (error) {
      if (start || stop) {
        try {
          const latest = await api();
          if (latest.case_id === state?.case_id) state.on = latest.on;
        } catch (_) {}
      }
      note(error.message, 'error');
    } finally {
      starting = false;
      stopping = false;
      busy = false;
      controls();
    }
  }
  $('thanksSave').onclick = () =>
    action(async () => {
      await save();
      note('Update saved.');
    });
  const startSending = () =>
    action(async () => {
      await save();
      state = await api('start', { case_id: state.case_id, revision: state.revision });
      fill();
      note('Sending. You can close this panel.');
    }, true);
  const pauseSending = () =>
    action(async () => {
      state = await api('stop', { case_id: state.case_id });
      fill();
      note('Paused. An upload already started may finish.', 'warning');
    }, false, true);
  $('thanksSwitch').onclick = () => (state?.on ? pauseSending() : startSending());
  $('thanksTest').onclick = () =>
    action(async () => {
      const button = $('thanksTest');
      button.textContent = 'Testing…';
      note('Sending test…');
      try {
        await save();
        note((await api('test', { case_id: state.case_id })).reply);
      } finally {
        button.textContent = 'Test';
      }
    });
  for (const [id, accept] of [
    ['thanksAttachImg', 'image/jpeg,image/png,image/webp'],
    ['thanksAttachVid', 'video/mp4'],
  ])
    $(id).onclick = () => {
      $('thanksFile').accept = accept;
      $('thanksFile').click();
    };
  $('thanksFile').onchange = () =>
    action(async () => {
      for (const file of [...$('thanksFile').files]) {
        if (state.media.length >= MAX_MEDIA)
          throw Error('At most ' + MAX_MEDIA + ' images or videos.');
        if (file.size > 15000000) throw Error(file.name + ' is over 15 MB.');
        note('Uploading ' + file.name + '…');
        const data = await new Promise((ok, no) => {
          const reader = new FileReader();
          reader.onload = () => ok(reader.result);
          reader.onerror = () => no(Error('Could not read the file.'));
          reader.readAsDataURL(file);
        });
        const response = await fetch('/upload-image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ use: 'bulk', data }),
        });
        const result = await response.json();
        if (!response.ok) throw Error(result.error || 'Upload failed.');
        state.media.push({ id: result.id, filename: file.name, mime: file.type, caption: '' });
        renderList();
      }
      $('thanksFile').value = '';
      note('Media ready. Captions and message are optional.');
    });
  $('thanksMessage').addEventListener('input', () => {
    controls();
    note('Unsaved changes');
    keepFocusedFieldVisible();
  });
  function close() {
    if (busy) return;
    dialog.close();
    viewVersion++;
    clearTimeout(poll);
  }
  $('thanksClose').onclick = close;
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    close();
  });
  async function refresh() {
    if (!dialog.open) return;
    try {
      if (state.on && !busy) {
        const version = actionVersion;
        const latest = await api();
        if (!busy && version === actionVersion && latest.case_id === state.case_id) {
          state = latest;
          audience();
          controls();
          note(state.error || (state.on ? 'Updates are sending.' : 'Updates finished or paused.'), state.error ? 'error' : 'info');
        }
      }
    } catch (_) {}
    poll = setTimeout(refresh, 5000);
  }
  window.DonorThanks = {
    async open() {
      const version = ++viewVersion,
        path = Nav.path();
      try {
        const loaded = await api();
        if (version !== viewVersion || path !== Nav.path() || !window.DonorHub?.isOpen()) return;
        state = loaded;
        for (const details of dialog.querySelectorAll('details')) details.open = false;
        fill();
        note('');
        dialog.showModal();
        refresh();
      } catch (error) {
        const status = document.getElementById('donorNotice');
        if (status) status.textContent = error.message;
      }
    },
  };
  // This is a per-screen sending mode, deliberately off on a fresh page or another tab.
  const mode = document.createElement('label');
  mode.className = 'thanks-row-mode';
  mode.innerHTML =
    '<input type="checkbox" id="thanksDonorMode"><span>Thanks donor</span><small id="thanksRowStatus" role="status" aria-live="polite">Normal saved DM · check to send thanks</small>';
  /* The Donated tab: the "Thanks donor" check, then the start toggle and Test, all in the same one row. */
  const tabRow = document.createElement('div');
  tabRow.className = 'thanks-tab-row';
  const ctl = document.createElement('div');
  ctl.className = 'thanks-tab-ctl';
  ctl.innerHTML =
    '<span id="thanksTabLabel">… donors</span><button type="button" role="switch" id="thanksTabSwitch" aria-checked="false" aria-label="Start sending thank-you updates"><i></i></button><button type="button" id="thanksTabTest" title="Send this update to the GiveLife test group only">Test</button>';
  tabRow.append(mode, ctl);
  document.querySelector('#donorsPage .donor-toolbar')?.after(tabRow);
  const toggle = mode.querySelector('input');
  const directory = document.getElementById('donorsPage');
  let modeCase = null,
    modeBusy = false;
  const modeNotice = (text) => {
    const target = mode.querySelector('#thanksRowStatus');
    if (target) target.textContent = text;
  };
  function paintMode() {
    const on = toggle.checked && !!modeCase;
    directory.toggleAttribute('data-thanks-mode', on);
    for (const dm of directory.querySelectorAll('#donorRows .donor-dm')) {
      if (on) {
        if (!dm.dataset.thanksOriginalLabel)
          dm.dataset.thanksOriginalLabel = dm.getAttribute('aria-label') || 'Send saved DM';
        dm.setAttribute(
          'aria-label',
          dm.dataset.thanksOriginalLabel.replace('Send saved DM', 'Send saved thanks'),
        );
      } else if (dm.dataset.thanksOriginalLabel) {
        dm.setAttribute('aria-label', dm.dataset.thanksOriginalLabel);
        delete dm.dataset.thanksOriginalLabel;
      }
    }
  }
  function resetMode() {
    toggle.checked = false;
    modeCase = null;
    paintMode();
    modeNotice('Normal saved DM · check to send thanks');
  }
  toggle.onchange = async () => {
    if (!toggle.checked) {
      resetMode();
      return;
    }
    toggle.disabled = true;
    try {
      const saved = await api();
      if (directory.dataset.panel !== 'donated') return resetMode();
      if (saved.left > 0) throw Error('Finish this case before sending thank-you updates.');
      if (!saved.media.length && !saved.message.trim())
        throw Error('Open Thank donors and save your update first.');
      modeCase = saved.case_id;
      paintMode();
      modeNotice('Saved thank-you update · one donor per click');
    } catch (error) {
      resetMode();
      modeNotice(error.message);
    } finally {
      toggle.disabled = false;
    }
  };
  new MutationObserver(() => {
    if (directory.dataset.panel !== 'donated') resetMode();
  }).observe(directory, { attributes: true, attributeFilter: ['data-panel'] });
  new MutationObserver(() => {
    if (modeCase) paintMode();
  }).observe(document.getElementById('donorRows'), { childList: true, subtree: true });
  window.DonorThanks.rowMode = () => toggle.checked && !!modeCase;
  window.DonorThanks.sendOne = async (ident) => {
    if (modeBusy) return;
    modeBusy = true;
    toggle.disabled = true;
    try {
      const saved = await api();
      if (saved.case_id !== modeCase) {
        resetMode();
        throw Error(
          'The case changed. Check the saved thank-you update and turn Thanks donor on again.',
        );
      }
      const result = await api('send_one', {
        case_id: saved.case_id,
        revision: saved.revision,
        id: ident,
      });
      const name = result.recipients.find((r) => r.id === ident)?.name || 'this donor';
      modeNotice(
        'Sending the saved thank-you update to ' +
          name +
          '. Check Thank donors for delivery status.',
      );
    } catch (error) {
      modeNotice(error.message);
    } finally {
      modeBusy = false;
      toggle.disabled = false;
    }
  };
  let tabState = null,
    tabBusy = false,
    tabStarting = false,
    tabStopping = false,
    tabActionVersion = 0;
  const tabSwitch = ctl.querySelector('#thanksTabSwitch'),
    tabTest = ctl.querySelector('#thanksTabTest'),
    tabLabel = ctl.querySelector('#thanksTabLabel');
  const hasUpdate = () => !!tabState && !!(tabState.media.length || tabState.message.trim());
  function paintTab() {
    const on = !tabStopping && (!!tabState?.on || tabStarting);
    tabSwitch.setAttribute('aria-checked', String(on));
    tabSwitch.setAttribute('aria-busy', String(tabStarting || tabStopping));
    tabSwitch.setAttribute('aria-label', tabStopping ? 'Stopping thank-you updates' : tabStarting ? 'Starting thank-you updates' : on ? 'Stop sending thank-you updates' : 'Start sending thank-you updates');
    tabSwitch.disabled =
      tabBusy || !tabState || (!on && (tabState.left > 0 || tabState.pending === 0));
    tabTest.disabled = tabBusy || !tabState;
    tabLabel.textContent = tabStopping
      ? 'Stopping…'
      : tabStarting
      ? 'Starting…'
      : !tabState
      ? '… donors'
      : on
        ? `${tabState.sent}/${tabState.total} sent`
        : `${tabState.pending} donors`;
  }
  async function loadTab() {
    if (directory.dataset.panel !== 'donated' || tabBusy) return;
    try {
      const version = tabActionVersion;
      const latest = await api();
      if (tabBusy || version !== tabActionVersion) return;
      tabState = latest;
      paintTab();
    } catch (_) {}
  }
  const needsSaved = () => {
    if (hasUpdate()) return false;
    modeNotice('Open Thank donors and save your update first.');
    window.DonorThanks.open();
    return true;
  };
  tabSwitch.onclick = async () => {
    if (tabBusy || !tabState) return;
    tabActionVersion++;
    tabBusy = true;
    tabStopping = !!tabState.on;
    tabStarting = !tabState.on && hasUpdate() && tabState.left <= 0;
    if (tabStarting) modeNotice('Starting…');
    if (tabStopping) modeNotice('Stopping…');
    paintTab();
    try {
      if (tabState.on) {
        tabState = await api('stop', { case_id: tabState.case_id });
        modeNotice('Paused. An upload already started may finish.');
      } else if (!needsSaved()) {
        if (tabState.left > 0) throw Error('Finish this case before sending thank-you updates.');
        tabState = await api('start', { case_id: tabState.case_id, revision: tabState.revision });
        modeNotice('Sending the saved update to every donor, at your timing.');
      }
    } catch (error) {
      if (tabStarting || tabStopping) {
        try { tabState = await api(); } catch (_) {}
      }
      modeNotice(error.message);
    } finally {
      tabStarting = false;
      tabStopping = false;
      tabBusy = false;
      paintTab();
    }
  };
  tabTest.onclick = async () => {
    if (tabBusy || !tabState || needsSaved()) return;
    tabActionVersion++;
    tabBusy = true;
    tabTest.textContent = 'Testing…';
    modeNotice('Sending test…');
    paintTab();
    try {
      modeNotice((await api('test', { case_id: tabState.case_id })).reply);
    } catch (error) {
      modeNotice(error.message);
    } finally {
      tabTest.textContent = 'Test';
      tabBusy = false;
      paintTab();
    }
  };
  new MutationObserver(loadTab).observe(directory, {
    attributes: true,
    attributeFilter: ['data-panel'],
  });
  setInterval(loadTab, 5000);
  loadTab();
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'donor-thanks';
  button.textContent = 'Thank donors';
  button.onclick = () => window.DonorThanks.open();
  const bar = document.querySelector('#donorsPage .donor-bottom');
  bar?.insertBefore(button, document.getElementById('donorSendImportant'));
})();
