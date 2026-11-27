const { test, expect } = require('@playwright/test');
test('a cloud HTML error after a send is readable, marked not confirmed, and never retried', async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.route('**/wa-status', (r) =>
    r.fulfill({ json: { results: { is_connected: true, is_logged_in: true } } }),
  );
  let calls = 0;
  await page.route('**/test', (r) => {
    calls++;
    return r.fulfill({
      status: 503,
      contentType: 'text/html',
      body: '<!DOCTYPE html><title>Service unavailable</title>',
    });
  });
  await page.goto('/old');
  await expect(page.locator('#leftChip')).toContainText('25,000');
  await page.locator('.test-row').click();
  // the request may have gone: the owner is told to check WhatsApp, not that nothing happened
  await expect(page.locator('#live')).toContainText('not confirmed. Check WhatsApp');
  await expect(page.locator('#live')).not.toContainText('Unexpected token');
  expect(calls).toBe(1);
});
