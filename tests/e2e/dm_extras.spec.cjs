/* DM PDF and video: tick both, one or none (Msgs tab, Donors bar, batch picker); a missing file is refused. Fake WhatsApp. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 482;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
test.describe.configure({ mode: 'serial' });

const PDF = 'data:application/pdf;base64,' + Buffer.concat([Buffer.from('%PDF-1.4\n'), Buffer.alloc(300, 120)]).toString('base64');
const MP4 = 'data:video/mp4;base64,' + Buffer.concat([Buffer.from([0, 0, 0, 24]), Buffer.from('ftypmp42'), Buffer.alloc(300)]).toString('base64');

const openOptions = async (page) => {
  const sum = page.locator('.bank-extras-sum');
  if ((await sum.isVisible()) && (await sum.getAttribute('aria-expanded')) !== 'true') await sum.click();
};

async function openMsgs(page, width = 390) {
  await page.setViewportSize({ width, height: 800 });
  await page.addInitScript((k) => {
    localStorage.setItem('givelife-cloud-key', k);
  }, KEY);
  await page.goto('/new#/donors/messages');
  await expect(page.locator('#donorsPage')).toBeVisible();
  // on a phone the chips are in the "Send options" row that opens above it
  const sum = page.locator('.bank-extras-sum');
  await expect(page.locator('.bank-extras')).toBeVisible();
  if (await sum.isVisible()) await sum.click();
  await expect(page.locator('#msgPdf')).toBeVisible();
}

test('Msgs tab has Also send: PDF and Video, unticked at first', async ({ page }) => {
  await openMsgs(page);
  await expect(page.locator('.bank-extras-label')).toHaveText('Also send:');
  await expect(page.locator('#msgPdf')).not.toBeChecked();
  await expect(page.locator('#msgVideo')).not.toBeChecked();
});

test('ticking one with nothing saved is refused with a plain reason and stays unticked', async ({ page }) => {
  await openMsgs(page);
  await page.locator('#msgPdf').click({ force: true });
  await expect(page.locator('#donorNotice')).toContainText('No PDF is saved yet');
  await expect(page.locator('#msgPdf')).not.toBeChecked();
});

test('the server refuses a DM send that asks for a file that is not saved', async () => {
  const r = await api(port, '/donor-send', { id: 'x'.repeat(8), request_id: 'req-abcdefgh', pdf: true });
  expect(String(r.error)).toContain('No PDF is saved yet');
  const b = await api(port, '/donor-delivery', { scope: 'all', limit: 1, video: true });
  expect(String(b.error)).toContain('No Video is saved yet');
});

test('with both files saved: both, one, or none can be ticked, and the Donors bar and batch picker follow', async ({ page }) => {
  await api(port, '/group-extras', { action: 'add', kind: 'pdf', data: PDF, name: 'report.pdf' });
  await api(port, '/group-extras', { action: 'add', kind: 'video', data: MP4, name: 'clip.mp4' });
  await openMsgs(page);
  await page.locator('#msgPdf').click({ force: true });
  await page.locator('#msgVideo').click({ force: true });
  await expect(page.locator('#msgPdf')).toBeChecked();
  await expect(page.locator('#msgVideo')).toBeChecked();
  // the same two ticks live in the Donors bar (All tab) and in the DM batch picker
  await page.evaluate(() => { location.hash = '#/donors/all'; });
  await expect(page.locator('#donorPdf')).toBeChecked();
  await expect(page.locator('#donorVideo')).toBeChecked();
  await page.locator('#donorPace').evaluate((b) => b.click()); // opens the batch picker (the button can sit in a menu)
  await page.locator('#donorBatchPicker summary', { hasText: 'More options' }).click(); // Poster / Follow-up / PDF / Video live here
  await expect(page.locator('#batchPdf')).toBeVisible();
  await expect(page.locator('#batchPdf')).toBeChecked();
  await expect(page.locator('#batchVideo')).toBeChecked();
  // untick the PDF in the picker: only the video goes, and the Donors bar follows
  await page.locator('#batchPdf').click({ force: true });
  await expect(page.locator('#batchPdf')).not.toBeChecked();
  await expect(page.locator('#batchVideo')).toBeChecked();
  await expect(page.locator('#donorPdf')).not.toBeChecked();
  await expect(page.locator('#donorVideo')).toBeChecked();
  await page.locator('#batchCancel').click();
  await expect
    .poll(() => page.evaluate(() => [localStorage.getItem('givelife-dm-pdf'), localStorage.getItem('givelife-dm-video')]))
    .toEqual(['0', '1']);
  // survives a reload; the Msgs tab shows the same
  await page.evaluate(() => { location.hash = '#/donors/messages'; });
  await expect(page.locator('.bank-extras')).toBeVisible();
  await openOptions(page);
  await expect(page.locator('#msgPdf')).toBeVisible(); // the tab has rendered (and remembered itself) before we reload
  await page.reload();
  await expect(page.locator('.bank-extras')).toBeVisible();
  await openOptions(page);
  await expect(page.locator('#msgPdf')).toBeVisible();
  await expect(page.locator('#msgPdf')).not.toBeChecked();
  await expect(page.locator('#msgVideo')).toBeChecked();
  // none
  await page.locator('#msgVideo').click({ force: true });
  await expect(page.locator('#msgVideo')).not.toBeChecked();
});

test('removing a saved file unticks it the next time Donors opens (a new case starts with none)', async ({ page }) => {
  await openMsgs(page);
  await page.locator('#msgPdf').click({ force: true });
  await expect(page.locator('#msgPdf')).toBeChecked();
  await api(port, '/group-extras', { action: 'remove', kind: 'pdf' });
  await page.reload();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page.locator('.bank-extras')).toBeVisible();
  await openOptions(page);
  await expect(page.locator('#msgPdf')).toBeVisible();
  await expect(page.locator('#msgPdf')).not.toBeChecked();
});

test('the Msgs checkboxes fit at 320px with real tap targets', async ({ page }) => {
  await openMsgs(page, 320);
  for (const id of ['#msgPdf', '#msgVideo']) {
    const b = await page.locator(id).locator('xpath=..').boundingBox();
    expect(b.height).toBeGreaterThanOrEqual(38);
    expect(b.x).toBeGreaterThanOrEqual(0);
    expect(b.x + b.width).toBeLessThanOrEqual(320.5);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test('the DM ticks are saved on the server too, so Auto, the chat and Test start with the same files', async ({ page }) => {
  await api(port, '/group-extras', { action: 'add', kind: 'pdf', data: PDF, name: 'report.pdf' });
  await api(port, '/group-extras', { action: 'add', kind: 'video', data: MP4, name: 'clip.mp4' });
  await api(port, '/group-extras', { action: 'setup', profile: 'dm', field: 'pdf', value: false });
  await api(port, '/group-extras', { action: 'setup', profile: 'dm', field: 'video', value: false });
  await openMsgs(page);
  await page.locator('#msgPdf').click({ force: true });
  await expect(page.locator('#msgPdf')).toBeChecked();
  await expect
    .poll(async () => (await (await page.request.get('/group-extras', { headers: { Authorization: 'Bearer ' + KEY } })).json()).setup.dm.pdf)
    .toBe(true);
  await page.locator('#msgPdf').click({ force: true });
  await expect(page.locator('#msgPdf')).not.toBeChecked();
  await expect
    .poll(async () => (await (await page.request.get('/group-extras', { headers: { Authorization: 'Bearer ' + KEY } })).json()).setup.dm.pdf)
    .toBe(false);
});

test('the server wins: a tick saved there shows on a screen that never had it (another phone)', async ({ browser }) => {
  await api(port, '/group-extras', { action: 'setup', profile: 'dm', field: 'video', value: true });
  const page = await (await browser.newContext()).newPage();
  await openMsgs(page);
  await expect(page.locator('#msgVideo')).toBeChecked();
  await expect(page.locator('#msgPdf')).not.toBeChecked();
  await api(port, '/group-extras', { action: 'setup', profile: 'dm', field: 'video', value: false });
});

test('Msgs tab has a Follow-up tick (the Donors bar one is hidden on phones): same choice, in the Order line, fits at 320', async ({ page }) => {
  await openMsgs(page, 320);
  const tick = page.locator('#msgFollowUp');
  await expect(tick).toBeVisible();
  await expect(page.locator('.bank-extras-label')).toHaveText('Also send:');
  const box = await tick.locator('xpath=..').boundingBox();
  expect(box.height).toBeGreaterThanOrEqual(38);
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(320.5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await tick.setChecked(true, { force: true });
  await expect(page.locator('#msgOrder')).toContainText('Follow-up');
  await expect(page.locator('#donorFollowUp')).toBeChecked(); // the Donors bar tick follows (hidden on phones)
  expect(await page.evaluate(() => localStorage.getItem('givelife-follow-up'))).toBe('1');
  await tick.setChecked(false, { force: true });
  await expect(page.locator('#msgOrder')).not.toContainText('Follow-up');
  expect(await page.evaluate(() => localStorage.getItem('givelife-follow-up'))).toBe('0');
});


test('phone: Also send / Text with / Order are one 40px row that opens above it, and the message keeps its height', async ({ page }) => {
  await api(port, '/group-extras', { action: 'add', kind: 'pdf', data: PDF, name: 'report.pdf' });
  await api(port, '/group-extras', { action: 'add', kind: 'video', data: MP4, name: 'clip.mp4' });
  await page.setViewportSize({ width: 369, height: 640 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/messages');
  const sum = page.locator('.bank-extras-sum');
  await expect(sum).toBeVisible();
  const box = await sum.boundingBox();
  expect(box.height).toBeLessThanOrEqual(44);
  await expect(page.locator('#msgPdf')).toBeHidden(); // closed: nothing but the row
  const card = await page.locator('.bank-detail').boundingBox();
  expect(card.height).toBeGreaterThan(300); // was 212px with the rows open
  await sum.click();
  await expect(page.locator('#msgPdf')).toBeVisible();
  await expect(page.locator('#msgOrder')).toBeVisible();
  await page.locator('#msgPdf').click({ force: true });
  await expect(sum).toContainText('PDF'); // the row says what is ticked
  await page.keyboard.press('Escape');
  await expect(page.locator('#msgPdf')).toBeHidden();
  await expect(sum).toHaveAttribute('aria-expanded', 'false');
});

test('phone: the whole message shows without scrolling inside its box', async ({ page }) => {
  const long = '*Mirha is only 2. Her life is at risk.*\n\nShe urgently needs 2 oxygen cylinders.\n\n' + 'Every single breath is hard for her and her family begs for help today.\n\n'.repeat(3) + 'Easypaisa ONLY\n03097458815\nWajdan Khan';
  await page.route('**/donor-messages', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    const r = await route.fetch();
    const d = await r.json();
    d.items = d.items.slice(0, 20).map((it) => ({ ...it, text: long }));
    d.generation = null;
    await route.fulfill({ response: r, json: d });
  });
  await page.setViewportSize({ width: 369, height: 640 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/messages');
  await expect(page.locator('.bank-preview')).toContainText('Easypaisa ONLY');
  await page.waitForTimeout(400);
  const r = await page.evaluate(() => {
    const card = document.querySelector('.bank-detail');
    return { over: card.scrollHeight - card.clientHeight, size: parseFloat(getComputedStyle(document.querySelector('.bank-preview')).fontSize) };
  });
  expect(r.over).toBeLessThanOrEqual(1);
  expect(r.size).toBeGreaterThanOrEqual(11);
  expect(r.size).toBeLessThanOrEqual(14);
});
