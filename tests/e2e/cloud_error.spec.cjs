const { test, expect } = require('@playwright/test');
test('cloud HTML errors are readable and sends are not retried', async ({ page }) => {
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
  await page.goto('/');
  await expect(page.locator('#leftChip')).toContainText('25,000');
  await page.locator('.test-row').click();
  await expect(page.locator('#live')).toContainText('cloud is restarting');
  await expect(page.locator('#live')).not.toContainText('Unexpected token');
  expect(calls).toBe(1);
});
