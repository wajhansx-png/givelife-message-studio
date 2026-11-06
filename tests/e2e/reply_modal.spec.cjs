const { test, expect } = require('@playwright/test');
/* Reply setup: one screen, two audiences, Save persists + closes, unsaved edits are not thrown away silently. */
for (const [width, height] of [
  [320, 568],
  [375, 667],
  [1280, 800],
])
  test(`reply modal at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    await page.goto('/');
    await page.waitForTimeout(800);
    const openReply = async () => {
      await page.locator('#mainNavMore > summary').click();
      await page.locator('.reply-open').first().click();
      await expect(page.locator('.replies-dialog')).toBeVisible();
    };
    await openReply();
    const dlg = page.locator('.replies-dialog');
    await expect
      .poll(() => dlg.evaluate(() => { const s = document.getElementById('repSave').getBoundingClientRect(); return s.bottom <= innerHeight && s.top >= 0; }))
      .toBe(true);
    const sw = await page.locator('#repEnabled').boundingBox();
    expect(sw.width).toBeGreaterThanOrEqual(24);
    const existing = 'Share this case please ' + width,
      fresh = 'Join GiveLife ' + width;
    await page.locator('#repList textarea').first().fill(existing);
    await page.locator('#repNewList textarea').first().fill(fresh);
    await page.locator('#repSave').click();
    await expect(page.locator('#repNote')).toContainText('Saved ✓');
    await expect(dlg).toBeHidden();
    await page.reload();
    await page.waitForTimeout(600);
    await openReply();
    await expect(page.locator('#repList textarea').first()).toHaveValue(existing);
    await expect(page.locator('#repNewList textarea').first()).toHaveValue(fresh);
    await expect(page.locator('#repEnabled')).toBeChecked();
    // Unsaved edit + Close: the confirm is declined, so the modal stays open with the text.
    await page
      .locator('#repList textarea')
      .first()
      .fill(existing + ' changed');
    page.once('dialog', (d) => d.dismiss());
    await page.locator('#repClose').click();
    await expect(dlg).toBeVisible();
    await expect(page.locator('#repList textarea').first()).toHaveValue(existing + ' changed');
  });
