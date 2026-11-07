const { test, expect } = require('@playwright/test');
const job = {
  id: 'fake',
  state: 'Sending',
  sent: 2,
  previous_sent: 0,
  total: 5,
  original_total: 5,
  pending: 3,
  failed: 0,
  skipped: 0,
  receipts: [],
  scope: 'important',
  updated_at: 1,
  chunk: 20,
  gap_seconds: 25,
  batches: 1,
  batch: 1,
};
for (const [width, height] of [
  [320, 568],
  [375, 667],
  [430, 932],
  [1280, 800],
])
  test(`row menu, progress box and More menu at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    await page.route('**/donor-delivery', (r) =>
      r.request().method() === 'GET' ? r.fulfill({ json: job }) : r.continue(),
    );
    await page.goto('/#/donors/all');
    await expect(page.locator('.donor-row').first()).toBeVisible();
    // Progress box: plain line, plan line, Hide last, outside click folds it to a small chip.
    const box = page.locator('#donorProgress');
    await expect(box).toBeVisible();
    await expect(box.locator('span').first()).toHaveText(/Sending: 2 of 5 sent · 3 left/);
    await expect(page.locator('#donorProgressFacts')).toContainText('gap 25 sec');
    expect(await box.evaluate((e) => e.lastElementChild.id)).toBe('donorProgressHide');
    await page.mouse.click(4, 4);
    await expect(box).toBeHidden();
    await expect(page.locator('#donorProgressShow')).toHaveText(/2\/5/);
    await page.locator('#donorProgressShow').click();
    await expect(box).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(box).toBeHidden();
    // Row menu: opens inside the screen, Escape and outside click close it, one at a time.
    const rows = page.locator('.donor-row');
    await rows.nth(0).locator('.donor-more > summary').click();
    const open = page.locator('.donor-more[open]');
    await expect(open).toHaveCount(1);
    await expect
      .poll(() =>
        open.locator('> div').evaluate((m) => m.getBoundingClientRect().bottom <= innerHeight + 1),
      )
      .toBe(true);
    await page.keyboard.press('Escape');
    await expect(open).toHaveCount(0);
    await rows.nth(0).locator('.donor-more > summary').click();
    await page.mouse.click(4, 4);
    await expect(open).toHaveCount(0);
    // More menu (phone): only Bulk message; Test DM lives in the Send DMs setup.
    if (width <= 560) {
      await page.locator('#donorNavMore > summary').click();
      const panel = page.locator('#donorNavMore .compact-nav-panel');
      await expect(panel.locator('#donorBulk')).toBeVisible();
      await expect(panel.locator('#donorTest')).toHaveCount(0);
      await expect(panel.locator('.donor-poster-toggle')).toHaveCount(0);
      await page.keyboard.press('Escape');
      await page.locator('#donorSendImportant').click();
      await expect(page.locator('#donorBatchPicker #donorTest')).toHaveCount(1);
    }
  });
