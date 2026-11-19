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
    const next = await page.locator('#ui2Swipe .ui2-swipe-next').boundingBox();
    expect((await g.boundingBox()).x - (next.x + next.width), 'gap between › and ✦').toBeGreaterThanOrEqual(16);
    // pressing it starts writing: the real Generate button is pressed (it is busy while versions are written)
    await g.click();
    await expect.poll(async () => (await api(port, '/focus-bank?kind=group')).state).not.toBe('Not generated');
  });

test('while 5 versions are written the sparkle shows the live count 0/5 … then comes back', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  const real = await api(port, '/focus-bank?kind=group');
  let done = 0,
    ready = false;
  const row = () => ({
    ...real,
    items: Array.from({ length: done }, (_, i) => `*Version ${i + 1}* Please help today. Rs. 5,000 needed.`),
    state: ready ? 'Ready' : 'Generating',
    batch: ready ? null : { goal: 5, auto: false, at: Date.now() / 1000 },
  });
  await page.route('**/focus-bank**', (route) => route.fulfill({ json: row() }));
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  const g = page.locator('#ui2Swipe .ui2-gen-btn');
  await expect(g).toHaveText('0/5');
  await expect(g).toHaveAccessibleName('Writing versions 0 of 5');
  done = 2;
  await expect(g).toHaveText('2/5');
  done = 5;
  ready = true;
  await expect(g.locator('svg')).toBeVisible(); // finished: the sparkle is back
  await expect(g).toHaveAccessibleName('Write 5 new versions');
  await expect(g).toBeEnabled();
});

