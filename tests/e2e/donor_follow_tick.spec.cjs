/* The Donors tab's "Send with follow-up" tick is also kept by the server, so DM Top / DM Important Auto obey it.
   Fake WhatsApp only: nothing is sent. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 611;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => {
  server = await startOwnServer(port);
  await api(port, '/donor-messages', { action: 'follow_up', text: 'Synthetic follow-up' });
});
test.afterAll(() => server?.kill());

test('ticking and unticking Send with follow-up is saved on the server', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((key) => {
    localStorage.setItem('givelife-cloud-key', key);
    localStorage.setItem('givelife-follow-up', '0');
  }, KEY);
  await page.goto('/new#/donors/top');
  const box = page.locator('#donorFollowUp');
  await expect(box).toBeVisible();
  await expect(box).not.toBeChecked();
  await box.check();
  await expect.poll(async () => (await api(port, '/donor-messages')).follow_tick).toBe(true);
  await box.uncheck();
  await expect.poll(async () => (await api(port, '/donor-messages')).follow_tick).toBe(false);
});
