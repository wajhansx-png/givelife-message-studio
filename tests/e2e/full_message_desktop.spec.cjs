const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 257;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
const text = `*Your Rs. 1,000 can help a father clear the money he borrowed for his little son's Janazah. 💔*

He has already lost his two-year-old son. People are coming to his home asking for the money, and the family cannot manage this burden alone. Your support can give this father room to breathe after a heartbreaking loss.

یہ خاندان پہلے ہی ایک بہت بڑا صدمہ برداشت کر چکا ہے۔ آپ کی تھوڑی سی مدد ان کی پریشانی کم کر سکتی ہے۔ براہ کرم اس مشکل وقت میں ان کا ساتھ دیں۔

Allah says: “Whatever you spend in charity, He will compensate you for it.” (Surah Saba 34:39)

🔴 Rs. 25,000 STILL NEEDED.

Just 25 people giving Rs. 1,000 can complete the remaining amount. Please give what you can and share this appeal with someone who may be able to help. Even a small donation can make a real difference for this family. 🤲

03097458815
EASYPAISA ONLY (Wajdan Khan)

Reply Done after donating.\n— GiveLife Foundation`;
for (const [width, height] of [
  [1920, 900],
  [1440, 900],
  [1280, 720],
  [1280, 600],
  [1024, 600],
  [960, 700],
]) {
  test(`full desktop DM fits at ${width}x${height} without changing message font`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.route('**/donor-messages', async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      data.items[0].text = text;
      await route.fulfill({ response, json: data });
    });
    await page.goto('/new#/donors/messages');
    const preview = page.locator('.bank-preview');
    await expect(preview).toContainText('GiveLife Foundation');
    await expect(page.locator('.ui2-desktop-copy')).toBeVisible();
    const result = await preview.evaluate((e) => {
      const r = e.getBoundingClientRect(),
        last = e.querySelector('.bank-line:last-of-type').getBoundingClientRect();
      return {
        overflow: e.scrollHeight > e.clientHeight + 1,
        top: r.y,
        bottom: r.bottom,
        last: last.bottom,
        font: getComputedStyle(e.querySelector('.bank-line')).fontSize,
      };
    });
    expect(result.overflow).toBe(false);
    expect(result.font).toBe('12px');
    expect(result.top).toBeGreaterThan(0);
    expect(result.bottom).toBeLessThan(height);
    expect(result.last).toBeLessThanOrEqual(result.bottom);
    const column = await page.locator('.bank-workspace').boundingBox();
    expect(column.width).toBeLessThanOrEqual(640);
    expect(Math.abs(column.x + column.width / 2 - width / 2)).toBeLessThan(2);
    const dock = await page.locator('.bank-actions').boundingBox();
    expect(dock.y + dock.height).toBeLessThanOrEqual(height);
    for (const tab of await page.locator('.bank-subtabs button').all()) {
      const b = await tab.boundingBox();
      expect(b.height).toBeLessThanOrEqual(36);
      expect(b.width).toBeLessThan(200);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
}
