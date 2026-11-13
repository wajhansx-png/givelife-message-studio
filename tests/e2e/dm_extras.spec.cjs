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

async function openMsgs(page, width = 390) {
  await page.setViewportSize({ width, height: 800 });
  await page.addInitScript((k) => {
    localStorage.setItem('givelife-cloud-key', k);
  }, KEY);
  await page.goto('/new#/donors/messages');
  await expect(page.locator('#donorsPage')).toBeVisible();
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
  await page.locator('#msgPdf').check({ force: true });
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
  await page.locator('#msgPdf').check({ force: true });
  await page.locator('#msgVideo').check({ force: true });
  await expect(page.locator('#msgPdf')).toBeChecked();
  await expect(page.locator('#msgVideo')).toBeChecked();
  // the same two ticks live in the Donors bar (All tab) and in the DM batch picker
  await page.evaluate(() => Nav.go('donors/all'));
  await expect(page.locator('#donorPdf')).toBeChecked();
  await expect(page.locator('#donorVideo')).toBeChecked();
  await page.locator('#donorPace').evaluate((b) => b.click()); // opens the batch picker (the button can sit in a menu)
  await page.locator('#donorBatchPicker summary', { hasText: 'More options' }).click(); // Poster / Follow-up / PDF / Video live here
  await expect(page.locator('#batchPdf')).toBeVisible();
  await expect(page.locator('#batchPdf')).toBeChecked();
  await expect(page.locator('#batchVideo')).toBeChecked();
  // untick the PDF in the picker: only the video goes, and the Donors bar follows
  await page.locator('#batchPdf').uncheck({ force: true });
  await expect(page.locator('#batchPdf')).not.toBeChecked();
  await expect(page.locator('#batchVideo')).toBeChecked();
  await expect(page.locator('#donorPdf')).not.toBeChecked();
  await expect(page.locator('#donorVideo')).toBeChecked();
  await page.locator('#batchCancel').click();
  expect(await page.evaluate(() => [localStorage.getItem('givelife-dm-pdf'), localStorage.getItem('givelife-dm-video')])).toEqual(['0', '1']);
  // survives a reload; the Msgs tab shows the same
  await page.evaluate(() => Nav.go('donors/messages'));
  await page.reload();
  await expect(page.locator('#msgPdf')).toBeVisible();
  await expect(page.locator('#msgPdf')).not.toBeChecked();
  await expect(page.locator('#msgVideo')).toBeChecked();
  // none
  await page.locator('#msgVideo').uncheck({ force: true });
  await expect(page.locator('#msgVideo')).not.toBeChecked();
});

test('removing a saved file unticks it the next time Donors opens (a new case starts with none)', async ({ page }) => {
  await openMsgs(page);
  await page.locator('#msgPdf').check({ force: true });
  await expect(page.locator('#msgPdf')).toBeChecked();
  await api(port, '/group-extras', { action: 'remove', kind: 'pdf' });
  await page.reload();
  await expect(page.locator('#donorsPage')).toBeVisible();
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
