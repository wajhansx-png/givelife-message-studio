/* Completion proof, its attached caption, and an optional independent message. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'donorThanksDialog';
  dialog.setAttribute('aria-labelledby', 'thanksTitle');
  dialog.innerHTML = `<header><div><h2 id="thanksTitle" tabindex="-1" autofocus>Thank donors</h2><small id="thanksContext"></small></div></header>
  <div class="thanks-body"><section class="thanks-compose">
    <div class="thanks-media">
      <div class="thanks-slot" data-slot="1"><button type="button" class="thanks-attach" id="thanksAttachImg">Attach image</button><div class="thanks-attached" hidden><span class="thanks-name"></span><button type="button" class="thanks-remove" aria-label="Remove image">Remove</button><details class="thanks-capd"><summary>+ Caption</summary><textarea id="thanksCaption" aria-label="Caption" maxlength="4000" rows="2" placeholder="Caption (optional)"></textarea></details></div></div>
      <div class="thanks-slot" data-slot="2"><button type="button" class="thanks-attach" id="thanksAttachVid">Attach video</button><div class="thanks-attached" hidden><span class="thanks-name"></span><button type="button" class="thanks-remove" aria-label="Remove video">Remove</button><details class="thanks-capd"><summary>+ Caption</summary><textarea id="thanksCaption2" aria-label="Video caption" maxlength="4000" rows="2" placeholder="Caption (optional)"></textarea></details></div></div>
    </div>
    <input id="thanksFile" type="file" aria-label="Attach file" accept="image/jpeg,image/png,image/webp,video/mp4" hidden>
    <details class="thanks-msg"><summary>+ Message</summary>
      <label for="thanksMessage">Message</label><textarea id="thanksMessage" aria-describedby="thanksNameHint" maxlength="4000" rows="4" placeholder="Write a thank-you message…"></textarea>
      <small id="thanksNameHint">Use {name} for their first name. Sent after any attachment.</small>
    </details>
    <section class="thanks-timing"><b>Timing</b>
      <div class="thanks-grid">
        <div class="thanks-opt" data-k="gap"><label>Gap between donors<select id="thanksGapSel"></select></label><div class="thanks-custom" hidden><label>min<input id="thanksGap" type="number" min="0" max="1440" inputmode="numeric"></label><label>sec<input id="thanksGapSec" type="number" min="0" max="59" inputmode="numeric"></label></div></div>
        <div class="thanks-opt" data-k="vary"><label>Vary gap by ±<select id="thanksVarySel"></select></label><div class="thanks-custom" hidden><label>sec<input id="thanksVary" type="number" min="0" max="300" inputmode="numeric"></label></div></div>
        <div class="thanks-opt" data-k="batch"><label>Donors per batch<select id="thanksBatchSel"></select></label><div class="thanks-custom" hidden><label>donors<input id="thanksBatch" type="number" min="1" max="100" inputmode="numeric"></label></div></div>
        <div class="thanks-opt" data-k="rest"><label>Rest after a batch<select id="thanksRestSel"></select></label><div class="thanks-custom" hidden><label>min<input id="thanksRest" type="number" min="0" max="1440" inputmode="numeric"></label><label>sec<input id="thanksRestSec" type="number" min="0" max="59" inputmode="numeric"></label></div></div>
      </div></section>
  </section></div>
  <div class="thanks-start"><span id="thanksStartLabel">Start sending</span><button type="button" role="switch" id="thanksSwitch" aria-checked="false" aria-label="Start sending the thank-you updates"><i></i></button></div><p id="thanksStatus" role="status" aria-live="polite"></p><footer><button type="button" id="thanksSave">Save</button><button type="button" id="thanksTest" title="Send this to the GiveLife test group only">Test</button><button type="button" id="thanksClose" aria-label="Close Thank donors">Back</button></footer>`;
  document.body.append(dialog);
  const $ = (id) => dialog.querySelector('#' + id);
  let state,
    viewVersion = 0,
    busy = false,
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
  const note = (text) => ($('thanksStatus').textContent = text);
  function controls() {
    for (const field of dialog.querySelectorAll('input,textarea'))
      field.disabled = busy || state?.on;
    for (const sel of dialog.querySelectorAll('select')) sel.disabled = busy || state?.on;
    $('thanksSave').disabled = busy || state?.on;
    $('thanksTest').disabled =
      busy || !state || (!state.attachment && !state.attachment2 && !$('thanksMessage').value.trim());
    const on = !!state?.on;
    $('thanksSwitch').setAttribute('aria-checked', String(on));
    $('thanksSwitch').disabled =
      busy ||
      !state ||
      (!on &&
        (state.left > 0 ||
          (!state.attachment && !state.attachment2 && !$('thanksMessage').value.trim()) ||
          state.pending === 0));
    $('thanksStartLabel').textContent = on
      ? 'Sending · switch off to pause'
      : state
        ? 'Send to ' + state.pending + ' donors'
        : 'Start sending';
    for (const b of dialog.querySelectorAll('.thanks-remove, .thanks-attach')) b.disabled = busy || state?.on;
  }
  /* Two attachment slots (an image and a video), each with its own optional caption. */
  const SLOTS = [
    { n: 1, att: 'attachment', file: 'filename', mime: 'mime', cap: 'thanksCaption', accept: 'image/jpeg,image/png,image/webp' },
    { n: 2, att: 'attachment2', file: 'filename2', mime: 'mime2', cap: 'thanksCaption2', accept: 'video/mp4' },
  ];
  const slotBox = (sl) => dialog.querySelector(`[data-slot="${sl.n}"]`);
  let slot = SLOTS[0];
  function preview() {
    for (const sl of SLOTS) {
      const has = !!state?.[sl.att];
      slotBox(sl).querySelector('.thanks-attach').hidden = has;
      slotBox(sl).querySelector('.thanks-attached').hidden = !has;
      slotBox(sl).querySelector('.thanks-name').textContent = has ? state[sl.file] : '';
    }
    controls();
  }
  function audience() {
    $('thanksContext').textContent =
      `${state.case_name} · ${state.total} donors` +
      (state.sent ? ` · ${state.sent} sent · ${state.pending} waiting` : '') +
      (state.left > 0 ? ' · Finish case to send' : '');
  }
  function fill() {
    $('thanksCaption').value = state.caption;
    $('thanksCaption2').value = state.caption2 || '';
    for (const sl of SLOTS) slotBox(sl).querySelector('.thanks-capd').open = !!$(sl.cap).value; // a saved caption shows itself
    $('thanksMessage').value = state.message;
    if (state.message) dialog.querySelector('.thanks-msg').open = true; // a saved message shows itself
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
  const words = (k, v) =>
    k === 'batch'
      ? v + ' donors'
      : k === 'vary' && !v
        ? 'No variation'
        : v < 60
          ? v + ' sec'
          : Math.floor(v / 60) + ' min' + (v % 60 ? ' ' + (v % 60) + ' sec' : '');
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
    rest: (v) => (($('thanksRest').value = Math.floor(v / 60)), ($('thanksRestSec').value = v % 60)),
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
    for (const v of OPTS[k]) sel.append(new Option(words(k, v), v));
    sel.append(new Option('Custom…', 'custom'));
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
      attachment: state.attachment,
      filename: state.filename,
      attachment2: state.attachment2 || null,
      filename2: state.filename2 || '',
      caption2: $('thanksCaption2').value,
      caption: $('thanksCaption').value,
      message: $('thanksMessage').value,
    });
    state = await api('settings', {
      case_id: state.case_id,
      settings: {
        gap_minutes: num('thanksGap'),
        gap_seconds: num('thanksGapSec'),
        vary_seconds: num('thanksVary'),
        batch_size: num('thanksBatch'),
        rest_minutes: num('thanksRest'),
        rest_seconds: num('thanksRestSec'),
      },
    });
    fill();
  }
  async function action(task) {
    if (busy) return;
    busy = true;
    controls();
    try {
      await task();
    } catch (error) {
      note(error.message);
    } finally {
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
    });
  const pauseSending = () =>
    action(async () => {
      state = await api('stop', { case_id: state.case_id });
      fill();
      note('Paused. An upload already started may finish.');
    });
  $('thanksSwitch').onclick = () => (state?.on ? pauseSending() : startSending());
  $('thanksTest').onclick = () =>
    action(async () => {
      await save();
      note((await api('test', { case_id: state.case_id })).reply);
    });
  for (const sl of SLOTS)
    slotBox(sl).querySelector('.thanks-attach').onclick = () => {
      slot = sl;
      $('thanksFile').accept = sl.accept;
      $('thanksFile').click();
    };
  $('thanksFile').onchange = () =>
    action(async () => {
      const file = $('thanksFile').files[0];
      if (!file) return;
      if (file.size > 15000000) throw Error('Choose a file under 15 MB.');
      note('Uploading privately…');
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
      state[slot.att] = result.id;
      state[slot.mime] = file.type;
      state[slot.file] = file.name;
      slot = SLOTS[0];
      preview();
      note('Media ready. Caption and message are optional.');
    });
  for (const sl of SLOTS)
    slotBox(sl).querySelector('.thanks-remove').onclick = () => {
      state[sl.att] = null;
      state[sl.mime] = '';
      state[sl.file] = '';
      $('thanksFile').value = '';
      $(sl.cap).value = '';
      slotBox(sl).querySelector('.thanks-capd').open = false;
      preview();
      note('Attachment removed. Save to keep this change.');
    };
  for (const id of ['thanksCaption', 'thanksCaption2', 'thanksMessage'])
    $(id).addEventListener('input', () => {
      preview();
      note('Unsaved changes');
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
        const latest = await api();
        if (latest.case_id === state.case_id) {
          state = latest;
          audience();
          controls();
          note(state.error || (state.on ? 'Updates are sending.' : 'Updates finished or paused.'));
        }
      }
    } catch (_) {}
    poll = setTimeout(refresh, 5000);
  }
  window.DonorThanks = {
    async open() {
      const version = ++viewVersion;
      try {
        const loaded = await api();
        if (version !== viewVersion) return;
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
      if (!saved.attachment && !saved.message.trim())
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
    tabBusy = false;
  const tabSwitch = ctl.querySelector('#thanksTabSwitch'),
    tabTest = ctl.querySelector('#thanksTabTest'),
    tabLabel = ctl.querySelector('#thanksTabLabel');
  const hasUpdate = () => !!tabState && !!(tabState.attachment || tabState.attachment2 || tabState.message.trim());
  function paintTab() {
    const on = !!tabState?.on;
    tabSwitch.setAttribute('aria-checked', String(on));
    tabSwitch.disabled = tabBusy || !tabState || (!on && (tabState.left > 0 || tabState.pending === 0));
    tabTest.disabled = tabBusy || !tabState;
    tabLabel.textContent = !tabState
      ? '… donors'
      : on
        ? `${tabState.sent}/${tabState.total} sent`
        : `${tabState.pending} donors`;
  }
  async function loadTab() {
    if (directory.dataset.panel !== 'donated' || tabBusy) return;
    try {
      tabState = await api();
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
    tabBusy = true;
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
      modeNotice(error.message);
    } finally {
      tabBusy = false;
      paintTab();
    }
  };
  tabTest.onclick = async () => {
    if (tabBusy || !tabState || needsSaved()) return;
    tabBusy = true;
    paintTab();
    try {
      modeNotice((await api('test', { case_id: tabState.case_id })).reply);
    } catch (error) {
      modeNotice(error.message);
    } finally {
      tabBusy = false;
      paintTab();
    }
  };
  new MutationObserver(loadTab).observe(directory, { attributes: true, attributeFilter: ['data-panel'] });
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
