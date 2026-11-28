const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('node:fs');
test.use({ actionTimeout: 7000 });
async function setup(page) {
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-theme', 'dark');
  });
}
test('refresh never paints Main before the requested screen, even with slow scripts', async ({
  page,
}) => {
  await setup(page);
  await page.route('**/donors.js', async (route) => {
    await new Promise((r) => setTimeout(r, 600));
    await route.continue();
  });
  await page.addInitScript(() => {
    window.wrongScreenFrames = 0;
    function inspect() {
      const main = document.querySelector('.app'),
        donors = document.getElementById('donorsPage');
      if (
        main &&
        !donors?.open &&
        getComputedStyle(main).visibility === 'visible' &&
        getComputedStyle(main).display !== 'none'
      )
        window.wrongScreenFrames++;
      if (!donors?.open) requestAnimationFrame(inspect);
    }
    requestAnimationFrame(inspect);
  });
  await page.goto('/new#/donors/messages');
  await expect(page.locator('#donorsPage')).toBeVisible();
  expect(await page.evaluate(() => wrongScreenFrames)).toBe(0);
});
test('Memory restores without redoing actions', async ({ page }) => {
  await setup(page);
  await page.goto('/new#/settings/memory');
  await expect(page.locator('#memoryDialog')).toBeVisible();
  await page.reload();
  await expect(page.locator('#memoryDialog')).toBeVisible();
  await page.locator('#memoryClose').click();
  await expect(page).toHaveURL(/#\/settings$/);
});
test('secondary forms restore and close without sending', async ({ page }) => {
  await setup(page);
  for (const [route, id, close] of [
    ['donors/all/add', 'donorAddDialog', 'donorAddCancel'],
    ['donors/all/bulk', 'donorPasteDialog', 'pasteCancel'],
    ['donors/all/pace', 'donorBatchPicker', 'batchCancel'],
    ['settings/poster', 'posterDialog', 'posterClose'],
  ]) {
    await page.goto('/new#/' + route);
    await expect(page.locator('#' + id)).toBeVisible();
    await page.reload();
    await expect(page.locator('#' + id)).toBeVisible();
    await page.locator('#' + close).click();
    await expect(page.locator('#' + id)).not.toBeVisible();
  }
});
test('closing Memory while its response is delayed never reopens it', async ({ page }) => {
  await setup(page);
  let release;
  const ready = new Promise((r) => (release = r));
  await page.route('**/knowledge', async (route) => {
    await ready;
    await route.fulfill({ json: { entries: [], feedback_count: 0, archived_turns: 0 } });
  });
  await page.goto('/new#/settings/memory');
  await expect(page.locator('#memoryDialog')).toBeVisible();
  await page.locator('#memoryClose').click();
  release();
  await page.waitForTimeout(100);
  await expect(page.locator('#memoryDialog')).not.toBeVisible();
  await expect(page).toHaveURL(/#\/settings$/);
});
