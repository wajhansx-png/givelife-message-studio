const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');

const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 291;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}`, reducedMotion: 'reduce' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server && server.kill());

for (const base of ['/', '/new']) {
  test(`responsive layer wins the existing donor cascade on ${base}`, async ({ page }) => {
    test.setTimeout(90000);
    await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
    await page.goto(base + '#/donors/all');
    const row = page.locator('.donor-row').first();
    await expect(row).toBeVisible();

    for (const width of [280, 299, 320, 359, 360, 380, 390, 540, 768, 899]) {
      await page.setViewportSize({ width, height: 820 });
      const geometry = await row.evaluate((el) => {
        const rect = (node) => {
          const r = node.getBoundingClientRect();
          return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
        };
        const controls = [...el.querySelectorAll('.donor-star,.donor-dm,.donor-status,.donor-more > summary')];
        return {
          pageFits: document.documentElement.scrollWidth <= innerWidth + 1,
          name: rect(el.querySelector('.donor-name')),
          controls: controls.map((node) => {
            const r = rect(node);
            const at = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
            return { ...r, reachable: at === node || node.contains(at) };
          }),
        };
      });
      expect(geometry.pageFits, `${base} ${width}px page overflow`).toBe(true);
      expect(geometry.name.width, `${base} ${width}px readable name area`).toBeGreaterThanOrEqual(70);
      for (const control of geometry.controls) {
        expect(control.width, `${base} ${width}px target width`).toBeGreaterThanOrEqual(44);
        expect(control.height, `${base} ${width}px target height`).toBeGreaterThanOrEqual(44);
        expect(control.x).toBeGreaterThanOrEqual(0);
        expect(control.right).toBeLessThanOrEqual(width);
        expect(control.reachable, `${base} ${width}px covered control`).toBe(true);
      }
      await expect(row.locator('.donor-top-chip')).toBeHidden();
      const tabs = page.getByRole('tablist', { name: 'Donor filters' });
      for (const tab of await tabs.getByRole('tab').all()) {
        await tab.scrollIntoViewIfNeeded();
        const fit = await tab.evaluate((el) => ({
          width: el.getBoundingClientRect().width,
          height: el.getBoundingClientRect().height,
          fits: el.scrollWidth <= el.clientWidth + 1,
          font: parseFloat(getComputedStyle(el).fontSize),
        }));
        expect(fit.fits, `${base} ${width}px tab label`).toBe(true);
        expect(fit.height).toBeGreaterThanOrEqual(44);
        expect(fit.width).toBeGreaterThanOrEqual(44);
        expect(fit.font).toBeGreaterThanOrEqual(12);
      }
    }

    await page.setViewportSize({ width: 390, height: 820 });
    await row.locator('.donor-more > summary').click();
    await expect(row.locator('.donor-menu-top')).toBeVisible();
    const wasTop = await row.locator('.donor-top-chip').getAttribute('aria-pressed');
    await row.locator('.donor-menu-top').click();
    await expect(row.locator('.donor-top-chip')).toHaveAttribute('aria-pressed', wasTop === 'true' ? 'false' : 'true');
    for (const width of [900, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(row.locator('.donor-top-chip')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    }
  });
}
