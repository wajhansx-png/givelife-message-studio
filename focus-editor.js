(() => {
  const $ = (id) => document.getElementById(id);
  const screen = document.createElement('section');
  screen.id = 'messageFocus';
  screen.hidden = true;
  screen.innerHTML = `<header><span id="focusState" role="status" aria-live="polite"></span></header><div class="focus-workspace"><main class="focus-paper"><div id="focusFormatted" tabindex="0" aria-label="Message preview"></div><textarea id="focusText" aria-label="Edit WhatsApp message" spellcheck="true" hidden></textarea></main><aside class="focus-rail" aria-label="Message tools"><button id="focusEdit">Edit</button><button id="focusCopy">Copy</button><button id="focusNext">Next version</button><small id="focusVersion">Original</small><button id="focusPoster">Change poster</button><button data-mark="*"><b>Bold</b></button><button data-mark="_"><i>Italic</i></button><button data-emoji="💔">💔 Heart</button><button data-emoji="🤲">🤲 Dua</button><button id="focusRetry">Generate 5 Versions</button></aside></div>`;
  document.body.append(screen);
  // Scroll targets must clear the sticky tool dock at every viewport size.
  const focusDock = screen.querySelector('.focus-rail');
  new ResizeObserver(() => {
    screen.style.setProperty('--focus-dock-height', focusDock.offsetHeight + 'px');
    screen.style.setProperty(
      '--focus-header-height',
      screen.querySelector('header').offsetHeight + 'px',
    );
  }).observe(focusDock);
  const dmPanel = document.querySelector('.dm-send'),
    dmAnchor = document.createComment('DM sending panel home');
  if (dmPanel) dmPanel.before(dmAnchor);
  function placeDmPanel(on) {
    screen.classList.toggle('with-dm', on);
    if (!dmPanel) return;
    if (on) screen.querySelector('.focus-workspace').append(dmPanel);
    else if (dmAnchor.parentNode) dmAnchor.after(dmPanel);
  }
  const groupPanel = document.querySelector('.group-send'),
    groupAnchor = document.createComment('Group sending panel home');
  if (groupPanel) groupPanel.before(groupAnchor);
  function placeGroupPanel(on) {
    screen.classList.toggle('with-group', on);
    if (!groupPanel) return;
    if (on) screen.querySelector('.focus-workspace').append(groupPanel);
    else if (groupAnchor.parentNode) groupAnchor.after(groupPanel);
  }
  for (const button of groupPanel?.querySelectorAll('[data-group],#sendAll,[data-test]') || []) {
    const original = button.onclick;
    button.onclick = async (e) => {
      if (actionBusy) return;
      actionBusy = true;
      try {
        if (editing) edit(false);
        await save();
        $('group').value = row?.source || $('focusText').value;
        await original?.call(button, e);
      } catch (error) {
        status(error.message);
      } finally {
        actionBusy = false;
      }
    };
  }
  const saveBase = document.createElement('button');
  saveBase.id = 'focusSave';
  saveBase.textContent = 'Save Base Message';
  saveBase.title = 'Save this message only. No versions are written.';
  screen.querySelector('.focus-rail').insertBefore(saveBase, $('focusCopy'));
  saveBase.textContent = 'Save Base';
  const baseDialog = document.createElement('dialog');
  baseDialog.id = 'focusBaseDialog';
  baseDialog.className = 'focus-base-dialog';
  baseDialog.setAttribute('aria-label', 'Save base message');
  baseDialog.innerHTML =
    '<h2>Save base message?</h2><p id="focusBaseNote"></p><div class="focus-base-actions"><button type="button" id="focusBaseCancel">Cancel</button><button type="button" class="primary" id="focusBaseSave">Save</button></div>';
  document.body.append(baseDialog);
  saveBase.onclick = () => {
    if (editing) edit(false);
    const hasVersions = (row?.items?.length || 0) > 0;
    $('focusBaseNote').textContent = !dirty
      ? 'Nothing has changed. This is already your base message.'
      : hasVersions
        ? 'This becomes your base message. The ' + row.items.length + ' saved versions were written from the old text, so they are cleared. Press Generate 5 Versions for new ones.'
        : 'This becomes your base message. No versions are written.';
    $('focusBaseSave').textContent = dirty ? 'Save' : 'OK';
    baseDialog.showModal();
  };
  $('focusBaseCancel').onclick = () => baseDialog.close();
  $('focusBaseSave').onclick = async () => {
    try {
      const changed = dirty;
      await save();
      baseDialog.close();
      status(changed ? 'Saved base message ✓' : 'Saved base message · nothing changed');
    } catch (e) {
      baseDialog.close();
      status(e.message);
    }
  };
  const manualButton = document.createElement('button');
  manualButton.id = 'focusManual';
  manualButton.textContent = 'Manual messages';
  screen.querySelector('.focus-rail').append(manualButton);
  const testButton = document.createElement('button');
  testButton.id = 'focusTest';
  testButton.textContent = 'Test';
  testButton.title = 'Send this message to the Test group';
  screen.querySelector('.focus-rail').insertBefore(testButton, $('focusNext'));
  const regen = document.createElement('button');
  regen.id = 'focusRegenerate';
  regen.textContent = 'Replace with fresh 5';
  regen.title = 'Remove the saved versions and write a fresh 5';
  screen.querySelector('.focus-rail').append(regen);
  const backBottom = document.createElement('button');
  backBottom.id = 'focusBack';
  backBottom.className = 'back-action';
  backBottom.textContent = '← Back';
  screen.querySelector('.focus-rail').append(backBottom);
  const manual = document.createElement('dialog');
  manual.id = 'manualMessages';
  manual.setAttribute('aria-label', 'Manual messages');
  manual.innerHTML =
    '<header><b>Add your messages</b><button id="manualClose" aria-label="Close manual messages">×</button></header><div class="manual-nav"><button id="manualPrev">←</button><span id="manualSlot"></span><button id="manualNext">→</button></div><textarea id="manualText" aria-label="Manual message" rows="10" maxlength="10000"></textarea><p id="manualState" role="status"></p><button id="manualSave">Save messages</button>';
  document.body.append(manual);
  let slots = [],
    slot = 0;
  function slotShow() {
    $('manualSlot').textContent = 'Message ' + (slot + 1) + ' / 10';
    $('manualText').value = slots[slot] || '';
  }
  manualButton.onclick = async () => {
    try {
      if (editing) edit(false);
      await save();
      row = await api();
      slots = Array.from({ length: 10 }, (_, i) => row.manual?.[i] || '');
      slot = 0;
      slotShow();
      $('manualState').textContent = '';
      manual.showModal();
    } catch (e) {
      status(e.message);
    }
  };
  for (const [id, step] of [
    ['manualPrev', -1],
    ['manualNext', 1],
  ])
    $(id).onclick = () => {
      slots[slot] = $('manualText').value;
      slot = (slot + step + 10) % 10;
      slotShow();
    };
  $('manualClose').onclick = () => manual.close();
  $('manualSave').onclick = async () => {
    slots[slot] = $('manualText').value;
    $('manualSave').disabled = true;
    try {
      row = await api({ action: 'manual', messages: slots });
      manual.close();
      status(row.items.length + ' manual messages ready');
      genButton();
    } catch (e) {
      $('manualState').textContent = e.message;
    } finally {
      $('manualSave').disabled = false;
    }
  };
  regen.onclick = async () => {
    try {
      if (editing) edit(false);
      await save();
      row = await api({ action: 'regenerate' });
      status('Writing 5 fresh versions…');
      genButton();
      watch();
    } catch (e) {
      status(e.message);
    }
  };
  const groupTab = document.querySelector('[data-view-button="group"]');
  if (groupTab) {
    const original = groupTab.onclick;
    groupTab.onclick = (e) => {
      original?.call(groupTab, e);
      location.hash = 'preview';
    };
  }
  let actionBusy = false;
  for (const button of dmPanel?.querySelectorAll('#sendDm,[data-test="dm"]') || []) {
    const original = button.onclick;
    button.onclick = async (e) => {
      if (actionBusy) return;
      actionBusy = true;
      try {
        if (editing) edit(false);
        await save();
        $('dm').value = $('focusText').value;
        await original?.call(button, e);
      } catch (error) {
        status(error.message);
      } finally {
        actionBusy = false;
      }
    };
  }
  const log = $('log');
  if (log)
    new MutationObserver(() => {
      if (!screen.hidden) {
        const last = log.querySelector('.e:last-of-type');
        if (last) {
          const text = last.cloneNode(true);
          text.querySelectorAll('.message-copy,.reply-feedback').forEach((n) => n.remove());
          status(text.textContent);
        }
      }
    }).observe(log, { childList: true, subtree: true });
  let kind = 'group',
    row = null,
    index = -1,
    editing = false,
    dirty = false,
    loading = 0,
    timer,
    saveChain = Promise.resolve();
  async function api(body) {
    const r = await fetch(
      '/focus-bank' + (body ? '' : '?kind=' + kind),
      body
        ? {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind, ...body }),
          }
        : {},
    );
    const d = await r.json();
    if (!r.ok) throw Error(d.error || 'Could not save. Your text is still here.');
    return d;
  }
  function syncSavedDrafts(data) {
    for (const k of ['group', 'dm'])
      if (typeof data?.drafts?.[k] === 'string') $(k).value = data.drafts[k];
  }
  // One batch at a time: the button waits while versions are being written.
  function genButton() {
    const b = $('focusRetry'),
      busy = row?.state === 'Generating';
    b.disabled = busy;
    b.textContent = busy ? 'Writing 5…' : 'Generate 5 Versions';
  }
  /* One short line. A long generation message shows as "1 of 5 ready ⓘ"; tap it for the full reason. */
  function status(text) {
    const node = $('focusState'),
      full = String(text || ''),
      m = /^(\d+) of (\d+) new versions passed every check\.?\s*(.*)$/s.exec(full);
    node.dataset.open = '';
    if (m) {
      node.textContent = m[1] + ' of ' + m[2] + ' new versions ready ⓘ';
      node.title = full;
      node.tabIndex = 0;
      node.onclick = () => {
        const open = node.dataset.open === '1';
        node.dataset.open = open ? '' : '1';
        node.textContent = open ? m[1] + ' of ' + m[2] + ' new versions ready ⓘ' : full;
      };
    } else {
      node.textContent = full;
      node.title = '';
      node.removeAttribute('tabindex');
      node.onclick = null;
    }
  }
  /* The whole message shows at once: the largest size (10.5–20px) at which it fits without scrolling. */
  function fit() {
    const p = $('focusFormatted');
    if (editing) return;
    p.style.setProperty('line-height', '1.3', 'important');
    let lo = 9.5,
      hi = 14,
      best = lo;
    for (let i = 0; i < 7; i++) {
      const mid = (lo + hi) / 2;
      p.style.setProperty('font-size', mid + 'px', 'important');
      if (p.scrollHeight <= p.clientHeight + 2) {
        best = mid;
        lo = mid;
      } else hi = mid;
    }
    p.style.setProperty('font-size', best + 'px', 'important');
    $('focusText').style.fontSize = Math.max(best, 14) + 'px';
  }
  function paint(text) {
    $('focusText').value = text;
    $('focusFormatted').innerHTML = window.waFormat(text);
    $('focusVersion').textContent =
      index < 0 ? 'Original' : index + 1 + ' / ' + (row?.items?.length || 0);
    requestAnimationFrame(fit);
  }
  function edit(on) {
    editing = on;
    $('focusText').hidden = !on;
    $('focusFormatted').hidden = on;
    $('focusEdit').textContent = on ? 'Done' : 'Edit';
    if (on) clearTimeout(timer);
    if (on) $('focusText').focus({ preventScroll: true });
    else {
      if (dirty) save();
      $('focusFormatted').innerHTML = window.waFormat($('focusText').value);
      fit();
    }
  }
  async function save() {
    if (!dirty) return saveChain;
    const text = $('focusText').value,
      rev = row?.revision;
    dirty = false;
    status('Saving…');
    saveChain = saveChain
      .catch(() => {})
      .then(async () => {
        try {
          row = await api({ action: 'save', text, revision: rev });
          syncSavedDrafts(row);
          if ($('focusText').value === text) sessionStorage.removeItem('focus-draft-' + kind);
          index = -1;
          $(kind).value = text;
          status('Saved base message · TEST works · tap Generate 5 Versions for versions');
          genButton();
        } catch (e) {
          dirty = true;
          status(e.message);
          throw e;
        }
      });
    return saveChain;
  }
  function watch() {
    clearTimeout(timer);
    if (screen.hidden || row?.state !== 'Generating') return;
    timer = setTimeout(async () => {
      try {
        const d = await api();
        if (screen.hidden || editing) return;
        row = d;
        status(
          d.state === 'Ready'
            ? (d.items?.length || 0) + ' versions ready'
            : d.state === 'Generating'
              ? 'Writing 5 more · ' + (d.items?.length || 0) + ' ready so far…'
              : d.error || (d.items?.length || 0) + ' versions ready',
        );
        genButton();
        watch();
      } catch (e) {
        status('Original saved. Could not refresh versions.');
      }
    }, 2500);
  }
  async function open() {
    const epoch = ++loading;
    screen.hidden = false;
    document.body.classList.add('message-focus-open');
    kind = document.body.dataset.view === 'dm' ? 'dm' : 'group';
    placeDmPanel(kind === 'dm');
    placeGroupPanel(kind === 'group');
    status('Loading saved message…');
    try {
      row = await api();
      syncSavedDrafts(row);
      if (epoch !== loading || screen.hidden) return;
      index = -1;
      editing = false;
      dirty = false;
      paint(row.source);
      const pending = sessionStorage.getItem('focus-draft-' + kind);
      if (pending && pending !== row.source) {
        paint(pending);
        dirty = true;
        status('Unsaved text restored. Tap Done to save.');
        edit(true);
      } else {
        edit(false);
        status(
          row.error ||
            (row.state === 'Ready'
              ? row.items.length + ' versions ready'
              : row.state === 'Generating'
                ? 'Writing 5 more versions…'
                : row.items?.length
                  ? row.items.length + ' versions ready'
                  : 'Saved base message · TEST works without versions'),
        );
      }
      if (!row.revision && !dirty) {
        dirty = true;
        await save();
      }
      genButton();
      watch();
    } catch (e) {
      status(e.message);
    }
  }
  function sync() {
    if (location.hash.replace(/^#\/?/, '') === 'preview') {
      if (screen.hidden) open();
    } else if (!screen.hidden) {
      screen.hidden = true;
      placeDmPanel(false);
      placeGroupPanel(false);
      document.body.classList.remove('message-focus-open');
      clearTimeout(timer);
      ++loading;
    }
  }
  $('focusText').oninput = () => {
    dirty = true;
    sessionStorage.setItem('focus-draft-' + kind, $('focusText').value);
    status('Editing · saved when you tap Done');
  };
  /* Clicking outside the editor saves the edit and leaves editing (buttons in the tool rail keep their own behaviour). */
  document.addEventListener('pointerdown', (e) => {
    if (screen.hidden || !editing || baseDialog.open) return;
    if ($('focusText').contains(e.target) || e.target.closest('.focus-rail, dialog, #waMarkBar'))
      return;
    edit(false);
  });
  $('focusEdit').onclick = () => edit(!editing);
  /* A small purple arrow on the card's right edge moves to the next version; the big Next button is retired. */
  {
    const arrow = document.createElement('button');
    arrow.id = 'focusNextArrow';
    arrow.className = 'focus-next-arrow';
    arrow.type = 'button';
    arrow.textContent = '›';
    arrow.title = 'Next version';
    arrow.setAttribute('aria-label', 'Next version');
    arrow.onclick = () => $('focusNext').click();
    const gen = document.createElement('button');
    gen.id = 'focusGenIcon';
    gen.className = 'focus-gen-icon';
    gen.type = 'button';
    gen.textContent = '↻';
    gen.title = 'Generate 5 versions';
    gen.setAttribute('aria-label', 'Generate 5 versions');
    gen.onclick = () => $('focusRetry').click();
    $('focusFormatted').parentElement.append(arrow, gen);
    const more = document.createElement('details');
    more.className = 'focus-rail-more';
    more.innerHTML = '<summary>More</summary><div></div>';
    for (const id of ['focusPoster', 'focusManual', 'focusRetry', 'focusRegenerate'])
      more.lastChild.append($(id));
    screen.querySelector('.focus-rail').insertBefore(more, $('focusBack'));
    document.addEventListener('pointerdown', (e) => {
      if (more.open && !more.contains(e.target)) more.open = false;
    });
  }
  $('focusFormatted').ondblclick = () => edit(true);
  $('focusBack').onclick = async () => {
    try {
      if (editing) edit(false);
      await save();
      sessionStorage.removeItem('focus-draft-' + kind);
      location.hash = '';
    } catch (e) {
      status(e.message);
    }
  };
  $('focusCopy').onclick = async () => {
    try {
      await navigator.clipboard.writeText($('focusText').value);
      status('Copied');
    } catch (e) {
      status('Could not copy. Select the text and copy.');
    }
  };
  $('focusNext').onclick = async () => {
    try {
      if (editing) edit(false);
      await save();
      row = await api();
      if (!row.items?.length) {
        status(row.error || 'No versions yet. Tap Generate 5 Versions. TEST works without them.');
        return;
      }
      index = ((index + 2) % (row.items.length + 1)) - 1;
      paint(index < 0 ? row.source : row.items[index]);
      status(
        index < 0
          ? 'Original'
          : 'Version ' + (index + 1) + ' · edit and Done to save as your message',
      );
    } catch (e) {
      status(e.message);
    }
  };
  $('focusTest').onclick = async () => {
    if (actionBusy) return;
    actionBusy = true;
    $('focusTest').disabled = true;
    try {
      if (editing) edit(false);
      await save();
      $('group').value = row?.source || $('focusText').value;
      await window.sendTest('group');
    } catch (error) {
      status(error.message);
    } finally {
      actionBusy = false;
      $('focusTest').disabled = false;
    }
  };
  $('focusPoster').onclick = () => {
    $('posterDialog').dataset.returnRoute = 'preview';
    window.DonorHub.openPoster();
  };
  $('focusRetry').onclick = async () => {
    try {
      if (editing) edit(false);
      await save();
      row = await api({ action: 'generate' });
      status('Writing 5 versions…');
      genButton();
      watch();
    } catch (e) {
      status(e.message);
    }
  };
  screen.querySelectorAll('[data-mark],[data-emoji]').forEach((b) => {
    b.onmousedown = (e) => e.preventDefault();
    b.onclick = () => {
      if (!editing) edit(true);
      const t = $('focusText');
      if (b.dataset.mark) {
        /* Nothing selected: the line the cursor is on, as before. */
        window.waMark.apply(t, b.dataset.mark, { lineIfEmpty: true });
        return;
      }
      t.setRangeText(b.dataset.emoji, t.selectionStart, t.selectionEnd, 'select');
      t.dispatchEvent(new Event('input'));
      t.focus({ preventScroll: true });
    };
  });
  addEventListener('studio-navigate', sync);
  addEventListener('popstate', sync);
  addEventListener('hashchange', sync);
  addEventListener('resize', fit);
  addEventListener('beforeunload', () => {
    if (dirty) sessionStorage.setItem('focus-draft-' + kind, $('focusText').value);
  });
  sync();
})();
