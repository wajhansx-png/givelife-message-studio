const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');

/* The Donors dock has ONE DM button. In every tab Important stays Important and Top stays Top:
   the Top tab shows "DM Top donors" and picks the Top list; every other tab shows "DM ★ Important" and
   picks the Important list. The start request is stubbed, so nothing is ever sent (fake WhatsApp only). */
const PORT = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 203;
let server;
test.use({ baseURL: `http://127.0.0.1:${PORT}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => {
  server = await startOwnServer(PORT);
  // Fake donors: 3 Important, and 2 of them are Top too (a Top donor is always Important).
  const important = (await api(PORT, '/donors?tab=important')).items.slice(0, 3);
  expect(important).toHaveLength(3);
  for (const d of important.slice(0, 2))
    await api(PORT, '/donors', { action: 'update', id: d.id, top_donor: true });
});
test.afterAll(() => server && server.kill());

const TABS = [
  ['all', 'DM ★ Important', 'important', '3'],
  ['important', 'DM ★ Important', 'important', '3'],
  ['top', 'DM Top donors', 'top', '2'],
  ['donated', 'DM ★ Important', 'important', '3'],
  ['not_contacted', 'DM ★ Important', 'important', '3'],
];

for (const [width, height] of [
  [360, 740],
  [1440, 900],
]) {
  test(`each tab sends to its own list at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    page.on('dialog', (d) => d.accept());
    const posts = [];
    await page.route('**/donor-delivery', async (r) => {
      if (r.request().method() !== 'POST') return r.continue();
      posts.push(r.request().postDataJSON());
      return r.fulfill({ json: { reply: 'Stubbed: nothing was sent.' } });
    });
    await page.goto('/#/donors/all');
    await expect(page.locator('.donor-row').first()).toBeVisible();
    for (const [tab, label, scope, free] of TABS) {
      await page.locator(`.donor-tabs [data-tab="${tab}"]`).click();
      const dm = page.locator('#donorSendImportant');
      if (tab === 'donated') {
        // People who already gave are thanked, not asked again: Thank donors replaces the DM button here.
        await expect(dm, tab).toBeHidden();
        await expect(page.locator('#donorsPage .donor-thanks'), tab).toBeVisible();
        continue;
      }
      await expect(dm, tab).toHaveText(label);
      await dm.click();
      await expect(page.locator('#batchAudience'), tab).toContainText(`${free} not contacted yet`);
      const before = posts.length;
      await page.locator('#batchStart').click();
      await expect.poll(() => posts.length, { message: tab }).toBe(before + 1);
      expect(posts[before].scope, tab).toBe(scope);
      await expect(page.locator('#batchStart')).toBeHidden();
    }
  });
}
