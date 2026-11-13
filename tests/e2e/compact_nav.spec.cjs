const { test, expect } = require('@playwright/test');
const { openDonorMessages } = require('./helpers.cjs');
for (const width of [1440, 1024, 390, 320])
  test(`compact navigation keeps actions reachable ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/old');
    await expect(page.locator('#openTeam')).toHaveCount(0);
    await expect(page.locator('.message-copy').first()).toHaveCSS('font-size', '0px');
    const main = page.locator('#mainNavMore');
    await expect(main).toBeVisible();
    await expect(page.locator('.brandbar #donorNotesShortcut')).toBeVisible();
    await expect(page.locator('#desktopPreview')).toHaveCount(1);
    await main.locator('summary').click();
    await expect(page.locator('#caseSelect')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(main).not.toHaveAttribute('open');
    await main.locator('summary').click();
    await page.locator('#keyboardHelp').click();
    await expect(page.locator('#keyboardDialog')).toBeVisible();
    await page.locator('#keyboardClose').click();
    await page.goto('/old#/donors/all');
    const more = page.locator('#donorNavMore');
    await expect(more).toBeVisible();
    await expect(page.locator('#donorBulk')).not.toBeVisible();
    await more.locator('summary').click();
    await openDonorMessages(page);
    await expect(page.locator('#donorMessages')).toBeVisible();
    await expect(more).not.toHaveAttribute('open');
    await page.goto('/old#/donors/all');
    await more.locator('summary').click();
    await page.locator('#donorBulk').click();
    await expect(page.locator('#donorPasteDialog')).toBeVisible();
    await page.locator('#pasteCancel').click();
    await expect(page.locator('#donorPasteDialog')).not.toBeVisible();
    await page.goto('/old#/donors/all');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/nav-donors-${width}.png` });
    await page.locator('#donorMainBottom').click();
    await expect(page.locator('#donorsPage')).not.toBeVisible();
    await page.screenshot({ path: `test-results/nav-main-${width}.png` });
  });
