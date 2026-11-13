const { test, expect } = require('@playwright/test');
const auth = { Authorization: 'Bearer manual-fix-preview-key' };
async function open(page, request, width = 1280, height = 800) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await request.post('/__test/seed', {
    headers: auth,
    data: { reply: 'Ready.', reset_notes: true },
  });
  await page.goto('/old');
  /* Notes has its own button in the main navigation. */
  await page.locator('#donorNotesShortcut').click();
  await expect(page.locator('#foundationNotes')).toBeVisible();
}
/* The edit tools hide in a side panel; a slim handle on either screen edge opens it. */
async function openTools(page, side = 'right') {
  await page.locator('.notes-edge[data-side="' + side + '"]').click();
  await expect(page.locator('.notes-toolbar')).toBeVisible();
}
test('private notes: password, autosave, reload, desktop remembrance and lock', async ({
  page,
  request,
}) => {
  await open(page, request);
  await expect(page.locator('#notesLocked')).toBeVisible();
  await page.locator('#notesPassword').fill('wrong');
  await page.locator('#notesUnlockButton').click();
  await expect(page.locator('#notesError')).toContainText('Incorrect');
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  const editor = page.locator('#notesEditor');
  await expect(editor).toBeVisible();
  await editor.fill('Plan student volunteer outreach');
  await expect(page.locator('#notesSync')).toHaveText('Saved', { timeout: 10000 });
  await page.mouse.move(100, 18); // reveal hidden navigation as a user would
  await page.locator('#notesBack').click();
  await page.locator('#donorNotesShortcut').click();
  await expect(editor).toContainText('Plan student volunteer outreach');
  await expect(page.locator('#notesLocked')).toBeHidden();
  await page.reload();
  await expect(page.locator('#foundationNotes')).toBeVisible();
  await expect(page.locator('#notesLocked')).toBeHidden();
  await expect(editor).toContainText('Plan student volunteer outreach');
  await page.mouse.move(100, 18);
  await page.locator('#notesLock').click();
  await expect(page.locator('#notesLocked')).toBeVisible();
  await page.mouse.move(100, 18); // reveal hidden navigation as a user would
  await page.mouse.move(100, 18);
  await page.locator('#notesBack').click();
  await page.locator('#donorNotesShortcut').click();
  await expect(page.locator('#notesLocked')).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('givelife-notes-password'))).toBeNull();
});
test('phone notes: readable editing surface, toolbar and no sideways scrolling', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 844);
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  const editor = page.locator('#notesEditor');
  await expect(editor).toBeVisible();
  await editor.fill('Find university representatives');
  await editor.press('ControlOrMeta+A');
  // Formatting controls live in the side panel opened by the edge handle.
  await openTools(page);
  await page
    .locator('.notes-toolbar')
    .getByRole('button', { name: 'Bullets', exact: true })
    .click();
  await expect(editor.locator('ul li')).toContainText('Find university representatives');
  await expect(page.locator('#notesSync')).toHaveText('Saved', { timeout: 10000 });
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  expect(wide).toBe(false);
  const bar = await page.locator('.notes-toolbar').boundingBox();
  expect(bar.x + bar.width).toBeLessThanOrEqual(391);
});

test('mobile virtual keyboard keeps Notes paper tall while the caret stays visible', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 844);
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  const editor = page.locator('#notesEditor');
  await expect(editor).toBeVisible();
  // Opening Notes must not force the mobile keyboard until the user taps the page.
  expect(await page.evaluate(() => document.activeElement?.id)).not.toBe('notesEditor');
  const initial = await page.evaluate(() => ({
    paper: document.querySelector('.notes-paper').getBoundingClientRect().height,
    scroller: document.querySelector('.notes-paper-scroll').getBoundingClientRect().height,
  }));
  await editor.fill(Array.from({ length: 36 }, (_, i) => 'Foundation idea ' + (i + 1)).join('\\n'));
  await editor.focus();
  // Mobile Chromium has no native keyboard, so resize the visual viewport as an
  // Android keyboard does with interactive-widget=resizes-content.
  await page.setViewportSize({ width: 390, height: 460 });
  await expect(page.locator('#foundationNotes')).toHaveAttribute('data-keyboard', 'open');
  const smaller = await page.evaluate(() => {
    const paper = document.querySelector('.notes-paper'),
      scroller = document.querySelector('.notes-paper-scroll');
    const bar = document.querySelector('.notes-toolbar');
    const bounds = scroller.getBoundingClientRect();
    return {
      paper: paper.getBoundingClientRect().height,
      scroller: bounds.height,
      toolbarBottom: bar.getBoundingClientRect().bottom,
      xOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      scrollable:
        document.querySelector('#notesEditor').scrollHeight >
        document.querySelector('#notesEditor').clientHeight + 20,
      keyboardOverlay: bounds.bottom > innerHeight + 1,
    };
  });
  expect(smaller.paper).toBeGreaterThan(150);
  expect(smaller.paper).toBeLessThanOrEqual(460);
  expect(smaller.scroller).toBeGreaterThan(150);
  expect(smaller.toolbarBottom).toBeLessThanOrEqual(460);
  expect(smaller.scrollable).toBe(true);
  expect(smaller.xOverflow).toBe(false);
  expect(smaller.keyboardOverlay).toBe(false);
  await editor.press('End');
  await editor.type(' Extra mobile update');
  await expect(editor).toContainText('Extra mobile update');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('#foundationNotes')).toHaveAttribute('data-keyboard', 'closed');
  expect((await page.locator('.notes-paper-scroll').boundingBox()).height).toBeGreaterThan(
    smaller.scroller,
  );
});

