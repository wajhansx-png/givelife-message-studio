const { test, expect } = require('@playwright/test');
/* DM Messages: no donor tabs, arrow moves one message, one small status that expands on tap. */
for (const [width, height] of [
  [320, 568],
  [375, 667],
  [430, 932],
  [1280, 800],
])
  test(`DM messages screen at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    const detail =
      'The AI returned only 0 sufficiently different versions that kept the facts and formatting. The last problem was: a number, amount or phone number changed';
    await page.route('**/donor-messages**', async (route) => {
      const res = await route.fetch();
      let json;
      try {
        json = await res.json();
      } catch (e) {
        return route.fulfill({ response: res });
      }
      if (json && Array.isArray(json.items))
        json.generation = {
          state: 'Partial',
          ready: Math.max(1, json.items.length - 1),
          target: json.items.length,
          error: detail,
        };
      return route.fulfill({ response: res, json });
    });
    await page.goto('/old#/donors/messages');
    await expect(page.locator('.bank-preview').first()).toBeVisible();
    await expect(page.locator('.donor-tabs')).toBeHidden();
    const status = page.locator('.bank-generation-state');
    await expect(status).toContainText(/ready · \d+ need review/);
    expect((await status.innerText()).length).toBeLessThan(40);
    await status.click();
    await expect(status).toContainText('a number, amount or phone number changed');
    const title = page.locator('.bank-current');
    const before = await title.innerText();
    await page.locator('.bank-next-arrow').click();
    await expect(title).not.toHaveText(before);
    await expect(page.locator('.bank-gen-icon')).toBeVisible();
    await expect(page.locator('.bank-pagination [data-bank-nav="next"]')).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    const arrowOk = await page.evaluate(() => {
      const a = document.querySelector('.bank-next-arrow').getBoundingClientRect();
      return a.right <= innerWidth && a.left >= 0;
    });
    expect(arrowOk).toBe(true);
  });
