const { test, expect } = require('@playwright/test');
/* Group preview: edit -> click outside saves -> refresh keeps it; Save Base opens a modal; arrow + More. */
for (const [width, height] of [
  [320, 568],
  [375, 667],
  [1280, 800],
])
  test(`group preview edit, Save Base and controls at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      if (!sessionStorage.getItem('seeded')) {
        localStorage.clear();
        sessionStorage.setItem('seeded', '1');
      }
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    await page.goto('/#/preview');
    await expect(page.locator('#focusFormatted')).toBeVisible();
    const marker = ' EDIT' + width;
    await page.locator('#focusFormatted').dblclick();
    const box = page.locator('#focusText');
    await expect(box).toBeVisible();
    await box.press('Control+End');
    await box.pressSequentially(marker);
    await page.mouse.click(3, 3); // outside the editor and the tool rail
    await expect(box).toBeHidden();
    await expect(page.locator('#focusState')).toContainText(/Saved/);
    await page.reload();
    await expect(page.locator('#focusFormatted')).toContainText(marker.trim());
    // Save Base opens a small modal; Cancel closes it, Save confirms.
    await expect(page.locator('#focusSave')).toHaveText('Save Base');
    await page.locator('#focusSave').click();
    await expect(page.locator('#focusBaseDialog')).toBeVisible();
    await page.locator('#focusBaseCancel').click();
    await expect(page.locator('#focusBaseDialog')).toBeHidden();
    // Controls: arrow on the card edge, rare tools folded under More.
    const arrow = page.locator('#focusNextArrow');
    await expect(arrow).toBeVisible();
    const sides = await page.evaluate(() => {
      const a = document.getElementById('focusNextArrow').getBoundingClientRect();
      const c = document.getElementById('focusFormatted').getBoundingClientRect();
      return {
        right: a.right <= innerWidth,
        mid: Math.abs(a.top + a.height / 2 - (c.top + c.height / 2)) < c.height / 2,
      };
    });
    expect(sides).toEqual({ right: true, mid: true });
    await expect(page.locator('#focusPoster')).toBeHidden();
    await page.locator('.focus-rail-more > summary').click();
    await expect(page.locator('#focusPoster')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
