const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 237;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}`, reducedMotion: 'reduce' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
for (const active of [false, true]) {
  for (const [width, height] of [
    [1440, 900],
    [1920, 700],
    [390, 844],
    [320, 568],
    [844, 390],
  ]) {
    test(`Report summary fits without scrolling at ${width}x${height} (${active ? 'ON' : 'OFF'})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
      if (active)
        await page.route('**/auto-controls', async (route) => {
          const response = await route.fetch();
          const data = await response.json();
          for (const control of Object.values(data.controls)) {
            control.on = true;
            control.state = 'ON';
            control.note = 'Scheduled for the next send.';
          }
          await route.fulfill({ response, json: data });
        });
      await page.goto('/new');
      await page.evaluate(() => document.querySelector('.report-open').click());
      const report = page.getByRole('dialog', { name: 'Report', exact: true });
      await expect(report).toBeVisible();
      await expect(report.locator('.auto-card')).toHaveCount(4);
      const overflow = await report.locator('.report-card').evaluate((e) => {
        const r = e.getBoundingClientRect();
        return {
          scroll: e.scrollHeight > e.clientHeight + 1,
          top: r.top,
          bottom: r.bottom,
          width: document.documentElement.scrollWidth,
        };
      });
      expect(overflow.scroll).toBe(false);
      expect(overflow.top).toBeGreaterThanOrEqual(0);
      expect(overflow.bottom).toBeLessThanOrEqual(height);
      expect(overflow.width).toBeLessThanOrEqual(width);
      for (const sw of await report.getByRole('switch').all())
        await expect(sw).toBeInViewport({ ratio: 1 });
      await expect(report.getByRole('button', { name: 'Close report' })).toBeInViewport({
        ratio: 1,
      });
      if (active)
        await expect(
          report.getByRole('button', { name: 'Stop all Auto', exact: true }),
        ).toBeInViewport({ ratio: 1 });
      await report.locator('.auto-head h4').first().click();
      await expect(report.locator('.auto-form:not([hidden])')).toBeVisible();
      await report.getByRole('button', { name: 'Cancel', exact: true }).click();
      await expect(report.locator('.auto-card:visible')).toHaveCount(4);
    });
  }
}
