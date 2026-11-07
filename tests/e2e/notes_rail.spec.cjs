const { test, expect } = require('@playwright/test');
for (const width of [1440, 390, 320])
  test(`Notes selection format bar ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
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
    const editor = page.locator('#notesEditor'),
      rail = page.locator('.notes-toolbar');
    await expect(rail).toBeHidden(); /* nothing selected: no bar */
    await editor.fill('Foundation task');
    await editor.press('ControlOrMeta+A');
    await expect(rail).toBeVisible();
    for (const name of ['Bold', 'Italic', 'Numbers', 'Bullets', 'Checklist', 'Smaller', 'Larger'])
      await expect(rail.getByText(name, { exact: true })).toBeVisible();
    for (const tag of ['h1', 'h2', 'h3'])
      await expect(rail.locator('[data-block="' + tag + '"]')).toBeVisible();
    {
      const sel = await editor.evaluate(() => {
          const r = getSelection().getRangeAt(0).getBoundingClientRect();
          return { bottom: r.bottom, top: r.top };
        }),
        bar = await rail.boundingBox();
      expect(bar.y).toBeGreaterThanOrEqual(sel.bottom); /* shown under the selected text */
      expect(bar.x).toBeGreaterThanOrEqual(0);
      expect(bar.x + bar.width).toBeLessThanOrEqual(width);
    }
    await rail.getByRole('button', { name: 'Bold', exact: true }).click();
    await expect(editor.locator('b,strong')).toContainText('Foundation task');
    await rail.getByLabel('Text color', { exact: true }).selectOption('#f4a4ad');
    await rail.getByLabel('Text color', { exact: true }).selectOption('#ededed');
    await rail.getByRole('button', { name: 'Increase notes font size' }).click();
    /* Default is 23 on phones and 27 on desktop; one tap adds 1. */
    await expect(editor).toHaveCSS('font-size', (width <= 720 ? 24 : 28) + 'px');
    await expect(rail.getByRole('button', { name: 'Numbered list' })).toHaveText('Numbers');
    await expect(page.locator('.notes-paper')).toHaveCSS('border-top-width', '0px');
    await editor.fill(Array.from({ length: 100 }, (_, i) => 'Task ' + i).join('\n'));
    await editor.evaluate((e) => (e.scrollTop = 0));
    await editor.hover();
    await page.mouse.wheel(0, 700);
    await expect.poll(() => editor.evaluate((e) => e.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollTop)).toBe(0);
    await expect(page.locator('#notesSync')).toHaveText('Saved');
    await page.screenshot({ path: `test-results/notes-rail-${width}.png` });
  });
