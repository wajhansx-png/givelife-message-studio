const { test, expect } = require('@playwright/test');
for (const width of [1440, 390])
  test(`preview poster returns to focused editor ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/old#/preview');
    await expect(page.locator('#focusFormatted')).not.toHaveText('');
    await page.locator('#focusPoster').click();
    await expect(page.locator('#posterDialog')).toBeVisible();
    await page.locator('#posterClose').click();
    await expect(page.locator('#messageFocus')).toBeVisible();
    await expect(page.locator('#set')).not.toBeVisible();
    await expect(page.locator('#focusCopy')).toBeVisible();
  });
