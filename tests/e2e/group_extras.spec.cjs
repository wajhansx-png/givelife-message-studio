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

/* The main Message page has no PDF / Video row: the ticks live in the message screen (reader) and in Donors. */
test('Message page: no Also send row', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  await page.waitForFunction(() => typeof setView === 'function' && window.DonorHub);
  await expect(page.locator('#ui2Extras')).toHaveCount(0);
  await expect(page.locator('.ui2-xi')).toHaveCount(0);
});

for (const [view, width] of [['group', 280], ['group', 320], ['group', 360], ['dm', 360], ['dm', 412], ['group', 1280]])
  test(`Reader (${view}) at ${width}px: the ticks show in one line above the buttons, never covered`, async ({ page }) => {
    await page.setViewportSize({ width, height: width >= 900 ? 900 : 740 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new');
    await page.waitForFunction(() => typeof setView === 'function' && window.DonorHub);
    if (view === 'dm') await page.evaluate(() => setView('dm'));
    await page.evaluate(() => { location.hash = '#/preview'; });
    const box = page.locator('#ui2ReaderExtras');
    await expect(box).toBeVisible();
    const m = await page.evaluate(() => {
      const r = (e) => e.getBoundingClientRect();
      const b = r(document.getElementById('ui2ReaderExtras'));
      const dock = r(document.querySelector('#messageFocus .ui2-reader-dock'));
      const chips = [...document.querySelectorAll('#ui2ReaderExtras .ui2-rx-chip')].map(r);
      const hit = [...document.querySelectorAll('#ui2ReaderExtras .ui2-rx-chip')].map((c) => {
        const q = r(c);
        const top = document.elementFromPoint(q.x + q.width / 2, q.y + q.height / 2);
        return c.contains(top);
      });
      return { b, dock, chips, hit, sw: document.documentElement.scrollWidth, w: innerWidth };
    });
    expect(m.b.bottom, 'above the dock').toBeLessThanOrEqual(m.dock.top + 1);
    expect(m.sw).toBeLessThanOrEqual(m.w + 1);
    for (const c of m.chips) {
      expect(c.height).toBeGreaterThanOrEqual(39);
      expect(c.x).toBeGreaterThanOrEqual(0);
      expect(c.x + c.width).toBeLessThanOrEqual(m.w + 0.5);
    }
    expect(m.hit).toEqual([true, true]); // nothing sits on top of the ticks
    expect(m.b.height, 'one line').toBeLessThan(60);
  });

/* The same two ticks under the message in the reader: group message (after the poster) and DM (after each DM). */
async function openReader(page, view = 'group', width = 390) {
  await page.setViewportSize({ width, height: width >= 900 ? 900 : 760 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  await page.waitForFunction(() => typeof setView === 'function' && window.DonorHub);
  if (view === 'dm') await page.evaluate(() => setView('dm'));
  await page.evaluate(() => { location.hash = '#/preview'; });
  await expect(page.locator('#ui2ReaderExtras')).toBeVisible();
}

test('Reader: nothing saved means disabled ticks and an Add files button', async ({ page }) => {
  await api(port, '/group-extras', { action: 'remove', kind: 'pdf' });
  await api(port, '/group-extras', { action: 'remove', kind: 'video' });
  await openReader(page);
  await expect(page.locator('#ui2Rx-pdf')).toBeDisabled();
  await expect(page.locator('#ui2Rx-video')).toBeDisabled();
  await expect(page.locator('.ui2-rx-add')).toBeVisible();
});

test('Reader (group message): tick PDF and video, both / one / none, applied to the group posts', async ({ page }) => {
  await api(port, '/group-extras', { action: 'add', kind: 'pdf', data: 'data:application/pdf;base64,' + PDF.toString('base64'), name: 'a.pdf' });
  await api(port, '/group-extras', { action: 'add', kind: 'video', data: 'data:video/mp4;base64,' + MP4.toString('base64'), name: 'b.mp4' });
  await openReader(page, 'group');
  await expect(page.locator('#ui2ReaderExtras')).toHaveAttribute('title', /after the poster and caption in every group post/);
  await expect(page.locator('#ui2Rx-pdf')).toBeChecked();
  await expect(page.locator('#ui2Rx-video')).toBeChecked();
  await page.locator('#ui2Rx-pdf').uncheck();
  let v = await api(port, '/group-extras');
  expect([v.pdf.on, v.video.on]).toEqual([false, true]); // only the video goes
  await page.locator('#ui2Rx-video').uncheck();
  v = await api(port, '/group-extras');
  expect([v.pdf.on, v.video.on]).toEqual([false, false]); // none
  await page.locator('#ui2Rx-pdf').check();
  await page.locator('#ui2Rx-video').check();
  v = await api(port, '/group-extras');
  expect([v.pdf.on, v.video.on]).toEqual([true, true]); // both
});

test('Reader (DM message): its own ticks, remembered for DMs, group choice untouched', async ({ page }) => {
  await openReader(page, 'dm');
  await expect(page.locator('#ui2ReaderExtras')).toHaveAttribute('title', /after each DM/);
  await expect(page.locator('#ui2Rx-pdf')).not.toBeChecked(); // DMs start unticked
  await page.locator('#ui2Rx-pdf').check();
  await expect(page.locator('#ui2Rx-pdf')).toBeChecked();
  await expect
    .poll(() => page.evaluate(() => [localStorage.getItem('givelife-dm-pdf'), localStorage.getItem('givelife-dm-video')]))
    .toEqual(['1', null]);
  const v = await api(port, '/group-extras');
  expect([v.pdf.on, v.video.on]).toEqual([true, true]); // the group ticks did not change
  await page.locator('#ui2Rx-pdf').uncheck();
  await page.locator('#ui2Rx-video').check();
  await expect
    .poll(() => page.evaluate(() => [localStorage.getItem('givelife-dm-pdf'), localStorage.getItem('givelife-dm-video')]))
    .toEqual(['0', '1']); // checked against the saved files first, so it lands a moment later
  // the Donors page shows the same ticks
  await expect(page.locator('#donorVideo')).toBeChecked();
  await expect(page.locator('#donorPdf')).not.toBeChecked();
});

for (const width of [390, 430, 1440])
  test(`Reader: the PDF / Video ticks fit at ${width}px with real tap targets`, async ({ page }) => {
    await openReader(page, 'group', width);
    for (const sel of ['#ui2Rx-pdf', '#ui2Rx-video']) {
      const b = await page.locator(sel).locator('xpath=..').boundingBox();
      expect(b.height, sel).toBeGreaterThanOrEqual(39);
      expect(b.x, sel).toBeGreaterThanOrEqual(0);
      expect(b.x + b.width, sel).toBeLessThanOrEqual(width + 0.5);
    }
    // one line, and above the bottom dock on phones (nothing under it)
    const box = await page.locator('#ui2ReaderExtras').boundingBox();
    expect(box.height).toBeLessThan(48);
    const dock = await page.locator('.ui2-reader-dock').boundingBox().catch(() => null);
    if (dock && width < 900 && dock.height > 0) expect(box.y + box.height).toBeLessThanOrEqual(dock.y + 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
