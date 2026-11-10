/* Completion proof, its attached caption, and an optional independent message. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'donorThanksDialog';
  dialog.setAttribute('aria-labelledby', 'thanksTitle');
  dialog.innerHTML = `<header><div><h2 id="thanksTitle" tabindex="-1" autofocus>Thank donors</h2><small id="thanksContext"></small></div></header>
  <div class="thanks-body"><section class="thanks-compose">
    <label for="thanksMessage">Message</label><textarea id="thanksMessage" aria-describedby="thanksNameHint" maxlength="4000" rows="4" placeholder="Write a thank-you message…"></textarea>
    <small id="thanksNameHint">Use {name} for their first name. Sent after any attachment.</small>
    <div class="thanks-attach-row"><button type="button" id="thanksAttach">+ Attach file</button><small id="thanksFileHint">Photo, video or PDF</small></div>
    <input id="thanksFile" type="file" aria-label="Attach file" accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf" hidden>
    <div class="thanks-file-row" hidden><span id="thanksFileName"></span><button type="button" id="thanksRemove" hidden>Remove</button></div>
    <div id="thanksCaptionWrap" hidden><label for="thanksCaption">Caption</label><textarea id="thanksCaption" maxlength="4000" rows="2" placeholder="Optional · shown with the attachment"></textarea></div>
    <details class="thanks-review"><summary>Preview</summary><div id="thanksPreview" aria-label="Message preview"></div><details><summary id="thanksAudience">Recipients</summary><ul id="thanksRecipients"></ul></details></details>
    <section class="thanks-timing"><div class="thanks-pace-row"><b>Timing</b> <span id="thanksPace"></span></div>
      <div class="thanks-presets" role="group" aria-label="Quick speed"><button type="button" data-preset="fast">Fast</button><button type="button" data-preset="normal">Normal</button><button type="button" data-preset="slow">Slow</button></div>
      <details class="thanks-custom"><summary>Custom</summary><div class="thanks-grid">
        <fieldset><legend>Gap</legend><label>min<input id="thanksGap" type="number" min="0" max="1440" inputmode="numeric"></label><label>sec<input id="thanksGapSec" type="number" min="0" max="59" inputmode="numeric"></label></fieldset>
        <label>± vary (sec)<input id="thanksVary" type="number" min="0" max="300" inputmode="numeric"></label>
        <label>Batch of<input id="thanksBatch" type="number" min="1" max="100" inputmode="numeric"></label>
        <fieldset><legend>Rest</legend><label>min<input id="thanksRest" type="number" min="0" max="1440" inputmode="numeric"></label><label>sec<input id="thanksRestSec" type="number" min="0" max="59" inputmode="numeric"></label></fieldset>
      </div></details></section>
  </section></div>
  <p id="thanksStatus" role="status" aria-live="polite"></p><footer><button type="button" id="thanksSave">Save</button><button type="button" id="thanksTest" title="Send this to the GiveLife test group only">Test</button><button type="button" id="thanksSend" class="primary">Send</button><button type="button" id="thanksPause" hidden>Pause</button><button type="button" id="thanksClose" aria-label="Close Thank donors">Back</button></footer>`;
  document.body.append(dialog);
  const $ = (id) => dialog.querySelector('#' + id);
  let state,
    viewVersion = 0,
    busy = false,
    previewURL,
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
    $('thanksSave').disabled = busy || state?.on;
    $('thanksTest').disabled = busy || !state || (!state.attachment && !$('thanksMessage').value.trim());
    $('thanksSend').hidden = !!state?.on;
    $('thanksSend').disabled =
      busy ||
      !state ||
      state.left > 0 ||
      (!state.attachment && !$('thanksMessage').value.trim()) ||
      state.pending === 0;
    $('thanksPause').hidden = !state?.on;
    $('thanksPause').disabled = busy;
    $('thanksRemove').disabled = busy || state?.on;
    $('thanksAttach').disabled = busy || state?.on;
  }
  function preview() {
    const box = $('thanksPreview');
    box.replaceChildren();
    if (state?.attachment) {
      const bubble = document.createElement('div');
      bubble.className = 'thanks-bubble';
      if (previewURL) {
        const media = document.createElement(
          state.mime.startsWith('image/') ? 'img' : state.mime.startsWith('video/') ? 'video' : 'a',
        );
        if (media.tagName === 'A') {
          media.href = previewURL;
          media.textContent = '📄 ' + state.filename;
          media.target = '_blank';
          media.rel = 'noopener';
        } else {
          media.src = previewURL;
          if (media.tagName === 'VIDEO') media.controls = true;
          else media.alt = 'Completion proof';
        }
        bubble.append(media);
      } else {
        const name = document.createElement('strong');
        name.textContent = state.filename;
        bubble.append(name);
      }
      if ($('thanksCaption').value) {
        const caption = document.createElement('p');
        caption.textContent = $('thanksCaption').value;
        bubble.append(caption);
      }
      box.append(bubble);
    }
    if ($('thanksMessage').value) {
      const text = document.createElement('p');
      text.className = 'thanks-bubble';
      text.textContent = $('thanksMessage').value;
      box.append(text);
    }
    if (!box.children.length) box.textContent = 'Your message or attachment will appear here.';
    $('thanksCaptionWrap').hidden = !state?.attachment;
    $('thanksRemove').hidden = !state?.attachment;
    $('thanksAttach').hidden = !!state?.attachment;
    $('thanksFileHint').hidden = !!state?.attachment;
    dialog.querySelector('.thanks-file-row').hidden = !state?.attachment;
    $('thanksFileName').textContent = state?.attachment ? state.filename : '';
    controls();
  }
  function audience() {
    $('thanksAudience').textContent =
      `${state.total} recipients` +
      (state.sent ? ` · ${state.sent} sent · ${state.pending} waiting` : '');
    $('thanksRecipients').replaceChildren(
      ...state.recipients.map((row) => {
        const li = document.createElement('li');
        li.textContent = row.name + ' · ' + (row.state === 'Sent' ? 'Update sent' : row.state);
        return li;
      }),
    );
    $('thanksContext').textContent =
      `${state.case_name} · ${state.total} donors` +
      (state.left > 0 ? ' · Finish case to send' : '');
    $('thanksSend').textContent = 'Send to ' + state.pending;
  }
  function fill() {
    $('thanksCaption').value = state.caption;
    $('thanksMessage').value = state.message;
    const c = state.settings;
    $('thanksGap').value = c.gap_minutes;
    $('thanksGapSec').value = c.gap_seconds || 0;
    $('thanksVary').value = c.vary_seconds || 0;
    $('thanksBatch').value = c.batch_size;
    $('thanksRest').value = c.rest_minutes;
    $('thanksRestSec').value = c.rest_seconds || 0;
    pace();
    audience();
    preview();
  }
  /* The timing in one short line, and the three quick speeds. */
  const num = (id) => Number($(id).value) || 0;
  const dur = (m, s) => (m ? m + ' min' : '') + (m && s ? ' ' : '') + (s || !m ? s + ' sec' : '');
  function pace() {
    $('thanksPace').textContent =
      dur(num('thanksGap'), num('thanksGapSec')) +
      ' apart' +
      (num('thanksVary') ? ' ±' + num('thanksVary') + 's' : '') +
      ' · batches of ' +
      num('thanksBatch');
  }
  const PRESETS = {
    fast: [0, 30, 10, 20, 5, 0],
    normal: [5, 0, 30, 10, 20, 0],
    slow: [10, 0, 60, 5, 30, 0],
  };
  for (const b of dialog.querySelectorAll('[data-preset]'))
    b.addEventListener('click', () => {
      const [gm, gs, vary, batch, rm, rs] = PRESETS[b.dataset.preset];
      for (const [id, v] of [
        ['thanksGap', gm],
        ['thanksGapSec', gs],
        ['thanksVary', vary],
        ['thanksBatch', batch],
        ['thanksRest', rm],
        ['thanksRestSec', rs],
      ])
        $(id).value = v;
      pace();
    });
  for (const id of ['thanksGap', 'thanksGapSec', 'thanksVary', 'thanksBatch', 'thanksRest', 'thanksRestSec'])
    $(id).addEventListener('input', pace);
  async function save() {
    state = await api('save', {
      case_id: state.case_id,
      revision: state.revision,
      attachment: state.attachment,
      filename: state.filename,
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
  $('thanksSend').onclick = () =>
    action(async () => {
      await save();
      state = await api('start', { case_id: state.case_id, revision: state.revision });
      fill();
      note('Sending. You can close this panel.');
    });
  $('thanksTest').onclick = () =>
    action(async () => {
      await save();
      note((await api('test', { case_id: state.case_id })).reply);
    });
  $('thanksPause').onclick = () =>
    action(async () => {
      state = await api('stop', { case_id: state.case_id });
      fill();
      note('Paused. An upload already started may finish.');
    });
  $('thanksAttach').onclick = () => $('thanksFile').click();
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
      if (previewURL) URL.revokeObjectURL(previewURL);
      previewURL = URL.createObjectURL(file);
      state.attachment = result.id;
      state.mime = file.type;
      state.filename = file.name;
      preview();
      note('Media ready. Caption and message are optional.');
    });
  $('thanksRemove').onclick = () => {
    state.attachment = null;
    state.mime = '';
    state.filename = '';
    $('thanksFile').value = '';
    $('thanksCaption').value = '';
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null;
    preview();
    note('Attachment removed. Save to keep this change.');
  };
  for (const id of ['thanksCaption', 'thanksMessage'])
    $(id).addEventListener('input', () => {
      preview();
      note('Unsaved changes');
    });
  function close() {
    if (busy) return;
    dialog.close();
    viewVersion++;
    clearTimeout(poll);
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null;
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
        if (state.attachment) {
          const r = await fetch('/thanks-media/' + state.attachment);
          if (r.ok) {
            const blob = await r.blob();
            if (!dialog.open || version !== viewVersion) return;
            previewURL = URL.createObjectURL(blob);
            preview();
          }
        }
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
  document.querySelector('#donorsPage .donor-toolbar')?.after(mode);
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
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'donor-thanks';
  button.textContent = 'Thank donors';
  button.onclick = () => window.DonorThanks.open();
  const bar = document.querySelector('#donorsPage .donor-bottom');
  bar?.insertBefore(button, document.getElementById('donorSendImportant'));
})();
