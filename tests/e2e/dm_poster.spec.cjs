const { test, expect } = require('@playwright/test');
const { showPreview, showDm } = require('./helpers.cjs');

for (const width of [390, 1440])
  test('DM Attach Poster works inside focused editor ' + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/old');
    await showDm(page);
    await showPreview(page);
    await expect(page.locator('#messageFocus')).toBeVisible();
    const poster = page.locator('#dmPoster');
    await expect(poster).toBeVisible();
    await expect(poster).toBeChecked();
    await poster.uncheck();
    await expect(page.locator('#sendDm')).toHaveText('Send text-only DM');
    await poster.check();
    await expect(page.locator('#sendDm')).toHaveText('Send DM with poster');
    await expect(page.locator('#batchPoster')).toBeChecked();
  });
