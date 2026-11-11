const { test, expect } = require('@playwright/test');
for (const width of [1440, 390])
  test(`DM counts stay visible including resumed errors ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    let job = {
      id: 'fake-resumed',
      state: 'Stopped',
      sent: 0,
      previous_sent: 7,
      total: 3,
      original_total: 10,
      pending: 3,
      failed: 0,
      skipped: 0,
      receipts: [],
      paused: true,
      error: 'Sending is on hold.',
      scope: 'important',
      updated_at: 1,
    };
    await page.route('**/donor-delivery', async (route) => {
      if (route.request().method() === 'GET') await route.fulfill({ json: job });
      else await route.continue();
    });
    await page.goto('/#/donors/all');
    const progress = page.locator('#donorProgress');
    await expect(progress).toBeVisible();
    await expect(progress).toContainText('7 of 10 sent');
    await expect(progress).toContainText('3 left');
    job = {
      ...job,
      state: 'Completed',
      sent: 3,
      pending: 0,
      paused: false,
      error: '',
      updated_at: 2,
    };
    await page.reload();
    await expect(progress).toBeVisible();
    await expect(progress).toContainText('10 of 10 sent');
    await expect(progress).toContainText('0 left');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/dm-progress-${width}.png` });
  });
