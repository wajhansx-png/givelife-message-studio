const { test, expect } = require('@playwright/test');
for (const [width, height] of [
  [320, 568],
  [768, 1024],
  [1440, 900],
]) {
  test(`Group finder and its settings fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/group-finder');
    await expect(page.locator('h1')).toHaveText('Group finder');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await page.locator('#targetsOpen').click();
    const dialog = page.locator('#targets');
    await expect(dialog).toBeVisible();
    const box = await dialog.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    expect(box.y + box.height).toBeLessThanOrEqual(height + 1);
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await dialog.getByRole('button', { name: 'Done', exact: true }).click();
    await expect(dialog).toBeHidden();
  });
}
