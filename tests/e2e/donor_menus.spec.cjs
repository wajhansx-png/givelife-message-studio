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
test('a failed usual donation save keeps the edit open and reports the failure', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.route('**/donors', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 409, json: { error: 'Donor changed. Refresh before saving.' } })
      : route.continue(),
  );
  await page.goto('/new#/donors/all');
  const menu = page.locator('.donor-more').first();
  await menu.locator('summary').click();
  const input = menu.getByRole('spinbutton', { name: 'Usually donates (Rs.)' });
  await input.fill('2300');
  await input.press('Enter');
  await expect(page.locator('#donorNotice')).toHaveText(/Donor changed/);
  await expect(menu).toHaveAttribute('open', '');
  await expect(input).toHaveValue('2300');
});
