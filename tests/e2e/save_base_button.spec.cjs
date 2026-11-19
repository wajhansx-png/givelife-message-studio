/* Save base: the reader's thin row has a Save base button; with a version showing, it makes THAT version the base
   message and clears the old versions (new ones are written from it). Fake WhatsApp / no real AI send. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 641;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

const BASE = '*Base wording* of the case. Please help today. Rs. 5,000 needed.';
const V1 = '*Second wording* of the case. Please help today. Rs. 5,000 needed.';
const V2 = '*Third wording* of the case. Please help today. Rs. 5,000 needed.';

for (const width of [320, 390, 1280])
  test(`a version shown in the reader becomes the base with Save base at ${width}px`, async ({ page }) => {
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
    await api(port, '/focus-bank', { kind: 'group', action: 'manual', messages: [V1, V2] });
    await page.setViewportSize({ width, height: width < 900 ? 800 : 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/preview');
    const btn = page.locator('#ui2Swipe .ui2-base-btn');
    await expect(btn).toBeVisible();
    await expect(btn).toHaveText('Save base');
    const box = await btn.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(40);
    const row = await page.locator('#ui2Swipe').boundingBox();
    expect(box.x + box.width).toBeLessThanOrEqual(row.x + row.width + 1);
    for (const sel of ['.ui2-swipe-prev', '.ui2-swipe-next', '.ui2-files-btn']) {
      const b = await page.locator('#ui2Swipe ' + sel).boundingBox();
      expect(b.x + b.width, sel).toBeLessThanOrEqual(width + 1);
    }
    await expect(btn).not.toHaveAttribute('data-pending', '1'); // the original is showing
    await page.locator('#ui2Swipe .ui2-swipe-next').click();
    await expect(page.locator('#focusFormatted')).toContainText('Second wording');
    await expect(btn).toHaveAttribute('data-pending', '1');
    await btn.click();
    await expect(page.locator('#focusBaseDialog')).toBeVisible();
    await expect(page.locator('#focusBaseNote')).toContainText('becomes your base message');
    await page.locator('#focusBaseSave').click();
    await expect.poll(async () => (await api(port, '/focus-bank?kind=group')).source).toBe(V1);
    const d = await api(port, '/focus-bank?kind=group');
    expect(d.items).not.toContain(BASE); // nothing written from the old base is left over
    await expect(page.locator('#focusFormatted')).toContainText('Second wording');
  });

for (const width of [320, 390, 1280])
  test(`the reader's thin row has a Write 5 new versions icon that fits at ${width}px`, async ({ page }) => {
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
    await page.setViewportSize({ width, height: width < 900 ? 800 : 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/preview');
    const g = page.locator('#ui2Swipe .ui2-gen-btn');
    await expect(g).toBeVisible();
    await expect(g).toHaveAccessibleName('Write 5 new versions');
    const row = await page.locator('#ui2Swipe').boundingBox();
    const boxes = [];
    for (const sel of ['.ui2-swipe-prev', '.ui2-ver', '.ui2-swipe-next', '.ui2-gen-btn', '.ui2-base-btn', '.ui2-files-btn']) {
      const b = await page.locator('#ui2Swipe ' + sel).boundingBox();
      expect(b.x, sel).toBeGreaterThanOrEqual(row.x - 1);
      expect(b.x + b.width, sel).toBeLessThanOrEqual(row.x + row.width + 1);
      boxes.push([sel, b]);
    }
    for (let i = 0; i < boxes.length - 1; i++) // nothing overlaps its neighbour
      expect(boxes[i][1].x + boxes[i][1].width, boxes[i][0]).toBeLessThanOrEqual(boxes[i + 1][1].x + 1);
    expect((await g.boundingBox()).height).toBeGreaterThanOrEqual(40);
    // pressing it starts writing: the real Generate button is pressed (it is busy while versions are written)
    await g.click();
    await expect.poll(async () => (await api(port, '/focus-bank?kind=group')).state).not.toBe('Not generated');
  });
