const { test, expect } = require('@playwright/test');
test.use({ trace: 'off' });

const original =
  '*Ready to review*\n\nThe original has _emphasis_, `code`, an & sign, and <literal text>.\n\n' +
  Array.from(
    { length: 8 },
    (_, i) =>
      `${i + 1}. *Review step ${i + 1}.* Keep the exact saved message and recipient. This synthetic reply checks fitting without sending any message.`,
  ).join('\n\n') +
  '\n\nWould you like to review it?';
const userText = 'Please review the *entire* original message.\nKeep its line breaks.';
async function open(page, width = 1280, height = 720) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-theme', 'dark');
  });
  await page.route('**/chat', (route) =>
    route.fulfill({
      json: {
        items: [
          { who: 'you', text: userText, t: 1, turn_id: 'render-user' },
          { who: 'app', text: original, t: 2, turn_id: 'render-reply' },
        ],
      },
    }),
  );
  await page.goto('/new');
  await expect(page.locator('#leftChip')).toContainText('25,000');
  await expect(page.locator('#log .bot')).toContainText('Ready to review');
  await page.evaluate(() => document.fonts.ready);
}

test('refresh and thinking preserve the same boxed reply and its fitted layout', async ({
  page,
}) => {
  await open(page);
  const result = await page.evaluate(async () => {
    const reply = document.querySelector('#log .e.bot:not(.dots)'),
      samples = [];
    // Observe painted frames, including the extra ResizeObserver frames after fitting.
    const sample = () => {
      const el = document.querySelector('#log .e.bot:not(.dots)'),
        cs = getComputedStyle(el),
        r = el.getBoundingClientRect();
      samples.push({
        same: el === reply,
        cols: cs.columnCount,
        long: el.closest('.talk').classList.contains('long-reply'),
        box: cs.backgroundColor,
        border: cs.borderTopWidth,
        x: r.x,
        y: r.y,
        w: r.width,
        h: r.height,
      });
    };
    await syncChat();
    think(true);
    think(false);
    for (let i = 0; i < 20; i++) {
      await new Promise(requestAnimationFrame);
      sample();
    }
    return samples;
  });
  expect(
    result.every((x) => x.same),
    'An unchanged reply must keep its DOM node when chat refreshes or thinking changes',
  ).toBe(true);
  expect(result.every((x) => x.box !== 'rgba(0, 0, 0, 0)' && parseFloat(x.border) > 0)).toBe(true);
  expect(
    new Set(result.slice(2).map((x) => JSON.stringify([x.cols, x.long, x.x, x.y, x.w, x.h]))).size,
    'The fitted reply must settle without a ResizeObserver feedback loop',
  ).toBe(1);
});
