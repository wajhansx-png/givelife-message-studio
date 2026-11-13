const { test, expect } = require('@playwright/test');
test('one dismissible outcome stays dismissed across refresh; next job appears', async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  let job = {
    id: 'old-failure',
    state: 'Nothing sent',
    sent: 0,
    total: 1,
    skipped: 1,
    failed: 0,
    error: 'All selected recipients were excluded.',
    receipts: [
      { id: 'synthetic', name: 'Ali', state: 'Skipped: This recipient opted out of messages.' },
    ],
  };
  await page.route('**/donor-delivery', (route) => route.fulfill({ json: job }));
  await page.goto('/old#/donors/all');
  await expect(page.locator('#donorNotice')).toContainText('Ali: This recipient opted out');
  await expect(page.locator('#donorProgress')).toBeVisible();
  await expect(page.locator('#donorProgress')).toContainText('0 of 1 sent');
  await expect(page.locator('#donorBatchList')).toBeHidden();
  await page.getByRole('button', { name: 'Dismiss notification', exact: true }).click();
  await expect(page.locator('#donorNotice')).toBeHidden();
  await expect(page.locator('#donorProgress')).toBeHidden();
  await page.reload();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page.locator('#donorNotice')).toBeHidden();
  await expect(page.locator('#donorProgress')).toBeHidden();
  job = { ...job, id: 'new-failure' };
  await page.reload();
  await expect(page.locator('#donorNotice')).toContainText('Ali: This recipient opted out');
  await expect(page.locator('#donorProgress')).toBeVisible();
  await expect(page.locator('#donorBatchList')).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/notification-mobile.png' });
});

test('a finished batch shows no "Batch complete" pop-up; the progress bar already shows it', async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    /* Record every text the notice ever holds (it hides itself after 4 s). */
    window.__noticeTexts = [];
    new MutationObserver(() => {
      const n = document.getElementById('donorNotice');
      if (n && n.textContent.trim()) window.__noticeTexts.push(n.textContent.trim());
    }).observe(document, { childList: true, subtree: true, characterData: true });
  });
  const job = { id: 'done-ok', state: 'Complete', sent: 5, total: 5, skipped: 0, failed: 0 };
  await page.route('**/donor-delivery', (route) => route.fulfill({ json: job }));
  await page.goto('/old#/donors/all');
  await expect(page.locator('#donorProgress')).toContainText('5 of 5 sent');
  await page.waitForTimeout(1000);
  expect(await page.evaluate(() => window.__noticeTexts)).toEqual([]);
});
