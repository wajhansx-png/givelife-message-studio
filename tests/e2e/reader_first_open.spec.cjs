/* The message page on a slow phone: while the message is still coming, the page shows a calm card (never a thin
   green strip, never icons floating in the middle, never a blank screen), and the text then fades in with the
   tools under it. Fake WhatsApp / no real AI. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 757;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

const BASE = '*Base wording* of the case. Please help today. Rs. 5,000 needed.\n\n03097458815\nEASYPAISA ONLY (Wajdan Khan)';

for (const [width, height] of [
  [320, 640],
  [390, 844],
  [820, 1180],
  [1280, 720],
])
  test(`first open at ${width}px: a calm card while the message loads, then the text, no thin strip`, async ({ page }) => {
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
    await page.setViewportSize({ width, height });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    let release;
    const gate = new Promise((r) => (release = r));
    await page.route('**/focus-bank?kind=*', async (route) => {
      await gate; // a slow network: the message arrives late
      await route.continue();
    });
    await page.goto('/new#/preview');
    const msg = page.locator('#focusFormatted');
    await expect(page.locator('#messageFocus')).toBeVisible();
    await page.waitForTimeout(400);
    const loading = await page.evaluate(() => {
      const f = document.getElementById('focusFormatted');
      const paper = document.querySelector('#messageFocus .focus-paper');
      const tools = document.getElementById('ui2MsgTools');
      const card = getComputedStyle(paper, '::before');
      return {
        empty: f.textContent.trim() === '',
        formattedH: f.getBoundingClientRect().height,
        formattedHidden: getComputedStyle(f).visibility === 'hidden' || f.getBoundingClientRect().height === 0,
        toolsHidden: !tools || getComputedStyle(tools).visibility === 'hidden',
        cardH: parseFloat(card.height) || 0,
        cardContent: card.content,
        scroll: document.documentElement.scrollWidth <= innerWidth + 1,
      };
    });
    expect(loading.empty).toBe(true);
    expect(loading.formattedHidden).toBe(true); // no strip
    expect(loading.toolsHidden).toBe(true); // no icons floating in the middle
    expect(loading.cardContent).not.toBe('none'); // the calm card is there instead of a blank screen
    expect(loading.cardH).toBeGreaterThan(100);
    expect(loading.scroll).toBe(true);
    release();
    await expect(msg).toContainText('Base wording');
    const done = await page.evaluate(() => {
      const f = document.getElementById('focusFormatted').getBoundingClientRect();
      const t = document.getElementById('ui2MsgTools');
      return { w: f.width, h: f.height, tools: getComputedStyle(t).visibility, toolsY: t.getBoundingClientRect().y, fy: f.y };
    });
    expect(done.w).toBeGreaterThan(Math.min(width - 40, 250)); // a real message card, not a strip
    expect(done.h).toBeGreaterThan(60);
    expect(done.tools).toBe('visible');
    expect(done.toolsY).toBeGreaterThanOrEqual(done.fy); // the icons sit on the message
    const card = await page.evaluate(() => getComputedStyle(document.querySelector('#messageFocus .focus-paper'), '::before').content);
    expect(card).toBe('none'); // the card is gone once the text is there
  });

for (const width of [390, 1440])
  test(`opened straight on the message page (${width}px): Back shows the new main screen, not the old layout`, async ({ page }) => {
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/preview');
    await expect(page.locator('#focusBack')).toBeVisible();
    await page.locator('#focusBack').click();
    await expect(page.locator('#messageFocus')).toBeHidden();
    await expect(page.locator('.app')).toHaveClass(/ui2-message-home/);
    await expect(page.locator('#btnGivelife')).toBeVisible();
  });
