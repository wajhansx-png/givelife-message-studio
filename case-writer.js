/* A persistent case brief and an independently editable message. Generation never sends. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'caseWriterDialog';
  dialog.setAttribute('aria-labelledby', 'caseWriterTitle');
  dialog.innerHTML = `<header><h2 id="caseWriterTitle">Write Case</h2><span id="caseWriterContext"></span></header>
    <div class="case-writer-workspace">
      <section><label for="caseWriterDetails">Case details</label>
        <textarea id="caseWriterDetails" maxlength="12000" placeholder="Who needs help? What happened, what is needed, and which facts should the message include?"></textarea>
        <label for="caseWriterStyle">Writing style</label>
        <select id="caseWriterStyle"><option value="ur_en">Urdu + English</option><option value="ur_en_more">Urdu + English · stronger</option><option value="en">English</option><option value="en_more">English · stronger</option></select>
        <small>Edit these details before or after generating. They stay saved for this case.</small></section>
      <section><label for="caseWriterMessage">Generated message <small>Editable</small></label>
        <textarea id="caseWriterMessage" maxlength="10000" placeholder="Your message appears here. You can edit it before using it."></textarea>
        <small id="caseWriterLearning"></small></section>
    </div>
    <p id="caseWriterStatus" role="status" aria-live="polite"></p>
    <footer><button type="button" id="caseWriterBack">Back</button><button type="button" class="primary" id="caseWriterGenerate">Generate message</button><button type="button" id="caseWriterUse">Use message</button></footer>`;
  document.body.append(dialog);
  const $ = (id) => dialog.querySelector('#' + id);
  let state,
    savedSnapshot = '',
    saves = Promise.resolve(),
    timer,
    busy = false,
    edits = 0;
  const fields = () => ({
    details: $('caseWriterDetails').value,
    text: $('caseWriterMessage').value,
    style: $('caseWriterStyle').value,
  });
  const status = (text) => {
    $('caseWriterStatus').textContent = text;
  };
  const cacheKey = () => 'givelife-case-writer-' + state.case_id;
  function cache() {
    try {
      sessionStorage.setItem(cacheKey(), JSON.stringify({ ...fields(), at: Date.now() / 1000 }));
    } catch (_) {
      /* Server saving still works. */
    }
  }
  function clearCache() {
    try {
      sessionStorage.removeItem(cacheKey());
    } catch (_) {}
  }
  async function request(action, payload) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 110000);
    try {
      const response = await fetch('/case-message', {
        ...(action
          ? {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ action, ...payload }),
            }
          : {}),
        signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok)
        throw Error(result.error || 'Could not save this case draft. Your text is still here.');
      return result;
    } catch (error) {
      if (error.name === 'AbortError')
        throw Error(
          'Writing took too long. Your case notes are saved. Reopen Write Case to check the result.',
        );
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
  function controls() {
    $('caseWriterGenerate').disabled = busy || !fields().details.trim();
    $('caseWriterGenerate').textContent = busy
      ? 'Writing…'
      : state?.text
        ? 'Regenerate message'
        : 'Generate message';
    $('caseWriterUse').disabled =
      busy ||
      !fields().text.trim() ||
      fields().details !== state?.generated_details ||
      fields().style !== state?.generated_style;
  }
  function saveNow() {
    clearTimeout(timer);
    const data = fields(),
      serial = edits;
    const next = saves
      .catch(() => {})
      .then(async () => {
        if (JSON.stringify(data) === savedSnapshot) return state;
        const result = await request('save', {
          ...data,
          case_id: state.case_id,
          revision: state.revision,
        });
        state = result;
        savedSnapshot = JSON.stringify(data);
        if (serial === edits) {
          clearCache();
          if (!busy) status('Saved');
        }
        controls();
        return state;
      });
    saves = next;
    return next;
  }
  function changed() {
    edits++;
    cache();
    controls();
    status(busy ? 'You can keep editing. Changed details will need a new generation.' : 'Saving…');
    clearTimeout(timer);
    timer = setTimeout(() => saveNow().catch((error) => status(error.message)), 400);
  }
  for (const id of ['caseWriterDetails', 'caseWriterMessage', 'caseWriterStyle'])
    $(id).addEventListener('input', changed);
  $('caseWriterGenerate').onclick = async () => {
    if (busy) return;
    busy = true;
    controls();
    try {
      await saveNow();
      const serial = edits;
      status('Writing in your saved style… Your case details stay editable.');
      const result = await request('generate', {
        ...fields(),
        case_id: state.case_id,
        revision: state.revision,
      });
      if (serial !== edits) {
        await saves.catch(() => {});
        state = await request();
        savedSnapshot = JSON.stringify({
          details: state.details,
          text: state.text,
          style: state.style,
        });
        await saveNow();
        status('The details changed while writing. Your edits are kept; generate again.');
        return;
      }
      state = result;
      $('caseWriterMessage').value = result.text;
      savedSnapshot = JSON.stringify(fields());
      clearCache();
      $('caseWriterLearning').textContent =
        result.saved_messages + ' messages saved · your edits guide future writing';
      status('Message saved. Edit either side, or use this message in Messages.');
    } catch (error) {
      status(error.message);
    } finally {
      busy = false;
      controls();
    }
  };
  $('caseWriterUse').onclick = async () => {
    try {
      await saveNow();
      const result = await request('use', {
        ...fields(),
        case_id: state.case_id,
        revision: state.revision,
      });
      state = result;
      dialog.close();
      document.dispatchEvent(new Event('donors-changed'));
    } catch (error) {
      status(error.message);
    }
  };
  async function close() {
    try {
      await saveNow();
      dialog.close();
    } catch (error) {
      status(error.message);
    }
  }
  $('caseWriterBack').onclick = close;
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    close();
  });
  window.CaseWriter = {
    async open() {
      try {
        await saves.catch(() => {});
        state = await request();
        savedSnapshot = JSON.stringify({
          details: state.details,
          text: state.text,
          style: state.style,
        });
        let pending;
        try {
          pending = JSON.parse(sessionStorage.getItem(cacheKey()) || 'null');
        } catch (_) {}
        const values = pending && pending.at > (state.updated_at || 0) ? pending : state;
        $('caseWriterDetails').value = values.details;
        $('caseWriterMessage').value = values.text;
        $('caseWriterStyle').value = values.style;
        $('caseWriterContext').textContent =
          'Current case · Rs. ' + state.left.toLocaleString('en-PK') + ' left';
        $('caseWriterLearning').textContent =
          state.saved_messages + ' messages saved · your edits guide future writing';
        status(
          values === pending
            ? 'Restored your unsaved edits.'
            : 'Case details and message are saved separately.',
        );
        controls();
        if (!dialog.open) dialog.showModal();
        $('caseWriterDetails').focus({ preventScroll: true });
        if (values === pending) changed();
      } catch (error) {
        // Opening errors belong in the existing Messages status area.
        const note = document.getElementById('donorNotice');
        if (note) note.textContent = error.message;
      }
    },
  };
})();
