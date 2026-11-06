const { test, expect } = require('@playwright/test');
for (const width of [1440, 390])
  test(
    'Donor resume offers now or PKT clock and persists the choice ' + width,
    async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript(() =>
        localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
      );
      await page.goto('/#/donors/all');
      // Start from a known state: an earlier test may have left DMs paused.
      await expect(page.locator('#donorToggle')).toBeVisible();
      if ((await page.locator('#donorToggle').innerText()).includes('Stop DMs'))
        await page.locator('#donorToggle').click();
      await expect(page.locator('#donorToggle')).toHaveText('Resume DMs');
      await page.locator('#donorToggle').click();
      const dialog = page.getByRole('dialog', { name: 'Resume donor DMs' });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole('button', { name: 'Resume now', exact: true })).toBeVisible();
      await dialog.getByRole('button', { name: 'Resume at a time', exact: true }).click();
      await expect(dialog.getByLabel('Date (Pakistan)', { exact: true })).toHaveAttribute(
        'type',
        'date',
      );
      await expect(dialog.getByLabel('Time (PKT)', { exact: true })).toHaveAttribute(
        'type',
        'time',
      );
      const tomorrow = new Date(Date.now() + 86400000 + 5 * 3600000).toISOString().slice(0, 10);
      await dialog.getByLabel('Date (Pakistan)', { exact: true }).fill(tomorrow);
      await dialog.getByLabel('Time (PKT)', { exact: true }).fill('18:30');
      await dialog.getByRole('button', { name: 'Schedule resume', exact: true }).click();
      await expect(dialog).not.toBeVisible();
      await expect(page.locator('#donorResumeStatus')).toContainText('06:30 PM PKT');
      await page.reload();
      await expect(page.locator('#donorResumeStatus')).toContainText('06:30 PM PKT');
      await expect(page.locator('#donorToggle')).toHaveText('Change resume');
      await page.getByRole('button', { name: 'Stop scheduled resume', exact: true }).click();
      await expect(page.locator('#donorResumeStatus')).toContainText('DMs paused');
      await expect(page.locator('#donorResumeStatus')).not.toContainText('PKT');
      await expect(
        page.getByRole('button', { name: 'Stop scheduled resume', exact: true }),
      ).not.toBeVisible();
      await page.locator('#donorToggle').click();
      await dialog.getByRole('button', { name: 'Resume now', exact: true }).click();
      await expect(dialog).not.toBeVisible();
      await expect(page.locator('#donorToggle')).toHaveText('Stop DMs');
    },
  );
