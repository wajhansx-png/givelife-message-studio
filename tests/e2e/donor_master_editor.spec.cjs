const { test, expect } = require('@playwright/test');
for (const width of [1440, 390])
  test('Donor Messages uses focused black Group-style editor ' + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/old#/donors/messages');
    await expect(page.locator('#donorsPage')).toBeVisible();
    await expect(page.locator('#donorsPage')).toHaveAttribute('data-panel', 'messages');
    await expect(page.locator('.bank-workspace')).toBeVisible();
    await expect(page.locator('.bank-message.bank-detail')).toBeVisible();
    await expect(page.locator('.bank-actions')).toBeVisible();
    // One message at a time with a single Next: the version list is intentionally not shown.
    await expect(page.locator('.bank-picker')).toBeHidden();
    await expect(page.locator('.bank-next-arrow')).toBeVisible();
    await expect(page.locator('[data-bank-nav=previous]')).toBeHidden();
    // The editor sits on a dark surface (own background, or the page's when it is transparent).
    const dark = await page.locator('#donorMessages').evaluate((el) => {
      for (let n = el; n; n = n.parentElement) {
        const m = getComputedStyle(n).backgroundColor.match(/[\d.]+/g);
        if (m && (m[3] === undefined || +m[3] > 0.5)) return (+m[0] + +m[1] + +m[2]) / 3 < 60;
      }
      return false;
    });
    expect(dark).toBe(true);
    const editor = page.locator('.bank-detail textarea');
    await page.locator('.bank-actions [data-bank-save-id]').click();
    await expect(editor).toBeVisible();
    await expect(page.locator('.bank-actions [data-bank-save-id]')).toHaveText('Save');
    // This is only a UI test: never click Send or submit an edited fundraising caption.
  });