test('quiet Notes keeps only writing visible; top-edge reveals controls and fullscreen', async ({
  page,
  request,
}) => {
  await open(page, request, 1280, 800);
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  await expect(page.locator('#notesEditor')).toBeVisible();
  const head = page.locator('.notes-head'),
    toolbar = page.locator('.notes-toolbar');
  // Pointer starts away from the top after entry so editing is distraction-free.
  await page.mouse.move(920, 600);
  await expect(head).toBeHidden();
  await expect(toolbar).toBeHidden();
  const colors = await page.evaluate(() => {
    const page = document.getElementById('foundationNotes');
    const paper = document.querySelector('.notes-paper');
    const editor = document.getElementById('notesEditor');
    return {
      page: getComputedStyle(page).backgroundColor,
      paper: getComputedStyle(paper).backgroundColor,
      editor: getComputedStyle(editor).backgroundColor,
      border: getComputedStyle(paper).borderTopWidth,
      outline: getComputedStyle(editor).outlineStyle,
      shadow: getComputedStyle(paper).boxShadow,
    };
  });
  expect(colors.page).toBe('rgb(36, 36, 36)');
  expect(colors.editor).toBe('rgba(0, 0, 0, 0)');
  expect(colors.border).toBe('1px'); /* a hairline border frames the writing column */
  expect(colors.outline).toBe('none');
  expect(colors.shadow).toBe('none'); /* no glow or shadow under the writing column (design rule) */
  await page.locator('#notesEditor').fill('A focused foundation idea');
  await expect(toolbar).toBeHidden();
  await page.mouse.move(100, 18);
  await expect(head).toBeVisible();
  await expect(toolbar).toBeHidden(); /* the tools only open from a side handle */
  await expect(page.getByRole('button', { name: 'Full screen', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Full screen', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(true);
  await page.evaluate(() => document.exitFullscreen());
  await page.mouse.move(920, 600);
  await expect(toolbar).toBeHidden();
  await page.keyboard.press('Alt+t');
  await expect(head).toBeVisible();
  await expect(toolbar).toBeVisible(); /* Alt+T also opens the side tools */
  await page.keyboard.press('Escape');
  await expect(toolbar).toBeHidden();
});
test('mobile Notes opens a hidden toolbar by tapping top edge without shrinking editor', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 844);
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  await expect(page.locator('#notesEditor')).toBeVisible();
  await expect(page.locator('.notes-toolbar')).toBeHidden();
  const height = (await page.locator('.notes-paper').boundingBox()).height;
  await page
    .locator('#foundationNotes')
    .dispatchEvent('pointerdown', { pointerType: 'touch', clientX: 12, clientY: 16 });
  await expect(page.locator('.notes-head')).toBeVisible();
  await page.locator('#notesEditor').fill('Volunteer outreach');
  await page.locator('#notesEditor').press('ControlOrMeta+A');
  await openTools(page);
  await page
    .locator('.notes-toolbar')
    .getByRole('button', { name: 'Bullets', exact: true })
    .click();
  await expect(page.locator('#notesEditor li')).toHaveText('Volunteer outreach');
  expect((await page.locator('.notes-paper').boundingBox()).height).toBeGreaterThanOrEqual(
    height - 2,
  );
  const edgeTap = () =>
    page
      .locator('#foundationNotes')
      .dispatchEvent('pointerdown', { pointerType: 'touch', clientX: 12, clientY: 16 });
  // The test's mouse clicks (a phone sends none) may already have folded the header; start from shown.
  if ((await page.locator('#foundationNotes').getAttribute('data-controls')) !== 'open')
    await edgeTap();
  await expect(page.locator('.notes-head')).toBeVisible();
  await edgeTap();
  await expect(page.locator('.notes-head')).toBeHidden();
});

test('desktop note-taking: type, select, style, save, reopen and keep writing focus', async ({
  page,
  request,
}) => {
  await open(page, request, 1440, 900);
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  const editor = page.locator('#notesEditor');
  await editor.fill('Meet university donors and plan outreach');
  await expect(page.locator('#notesSync')).toHaveText('Saved', { timeout: 10000 });
  await page.mouse.move(850, 620);
  await expect(page.locator('.notes-toolbar')).toBeHidden();
  await editor.focus();
  await editor.press('ControlOrMeta+A');
  await openTools(page);
  await page.locator('#notesRed').click();
  const selectedHtml = await editor.innerHTML();
  expect(selectedHtml, 'Red must apply visibly to the selected note text').toMatch(
    /<font[^>]*color="#f4a4ad"/i,
  );
  await expect(page.locator('#notesSync')).toHaveText('Saved', { timeout: 10000 });
  const editorHeight = (await editor.boundingBox()).height;
  await editor.focus();
  await editor.press('End');
  await editor.press('Enter');
  await editor.type('New volunteer recruitment ideas');
  await expect(editor).toContainText('New volunteer recruitment ideas');
  await expect(page.locator('.notes-toolbar')).toBeHidden(); /* typing puts the tools away */
  await expect(page.locator('#notesSync')).toHaveText('Saved', { timeout: 10000 });
  expect((await editor.boundingBox()).height).toBeGreaterThanOrEqual(editorHeight - 2);
  await page.mouse.move(110, 18);
  await page.locator('#notesBack').click();
  await page.locator('#donorNotesShortcut').click();
  await expect(editor).toContainText('Meet university donors');
  await expect(editor).toContainText('New volunteer recruitment ideas');
});
test('narrow phone: editor and formatting rail fit with keyboard open', async ({
  page,
  request,
}) => {
  await open(page, request, 320, 680);
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  const editor = page.locator('#notesEditor');
  await expect(editor).toBeVisible();
  await expect(page.locator('.notes-toolbar')).toBeHidden(); /* opens only from a side handle */
  await editor.fill('Contact committed donors today.');
  await expect(page.locator('#notesSync')).toHaveText('Saved', { timeout: 10000 });
  await editor.press('ControlOrMeta+A');
  await page
    .locator('#foundationNotes')
    .dispatchEvent('pointerdown', { pointerType: 'touch', clientX: 10, clientY: 12 });
  await openTools(page);
  const bounds = await page.evaluate(() => {
    const screen = document.getElementById('foundationNotes').getBoundingClientRect();
    const back = document.getElementById('notesBack').getBoundingClientRect();
    const lock = document.getElementById('notesLock').getBoundingClientRect();
    const full = document.getElementById('notesFullscreen').getBoundingClientRect();
    const bar = document.querySelector('.notes-toolbar').getBoundingClientRect();
    return {
      screen: [screen.left, screen.right],
      back: [back.left, back.right],
      backTop: back.top,
      lockBottom: lock.bottom,
      lock: [lock.left, lock.right],
      full: [full.left, full.right],
      toolbar: [bar.left, bar.right],
      overflow: document.documentElement.scrollWidth > innerWidth + 1,
    };
  });
  expect(bounds.back[0]).toBeGreaterThanOrEqual(0);
  expect(bounds.full[1]).toBeLessThanOrEqual(321);
  expect(bounds.lock[1]).toBeLessThanOrEqual(321);
  expect(bounds.back[0]).toBeGreaterThan(220);
  expect(bounds.backTop).toBeGreaterThan(bounds.lockBottom);
  expect(bounds.lock[1]).toBeLessThan(bounds.full[0]);
  expect(bounds.toolbar[1]).toBeLessThanOrEqual(321);
  expect(bounds.overflow).toBe(false);
  await page
    .locator('#foundationNotes')
    .dispatchEvent('pointerdown', { pointerType: 'touch', clientX: 10, clientY: 12 });
  await expect(page.locator('.notes-toolbar')).toBeVisible();
  await page.setViewportSize({ width: 320, height: 400 });
  await editor.focus();
  await expect(page.locator('#foundationNotes')).toHaveAttribute('data-keyboard', 'open');
  const paper = await page.locator('.notes-paper').boundingBox();
  expect(paper.height).toBeGreaterThan(150);
  expect(paper.y + paper.height).toBeLessThanOrEqual(401);
});

test('notes use a calm 18px column, start high, centred, with Bullets in the side tools', async ({
  page,
  request,
}) => {
  await open(page, request, 1920, 1080);
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  const editor = page.locator('#notesEditor');
  await editor.click();
  await page.keyboard.type('Plan outreach');
  await expect(editor).toHaveCSS('font-size', '18px');
  const paper = await page.locator('.notes-paper').boundingBox();
  expect(Math.abs(paper.x + paper.width / 2 - 960)).toBeLessThan(3);
  await expect(page.locator('.notes-toolbar')).toBeHidden(); /* tools stay out of the way */
  const line = await editor.locator('> *').first().boundingBox();
  expect(line.y).toBeGreaterThan(30);
  expect(line.y).toBeLessThan(120); /* starts near the top, not at screen centre */
  await page.keyboard.press('Home');
  await page.keyboard.press('Shift+End');
  await openTools(page);
  await page.getByRole('button', { name: 'Bullets', exact: true }).click();
  await expect(editor.locator('ul li')).toHaveText('Plan outreach');
  await page.getByRole('button', { name: 'Bullets', exact: true }).click();
  await expect(editor.locator('ul')).toHaveCount(0);
});
