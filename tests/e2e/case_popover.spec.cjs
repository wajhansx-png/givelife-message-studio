const { test, expect } = require('@playwright/test');
/* The case list is a small anchored popover. Prompts are dismissed, so no case is ever changed. */
for (const [width, height] of [
  [320, 568],
  [375, 667],
  [1280, 800],
])
  test(`case popover at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    const writes = [];
    page.on('request', (r) => {
      if (r.method() === 'POST' && /\/cases/.test(r.url())) writes.push(r.postData());
    });
    page.on('dialog', (d) => d.dismiss());
    await page.goto('/old');
    await page.waitForTimeout(800);
    const more = page.locator('#mainNavMore > summary');
    const select = page.locator('#caseSelect');
    const openList = async () => {
      if (!(await select.isVisible())) await more.click();
      await select.click();
    };
    await openList();
    const pop = page.locator('.case-pop');
    await expect(pop).toBeVisible();
    const box = await pop.evaluate((e) => {
      const r = e.getBoundingClientRect();
      return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight;
    });
    expect(box).toBe(true);
    await expect(pop.locator('button')).toHaveCount(await select.locator('option').count());
    await page.keyboard.press('Escape');
    await expect(pop).toHaveCount(0);
    await openList();
    await page.mouse.click(2, height - 2);
    await expect(pop).toHaveCount(0);
    await openList();
    await pop.locator('.case-pop-act').first().click(); // Rename: the prompt is dismissed
    await openList();
    await pop.locator('.case-pop-act').last().click(); // New case: the prompt is dismissed
    await page.waitForTimeout(400);
    expect(writes).toEqual([]);
  });