for (const width of [320, 360, 390, 412, 430, 480, 540])
  test(`the version label never overlaps the arrows with versions saved at ${width}px`, async ({ page }) => {
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
    await api(port, '/focus-bank', { kind: 'group', action: 'manual', messages: [V1, V2, V1.replace('Second', 'Fourth'), V1.replace('Second', 'Fifth'), V1.replace('Second', 'Sixth')] });
    await page.setViewportSize({ width, height: 860 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/preview');
    const sels = ['.ui2-swipe-prev', '.ui2-ver', '.ui2-swipe-next', '.ui2-gen-btn', '.ui2-base-btn'];
    for (const step of [0, 1]) {
      if (step) await page.locator('#ui2Swipe .ui2-swipe-next').click();
      const boxes = [];
      for (const s of sels) boxes.push(await page.locator('#ui2Swipe ' + s).boundingBox());
      for (let i = 0; i < boxes.length - 1; i++)
        expect(boxes[i].x + boxes[i].width, sels[i] + ' vs ' + sels[i + 1]).toBeLessThanOrEqual(boxes[i + 1].x + 1);
      const ver = page.locator('#ui2Swipe .ui2-ver');
      expect(await ver.evaluate((e) => e.scrollWidth <= e.clientWidth + 1), 'label fits').toBe(true);
    }
  });

test('✦ deletes the old versions and writes a fresh 5 (never adds to the old ones)', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  const posts = [];
  await page.route('**/focus-bank', async (route) => {
    if (route.request().method() === 'POST') posts.push(JSON.parse(route.request().postData() || '{}'));
    await route.continue();
  });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await page.locator('#ui2Swipe .ui2-gen-btn').click();
  await expect.poll(() => posts.map((b) => b.action)).toContain('regenerate');
  expect(posts.map((b) => b.action)).not.toContain('generate');
});
test('Save base then Cancel: swiping on never saves the version that was only looked at', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await api(port, '/focus-bank', { kind: 'group', action: 'manual', messages: [V1, V2] });
  const posts = [];
  await page.route('**/focus-bank', async (route) => {
    if (route.request().method() === 'POST') posts.push(JSON.parse(route.request().postData() || '{}'));
    await route.continue();
  });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await expect(page.locator('#focusFormatted')).toContainText('Second wording');
  await page.locator('#ui2Swipe .ui2-base-btn').click();
  await page.locator('#focusBaseCancel').click();
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await expect(page.locator('#focusFormatted')).toContainText('Third wording');
  await page.locator('#ui2Swipe .ui2-base-btn').click();
  await page.keyboard.press('Escape');
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await expect(page.locator('#focusFormatted')).toContainText('Base wording');
  expect(posts.filter((b) => b.action === 'save')).toEqual([]);
  expect((await api(port, '/focus-bank?kind=group')).source).toBe(BASE);
});
test('✦ while a version shows: the deleted version leaves the screen and the base shows', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await api(port, '/focus-bank', { kind: 'group', action: 'manual', messages: [V1] });
  await page.route('**/focus-bank', async (route) => {
    const b = JSON.parse(route.request().postData() || '{}');
    if (b.action === 'regenerate')
      return route.fulfill({ json: { source: BASE, items: [], state: 'Generating', revision: 'r', batch: { goal: 5 } } });
    await route.continue();
  });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await expect(page.locator('#focusFormatted')).toContainText('Second wording');
  await page.locator('#ui2Swipe .ui2-gen-btn').click();
  await expect(page.locator('#focusFormatted')).toContainText('Base wording');
  await expect(page.locator('#focusRegenerate')).toBeDisabled(); // one batch at a time
});
test('Test on the DM screen sends the DM and never changes the Group message', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await api(port, '/focus-bank', { kind: 'dm', action: 'save', text: 'Brother, ' + V2 });
  const sent = [];
  await page.route('**/test', (route) => {
    sent.push(JSON.parse(route.request().postData() || '{}').message);
    return route.fulfill({ json: { code: 'SUCCESS' } });
  });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => {
    localStorage.setItem('givelife-cloud-key', k);
    localStorage.setItem('givelife-view', 'dm');
  }, KEY);
  await page.goto('/new#/preview');
  await expect(page.locator('#messageFocus')).toHaveAttribute('data-kind', 'dm');
  await page.locator('#focusTest').click();
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]).toContain('Brother,');
  expect(page.url()).toContain('preview');
  await page.waitForTimeout(600);
  expect((await api(port, '/drafts')).group).toBe(BASE);
  expect((await api(port, '/focus-bank?kind=group')).source).toBe(BASE);
});
test('Save base while editing a message with versions: the dialog offers Save + write 5 new', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await api(port, '/focus-bank', { kind: 'group', action: 'manual', messages: [V1, V2] });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await page.locator('#focusEdit').click();
  await page.locator('#ui2Live').click();
  await page.keyboard.press('End');
  await page.keyboard.type(' Thank you.');
  await page.evaluate(() => document.getElementById('focusSave').click()); // Save base (rail / dock) while editing
  await expect(page.locator('#focusBaseSave')).toHaveText('Save + write 5 new');
  await page.locator('#focusBaseCancel').click();
  expect((await api(port, '/focus-bank?kind=group')).source).toBe(BASE); // Cancel saved nothing
});
test('Group: the version on screen goes with Send and Test; the base screen sends no pin', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await api(port, '/focus-bank', { kind: 'group', action: 'manual', messages: [V1, V2] });
  const bodies = [];
  await page.route('**/test', (route) => {
    bodies.push(JSON.parse(route.request().postData() || '{}'));
    return route.fulfill({ json: { code: 'SUCCESS' } });
  });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await page.locator('#focusTest').click();
  await expect.poll(() => bodies.length).toBe(1);
  expect(bodies[0].version).toBeUndefined(); // the base: the usual rotation
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await expect(page.locator('#focusFormatted')).toContainText('Third wording');
  await expect.poll(() => page.evaluate(() => window.focusShownVersion)).toBe(V2);
  await page.locator('#focusTest').click();
  await expect.poll(() => bodies.length).toBe(2);
  expect(bodies[1]).toMatchObject({ kind: 'group', version: V2 });
});
