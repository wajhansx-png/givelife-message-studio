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
const JPG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(300, 7)]);

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
  await expect(page.locator('#posterExtras h3')).toHaveText('Video and PDF (groups and DMs)');
  await expect(page.locator('.poster-extras-note')).toContainText('the file with the text first');
  await expect(page.locator('#posterTextOn-video')).toHaveAttribute('aria-pressed', 'true'); // a new case: text on the video
  await page.locator('#posterTextOn-poster').click();
  await expect(page.locator('#posterTextOn-poster')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#posterTextOn-video').click();
  await expect(page.locator('#posterTextOn-video')).toHaveAttribute('aria-pressed', 'true');
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

for (const [view, width] of [['group', 280], ['group', 320], ['group', 360], ['group', 375], ['group', 390], ['group', 412], ['dm', 280], ['dm', 360], ['dm', 412], ['group', 1280]])
  test(`Reader (${view}) at ${width}px: the ticks show in one line above the buttons, never covered`, async ({ page }) => {
    await api(port, '/group-extras', { action: 'add', kind: 'pdf', data: 'data:application/pdf;base64,' + PDF.toString('base64'), name: 'a.pdf' });
    await api(port, '/group-extras', { action: 'add', kind: 'video', data: 'data:video/mp4;base64,' + MP4.toString('base64'), name: 'b.mp4' });
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
      const chips = [...document.querySelectorAll('#ui2ReaderExtras .ui2-rx-item .ui2-rx-chip')].map(r);
      const hit = [...document.querySelectorAll('#ui2ReaderExtras .ui2-rx-item .ui2-rx-chip')].map((c) => {
        const q = r(c);
        const top = document.elementFromPoint(q.x + q.width / 2, q.y + q.height / 2);
        return c.contains(top);
      });
      const texts = [...document.querySelectorAll('#ui2RxText button')].map(r);
      return { b, dock, chips, hit, texts, sw: document.documentElement.scrollWidth, w: innerWidth };
    });
    // phone: above the fixed bottom bar; computer: the bar is part of the page, the row just stays on screen
    if (width < 900) expect(m.b.bottom, 'above the dock').toBeLessThanOrEqual(m.dock.top + 1);
    else expect(m.b.bottom, 'on screen').toBeLessThanOrEqual(900);
    expect(m.sw).toBeLessThanOrEqual(m.w + 1);
    for (const c of m.chips) {
      expect(c.height).toBeGreaterThanOrEqual(39);
      expect(c.x).toBeGreaterThanOrEqual(0);
      expect(c.x + c.width).toBeLessThanOrEqual(m.w + 0.5);
    }
    expect(m.hit).toEqual([true, true, true]); // PDF, Video and Poster: nothing sits on top of the ticks
    expect(Math.abs(m.chips[0].y - m.chips[1].y), 'PDF and Video on one line').toBeLessThan(2);
    // a video is attached: "Text goes with: Video / Poster" sits on the next line, real buttons, on screen
    expect(m.texts.length).toBe(2);
    for (const t of m.texts) {
      expect(t.height).toBeGreaterThanOrEqual(39);
      expect(t.x).toBeGreaterThanOrEqual(0);
      expect(t.x + t.width).toBeLessThanOrEqual(m.w + 0.5);
      if (width < 900) expect(t.bottom).toBeLessThanOrEqual(m.dock.top + 1);
    }
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

test('Reader: Text goes with Video / Poster is right under the ticks once a video is attached, and saves', async ({ page }) => {
  await api(port, '/group-extras', { action: 'add', kind: 'video', data: 'data:video/mp4;base64,' + MP4.toString('base64'), name: 'b.mp4' });
  await openReader(page);
  await expect(page.locator('#ui2RxText')).toBeVisible();
  await expect(page.locator('#ui2RxText-video')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#ui2RxText-poster').click();
  await expect(page.locator('#ui2RxText-poster')).toHaveAttribute('aria-pressed', 'true');
  expect((await api(port, '/group-extras')).text_on).toBe('poster');
  await page.locator('#ui2RxText-video').click();
  await expect.poll(async () => (await api(port, '/group-extras')).text_on).toBe('video');
  await api(port, '/group-extras', { action: 'remove', kind: 'video' });
  await page.reload();
  await expect(page.locator('#ui2ReaderExtras')).toBeVisible();
  await expect(page.locator('#ui2RxText')).toBeHidden(); // no video: nothing to choose
});

test('Reader: the after poster is its own picture: Add uploads it, the tick sends it after the message', async ({ page }) => {
  await api(port, '/group-extras', { action: 'remove', kind: 'poster' });
  await openReader(page);
  const item = page.locator('.ui2-rx-item[data-kind="poster"]');
  await expect(item).toBeVisible();
  await expect(page.locator('#ui2Rx-poster')).toBeDisabled(); // nothing to tick before it is added
  await expect(item.locator('.ui2-rx-add')).toHaveText('Add');
  await page.locator('#ui2RxFile-poster').setInputFiles({ name: 'after.jpg', mimeType: 'image/jpeg', buffer: JPG });
  await expect(item.locator('.ui2-rx-add')).toHaveText('Change', { timeout: 15000 });
  await expect(page.locator('#ui2Rx-poster')).toBeChecked(); // added = on for the groups
  const v = await api(port, '/group-extras');
  expect(v.poster.has).toBe(true);
  expect(v.setup.group.poster).toBe(true);
  expect(v.setup.dm.poster).toBe(false); // DMs and Giki keep their own tick
  expect(v.setup.giki.poster).toBe(false);
  await page.locator('#ui2Rx-poster').uncheck();
  await expect.poll(async () => (await api(port, '/group-extras')).setup.group.poster).toBe(false);
  await page.locator('#ui2Rx-poster').check();
  // the DM view ticks the DMs' own after poster, and has no upload button
  await openReader(page, 'dm');
  await expect(page.locator('#ui2Rx-poster')).not.toBeChecked();
  await page.locator('#ui2Rx-poster').check();
  await expect.poll(async () => (await api(port, '/group-extras')).setup.dm.poster).toBe(true);
  expect((await api(port, '/group-extras')).setup.group.poster).toBe(true);
  // a PDF offered as the poster is refused
  const r = await page.evaluate(async (k) => (await fetch('/group-extras-file', { method: 'POST', headers: { Authorization: 'Bearer ' + k, 'X-Extra-Kind': 'poster', 'Content-Type': 'application/pdf' }, body: '%PDF-1.4 not a picture' })).status, KEY);
  expect(r).toBe(400);
});

test('Reader (group message): nothing saved means disabled ticks and an Add button on each', async ({ page }) => {
  await api(port, '/group-extras', { action: 'remove', kind: 'pdf' });
  await api(port, '/group-extras', { action: 'remove', kind: 'video' });
  await openReader(page);
  for (const kind of ['pdf', 'video']) {
    await expect(page.locator(`#ui2Rx-${kind}`)).toBeDisabled();
    await expect(page.locator(`.ui2-rx-item[data-kind="${kind}"] .ui2-rx-add`)).toHaveText('Add');
  }
});

test('Reader (group message): attach a PDF and a video here, then tick which ones go', async ({ page }) => {
  await api(port, '/group-extras', { action: 'remove', kind: 'pdf' });
  await api(port, '/group-extras', { action: 'remove', kind: 'video' });
  await openReader(page);
  await page.locator('#ui2RxFile-pdf').setInputFiles({ name: 'case-report.pdf', mimeType: 'application/pdf', buffer: PDF });
  await expect(page.locator('#ui2Rx-pdf')).toBeChecked(); // a new file starts ticked: it goes
  await expect(page.locator('.ui2-rx-item[data-kind="pdf"] .ui2-rx-add')).toHaveText('Change');
  await expect(page.locator('.ui2-rx-item[data-kind="pdf"]')).toHaveAttribute('title', 'case-report.pdf');
  await page.locator('#ui2RxFile-video').setInputFiles({ name: 'oxygen.mp4', mimeType: 'video/mp4', buffer: MP4 });
  await expect(page.locator('#ui2Rx-video')).toBeChecked();
  let v = await api(port, '/group-extras');
  expect([v.pdf.has, v.pdf.on, v.video.has, v.video.on]).toEqual([true, true, true, true]);
  await page.locator('#ui2Rx-pdf').uncheck();
  v = await api(port, '/group-extras');
  expect([v.pdf.on, v.video.on]).toEqual([false, true]); // only the video goes; the PDF stays attached
  // a wrong file says why and changes nothing
  await page.locator('#ui2RxFile-pdf').setInputFiles({ name: 'clip.mp4', mimeType: 'video/mp4', buffer: MP4 });
  await expect(page.locator('.ui2-rx-msg')).toContainText('Choose a PDF');
  await expect(page.locator('.ui2-rx-item[data-kind="pdf"]')).toHaveAttribute('title', 'case-report.pdf');
});

/* Live percentage: a slow connection (CDP-throttled upload) makes the steps visible. */
async function slowUpload(page, kbps = 400) {
  const client = await page.context().newCDPSession(page);
  await client.send('Network.enable');
  await client.send('Network.emulateNetworkConditions', { offline: false, latency: 20, downloadThroughput: -1, uploadThroughput: kbps * 1024 });
}
const BIG_PDF = Buffer.concat([Buffer.from('%PDF-1.4\n'), Buffer.alloc(1_300_000, 120)]);

test('Reader: adding a PDF shows a live percentage that only rises, then Saving, then Change', async ({ page }) => {
  await api(port, '/group-extras', { action: 'remove', kind: 'pdf' });
  await openReader(page);
  await slowUpload(page);
  await page.evaluate(() => {
    window.__seen = [];
    const el = document.querySelector('.ui2-rx-item[data-kind="pdf"] .ui2-rx-add');
    new MutationObserver(() => window.__seen.push(el.textContent)).observe(el, { childList: true, characterData: true, subtree: true });
  });
  await page.locator('#ui2RxFile-pdf').setInputFiles({ name: 'big.pdf', mimeType: 'application/pdf', buffer: BIG_PDF });
  await expect(page.locator('.ui2-rx-item[data-kind="pdf"]')).toHaveAttribute('data-up', '1');
  await expect(page.locator('.ui2-rx-item[data-kind="pdf"] .ui2-rx-add')).toHaveText('Change', { timeout: 40000 });
  const seen = await page.evaluate(() => window.__seen);
  const pcts = seen.filter((t) => /^\d+%$/.test(t)).map((t) => parseInt(t, 10));
  expect(pcts.length, 'several live steps, not just the end: ' + seen.join(' ')).toBeGreaterThan(2);
  expect(pcts).toEqual([...pcts].sort((a, b) => a - b));
  expect(Math.max(...pcts)).toBeGreaterThan(50);
  expect(seen).toContain('Saving');
  await expect(page.locator('#ui2Rx-pdf')).toBeChecked();
  await expect(page.locator('.ui2-rx-item[data-kind="pdf"]')).not.toHaveAttribute('data-up', '1');
});

test('Poster dialog: adding a video shows percent and megabytes live', async ({ page }) => {
  await api(port, '/group-extras', { action: 'remove', kind: 'video' });
  await openPoster(page);
  await slowUpload(page);
  await page.evaluate(() => {
    window.__seen = [];
    const el = document.querySelector('.poster-extra[data-kind="video"] small');
    new MutationObserver(() => window.__seen.push(el.textContent)).observe(el, { childList: true, characterData: true, subtree: true });
  });
  const big = Buffer.concat([Buffer.from([0, 0, 0, 24]), Buffer.from('ftypmp42'), Buffer.alloc(1_300_000)]);
  await page.locator('#posterExtraFile-video').setInputFiles({ name: 'big.mp4', mimeType: 'video/mp4', buffer: big });
  await expect(row(page, 'video').locator('small')).toContainText('big.mp4', { timeout: 40000 });
  const seen = await page.evaluate(() => window.__seen);
  const live = seen.filter((t) => /^Uploading \d+% · [\d.]+ of 1\.2 MB$/.test(t));
  expect(live.length, seen.join(' | ')).toBeGreaterThan(2);
});

test('Reader (DM message): no attach buttons; a tick with no file says to attach it on the group message', async ({ page }) => {
  await api(port, '/group-extras', { action: 'remove', kind: 'pdf' });
  await api(port, '/group-extras', { action: 'remove', kind: 'video' });
  await openReader(page, 'dm');
  await expect(page.locator('.ui2-rx-add')).toHaveCount(3); // PDF, Video, Poster
  for (let i = 0; i < 3; i++) await expect(page.locator('.ui2-rx-add').nth(i)).toBeHidden(); // DMs never upload
  await page.locator('#ui2Rx-pdf').click({ force: true }); // refused at once, so it snaps back unticked
  await expect(page.locator('.ui2-rx-msg')).toContainText('Attach it on the group message first');
  await expect(page.locator('#ui2Rx-pdf')).not.toBeChecked();
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
  await expect(page.locator('#ui2ReaderExtras')).toHaveAttribute('title', /after each donor DM/);
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
    const pdf = await page.locator('#ui2Rx-pdf').locator('xpath=..').boundingBox(),
      video = await page.locator('#ui2Rx-video').locator('xpath=..').boundingBox();
    expect(Math.abs(pdf.y - video.y)).toBeLessThan(2); // the two ticks on one line
    const dock = await page.locator('.ui2-reader-dock').boundingBox().catch(() => null);
    if (dock && width < 900 && dock.height > 0) expect(box.y + box.height).toBeLessThanOrEqual(dock.y + 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
