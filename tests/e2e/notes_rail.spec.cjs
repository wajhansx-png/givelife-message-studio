const { test, expect } = require('@playwright/test');

async function unlock(page, width, height = 850) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.request.post('/__test/seed', {
    headers: { Authorization: 'Bearer manual-fix-preview-key' },
    data: { reset_notes: true },
  });
  await page.goto('/#/donors/all/notes');
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  await expect(page.locator('#notesEditor')).toBeVisible();
}

for (const width of [1440, 1024, 768, 390, 320])
  test(`Notes side tools and calm layout ${width}`, async ({ page }) => {
    await unlock(page, width);
    const editor = page.locator('#notesEditor'),
      panel = page.locator('.notes-toolbar'),
      paper = page.locator('.notes-paper');
    await editor.fill('Foundation task');
    await expect(panel).toBeHidden(); /* hidden until a side handle opens it */

    /* Calm defaults: 18px (17px on phones), a hairline border, centred column. */
    await expect(editor).toHaveCSS('font-size', (width <= 720 ? 17 : 18) + 'px');
    await expect(paper).toHaveCSS('border-top-width', '1px');
    const box = await paper.boundingBox();
    expect(Math.abs(box.x + box.width / 2 - width / 2)).toBeLessThan(3);
    expect(box.width).toBeLessThanOrEqual(780);

    /* Both handles sit inside the screen, one on each edge. */
    for (const side of ['left', 'right']) {
      const handle = page.locator(`.notes-edge[data-side="${side}"]`);
      await expect(handle).toBeVisible();
      const h = await handle.boundingBox();
      expect(h.x).toBeGreaterThanOrEqual(0);
      expect(h.x + h.width).toBeLessThanOrEqual(width);
    }

    for (const side of ['right', 'left']) {
      await page.locator(`.notes-edge[data-side="${side}"]`).click();
      await expect(panel).toBeVisible();
      for (const name of ['Bold', 'Italic', 'Numbers', 'Bullets', 'Checklist', 'Smaller', 'Larger'])
        await expect(panel.getByText(name, { exact: true })).toBeVisible();
      for (const tag of ['h1', 'h2', 'h3'])
        await expect(panel.locator(`[data-block="${tag}"]`)).toBeVisible();
      const bar = await panel.boundingBox();
      expect(bar.x).toBeGreaterThanOrEqual(0);
      expect(bar.x + bar.width).toBeLessThanOrEqual(width);
      if (width >= 1100) {
        /* wide screens: the panel never covers the writing column */
        if (side === 'right') expect(bar.x).toBeGreaterThan(box.x + box.width);
        else expect(bar.x + bar.width).toBeLessThan(box.x);
      }
      await page.keyboard.press('Escape');
      await expect(panel).toBeHidden();
    }

    /* Format the selection from the panel; nothing is lost. */
    await editor.press('ControlOrMeta+A');
    await page.locator('.notes-edge[data-side="right"]').click();
    await panel.getByRole('button', { name: 'Bold', exact: true }).click();
    await expect(editor.locator('b,strong')).toContainText('Foundation task');
    await panel.getByLabel('Text color', { exact: true }).selectOption('#f4a4ad');
    await panel.getByLabel('Text color', { exact: true }).selectOption('#ededed');
    await panel.getByRole('button', { name: 'Increase notes font size' }).click();
    await expect(editor).toHaveCSS('font-size', (width <= 720 ? 18 : 19) + 'px');

    /* Typing puts the tools away. */
    await editor.press('End');
    await editor.type(' more');
    await expect(panel).toBeHidden();

    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(
      false,
    );
    await editor.fill(Array.from({ length: 100 }, (_, i) => 'Task ' + i).join('\n'));
    await editor.evaluate((e) => (e.scrollTop = 0));
    await editor.hover();
    await page.mouse.wheel(0, 700);
    await expect.poll(() => editor.evaluate((e) => e.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollTop)).toBe(0);
    await expect(page.locator('#notesSync')).toHaveText('Saved');
  });

test('Enter starts the next paragraph in the default colour; earlier colour is kept', async ({
  page,
}) => {
  await unlock(page, 1280, 800);
  const editor = page.locator('#notesEditor');
  await editor.evaluate((e) => {
    e.innerHTML = '<p><font color="#f4a4ad">Red line</font></p>';
    const r = document.createRange();
    r.selectNodeContents(e.querySelector('font'));
    r.collapse(false);
    const s = getSelection();
    s.removeAllRanges();
    s.addRange(r);
    e.focus();
  });
  await page.keyboard.press('Enter');
  await page.keyboard.type('plain');
  const html = await editor.innerHTML();
  expect(html).toContain('<font color="#f4a4ad">Red line</font>');
  expect(html).toMatch(/<p>plain<\/p>/);
  expect(html).not.toMatch(/<font[^>]*>plain/);
});

test('Notes with the keyboard open keep the tools inside the visible area', async ({ page }) => {
  await unlock(page, 390, 844);
  const editor = page.locator('#notesEditor');
  await editor.fill(Array.from({ length: 30 }, (_, i) => 'Idea ' + i).join('\n'));
  await editor.focus();
  /* An on-screen keyboard shrinks the visible view. */
  await page.setViewportSize({ width: 390, height: 440 });
  await expect(page.locator('#foundationNotes')).toHaveAttribute('data-keyboard', 'open');
  await page.locator('.notes-edge[data-side="right"]').click();
  const panel = page.locator('.notes-toolbar');
  await expect(panel).toBeVisible();
  const bar = await panel.boundingBox();
  expect(bar.y).toBeGreaterThanOrEqual(0);
  expect(bar.y + bar.height).toBeLessThanOrEqual(441);
  const handle = await page.locator('.notes-edge[data-side="right"]').boundingBox();
  expect(handle.y + handle.height).toBeLessThanOrEqual(441);
});
