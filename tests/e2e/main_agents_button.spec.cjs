const { test, expect } = require('@playwright/test');

for (const [name, width, height] of [
  ['phone', 390, 844],
  ['desktop', 1440, 900],
]) {
  test(`main page has an Agents button and no Case plan button (${name})`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/');
    const btn = page.locator('#openCasePlan');
    await expect(btn).toHaveText('Agents');
    await expect(btn).toBeVisible();
    await expect(page.getByRole('button', { name: 'Case plan', exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await btn.click();
    await expect(page).toHaveURL(/\/agents$/);
    await expect(page.locator('#list .agent').first()).toContainText('Manager');
  });
}
