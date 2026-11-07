/* Private foundation notebook. The password stays on the server, not in localStorage. */
(() => {
  const donor = document.getElementById('donorsPage');
  if (!donor) return;
  const make = (tag, klass, text) => {
    const e = document.createElement(tag);
    if (klass) e.className = klass;
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const button = make('button', 'donor-notes-shortcut', 'Notes');
  button.type = 'button';
  button.id = 'donorNotesShortcut';
  button.setAttribute('aria-label', 'Open private foundation notes');
  const header = document.querySelector('.brandbar');
  header?.append(button);

  const page = make('dialog', 'foundation-notes');
  page.id = 'foundationNotes';
  page.setAttribute('aria-label', 'Private foundation notes');
  page.innerHTML = String.raw`
   <section class="notes-shell">
    <header class="notes-head">
     <button class="notes-back" type="button" id="notesBack" aria-label="Back to Donors">← Back</button>
     <div class="notes-headline"><h1>My Notes</h1></div>
     <span class="notes-sync" id="notesSync" role="status" aria-live="polite"></span>
     <button type="button" class="notes-lock" id="notesLock" hidden>Lock</button>
     <button type="button" class="notes-fullscreen" id="notesFullscreen" aria-pressed="false" title="Hide browser chrome while writing">Full screen</button>
    </header>
    <div class="notes-center" id="notesLocked" hidden>
      <div class="notes-unlock">
       <div class="notes-lock-icon" aria-hidden="true">✦</div>
       <form id="notesUnlockForm" autocomplete="off">
        <label for="notesPassword">Notes password</label>
        <div class="notes-password-row"><input id="notesPassword" type="password" name="notes_password" autocomplete="current-password" required placeholder="Enter password" aria-label="Notes password"><button class="notes-primary" type="submit" id="notesUnlockButton">Unlock notes</button></div>
        <p class="notes-error" id="notesError" role="alert"></p>
       </form>
      </div>
    </div>
    <section class="notes-workspace" id="notesWorkspace" hidden>
      <div class="notes-toolbar" role="toolbar" aria-label="Format your notes">
        <button type="button" id="notesFontDown" aria-label="Decrease notes font size" title="Smaller text">A−</button>
        <button type="button" id="notesFontUp" aria-label="Increase notes font size" title="Larger text">A+</button>
        <label class="notes-select-label"><span class="sr-only">Text style</span><select id="notesStyle" aria-label="Text style"><option value="p">Normal text</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option><option value="h3">Heading 3</option></select></label>
        <span class="notes-separator" aria-hidden="true"></span>
        <button type="button" data-command="bold" aria-label="Bold" title="Bold (Ctrl+B)"><b>B</b></button>
        <button type="button" data-command="italic" aria-label="Italic" title="Italic (Ctrl+I)"><i>I</i></button>
        <span class="notes-separator" aria-hidden="true"></span>
        <button type="button" data-command="insertUnorderedList" aria-label="Bulleted list" title="Bulleted list">☷</button>
        <button type="button" data-command="insertOrderedList" aria-label="Numbered list" title="Numbered list">1.</button>
        <button type="button" id="notesChecklist" aria-label="Checklist" title="Checklist">☑</button>
        <span class="notes-separator" aria-hidden="true"></span>
        <label class="notes-color-wrap" title="Text color"><span class="sr-only">Text color</span><select id="notesColor" aria-label="Text color">
         <option value="">Color</option><option value="#ededed">White (default)</option><option value="#d5d9e0">Slate</option><option value="#85b7f6">Blue</option>
         <option value="#8ddfba">Green</option><option value="#efc389">Amber</option><option value="#f4a4ad">Red</option>
         <option value="#c7aff6">Purple</option>
        </select></label>
      </div>
      <div class="notes-paper-scroll">
       <main class="notes-paper">
        <div id="notesEditor" class="notes-editor" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Your foundation notes" data-placeholder="" spellcheck="true"></div>
       </main>
      </div>
      <footer class="notes-foot"><span id="notesHint">Your ideas are private · Saved to GiveLife</span><button type="button" id="notesRetry" hidden>Retry save</button></footer>
    </section>
    <footer class="notes-back-dock" hidden></footer>
   </section>`;
  document.body.append(page);
  const el = (id) => document.getElementById(id);
  // Keep the same Back control in the phone dock and desktop header.
  const backHome = document.createComment('Desktop Notes Back position');
  const notesBack = el('notesBack');
  notesBack.before(backHome);
  const backDock = page.querySelector('.notes-back-dock');
  const phoneBack = matchMedia('(max-width: 899px)');
  const placeBack = () => {
    backDock.hidden = !phoneBack.matches;
    if (phoneBack.matches) backDock.append(notesBack);
    else backHome.after(notesBack);
  };
  placeBack();
  phoneBack.addEventListener('change', placeBack);
  const editor = el('notesEditor'),
    sync = el('notesSync'),
    retry = el('notesRetry');
  /* Big by default: easy on the eyes. */
  let fontSize = matchMedia('(max-width: 720px)').matches ? 23 : 27;
  try {
    const stored = Number(localStorage.getItem('givelife-notes-font-size-v2'));
    if (Number.isInteger(stored) && stored >= 14 && stored <= 36) fontSize = stored;
  } catch {}
  const paintFont = () => {
    editor.style.setProperty('--notes-font-size', fontSize + 'px');
    el('notesFontDown').disabled = fontSize <= 14;
    el('notesFontUp').disabled = fontSize >= 36;
    el('notesFontUp').title = 'Larger text · ' + fontSize + 'px';
    el('notesFontDown').title = 'Smaller text · ' + fontSize + 'px';
  };
  for (const [id, delta] of [
    ['notesFontDown', -1],
    ['notesFontUp', 1],
  ])
    el(id).onclick = () => {
      fontSize = Math.max(14, Math.min(36, fontSize + delta));
      paintFont();
      try {
        localStorage.setItem('givelife-notes-font-size-v2', String(fontSize));
      } catch {}
    };
  paintFont();
  let revision = 0,
    loaded = false,
    dirty = false,
    saving = false,
    saveTimer = null;
  // Writing mode is fully quiet. Hover the top 125px (desktop), tap the top
  // edge (touch), or press Alt+T (keyboard) to reveal actions. Editor focus
  // alone must NOT reveal the toolbar: typing should never feel distracting.
  const notesHead = page.querySelector('.notes-head'),
    notesToolbar = page.querySelector('.notes-toolbar');
  const fullscreenButton = el('notesFullscreen');
  const railLabels = {
    insertOrderedList: 'Numbers',
    insertUnorderedList: 'Bullets',
    bold: 'Bold',
    italic: 'Italic',
  };
  for (const [command, label] of Object.entries(railLabels))
    notesToolbar.querySelector('[data-command="' + command + '"]').textContent = label;
  el('notesChecklist').textContent = 'Checklist';
  el('notesFontDown').textContent = 'Smaller';
  el('notesFontUp').textContent = 'Larger';
  const styleLabel = el('notesStyle').closest('label'),
    colorLabel = el('notesColor').closest('label'),
    heading = make('div', 'notes-heading-box'),
    headingRow = make('div', 'notes-heading-row');
  /* The select stays for keyboard use; H1-H3 are buttons now. */
  styleLabel.classList.add('notes-style-hidden');
  for (const [tag, label] of [
    ['h1', 'H1'],
    ['h2', 'H2'],
    ['h3', 'H3'],
    ['p', 'Text'],
  ]) {
    const b = make('button', '', label);
    b.type = 'button';
    b.dataset.block = tag;
    b.title = tag === 'p' ? 'Normal text' : 'Heading ' + tag[1];
    b.setAttribute('aria-pressed', String(tag === 'p'));
    headingRow.append(b);
  }
  heading.append(make('span', 'notes-rail-label', 'Heading'), headingRow, styleLabel);
  notesToolbar.querySelectorAll('.notes-separator').forEach((e) => e.remove());
  notesToolbar.append(
    heading,
    notesToolbar.querySelector('[data-command="insertOrderedList"]'),
    notesToolbar.querySelector('[data-command="insertUnorderedList"]'),
    el('notesChecklist'),
    notesToolbar.querySelector('[data-command="bold"]'),
    notesToolbar.querySelector('[data-command="italic"]'),
    el('notesFontDown'),
    el('notesFontUp'),
    colorLabel,
  );
  /* The format bar appears only while text is selected, just below it (above if there is no room). */
  let selectionRect = null;
  function alignRail() {
    if (!page.open || page.dataset.mode !== 'writing') return;
    const selection = getSelection();
    const selected =
      selection?.rangeCount &&
      !selection.isCollapsed &&
      editor.contains(selection.anchorNode) &&
      selection.toString().trim() !== '';
    if (selected) selectionRect = selection.getRangeAt(0).getBoundingClientRect();
    const keep = notesToolbar.contains(document.activeElement); /* e.g. the Color list is open */
    if (!selectionRect || (!selected && !keep)) {
      notesToolbar.dataset.open = 'false';
      if (!selected) selectionRect = null;
      return;
    }
    const w = notesToolbar.offsetWidth,
      h = notesToolbar.offsetHeight;
    let top = selectionRect.bottom + 12;
    if (top + h > innerHeight - 8) top = selectionRect.top - h - 12;
    top = Math.max(8, Math.min(top, innerHeight - h - 8));
    const left = Math.max(
      8,
      Math.min(selectionRect.left + selectionRect.width / 2 - w / 2, innerWidth - w - 8),
    );
    notesToolbar.style.left = left + 'px';
    notesToolbar.style.top = top + 'px';
    notesToolbar.dataset.open = 'true';
  }
  editor.addEventListener('scroll', alignRail);
  new ResizeObserver(alignRail).observe(page.querySelector('.notes-paper'));
  document.addEventListener('selectionchange', alignRail);
  window.addEventListener('resize', alignRail);
  // Keep the same formatting controls beside the editor at every screen size.
  const wideNotes = matchMedia('(min-width:1100px)');
  function placeToolbar() {
    el('notesWorkspace').prepend(notesToolbar);
  }
  placeToolbar();
  wideNotes.addEventListener('change', placeToolbar);
  page.dataset.mode = 'loading';
  page.dataset.controls = 'closed';
  function revealControls() {
    if (page.dataset.mode === 'writing') page.dataset.controls = 'open';
  }
  function concealControls(force = false) {
    if (page.dataset.mode !== 'writing') return;
    if (
      !force &&
      (notesHead.contains(document.activeElement) || notesToolbar.contains(document.activeElement))
    )
      return;
    page.dataset.controls = 'closed';
  }
  page.addEventListener('pointermove', (event) => {
    if (page.dataset.mode !== 'writing' || event.pointerType === 'touch') return;
    const top = event.clientY - page.getBoundingClientRect().top;
    if (top <= 125) revealControls();
    else if (top > 160 && !notesHead.contains(event.target) && !notesToolbar.contains(event.target))
      concealControls(true);
  });
  page.addEventListener('pointerleave', () => concealControls());
  page.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'touch' || page.dataset.mode !== 'writing') return;
    const top = event.clientY - page.getBoundingClientRect().top;
    if (top <= 38 && !notesHead.contains(event.target) && !notesToolbar.contains(event.target)) {
      event.preventDefault();
      page.dataset.controls = page.dataset.controls === 'open' ? 'closed' : 'open';
    }
  });
  page.addEventListener('focusin', (event) => {
    if (notesHead.contains(event.target) || notesToolbar.contains(event.target)) revealControls();
  });
  let shortcutFocusPending = false,
    shortcutFocusRevision = 0;
  page.addEventListener(
    'pointerdown',
    () => {
      shortcutFocusRevision++;
    },
    true,
  );
  document.addEventListener('keyup', (event) => {
    if (event.key !== 'Alt' || !shortcutFocusPending) return;
    shortcutFocusPending = false;
    requestAnimationFrame(() => {
      if (page.open && page.dataset.mode === 'writing' && page.dataset.controls === 'open')
        el('notesStyle').focus({ preventScroll: true });
    });
  });
  document.addEventListener('keydown', (event) => {
    if (!page.open || page.dataset.mode !== 'writing') return;
    if (event.altKey && !event.ctrlKey && !event.metaKey && event.key.toLowerCase() === 't') {
      event.preventDefault();
      page.dataset.controls = page.dataset.controls === 'open' ? 'closed' : 'open';
      // Alt keyup is the reliable moment: Chromium may restore the editor's
      // focus when the modifier is released, undoing focus set on keydown.
      shortcutFocusPending = page.dataset.controls === 'open';
      if (shortcutFocusPending) {
        const revision = ++shortcutFocusRevision;
        // Some browsers restore the contenteditable focus after Alt keyup.
        // One guarded post-keyboard retry prevents that without stealing focus
        // from any subsequent pointer interaction.
        setTimeout(() => {
          if (page.open && revision === shortcutFocusRevision && page.dataset.controls === 'open')
            el('notesStyle').focus({ preventScroll: true });
        }, 140);
      }
    }
    if (event.key === 'Escape' && notesToolbar.dataset.open === 'true') {
      /* Escape puts the format bar away by clearing the selection. */
      getSelection().collapseToEnd();
      editor.focus({ preventScroll: true });
      alignRail();
    }
    if (event.key === 'Escape' && page.dataset.controls === 'open' && !document.fullscreenElement) {
      event.preventDefault();
      event.stopPropagation();
      concealControls(true);
      editor.focus({ preventScroll: true });
    }
  });
  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }
      // Native fullscreen rejects modal <dialog> in some browsers. Fullscreen the
      // document instead; its open Notes dialog remains the topmost visible layer.
      const target = document.documentElement;
      if (typeof target.requestFullscreen !== 'function') {
        setStatus('Full screen is unavailable on this browser.', true);
        return;
      }
      await target.requestFullscreen({ navigationUI: 'hide' });
    } catch (_) {
      setStatus('Browser did not allow full screen.', true);
    }
  }
  fullscreenButton.addEventListener('click', toggleFullscreen);
  let notesWasFullscreen = false;
  document.addEventListener('fullscreenchange', () => {
    const active = !!document.fullscreenElement;
    fullscreenButton.textContent = active ? 'Exit full screen' : 'Full screen';
    fullscreenButton.setAttribute('aria-pressed', String(active));
    if (active && page.open) {
      notesWasFullscreen = true;
      return;
    }
    if (!active && notesWasFullscreen && page.open) {
      notesWasFullscreen = false;
      // Chromium sometimes leaves the modal inert after a document-level
      // fullscreen transition. Reopen the same dialog to restore its top layer
      // without reloading Notes or touching the unsaved editor content.
      const scroll = paperScroll.scrollTop;
      page.close();
      page.showModal();
      paperScroll.scrollTop = scroll;
      scheduleSize();
      concealControls(true);
      if (!mobileNotes.matches)
        requestAnimationFrame(() => {
          if (page.open) {
            editor.focus({ preventScroll: true });
            concealControls(true);
          }
        });
    }
  });
  // A stable paper height prevents the editor itself from collapsing when a
  // mobile keyboard opens; only its scrollable viewport becomes shorter.
  const mobileNotes = matchMedia('(max-width:720px)');
  const paperScroll = page.querySelector('.notes-paper-scroll');
  let expandedHeight = 0,
    lastMobileWidth = 0,
    caretFrame = 0,
    layoutFrame = 0;
  function revealCaret() {
    if (!page.open || document.activeElement !== editor || !paperScroll) return;
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) return;
    const range = selection.getRangeAt(0).cloneRange();
    range.collapse(false);
    const caret = range.getBoundingClientRect(),
      viewport = paperScroll.getBoundingClientRect();
    if (!caret.height && !caret.width) return;
    const padding = 28;
    if (caret.bottom > viewport.bottom - padding)
      paperScroll.scrollTop += caret.bottom - (viewport.bottom - padding);
    else if (caret.top < viewport.top + padding)
      paperScroll.scrollTop -= viewport.top + padding - caret.top;
  }
  function scheduleCaret() {
    cancelAnimationFrame(caretFrame);
    caretFrame = requestAnimationFrame(() => requestAnimationFrame(revealCaret));
  }
  function sizeForKeyboard() {
    if (!page.open) return;
    if (!mobileNotes.matches) {
      page.dataset.keyboard = 'closed';
      for (const key of ('--notes-visible-height',
      '--notes-visible-top',
      '--notes-paper-min-height'))
        page.style.removeProperty(key);
      expandedHeight = 0;
      lastMobileWidth = 0;
      return;
    }
    const visual = window.visualViewport;
    const visibleHeight = Math.min(window.innerHeight, visual?.height || window.innerHeight);
    if (lastMobileWidth !== window.innerWidth) {
      lastMobileWidth = window.innerWidth;
      expandedHeight = Math.max(window.innerHeight, visibleHeight);
    }
    if (!expandedHeight) expandedHeight = Math.max(window.innerHeight, visibleHeight);
    const focused =
      document.activeElement === editor || document.activeElement === el('notesPassword');
    const keyboard =
      (focused || page.dataset.keyboard === 'open') && expandedHeight - visibleHeight > 120;
    if (!keyboard && !focused) expandedHeight = Math.max(expandedHeight, visibleHeight);
    page.dataset.keyboard = keyboard ? 'open' : 'closed';
    page.style.setProperty(
      '--notes-paper-min-height',
      Math.round(Math.max(380, expandedHeight - 80)) + 'px',
    );
    if (keyboard) {
      page.style.setProperty('--notes-visible-height', Math.round(visibleHeight) + 'px');
      page.style.setProperty('--notes-visible-top', Math.round(visual?.offsetTop || 0) + 'px');
      scheduleCaret();
    } else {
      page.style.removeProperty('--notes-visible-height');
      page.style.removeProperty('--notes-visible-top');
    }
  }
  function scheduleSize() {
    cancelAnimationFrame(layoutFrame);
    layoutFrame = requestAnimationFrame(sizeForKeyboard);
  }
  window.addEventListener('resize', scheduleSize);
  window.addEventListener('orientationchange', () => {
    expandedHeight = 0;
    lastMobileWidth = 0;
    scheduleSize();
  });
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', scheduleSize);
    window.visualViewport.addEventListener('scroll', scheduleSize);
  }
  page.addEventListener('focusin', scheduleSize);
  page.addEventListener('focusout', () => setTimeout(scheduleSize, 180));
  editor.addEventListener('input', scheduleCaret);
  editor.addEventListener('keyup', scheduleCaret);

  const setStatus = (s, error = false) => {
    sync.textContent = s;
    sync.dataset.error = String(error);
  };
  async function request(body) {
    const r = await fetch(
      '/notes',
      body === undefined
        ? { credentials: 'same-origin' }
        : {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
    );
    let response;
    try {
      response = await r.json();
    } catch (e) {
      throw Error('Notes server did not respond correctly.');
    }
    if (!r.ok) throw Error(response.error || 'Unable to save notes.');
    return response;
  }
  function screen(locked) {
    el('notesLocked').hidden = !locked;
    el('notesWorkspace').hidden = locked;
    el('notesLock').hidden = locked;
    page.dataset.mode = locked ? 'locked' : 'writing';
    placeToolbar();
    page.dataset.controls = 'closed';
  }
  async function load() {
    setStatus('Loading…');
    try {
      const r = await request();
      if (r.locked) {
        loaded = false;
        screen(true);
        setStatus('Locked');
        return;
      }
      if (!dirty || !loaded) {
        editor.innerHTML = r.html || '';
        normalizeBlocks();
        revision = r.revision || 0;
        dirty = false;
        loaded = true;
      }
      screen(false);
      setStatus(dirty ? 'Unsaved changes' : 'Saved');
    } catch (e) {
      setStatus(e.message, true);
      retry.hidden = false;
    }
  }
  let notesRoute = 'donors/all/notes',
    notesParentState = null;
  async function open() {
    const restoring = /(^|\/)notes$/.test(Nav.path());
    notesParentState = restoring ? window.history.state?.notesParent || null : window.history.state;
    const parent = Nav.path().replace(/(^|\/)notes$/, '');
    notesRoute = parent ? parent + '/notes' : 'notes'; // opened from the main screen: its own `notes` route
    el('notesBack').setAttribute('aria-label', parent ? 'Back to Donors' : 'Back');
    Nav.go(notesRoute);
    if (!restoring)
      window.history.replaceState(
        { ...window.history.state, notesParent: notesParentState },
        '',
        location.href,
      );
    if (!page.open) page.showModal();
    scheduleSize();
    await load();
    if (!page.open) return;
    scheduleSize();
    if (el('notesWorkspace').hidden) el('notesPassword').focus({ preventScroll: true });
    else if (!mobileNotes.matches) editor.focus({ preventScroll: true });
  }
  const rememberDirty = () => {
    dirty = true;
    retry.hidden = true;
    setStatus('Saving…');
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 800);
  };
  async function save() {
    clearTimeout(saveTimer);
    if (saving || !dirty || !loaded) return;
    saving = true;
    const html = editor.innerHTML,
      base = revision;
    try {
      const r = await request({ action: 'save', html, revision: base });
      revision = r.revision;
      dirty = editor.innerHTML !== html;
      retry.hidden = true;
      setStatus(dirty ? 'Saving…' : 'Saved');
    } catch (e) {
      dirty = true;
      setStatus(e.message, true);
      retry.hidden = false;
    } finally {
      saving = false;
      if (dirty && retry.hidden) saveTimer = setTimeout(save, 350);
    }
  }
  el('notesUnlockForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const pin = el('notesPassword').value,
      submit = el('notesUnlockButton');
    submit.disabled = true;
    el('notesError').textContent = '';
    try {
      const r = await request({ action: 'unlock', password: pin });
      el('notesPassword').value = '';
      revision = r.revision || 0;
      editor.innerHTML = r.html || '';
      normalizeBlocks();
      dirty = false;
      loaded = true;
      screen(false);
      setStatus('Saved');
      scheduleSize();
      if (!mobileNotes.matches) editor.focus({ preventScroll: true });
    } catch (err) {
      el('notesError').textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  /* Every line is its own paragraph, so Heading / Bullets / Numbers change only the chosen line,
     never a whole block of loose text. */
  function normalizeBlocks() {
    const BLOCK = /^(P|DIV|H1|H2|H3|H4|UL|OL|LI|BLOCKQUOTE|PRE|HR|TABLE)$/;
    let run = null;
    for (const node of [...editor.childNodes]) {
      const inline =
        node.nodeType === 3
          ? node.textContent.length > 0
          : node.nodeType === 1 && !BLOCK.test(node.tagName);
      if (inline) {
        if (!run) {
          run = document.createElement('p');
          editor.insertBefore(run, node);
        }
        run.append(node);
      } else run = null;
    }
    for (const div of [...editor.children].filter((n) => n.tagName === 'DIV' && !n.className)) {
      const p = document.createElement('p');
      while (div.firstChild) p.append(div.firstChild);
      div.replaceWith(p);
    }
    for (const p of [...editor.querySelectorAll(':scope > p')]) {
      const only = [...p.childNodes].filter((n) => !(n.nodeType === 3 && !n.textContent.trim()));
      if (only.length === 1 && /^(UL|OL|H1|H2|H3)$/.test(only[0].tagName || ''))
        p.replaceWith(only[0]);
    }
  }
  try {
    document.execCommand('defaultParagraphSeparator', false, 'p');
  } catch (e) {}
  editor.addEventListener('focus', () => {
    try {
      document.execCommand('defaultParagraphSeparator', false, 'p');
    } catch (e) {}
    if (!editor.firstElementChild && !editor.textContent.trim()) editor.innerHTML = '<p><br></p>';
  });
  editor.addEventListener('input', () => {
    if ([...editor.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) {
      const sel = window.getSelection(),
        r = sel.rangeCount ? sel.getRangeAt(0) : null,
        node = r?.startContainer,
        offset = r?.startOffset;
      normalizeBlocks();
      if (node && editor.contains(node)) {
        try {
          sel.collapse(node, offset);
        } catch (e) {}
      }
    }
  });
  editor.addEventListener('input', rememberDirty);
  // Paste text safely rather than allowing clipboard HTML to execute in the editor.
  editor.addEventListener('paste', (e) => {
    e.preventDefault();
    document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
    rememberDirty();
  });
  let savedRange = null;
  document.addEventListener('selectionchange', () => {
    if (!page.open || !loaded) return;
    const selection = window.getSelection();
    if (selection?.rangeCount && editor.contains(selection.anchorNode)) {
      savedRange = selection.getRangeAt(0).cloneRange();
      /* Light up the heading button that matches the line being edited. */
      let node = selection.anchorNode;
      if (node.nodeType === 3) node = node.parentElement;
      const tag = node?.closest('h1,h2,h3')?.tagName.toLowerCase() || 'p';
      for (const b of notesToolbar.querySelectorAll('[data-block]'))
        b.setAttribute('aria-pressed', String(b.dataset.block === tag));
    }
  });
  const restoreSelection = () => {
    editor.focus();
    if (savedRange && editor.contains(savedRange.commonAncestorContainer)) {
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(savedRange);
    }
  };
  // Keep the selected text while clicking toolbar buttons.
  page
    .querySelectorAll('.notes-toolbar button')
    .forEach((b) => b.addEventListener('mousedown', (e) => e.preventDefault()));
  page.querySelectorAll('[data-command]').forEach((b) =>
    b.addEventListener('click', () => {
      restoreSelection();
      normalizeBlocks();
      document.execCommand(b.dataset.command, false, null);
      normalizeBlocks();
      rememberDirty();
    }),
  );
  const applyBlock = (tag) => {
    restoreSelection();
    normalizeBlocks();
    document.execCommand('formatBlock', false, tag);
    rememberDirty();
  };
  el('notesStyle').addEventListener('change', (e) => {
    applyBlock(e.target.value);
    e.target.value = 'p';
  });
  notesToolbar.querySelectorAll('[data-block]').forEach((b) =>
    b.addEventListener('click', () => {
      const tag = b.dataset.block;
      /* Tapping the active heading again goes back to normal text. */
      applyBlock(tag !== 'p' && b.getAttribute('aria-pressed') === 'true' ? 'p' : tag);
    }),
  );
  el('notesColor').addEventListener('change', (e) => {
    if (!e.target.value) return;
    restoreSelection();
    document.execCommand('foreColor', false, e.target.value);
    e.target.value = '';
    rememberDirty();
  });
  const findList = () => {
    let node = window.getSelection()?.anchorNode;
    if (node?.nodeType === 3) node = node.parentElement;
    return node?.closest?.('ul,ol') || null;
  };
  el('notesChecklist').addEventListener('click', () => {
    restoreSelection();
    const old = findList();
    if (old && old.tagName === 'UL') {
      old.classList.toggle('notes-checklist');
    } else {
      document.execCommand('insertUnorderedList', false, null);
      const created = findList();
      if (created?.tagName === 'UL') created.classList.add('notes-checklist');
    }
    rememberDirty();
  });
  editor.addEventListener('click', (e) => {
    const li = e.target.closest('ul.notes-checklist > li');
    if (!li) return;
    const rect = li.getBoundingClientRect();
    if (e.clientX > rect.left + 16) return; // only the checkbox gutter toggles
    li.dataset.checked = li.dataset.checked === 'true' ? 'false' : 'true';
    rememberDirty();
  });

  retry.onclick = () => {
    retry.hidden = true;
    save();
  };
  async function back(allowed = () => true) {
    if (dirty) {
      clearTimeout(saveTimer);
      await save();
      if (!allowed()) return false;
      if (dirty) {
        setStatus('Save failed. Use Retry save before leaving.', true);
        retry.hidden = false;
        return;
      }
    }
    if (!allowed()) return false;
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
    if (!allowed()) return false;
    page.close();
    page.dataset.keyboard = 'closed';
    page.dataset.controls = 'closed';
    return true;
  }
  el('notesBack').onclick = async () => {
    if (await back()) {
      Nav.go(notesRoute === 'notes' ? '' : notesRoute.replace(/\/notes$/, ''), { replace: true });
      if (notesParentState) window.history.replaceState(notesParentState, '', location.href);
      renderNav();
    }
  };
  el('notesLock').onclick = async () => {
    if (dirty) {
      await save();
      if (dirty) {
        setStatus('Save changes before locking.', true);
        return;
      }
    }
    try {
      await request({ action: 'lock' });
      loaded = false;
      screen(true);
      setStatus('Locked');
    } catch (e) {
      setStatus(e.message, true);
    }
  };
  page.addEventListener('cancel', (e) => {
    e.preventDefault();
    el('notesBack').click();
  });
  window.addEventListener('beforeunload', (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
  window.FoundationNotes = {
    show: open,
    hide: back,
    isOpen: () => page.open,
    route: () => notesRoute,
  };
  button.onclick = open;
})();
