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
      /* Keep the panel fully on screen (it can sit past the left or right edge on 320 px phones). */
      panel.style.translate = '';
      if (details.open)
        requestAnimationFrame(() => {
          const r = panel.getBoundingClientRect();
          const dx =
            r.left < 8 ? 8 - r.left : r.right > innerWidth - 8 ? innerWidth - 8 - r.right : 0;
          if (dx) panel.style.translate = Math.round(dx) + 'px 0';
        });
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
    for (const selector of ['.donor-message-tablist', '#donorBulk', '#donorNumbers']) {
      const control = head.querySelector(selector);
      if (control) panel.append(control);
    }
    const normal = document.getElementById('donorNormalTotal')?.closest('.donor-total');
    if (normal) panel.append(normal);
    // Keep Messages beside Add on phones; Bulk stays under More so the
    // header fits on one line. Move the original controls without rebinding
    // their donor/send handlers.
    const donorPhone = matchMedia('(max-width:560px)');
    const navDetails = document.getElementById('donorNavMore');
    const placeDonorActions = () => {
      // The redesign owns these controls and nests Add inside its menu.
      if (document.body.classList.contains('ui2')) return;
      const messages = document.querySelector('.donor-message-tablist');
      const bulk = document.getElementById('donorBulk');
      const numbers = document.getElementById('donorNumbers');
      const add = document.getElementById('donorAdd');
      if (donorPhone.matches && add) {
        if (messages) head.insertBefore(messages, add.parentNode === head ? add : null);
        if (bulk) panel.append(bulk);
        if (numbers) panel.append(numbers);
        if (navDetails) {
          // More still exposes Test DM and Poster settings on phones.
          navDetails.hidden = false;
        }
      } else {
        if (messages) panel.append(messages);
        if (bulk) panel.append(bulk);
        if (numbers) panel.append(numbers);
        if (navDetails) navDetails.hidden = false;
      }
    };
    placeDonorActions();
    donorPhone.addEventListener('change', placeDonorActions);
    /* Classic phone/tablet header, one row on every tab: Donors, search icon, Messages, More.
       + Add and the Important-tab chips (hide contacted, deselect all) live in More; search opens in place
       over this row, so nothing below it ever moves. The controls are moved, never rebuilt. */
    if (!document.body.classList.contains('ui2')) {
      const compact = matchMedia('(max-width:899px)');
      const add = document.getElementById('donorAdd');
      const hideRow = document.getElementById('donorHideRow');
      const input = document.getElementById('donorSearch');
      const toolbar = document.querySelector('.donor-toolbar');
      const open = document.createElement('button');
      open.type = 'button';
      open.id = 'donorSearchOpen';
      open.className = 'donor-search-open';
      open.setAttribute('aria-label', 'Search donors');
      open.title = 'Search donors';
      open.innerHTML =
        '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>';
      const close = document.createElement('button');
      close.type = 'button';
      close.id = 'donorSearchClose';
      close.className = 'donor-search-close';
      close.setAttribute('aria-label', 'Close search');
      close.textContent = '×';
      const setSearch = (on) => {
        head.classList.toggle('search-open', on);
        open.setAttribute('aria-expanded', String(on));
        if (on) input?.focus();
      };
      const clearSearch = () => {
        if (!input || !input.value) return;
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      open.onclick = () => setSearch(true);
      close.onclick = () => {
        clearSearch();
        setSearch(false);
        open.focus();
      };
      input?.addEventListener('blur', () => {
        if (!input.value.trim()) setSearch(false);
      });
      input?.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        e.preventDefault();
        close.click();
      });
      /* A small dot on More says "contacted donors are hidden" while the Important list is filtered. */
      const more = navDetails?.querySelector('summary');
      const flag = () => {
        const chip = document.getElementById('donorHideSent');
        more?.toggleAttribute(
          'data-note',
          !!hideRow && !hideRow.hidden && !chip?.hidden && /hidden/.test(chip?.textContent || ''),
        );
      };
      if (hideRow) {
        new MutationObserver(flag).observe(hideRow, {
          attributes: true,
          childList: true,
          subtree: true,
          characterData: true,
        });
        flag();
      }
      const place = () => {
        if (compact.matches) {
          head.insertBefore(open, head.querySelector(':scope > .donor-message-tablist'));
          if (input) head.append(input);
          head.append(close);
          if (add) panel.prepend(add);
          if (hideRow) panel.prepend(hideRow);
        } else {
          open.remove();
          close.remove();
          setSearch(false);
          if (input && toolbar) toolbar.append(input);
          if (add) head.append(add);
          if (hideRow)
            head.insertBefore(hideRow, head.querySelector(':scope > .donor-message-tablist'));
        }
      };
      place();
      compact.addEventListener('change', place);
    }
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
