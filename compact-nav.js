/* Reuse live controls and handlers; this module only groups navigation. */
(() => {
  const menus = [];
  function menu(parent, id, label) {
    const details = document.createElement('details');
    details.id = id;
    details.className = 'compact-nav-menu';
    const summary = document.createElement('summary');
    summary.textContent = 'More';
    summary.setAttribute('aria-label', label);
    const panel = document.createElement('div');
    panel.className = 'compact-nav-panel';
    details.append(summary, panel);
    parent.append(details);
    menus.push(details);
    details.addEventListener('toggle', () => {
      if (details.open) for (const other of menus) if (other !== details) other.open = false;
    });
    panel.addEventListener('click', (e) => {
      if (e.target.closest('button')) details.open = false;
    });
    panel.addEventListener('change', () => (details.open = false));
    details.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        details.open = false;
        summary.focus();
      }
    });
    return panel;
  }
  // Keep both mobile shortcuts in the same bottom row; reuse their handlers.
  const chatShortcut = document.getElementById('chatOpen'),
    chatRow = chatShortcut?.parentElement,
    footer = document.querySelector('.foot'),
    mobileNav = matchMedia('(max-width:899px)');
  const placeChatShortcut = () => {
    if (!chatShortcut || !footer || !chatRow) return;
    if (mobileNav.matches) footer.prepend(chatShortcut);
    else chatRow.append(chatShortcut);
  };
  placeChatShortcut();
  mobileNav.addEventListener('change', placeChatShortcut);
  const bar = document.querySelector('.brandbar');
  if (bar) {
    const panel = menu(bar, 'mainNavMore', 'More app options');
    for (const selector of ['.case-pick', '#keyboardHelp']) {
      const control = document.querySelector(selector);
      if (control) panel.append(control);
    }
    const preview = document.getElementById('desktopPreview');
    if (preview) {
      preview.textContent = 'Message preview';
      preview.setAttribute('aria-label', 'Message preview');
      preview.title = 'Message preview';
      panel.prepend(preview);
    }
    const gear = document.getElementById('gear');
    if (gear) {
      gear.textContent = 'Settings';
      gear.setAttribute('aria-label', 'Settings');
      gear.title = 'Settings';
      panel.append(gear);
    }
    const chip = document.getElementById('leftChip');
    if (chip) {
      const amount = document.createElement('button');
      amount.type = 'button';
      amount.id = 'moreAmount';
      amount.className = 'more-amount';
      const sync = () => {
        amount.textContent = chip.textContent.trim();
      };
      sync();
      new MutationObserver(sync).observe(chip, {
        childList: true,
        characterData: true,
        subtree: true,
      });
      amount.onclick = () => chip.click();
      panel.prepend(amount);
    }
    const caseLabel = panel.querySelector('.case-pick .sr-only');
    if (caseLabel) caseLabel.classList.remove('sr-only');
  }
  // Keep common preview actions visible, retaining their existing handlers.
  const messageTools = document.querySelector('.msgcard .tools');
  if (messageTools) {
    const overflow = messageTools.querySelector('.overflow-tools');
    const copy = document.getElementById('copy');
    if (copy) {
      copy.textContent = 'Copy';
      messageTools.insertBefore(copy, overflow);
    }
    const poster = document.createElement('button');
    poster.type = 'button';
    poster.id = 'previewChangePoster';
    poster.className = 'tool';
    poster.textContent = 'Change poster';
    poster.onclick = () => {
      document.getElementById('posterDialog').dataset.returnRoute =
        window.Nav?.path?.() || 'preview';
      window.DonorHub?.openPoster();
    };
    messageTools.insertBefore(poster, document.getElementById('edit'));
    const hiddenPoster = overflow?.querySelector('button:not([id])');
    if (hiddenPoster) hiddenPoster.remove();
  }
  // Phone peek: tapping the message preview opens the full editor.
  const card = document.getElementById('card'),
    showMsg = document.getElementById('showMsg'),
    phone = matchMedia('(max-width:899px) and (min-height:600px)');
  if (card && showMsg)
    card.addEventListener('click', (e) => {
      if (
        phone.matches &&
        document.body.classList.contains('nomsg') &&
        !e.target.closest('button,a,input,select,textarea,summary')
      ) {
        e.preventDefault();
        showMsg.click();
      }
    });
  document.getElementById('openTeam')?.remove();
  const head = document.querySelector('.donor-head');
  if (head) {
    const panel = menu(head, 'donorNavMore', 'More donor options');
    for (const selector of ['.donor-message-tablist', '#donorBulk']) {
      const control = head.querySelector(selector);
      if (control) panel.append(control);
    }
    const normal = document.getElementById('donorNormalTotal')?.closest('.donor-total');
    if (normal) panel.append(normal);
    // At phone widths, show the two frequently used actions directly instead
    // of making the user open More. Move the original elements; never clone
    // buttons or rebind their donor/send handlers.
    const donorPhone = matchMedia('(max-width:560px)');
    const navDetails = document.getElementById('donorNavMore');
    const placeDonorActions = () => {
      const messages = document.querySelector('.donor-message-tablist');
      const bulk = document.getElementById('donorBulk');
      const add = document.getElementById('donorAdd');
      if (donorPhone.matches && add) {
        if (messages) head.insertBefore(messages, add);
        if (bulk) head.insertBefore(bulk, add);
        if (navDetails) {
          navDetails.open = false;
          navDetails.hidden = true;
        }
      } else {
        if (messages) panel.append(messages);
        if (bulk) panel.append(bulk);
        if (navDetails) navDetails.hidden = false;
      }
    };
    placeDonorActions();
    donorPhone.addEventListener('change', placeDonorActions);
  }
  document.addEventListener('pointerdown', (e) => {
    for (const m of menus) if (m.open && !m.contains(e.target)) m.open = false;
  });
  document.addEventListener(
    'toggle',
    (e) => {
      if (e.target instanceof HTMLDialogElement && e.target.open)
        for (const m of menus) m.open = false;
    },
    true,
  );
})();
