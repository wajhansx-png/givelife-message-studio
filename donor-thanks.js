/* Completion proof, its attached caption, and an optional independent message. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'donorThanksDialog';
  dialog.setAttribute('aria-labelledby', 'thanksTitle');
  dialog.innerHTML = `<header><div><h2 id="thanksTitle">Thank donors</h2><small id="thanksContext"></small></div><button type="button" id="thanksClose" aria-label="Close Thank donors">×</button></header>
  <div class="thanks-body"><section class="thanks-compose">
    <label for="thanksFile">Photo, video or document <small>Optional · up to 15 MB</small></label>
    <input id="thanksFile" type="file" accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf">
    <div class="thanks-file-row"><span id="thanksFileName">No media</span><button type="button" id="thanksRemove" hidden>Remove media</button></div>
    <div id="thanksCaptionWrap" hidden><label for="thanksCaption">Caption on the media</label><textarea id="thanksCaption" maxlength="4000" rows="3" placeholder="Optional. Appears below the photo, video or document."></textarea></div>
    <label for="thanksMessage">Separate message <small>Optional with media</small></label><textarea id="thanksMessage" maxlength="4000" rows="4" placeholder="A separate message after the attachment, or text alone. Use {name} for their first name."></textarea>
    <details class="thanks-timing"><summary>Sending pace <span id="thanksPace"></span></summary><div><label>Gap (minutes)<input id="thanksGap" type="number" min="1" max="1440"></label><label>Donors per batch<input id="thanksBatch" type="number" min="1" max="100"></label><label>Batch rest (minutes)<input id="thanksRest" type="number" min="1" max="1440"></label></div></details>
  </section><details class="thanks-review" open><summary>Preview &amp; recipients</summary><small>Media + its caption first. Separate message follows.</small><div id="thanksPreview" aria-label="Message preview"></div><details><summary id="thanksAudience">Donors for this case</summary><ul id="thanksRecipients"></ul></details></details></div>
  <p id="thanksStatus" role="status" aria-live="polite"></p><footer><button type="button" id="thanksSave">Save update</button><button type="button" id="thanksSend" class="primary">Send update</button><button type="button" id="thanksPause" hidden>Pause updates</button></footer>`;
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
    if (!box.children.length)
      box.textContent = 'Add media or write a message to preview your update.';
    $('thanksCaptionWrap').hidden = !state?.attachment;
    $('thanksRemove').hidden = !state?.attachment;
    $('thanksFile').hidden = !!state?.attachment;
    $('thanksFileName').textContent = state?.attachment ? state.filename : 'No media';
    controls();
  }
  function audience() {
    $('thanksAudience').textContent =
      `${state.total} donors · ${state.sent} updated · ${state.pending} waiting`;
    $('thanksRecipients').replaceChildren(
      ...state.recipients.map((row) => {
        const li = document.createElement('li');
        li.textContent = row.name + ' · ' + (row.state === 'Sent' ? 'Update sent' : row.state);
        return li;
      }),
    );
    $('thanksContext').textContent =
      state.case_name +
      ' · ' +
      (state.left > 0
        ? 'Prepare now. Sending unlocks when this case is complete.'
        : 'Completed · only donors who donated to this case');
    $('thanksSend').textContent = 'Send to ' + state.pending + ' donors';
  }
  function fill() {
    $('thanksCaption').value = state.caption;
    $('thanksMessage').value = state.message;
    $('thanksGap').value = state.settings.gap_minutes;
    $('thanksBatch').value = state.settings.batch_size;
    $('thanksRest').value = state.settings.rest_minutes;
    $('thanksPace').textContent =
      `${state.settings.gap_minutes} min · ${state.settings.batch_size} donors · ${state.settings.rest_minutes} min rest`;
    audience();
    preview();
  }
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
        gap_minutes: Number($('thanksGap').value),
        batch_size: Number($('thanksBatch').value),
        rest_minutes: Number($('thanksRest').value),
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
      note('Update saved. You can send it here or turn on Thanks donors in Report.');
    });
  $('thanksSend').onclick = () =>
    action(async () => {
      await save();
      state = await api('start', { case_id: state.case_id, revision: state.revision });
      fill();
      note('Sending with your saved pace. You can close this panel.');
    });
  $('thanksPause').onclick = () =>
    action(async () => {
      state = await api('stop', { case_id: state.case_id });
      fill();
      note('Paused. An upload already started may finish.');
    });
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
      note('Media ready. Add a caption, a separate message, or send the media alone.');
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
    note('Media and its caption removed. Save to keep this change.');
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
        dialog.querySelector('.thanks-review').open = matchMedia('(min-width: 651px)').matches;
        fill();
        note('Review your update and recipients before sending.');
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
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'donor-thanks';
  button.textContent = 'Thank donors';
  button.onclick = () => window.DonorThanks.open();
  const bar = document.querySelector('#donorsPage .donor-bottom');
  bar?.insertBefore(button, document.getElementById('donorSendImportant'));
})();
