const { test, expect } = require('@playwright/test');
const { openSettings, showPreview } = require('./helpers.cjs');
test.use({ actionTimeout: 8000 });
const path = require('node:path');
const auth = { Authorization: 'Bearer manual-fix-preview-key' };
const reply =
  'Here is the current update.\n\n*What is ready*\nThe saved caption and poster are ready to review. No messages were sent during this check.\n\n*Next steps*\n' +
  Array.from(
    { length: 7 },
    (_, i) =>
      `${i + 1}. *Review step ${i + 1}.* Keep the existing task, message and recipient unchanged. Open the relevant screen when you need it.`,
  ).join('\n\n');
async function open(page, request, width = 1440, height = 900, stableChat = true) {
  if (stableChat)
    await page.route('**/chat', (r) =>
      r.fulfill({
        json: { items: [{ who: 'app', text: reply, t: Date.now(), turn_id: 'smooth-review' }] },
      }),
    );
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-theme', 'dark');
  });
  await request.post('/__test/seed', { headers: auth, data: { reply } });
  await page.goto('/new');
  await expect(page.locator('#leftChip')).toContainText('25,000');
  await page.evaluate(() => document.fonts.ready);
}
test('refresh waits for unlock before restoring the requested tab', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto('/new#/donors/messages');
  await expect(page.locator('#cloudLogin')).toBeVisible();
  await page.locator('#cloudKey').fill('manual-fix-preview-key');
  await page.locator('#cloudUnlock').click();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page.locator('[data-tab=messages]')).toHaveAttribute('aria-selected', 'true');
  await page.reload();
  await expect(page.locator('[data-tab=messages]')).toHaveAttribute('aria-selected', 'true');
});
test('WhatsApp connection screen survives refresh and Back without reconnecting or sending', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 700);
  await page.locator('#whatsappConnection').click();
  await expect(page).toHaveURL(/#\/whatsapp$/);
  await page.reload();
  await expect(
    page.getByRole('dialog', { name: 'WhatsApp connection', exact: true }),
  ).toBeVisible();
  await page.locator('#waCloudClose').click();
  await expect(
    page.getByRole('dialog', { name: 'WhatsApp connection', exact: true }),
  ).not.toBeVisible();
});
