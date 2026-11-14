/* /giki: the Volunteers screen for the Giki list, its own WhatsApp (connect), Add many, Timer, DM Case. Fake WhatsApp only. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 531;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
test.describe.configure({ mode: 'serial' });

const PDF =
  'data:application/pdf;base64,' +
  Buffer.concat([Buffer.from('%PDF-1.4\n'), Buffer.alloc(300, 120)]).toString('base64');
const MP4 =
  'data:video/mp4;base64,' +
  Buffer.concat([Buffer.from([0, 0, 0, 24]), Buffer.from('ftypmp42'), Buffer.alloc(300)]).toString(
    'base64',
  );
const LIST = [
  '# Giki numbers',
  'Sources: a note, not a person +1 555 000 0000',
  '',
  '| # | Name | Number | Found on |',
  '|---:|------|--------|----------|',
  '| 1 | . Giki Donor 4 | +1 555 123 0001 | x |',
  '| 2 | Ali Donor Giki | +1 555 123 0002 | x |',
  '| 3 | Sara Giki | +1 555 123 0003 | x |',
].join('\n');

async function open(page, width = 390, height = 800) {
  await page.setViewportSize({ width, height });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on(
    'console',
    (m) =>
      m.type() === 'error' &&
      !/favicon|Failed to load resource/.test(m.text()) &&
      errors.push(m.text()),
  );
  await page.goto('/giki');
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page.locator('#donorVolunteers .vol-workspace')).toBeVisible();
  return errors;
}
async function writeShare(page, text) {
  await page.locator('.giki-edit').click();
  await expect(page.locator('#gikiSheet')).toBeVisible();
  await page.locator('#gikiSheet textarea').fill(text);
  await page.locator('#csFoot').getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('#gikiSheet')).toBeHidden();
  await expect(page.locator('.giki-share-line')).toContainText(text.slice(0, 18));
}
const events = async () => (await api(port, '/__test/events')).events;
const gikiSends = async () => (await events()).filter((e) => (e.device || '').startsWith('giki-'));
async function link() {
  await api(port, '/giki/wa', { action: 'code', phone: '0300 1234567' });
  await expect
    .poll(async () => (await api(port, '/giki/wa')).line.state, { timeout: 15000 })
    .toBe('ready');
}

test('/giki opens on the Giki list: no donor tabs, no main app, no errors', async ({ page }) => {
  const errors = await open(page);
  expect(new URL(page.url()).hash).toBe('#/donors/volunteers');
  await expect(page.locator('.giki-title')).toHaveText('Giki');
  await expect(page.locator('#donorsPage .donor-tabs')).toBeHidden();
  await expect(page.locator('#donorsPage .donor-head')).toBeHidden();
  await expect(
    page.locator('#donorsPage .vol-foot > .ui2-msgs-bottom:not(.giki-timer)'),
  ).toBeHidden();
  await expect(page.locator('.giki-timer')).toBeVisible();
  await expect(page.locator('#gikiWa')).toContainText('Connect WhatsApp');
  // the big message box is hidden: one short line with Write / Test stands in for it
  await expect(page.locator('#volMessage')).toBeHidden();
  await expect(page.locator('.vol-msg-heading')).toBeHidden();
  await expect(page.locator('.giki-share')).toBeVisible();
  await expect(page.locator('.giki-share-line')).toHaveText('Not written yet');
  await expect(page.locator('.giki-edit')).toHaveText('Write');
  await expect(page.locator('.giki-test')).toBeVisible();
  expect(errors).toEqual([]);
});

test('the main link and /old are not changed', async ({ page, request }) => {
  const home = await (await request.get('/')).text();
  expect(home).not.toContain('GIKI_LINE');
  expect(home).not.toContain('giki.js');
  expect(await (await request.get('/old')).text()).not.toContain('giki.js');
  expect(await (await request.get('/giki')).text()).toContain('giki.js');
});

test('Giki DMs are refused until the Giki WhatsApp is connected, and the main WhatsApp is not used', async ({
  page,
}) => {
  await api(port, '/giki/volunteers', { action: 'add', name: 'Early Bird', phone: '15551239999' });
  await api(port, '/giki/volunteers', { action: 'message', text: 'Salam {name}' });
  const before = (await events()).length;
  const r = await api(port, '/giki/volunteers', {
    action: 'send_one',
    id: (await api(port, '/giki/volunteers')).items[0].id,
    request_id: 'req-early-0001',
  });
  expect(String(r.error || '')).toMatch(/disconnected|link/i);
  expect((await events()).length).toBe(before);
  const gone = (await api(port, '/giki/volunteers')).items[0];
  await api(port, '/giki/volunteers', { action: 'delete', id: gone.id });
});

test('connect: a code is shown, then the page says connected', async ({ page }) => {
  await open(page);
  await page.locator('#gikiWa').click();
  await expect(page.locator('#gikiSheet')).toBeVisible();
  await expect(page.locator('.gk-state')).toContainText('Not connected');
  await page.locator('#gikiPhone').fill('abc');
  await page.getByRole('button', { name: 'Get code' }).click();
  await expect(page.locator('#csError')).toContainText('country code');
  await page.locator('#gikiPhone').fill('0300 1234567');
  await page.getByRole('button', { name: 'Get code' }).click();
  await expect(page.locator('.gk-code')).toHaveText('ABCD-EFGH');
  await expect(page.locator('.gk-steps li')).toHaveCount(4);
  await expect(page.locator('.gk-state')).toContainText('Connected', { timeout: 15000 });
  await expect(page.locator('#gikiWa')).toContainText('…8888');
  await expect(page.locator('#gikiWa')).toHaveAttribute('data-ok', '1');
  await page.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  await expect(page.locator('#gikiSheet')).toBeHidden();
});

test('QR code can be shown too, and Disconnect needs a confirmation', async ({ page }) => {
  await open(page);
  await expect(page.locator('#gikiWa')).toHaveAttribute('data-ok', '1'); // linked by the test before
  page.once('dialog', (d) => d.dismiss());
  await page.locator('#gikiWa').click();
  await page.locator('#csFoot').getByRole('button', { name: 'Disconnect' }).click();
  await expect(page.locator('.gk-state')).toContainText('Connected'); // cancelled: still connected
  page.once('dialog', (d) => d.accept());
  await page.locator('#csFoot').getByRole('button', { name: 'Disconnect' }).click();
  await expect(page.locator('.gk-state')).toContainText('Not connected yet');
  await page.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  await expect(page.locator('#gikiWa')).toContainText('Connect WhatsApp');
  await page.locator('#gikiWa').click();
  await page.getByRole('button', { name: 'QR code' }).click();
  await page.getByRole('button', { name: 'Show QR code' }).click();
  await expect(page.locator('.gk-qr')).toBeVisible();
});

test('Add many: check first, then add; names are kept and nobody is added twice', async ({
  page,
}) => {
  await open(page);
  await page.locator('.vol-add-panel > summary').click();
  await page.locator('.giki-many').click();
  await page
    .locator('#gikiSheet input[type=file]')
    .setInputFiles({ name: 'giki.md', mimeType: 'text/markdown', buffer: Buffer.from(LIST) });
  await page.locator('#csFoot').getByRole('button', { name: 'Check list' }).click();
  await expect(page.locator('#csBody')).toContainText('3 found · 3 new');
  expect((await api(port, '/giki/volunteers')).items).toHaveLength(0); // a check adds nothing
  await page.locator('#csFoot').getByRole('button', { name: 'Add 3 numbers' }).click();
  await expect(page.locator('.vol-row')).toHaveCount(3);
  await expect(page.locator('.vol-name')).toContainText([
    'Ali Donor Giki',
    'Giki Donor 4',
    'Sara Giki',
  ]);
  await expect(page.locator('#donorNotice')).toContainText('3 new numbers added');
  // the same list again: nothing new (the Add panel stays open after a change)
  if (!(await page.locator('.vol-add-panel').evaluate((d) => d.open)))
    await page.locator('.vol-add-panel > summary').click();
  await page.locator('.giki-many').click();
  await page.locator('#gikiSheet textarea').fill(LIST);
  await page.locator('#csFoot').getByRole('button', { name: 'Check list' }).click();
  await expect(page.locator('#csBody')).toContainText('0 new · 3 already in the list');
  await page.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  expect((await api(port, '/giki/volunteers')).items).toHaveLength(3);
  expect((await api(port, '/volunteers')).items).toHaveLength(0); // the main volunteers are untouched
});

test('Timer: the same sheet as the Case page, saved and used by DM all', async ({ page }) => {
  await open(page);
  await page.locator('.giki-timer').click();
  const sheet = page.locator('#gikiSheet');
  await expect(sheet.locator('h2')).toHaveText('Giki');
  await expect(sheet.getByRole('button', { name: 'Message', exact: true })).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Settings' })).toBeVisible();
  await expect(sheet.locator('.cr-set-row > span:first-child')).toHaveText([
    'Case goes with',
    '2nd message',
    '3rd message',
    'Minutes between DMs',
    'DMs per batch',
    'Rest between batches',
    'People',
  ]);
  const values = async () => sheet.locator('.cr-num').evaluateAll((l) => l.map((i) => i.value));
  expect(await values()).toEqual(['5', '10', '20']);
  // the same Text goes with setting as Poster on the main page (one setting for groups and DMs)
  await expect(sheet.getByRole('button', { name: 'Case goes with the video' })).toHaveAttribute(
    'data-on',
    '1',
  );
  await sheet.getByRole('button', { name: 'Case goes with the poster' }).click();
  await expect(sheet.getByRole('button', { name: 'Case goes with the poster' })).toHaveAttribute(
    'data-on',
    '1',
  );
  // the Giki page keeps its own choice: the groups' setting does not change
  const giki = async () => (await api(port, '/group-extras')).setup.giki;
  expect((await giki()).text_on).toBe('poster');
  expect((await api(port, '/group-extras')).text_on).toBe('video');
  await sheet.getByRole('button', { name: 'Case goes with the video' }).click();
  await expect.poll(async () => (await giki()).text_on).toBe('video');
  // Also send: Poster (the after poster) and PDF need their file first; Video only when the poster carries the text
  // 2nd / 3rd messages: Poster pic first by default; ticks wait for the files to be added on the group message
  await expect(sheet.getByRole('button', { name: '2nd message: Poster pic' })).toHaveAttribute(
    'data-on',
    '1',
  );
  await expect(sheet.locator('.gk-name3')).toHaveText('PDF');
  // what is picked is clearly blue
  const blue = (name) =>
    sheet.getByRole('button', { name }).evaluate((b) => getComputedStyle(b).backgroundColor);
  expect(await blue('2nd message: Poster pic')).toBe('rgb(47, 111, 228)');
  expect(await blue('2nd message: PDF')).not.toBe('rgb(47, 111, 228)');
  await expect(sheet.locator('#gikiTick-2')).toBeDisabled();
  await expect(sheet.locator('#gikiTick-3')).toBeDisabled();
  await sheet.getByRole('button', { name: '2nd message: PDF' }).click();
  await expect(sheet.locator('.gk-name3')).toHaveText('Poster pic');
  await expect.poll(async () => (await giki()).order).toBe('pdf_poster');
  await sheet.getByRole('button', { name: '2nd message: Poster pic' }).click();
  await expect.poll(async () => (await giki()).order).toBe('poster_pdf');
  await expect(sheet.locator('#gikiTick-video')).toHaveCount(0); // no extra things
  await expect(sheet.locator('.cr-set-link .cr-set-val')).toHaveText('3');
  await sheet.getByRole('button', { name: 'More: Minutes between DMs' }).click();
  await sheet.getByRole('button', { name: 'Less: DMs per batch' }).click();
  await sheet.getByRole('button', { name: 'More: Rest between batches' }).click();
  expect(await values()).toEqual(['6', '9', '25']);
  // limits are the Case page limits
  for (let i = 0; i < 15; i++)
    await sheet.getByRole('button', { name: 'More: Minutes between DMs' }).click();
  expect((await values())[0]).toBe('10');
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet).toBeHidden();
  await expect(page.locator('#donorNotice')).toContainText('Timer saved');
  expect((await api(port, '/giki/volunteers')).pace).toEqual({
    gap_minutes: 10,
    batch_size: 9,
    rest_minutes: 25,
  });
  await page.locator('.giki-timer').click();
  await expect.poll(values).toEqual(['10', '9', '25']);
  await sheet.getByRole('button', { name: 'People' }).click();
  await expect(sheet.locator('.cr-names')).toContainText('Sara Giki');
  await sheet.getByRole('button', { name: 'Back to settings' }).click();
  await sheet.getByRole('button', { name: 'Message', exact: true }).click();
  await expect(sheet.locator('.cr-block')).toContainText('Salam {name}'); // saved by the earlier test
  await sheet.getByRole('button', { name: 'Close' }).click();
  // the server refuses a value outside the range
  expect(
    String((await api(port, '/giki/volunteers', { action: 'pace', gap_minutes: 11 })).error),
  ).toContain('Minutes between DMs');
  expect((await api(port, '/giki/volunteers')).pace.gap_minutes).toBe(10);
});

test('DM Case sends the Group msgs text with the poster from the Giki WhatsApp, and the PDF / video only when they are on', async ({
  page,
}) => {
  await link();
  await api(port, '/focus-bank', {
    kind: 'group',
    text: 'GIKITEST case caption. Rs. 25,000 left.',
  });
  await api(port, '/giki/volunteers', { action: 'message', text: 'Different volunteer text' });
  await open(page);
  const ask = async (name) => {
    const before = (await gikiSends()).length;
    await page
      .locator('.vol-row', { hasText: name })
      .getByRole('button', { name: /^DM Case/ })
      .click();
    return before;
  };
  // 1. both off: poster + caption only
  let before = await ask('Sara Giki');
  await expect.poll(async () => (await gikiSends()).length, { timeout: 20000 }).toBe(before + 1);
  let sent = (await gikiSends()).slice(before);
  expect(sent[0].path).toBe('/send/image');
  expect(sent[0].fields.caption).toContain('GIKITEST case caption');
  expect(sent[0].fields.caption).not.toContain('Different volunteer text');
  expect(sent[0].fields.phone).toContain('15551230003');
  // 2. PDF + video saved (on the group message), PDF ticked on the Giki page: video with the text, poster, PDF
  await api(port, '/group-extras', { action: 'add', kind: 'pdf', data: PDF, name: 'report.pdf' });
  await api(port, '/group-extras', { action: 'add', kind: 'video', data: MP4, name: 'clip.mp4' });
  const giki = (field, value) =>
    api(port, '/group-extras', { action: 'setup', profile: 'giki', field, value });
  await giki('pdf', true);
  await page.waitForTimeout(500);
  before = await ask('Ali Donor');
  await expect.poll(async () => (await gikiSends()).length, { timeout: 30000 }).toBe(before + 2);
  sent = (await gikiSends()).slice(before);
  // text goes with the video (the default): the video with the case text, then the PDF (no after poster ticked)
  expect(sent.map((e) => e.path)).toEqual(['/send/video', '/send/file']);
  expect(sent[0].fields.caption).toContain('GIKITEST case caption');
  // 3. Giki text on the poster (video not ticked): the poster with the text, then the PDF
  await giki('text_on', 'poster');
  before = await ask('Giki Donor 4');
  await expect.poll(async () => (await gikiSends()).length, { timeout: 30000 }).toBe(before + 2);
  expect((await gikiSends()).slice(before).map((e) => e.path)).toEqual([
    '/send/image',
    '/send/file',
  ]);
  // the caption follows the case at the next click
  await api(port, '/focus-bank', {
    kind: 'group',
    text: 'GIKITEST second caption. Rs. 25,000 left.',
  });
  await giki('pdf', false);
  await api(port, '/giki/volunteers', {
    action: 'add',
    name: 'Fourth Person',
    phone: '15551230004',
  });
  await page.reload();
  await expect(page.locator('.vol-row')).toHaveCount(4);
  before = await ask('Fourth Person');
  await expect.poll(async () => (await gikiSends()).length, { timeout: 20000 }).toBe(before + 1);
  sent = (await gikiSends()).slice(before);
  expect(sent[0].fields.caption).toContain('GIKITEST second caption');
  // nothing went out of the main WhatsApp
  expect(
    (await events()).filter((e) => !e.device && /15551230/.test(JSON.stringify(e.fields))),
  ).toEqual([]);
});

test('Test sends the case, the PDF that is on, then the share message to my own WhatsApp from the Giki WhatsApp', async ({
  page,
}) => {
  await api(port, '/group-extras', { action: 'setup', profile: 'giki', field: 'pdf', value: true });
  await api(port, '/giki/volunteers', { action: 'message', text: '' });
  await open(page);
  // no share message written yet: the case (and its PDF) is still sent, and the notice says what was left out
  let before = (await gikiSends()).length;
  await page.locator('.giki-test').click();
  await expect(page.locator('#donorNotice')).toContainText('only the case was sent', {
    timeout: 30000,
  });
  expect((await gikiSends()).slice(before).map((e) => e.path)).toEqual([
    '/send/image',
    '/send/file',
  ]);
  before = (await gikiSends()).length;
  await writeShare(page, 'Test share for {name}');
  await page.locator('.giki-test').click();
  await expect(page.locator('#donorNotice')).toContainText('Test sent to your WhatsApp', {
    timeout: 30000,
  });
  const sent = (await gikiSends()).slice(before);
  expect(sent.map((e) => e.path)).toEqual(['/send/image', '/send/file', '/send/message']);
  expect(sent[0].fields.caption).toMatch(/^🧪 TEST DM/);
  expect(sent[0].fields.caption).toContain('GIKITEST second caption');
  expect(sent[2].fields.message).toContain('Test share for Test');
  expect(sent.every((e) => String(e.fields.phone).startsWith('923205069925'))).toBe(true); // my own number, nobody in the list
  expect((await api(port, '/giki/volunteers')).items.every((x) => x.delivery !== 'Sending')).toBe(
    true,
  );
});

test('DM all: each person gets the case first, then the share message; people already messaged are skipped', async ({
  page,
}) => {
  await api(port, '/giki/volunteers', {
    action: 'add',
    name: 'Fifth Person',
    phone: '15551230005',
  });
  await open(page);
  await expect(page.locator('.vol-row')).toHaveCount(5);
  await writeShare(page, 'Share message for {name}, please share.');
  await expect(page.locator('.giki-edit')).toHaveText('Edit');
  await expect(page.locator('.vol-foot .send-donors')).toHaveText('DM all (1)'); // four were messaged by DM Case
  await page.getByRole('button', { name: /^DM all/ }).click();
  await expect(page.locator('#volTimingTitle')).toHaveText('DM all Giki');
  await expect(page.locator('#volTimingAudience')).toContainText('The case goes first');
  await expect(page.locator('#volTimingAudience')).toContainText(
    '1 person is waiting (4 already messaged for this case)',
  );
  await expect(page.locator('#volTimingPlan')).toContainText(
    'One person every 10 minutes, 9 per batch, with 25 minutes rest',
  );
  const before = (await gikiSends()).length;
  await page.locator('#volTimingStart').click();
  await expect.poll(async () => (await gikiSends()).length, { timeout: 40000 }).toBe(before + 3);
  const sent = (await gikiSends()).slice(before);
  expect(sent.map((e) => e.path)).toEqual(['/send/image', '/send/file', '/send/message']); // case, the PDF that is on, share
  expect(sent[0].fields.caption).toContain('GIKITEST second caption');
  expect(sent[0].fields.caption).not.toContain('Share message for');
  expect(sent[2].fields.message).toBe('Share message for Fifth, please share.');
  expect(sent.every((e) => String(e.fields.phone).startsWith('15551230005'))).toBe(true);
  await expect.poll(async () => (await api(port, '/giki/volunteers')).waiting).toBe(0);
  await page.reload();
  await expect(page.locator('.vol-foot .send-donors')).toHaveText('DM all (0)');
  await expect(page.locator('.vol-foot .send-donors')).toBeDisabled();
});

for (const width of [320, 360, 390, 768, 1280]) {
  test(`fits at ${width}px: bar, sheets and bottom row`, async ({ page }) => {
    const errors = await open(page, width, width < 700 ? 700 : 800);
    const fit = () =>
      page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        out: [...document.querySelectorAll('.giki-bar *, .vol-foot *, #gikiSheet[open] *')]
          .filter((n) => n.offsetParent && n.getBoundingClientRect().width > 0)
          .filter((n) => n.tagName === 'SUMMARY' || !n.closest('details:not([open])')) // a closed panel is not on screen
          .filter((n) => {
            const r = n.getBoundingClientRect();
            return r.left < -1 || r.right > innerWidth + 1;
          })
          .map((n) => n.className || n.tagName)
          .slice(0, 5),
      }));
    expect(await fit()).toEqual({ scroll: 0, out: [] });
    for (const target of ['#gikiWa', '.giki-timer']) {
      await page.locator(target).click();
      await expect(page.locator('#gikiSheet')).toBeVisible();
      await page.waitForTimeout(400); // the sheet rises for 0.2 s: measure it once it has stopped
      expect(await fit()).toEqual({ scroll: 0, out: [] });
      const box = await page.locator('#gikiSheet').boundingBox();
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.y + box.height).toBeLessThanOrEqual((await page.viewportSize()).height + 1);
      await page.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
    }
    // the bottom row: every button is 40px or more high, none overlaps another
    const buttons = await page
      .locator('.vol-foot > :is(button, details > summary), .vol-foot > details > summary')
      .evaluateAll((l) =>
        l.filter((n) => n.offsetParent).map((n) => n.getBoundingClientRect().toJSON()),
      );
    for (const b of buttons) expect(b.height).toBeGreaterThanOrEqual(40);
    const sorted = [...buttons].sort((a, b) => a.left - b.left);
    for (let i = 1; i < sorted.length; i++)
      expect(sorted[i].left).toBeGreaterThanOrEqual(sorted[i - 1].right - 1);
    expect(errors).toEqual([]);
  });
}
