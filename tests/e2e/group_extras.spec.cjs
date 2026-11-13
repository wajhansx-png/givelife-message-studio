/* PDF and video that follow the poster in every group post: add, switch off, remove. Fake WhatsApp only. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 481;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
test.describe.configure({ mode: 'serial' });

const PDF = Buffer.concat([Buffer.from('%PDF-1.4\n'), Buffer.alloc(300, 120)]);
const MP4 = Buffer.concat([Buffer.from([0, 0, 0, 24]), Buffer.from('ftypmp42'), Buffer.alloc(300)]);

async function openPoster(page, width = 390, path = '/new') {
  await page.setViewportSize({ width, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto(path);
  await page.waitForFunction(() => window.DonorHub && window.DonorHub.openPoster);
  await page.evaluate(() => window.DonorHub.openPoster());
  await expect(page.locator('#posterExtras')).toBeVisible();
}
const row = (page, kind) => page.locator(`.poster-extra[data-kind="${kind}"]`);

test('the poster dialog lists the PDF and the video, empty at first, with the send order', async ({ page }) => {
  await openPoster(page);
  await expect(page.locator('#posterExtras h3')).toHaveText('Sent after the poster in groups');
  await expect(page.locator('.poster-extras-note')).toContainText('poster and caption, then the PDF, then the video');
  for (const kind of ['pdf', 'video']) {
    await expect(row(page, kind).locator('small')).toHaveText('Not added');
    await expect(row(page, kind).locator('.poster-extra-sw')).toBeHidden();
    await expect(row(page, kind).locator('.poster-extra-add')).toContainText('Add');
  }
});

test('add a PDF and a video: both switched on, and the server sends PDF first then video', async ({ page }) => {
  await openPoster(page);
  await row(page, 'pdf').locator('input[type=file]').setInputFiles({ name: 'oxygen-report.pdf', mimeType: 'application/pdf', buffer: PDF });
  await expect(row(page, 'pdf').locator('small')).toContainText('oxygen-report.pdf');
  await expect(row(page, 'pdf').locator('.poster-extra-sw')).toHaveAttribute('aria-checked', 'true');
  await row(page, 'video').locator('input[type=file]').setInputFiles({ name: 'cylinders.mp4', mimeType: 'video/mp4', buffer: MP4 });
  await expect(row(page, 'video').locator('small')).toContainText('cylinders.mp4');
  await expect(row(page, 'video').locator('.poster-extra-sw')).toHaveAttribute('aria-checked', 'true');
  const v = await api(port, '/group-extras');
  expect([v.pdf.has, v.pdf.on, v.video.has, v.video.on]).toEqual([true, true, true, true]);
  await expect(page.locator('#posterExtrasMsg')).toContainText('goes out after the poster');
});

test('switching the PDF off keeps it saved but skips it; the choice survives a reload', async ({ page }) => {
  await openPoster(page);
  const sw = row(page, 'pdf').locator('.poster-extra-sw');
  await expect(sw).toHaveAttribute('aria-checked', 'true');
  await sw.click();
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  const v = await api(port, '/group-extras');
  expect([v.pdf.has, v.pdf.on, v.video.on]).toEqual([true, false, true]); // still saved; the video is untouched
  await page.reload();
  await page.waitForFunction(() => window.DonorHub && window.DonorHub.openPoster);
  await page.evaluate(() => window.DonorHub.openPoster());
  await expect(row(page, 'pdf').locator('.poster-extra-sw')).toHaveAttribute('aria-checked', 'false');
  await expect(row(page, 'pdf').locator('small')).toContainText('oxygen-report.pdf');
  await row(page, 'pdf').locator('.poster-extra-sw').click(); // back on
  await expect(row(page, 'pdf').locator('.poster-extra-sw')).toHaveAttribute('aria-checked', 'true');
});

test('a wrong file is refused with a plain reason and nothing changes; remove clears one', async ({ page }) => {
  await openPoster(page);
  await row(page, 'pdf').locator('input[type=file]').setInputFiles({ name: 'clip.mp4', mimeType: 'video/mp4', buffer: MP4 });
  await expect(page.locator('#posterExtrasMsg')).toContainText('Choose a PDF');
  await expect(row(page, 'pdf').locator('small')).toContainText('oxygen-report.pdf'); // unchanged
  await row(page, 'video').locator('.poster-extra-rm').click();
  await expect(row(page, 'video').locator('small')).toHaveText('Not added');
  expect((await api(port, '/group-extras')).video.has).toBe(false);
});

for (const width of [320, 390, 1440])
  test(`the PDF and video rows fit the dialog at ${width}px with real tap targets`, async ({ page }) => {
    await openPoster(page, width);
    const dlg = await page.locator('#posterDialog').boundingBox();
    for (const kind of ['pdf', 'video']) {
      for (const sel of ['.poster-extra-add', '.poster-extra-sw', '.poster-extra-rm']) {
        const el = row(page, kind).locator(sel);
        if (!(await el.isVisible())) continue;
        const b = await el.boundingBox();
        expect(b.height, kind + sel).toBeGreaterThanOrEqual(43);
        expect(b.x, kind + sel).toBeGreaterThanOrEqual(dlg.x - 1);
        expect(b.x + b.width, kind + sel).toBeLessThanOrEqual(dlg.x + dlg.width + 1);
      }
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
