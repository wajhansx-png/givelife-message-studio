const { test, expect } = require('@playwright/test');
const screens = [
  ['donors/all', '#donorMainBottom'],
  ['donors/messages', '.bank-back-bottom'],
  ['donors/volunteers', '.vol-back'],
  ['preview', '#focusBack'],
  ['notes', '#notesBack'],
  [
    'notes',
    '#notesBack',
    async (page) => {
      await page.locator('#notesPassword').fill('test-preview-only-pin');
      await page.locator('#notesUnlockButton').click();
      await expect(page.locator('#notesEditor')).toBeVisible();
    },
  ],
  [
    'donors/all/bulk',
    '#pasteBack',
    async (page) => {
      await page.locator('#pastePeople').fill('0300 1234567, Ali');
      await expect(page.locator('#pasteNext')).toBeEnabled();
      await page.locator('#pasteNext').click();
    },
  ],
  ['settings', '#setCloseBottom'],
  ['chat', '#histMain'],
  ['/group-finder', 'a.back'],
];
for (const [width, height] of [
  [393, 700],
  [320, 568],
]) {
  test(`mobile Back controls stay in right-thumb reach ${width}x${height}`, async ({ browser }) => {
    test.setTimeout(60000);
    const context = await browser.newContext({
      viewport: { width, height },
      isMobile: true,
      hasTouch: true,
      reducedMotion: 'reduce',
    });
    await context.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    const page = await context.newPage();
    try {
      for (const [route, selector, prepare] of screens) {
        await page.goto('about:blank');
        await page.goto(route.startsWith('/') ? route : '/old#/' + route);
        if (prepare) await prepare(page);
        const back = page.locator(selector).first();
        await expect(back, route).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        const box = await back.boundingBox();
        expect(box.x + box.width / 2, route + ' right thumb').toBeGreaterThanOrEqual(width * 0.75);
        expect(box.y + box.height / 2, route + ' lower thumb zone').toBeGreaterThanOrEqual(
          height * 0.7,
        );
        expect(box.y + box.height, route + ' visible without scrolling').toBeLessThanOrEqual(
          height + 1,
        );
        expect(box.width, route + ' tap target').toBeGreaterThanOrEqual(43.99);
        expect(box.height, route + ' tap target').toBeGreaterThanOrEqual(43.99);
        const reachable = await back.evaluate((el) => {
          const b = el.getBoundingClientRect();
          const hit = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
          return hit === el || el.contains(hit);
        });
        expect(reachable, route + ' not covered').toBe(true);
        await page.screenshot({
          path: `test-results/back-thumb-${width}-${route.replaceAll('/', '-')}.png`,
        });
      }
    } finally {
      await context.close();
    }
  });
}
