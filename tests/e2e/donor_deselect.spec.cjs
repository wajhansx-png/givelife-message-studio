/* Deselect all on the Important, Top donors and Donated tabs: the same chip, one confirm, then the tab is empty.
   Fake WhatsApp only: nothing is sent. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 623;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

async function seed() {
  for (const [name, phone] of [['Deselect One', '03001119001'], ['Deselect Two', '03001119002']]) {
    const r = await api(port, '/donors', { action: 'add', name, phone });
    const id = r.donor.id;
    await api(port, '/donors', { action: 'update', id, important: true });
    await api(port, '/donors', { action: 'update', id, top_donor: true });
    await api(port, '/donors', { action: 'update', id, donated: true, amount: 1000 });
  }
}

for (const width of [390, 1280])
  test(`Top donors and Donated have Deselect all at ${width}px`, async ({ page }) => {
    await seed();
    await page.setViewportSize({ width, height: width < 900 ? 800 : 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    page.on('dialog', (d) => d.accept());
    for (const [tab, flag] of [['top', 'top_donor'], ['donated', 'donated']]) {
      await page.goto('/new#/donors/' + tab);
      await expect(page.locator('.donor-row').first()).toBeVisible();
      if (width < 900) await page.locator('#donorNavMore > summary').click();
      const chip = page.locator('#donorDeselectAll');
      await expect(chip).toBeVisible();
      await expect(chip).toHaveText(/^Deselect all \d+$/);
      await expect(page.locator('#donorHideSent')).toBeHidden(); // the Important-only chip stays out
      const box = await chip.boundingBox();
      expect(box.height).toBeGreaterThanOrEqual(width < 900 ? 44 : 28);
      expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
      await chip.click();
      await expect
        .poll(async () => (await api(port, '/donors')).items.filter((d) => d[flag]).length)
        .toBe(0);
    }
    const left = (await api(port, '/donors')).items.filter((d) => d.important).length;
    expect(left).toBeGreaterThan(0); // Top donors off keeps the star
  });
test('Donated tab: unmarking one donor takes that row out of the tab at once', async ({ page }) => {
  await seed();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  const rows = page.locator('.donor-row');
  await expect(rows.first()).toBeVisible();
  const before = await rows.count();
  await rows.first().locator('.donor-status').click();
  await expect(rows).toHaveCount(before - 1);
});
