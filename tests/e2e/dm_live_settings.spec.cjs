const { test, expect } = require('@playwright/test');
test('editing live DM settings never pauses or creates another batch', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  const posts = [];
  const job = {
    id: 'same-running-job',
    state: 'Waiting',
    scope: 'important',
    sent: 2,
    total: 10,
    pending: 8,
    paused: false,
    chunk: 5,
    rests: [600],
    gap_seconds: 240,
    poster: true,
    receipts: [],
  };
  await page.route('**/donor-delivery', async (route) => {
    if (route.request().method() === 'POST') {
      posts.push(route.request().postDataJSON());
      await route.fulfill({
        json: { reply: 'Settings saved. The existing batch continues.', job },
      });
    } else await route.fulfill({ json: job });
  });
  await page.goto('/old#/donors/all');
  await expect(page.locator('#donorEditBatch')).toBeVisible();
  await page.locator('#donorEditBatch').click();
  await expect(page.locator('#donorBatchPicker')).toBeVisible();
  expect(posts).toEqual([]);
  await expect(page.locator('#batchStart')).toHaveText('Save changes');
  await page.locator('#batchGap').fill('3');
  await page.locator('#batchStart').click();
  await expect(page.locator('#donorBatchPicker')).toBeHidden();
  expect(posts).toHaveLength(1);
  expect(posts[0].configure).toBe('same-running-job');
  expect(posts[0].settings.gap_seconds).toBe(180);
  expect(posts[0].stop).toBeUndefined();
});
