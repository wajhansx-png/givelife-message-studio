const { test, expect } = require('@playwright/test');
for (const width of [1440, 390])
  test('Volunteer batch has start-delay presets ' + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    const headers = { Authorization: 'Bearer manual-fix-preview-key' };
    await page.request.post('/volunteers', {
      headers,
      data: { action: 'add', name: 'Timing preview volunteer', phone: '15551239999' },
    });
    await page.goto('/#/donors/volunteers');
    await page.locator('#volMessage').fill('Please share this case.');
    await page.getByRole('button', { name: 'DM all volunteers', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'DM all volunteers', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('option')).toHaveText([
      'Send now',
      'In 5 minutes',
      'In 10 minutes',
      'In 15 minutes',
      'In 30 minutes',
      'In 1 hour',
      'In 2 hours',
    ]);
    await dialog.getByLabel('Start sending', { exact: true }).selectOption('3600');
    await expect(dialog.getByRole('button', { name: 'Schedule DMs', exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: 'Schedule DMs', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.locator('#volProgress')).toContainText('Scheduled');
    await page.reload();
    await expect(page.locator('#volProgress')).toContainText('Scheduled');
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    await expect(page.locator('#volProgress')).toContainText('Last send');
  });
