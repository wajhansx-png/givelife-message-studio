const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');

const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 371;
test.use({ baseURL: `http://127.0.0.1:${port}` });
let server;
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

for (const width of [1440, 390])
  test(
    'Donor resume offers now or PKT clock and persists the choice ' + width,
    async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await api(port, '/donor-delivery', { stop: true });
      await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
      await page.goto('/new#/donors/all');
      const resume = page.locator('#donorResumeStatus');
      await expect(resume).toContainText('DMs paused');
      await expect(resume.getByRole('button', { name: 'Resume now', exact: true })).toBeVisible();
      await resume.getByRole('button', { name: 'At a time…', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Resume donor DMs' });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole('button', { name: 'Resume now', exact: true })).toBeVisible();
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
      await expect(resume.getByRole('button', { name: 'Change time' })).toBeVisible();
      await page.getByRole('button', { name: 'Stop scheduled resume', exact: true }).click();
      await expect(page.locator('#donorResumeStatus')).toContainText('DMs paused');
      await expect(page.locator('#donorResumeStatus')).not.toContainText('PKT');
      await expect(
        page.getByRole('button', { name: 'Stop scheduled resume', exact: true }),
      ).not.toBeVisible();
      await resume.getByRole('button', { name: 'Resume now', exact: true }).click();
      await expect(resume).toBeHidden();
    },
  );
