const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 249;
let server;
test.use({ baseURL: 'http://127.0.0.1:' + port });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

const widths = [280, 299, 320, 359, 360, 390, 430, 600, 768, 900, 1024, 1440];
for (const width of widths) {
  test(
    'Thank donors modal fits and all actions remain available at ' + width + 'px',
    async ({ page }) => {
      const height = width <= 430 ? 740 : 900;
      await page.setViewportSize({ width, height });
      await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
      await page.goto('/new#/donors/donated');
      await page.getByRole('button', { name: 'Thank donors', exact: true }).click();
      const modal = page.locator('#donorThanksDialog');
      await expect(modal).toBeVisible();
      await expect(page.locator('#thanksMessage')).toBeVisible();
      for (const id of [
        'thanksAttachImg',
        'thanksAttachVid',
        'thanksGapSel',
        'thanksVarySel',
        'thanksBatchSel',
        'thanksRestSel',
        'thanksSave',
        'thanksTest',
        'thanksSwitch',
        'thanksClose',
      ])
        await expect(page.locator('#' + id)).toBeAttached();
      const metrics = await modal.evaluate((node) => {
        const rect = node.getBoundingClientRect();
        const footer = node.querySelector('footer');
        const footRect = footer.getBoundingClientRect();
        const body = node.querySelector('.thanks-body');
        const bRect = body.getBoundingClientRect();
        const fields = [...node.querySelectorAll('.thanks-timing select')];
        const timeFits = fields.every((el) => {
          const r = el.getBoundingClientRect();
          return r.left >= rect.left - 1 && r.right <= rect.right + 1;
        });
        const rectOf = (sel) => node.querySelector(sel).getBoundingClientRect();
        return {
          rect: {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            right: rect.right,
            bottom: rect.bottom,
          },
          body: {
            top: bRect.top,
            bottom: bRect.bottom,
            scrollHeight: body.scrollHeight,
            clientHeight: body.clientHeight,
          },
          footer: {
            top: footRect.top,
            bottom: footRect.bottom,
            scrollWidth: footer.scrollWidth,
            clientWidth: footer.clientWidth,
          },
          header: rectOf('header').bottom,
          timingFits: timeFits,
          backdrop: {
            background: getComputedStyle(node, '::backdrop').backgroundColor,
            filter: getComputedStyle(node, '::backdrop').backdropFilter,
          },
          actions: [...footer.querySelectorAll('button')].map((b) => {
            const r = b.getBoundingClientRect();
            return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, height: r.height };
          }),
        };
      });
      expect(metrics.rect.x).toBeGreaterThanOrEqual(-1);
      expect(metrics.rect.y).toBeGreaterThanOrEqual(-1);
      expect(metrics.rect.right).toBeLessThanOrEqual(width + 1);
      expect(metrics.rect.bottom).toBeLessThanOrEqual(height + 1);
      expect(metrics.rect.width).toBeLessThan(width);
      expect(metrics.rect.height).toBeLessThan(height);
      expect(metrics.header).toBeLessThanOrEqual(metrics.body.top + 2);
      expect(metrics.body.bottom).toBeLessThanOrEqual(metrics.footer.top + 2);
      expect(metrics.footer.scrollWidth).toBeLessThanOrEqual(metrics.footer.clientWidth + 2);
      expect(metrics.timingFits).toBe(true);
      if (width === 390) expect(metrics.rect.height).toBeLessThanOrEqual(560);
      for (const [id, name] of [
        ['thanksGapSel', 'Gap'],
        ['thanksVarySel', 'Vary'],
        ['thanksBatchSel', 'Batch'],
        ['thanksRestSel', 'Rest'],
      ]) {
        const options = await page.locator('#' + id + ' option').allTextContents();
        expect(options.some((value) => value.startsWith(name + ': '))).toBe(true);
      }
      const timingRows = await page
        .locator('.thanks-timing select')
        .evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top)));
      expect(new Set(timingRows).size).toBe(width <= 369 ? 2 : 1);
      // No blurred or semi-transparent backdrop that lets a purple dock show beneath the popup.
      expect(metrics.backdrop.background).toBe('rgb(5, 7, 12)');
      expect(metrics.backdrop.filter).toBe('none');
      expect(metrics.footer.bottom).toBeLessThanOrEqual(metrics.rect.bottom + 1);
      for (const action of metrics.actions) {
        expect(action.left).toBeGreaterThanOrEqual(metrics.rect.x - 1);
        expect(action.right).toBeLessThanOrEqual(metrics.rect.right + 1);
        expect(action.top).toBeGreaterThanOrEqual(metrics.footer.top - 1);
        expect(action.bottom).toBeLessThanOrEqual(metrics.footer.bottom + 1);
        expect(action.bottom).toBeLessThanOrEqual(metrics.rect.bottom - 6);
        expect(action.height).toBeGreaterThanOrEqual(40);
      }
      await page
        .locator('#thanksMessage')
        .fill('JazakAllah for helping Yousaf and his family. '.repeat(10));
      await page.locator('#thanksGapSel').selectOption('custom');
      await expect(page.locator('#thanksGap')).toBeVisible();
      await page.locator('#thanksGap').fill('5');
      await page.locator('#thanksBatchSel').selectOption('20');
      // This is a visual-only test: never start or test-send any donor messages.
      await expect(page.locator('#thanksClose')).toBeInViewport();
      await page.screenshot({ path: 'mobile-screenshots/thanks-modal-' + width + '.png' });
      await page.locator('#thanksClose').click();
      await expect(modal).toBeHidden();
    },
  );
}

test('Short mobile keyboard viewport: caption and message scroll above action bar', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 420 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await page.getByRole('button', { name: 'Thank donors', exact: true }).click();
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII=',
    'base64',
  );
  await page
    .locator('#thanksFile')
    .setInputFiles({ name: 'proof.png', mimeType: 'image/png', buffer: png });
  await expect(page.locator('.thanks-capd textarea')).toBeVisible();
  for (const sel of ['.thanks-capd textarea', '#thanksMessage']) {
    await page.locator(sel).fill('A real completion note for a donor. '.repeat(4));
    await page.locator(sel).focus();
    await expect
      .poll(async () =>
        page.locator(sel).evaluate((el) => {
          const r = el.getBoundingClientRect();
          const area = document
            .querySelector('#donorThanksDialog .thanks-body')
            .getBoundingClientRect();
          return r.top >= area.top - 2 && r.bottom <= area.bottom + 2;
        }),
      )
      .toBe(true);
  }
  await expect(page.locator('#thanksClose')).toBeInViewport();
  await expect(page.locator('#thanksSwitch')).toBeInViewport();
});
