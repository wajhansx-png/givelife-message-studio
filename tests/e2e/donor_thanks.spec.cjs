const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 241;
const headers = { Authorization: 'Bearer ' + KEY };
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
for (const width of [1440, 768, 390, 320, 280]) {
  test(`Thank donors composer and attached caption at ${width}px`, async ({ page, request }) => {
    const added = await (
      await request.post('/donors', {
        headers,
        data: {
          action: 'add',
          name: 'Supporter ' + width,
          phone: '1555123' + String(width).padStart(4, '0'),
        },
      })
    ).json();
    expect(added.donor).toBeTruthy();
    await request.post('/donors', {
      headers,
      data: { action: 'update', id: added.donor.id, donated: true },
    });
    await request.post('/left', { headers, data: { left: 0 } });
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/donors/donated');
    const button = page.getByRole('button', { name: 'Thank donors', exact: true });
    await expect(button).toBeVisible();
    const box = await button.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    await button.click();
    await expect(page.getByRole('dialog', { name: 'Thank donors', exact: true })).toBeVisible();
    const dialog = await page.locator('#donorThanksDialog').boundingBox();
    expect(dialog.width).toBeLessThanOrEqual(Math.min(width - 16, 680));
    await expect(page.locator('#thanksPreview')).not.toBeVisible();
    await expect(page.locator('#thanksGap')).not.toBeVisible();
    await page.locator('#thanksFile').setInputFiles({
      name: 'proof.png',
      mimeType: 'image/png',
      buffer: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII=',
        'base64',
      ),
    });
    await expect(page.locator('#thanksStatus')).toContainText('Media ready');
    await page.getByLabel('Caption', { exact: true }).fill('Alhamdulillah, the case is complete.');
    await page
      .locator('#donorThanksDialog')
      .getByLabel('Message', { exact: true })
      .fill('JazakAllah khair, {name}.');
    await page.locator('.thanks-review > summary').click();
    await expect(page.locator('#thanksPreview .thanks-bubble')).toHaveCount(2);
    await expect(page.locator('#thanksPreview')).toContainText(
      'Alhamdulillah, the case is complete.',
    );
    await expect(page.locator('#thanksPreview')).toContainText('JazakAllah khair, {name}.');
    // Timing is one short line with three quick speeds; the exact numbers sit under Custom.
    await expect(page.locator('#thanksPace')).toContainText(' apart');
    await page.locator('[data-preset="fast"]').click();
    await expect(page.locator('#thanksPace')).toHaveText('30 sec apart ±10s · batches of 20');
    await page.locator('[data-preset="normal"]').click();
    await page.locator('.thanks-custom > summary').click();
    await expect(page.locator('#thanksGap')).toHaveValue('5');
    await expect(page.locator('#thanksGapSec')).toHaveValue('0');
    await expect(page.locator('#thanksBatch')).toHaveValue('10');
    await expect(page.locator('#thanksRest')).toHaveValue('20');
    await page.locator('#thanksGapSec').fill('30');
    await expect(page.locator('#thanksPace')).toContainText('5 min 30 sec apart');
    await page.locator('#thanksGapSec').fill('0');
    // Test: the update goes to the GiveLife test group only, never to a donor.
    const beforeTest = (await (await request.get('/__test/events', { headers })).json()).events.length;
    await page.locator('#thanksTest').click();
    await expect(page.locator('#thanksStatus')).toContainText('Test sent to the GiveLife test group');
    const testEvents = (await (await request.get('/__test/events', { headers })).json()).events.slice(beforeTest);
    expect(testEvents).toHaveLength(2);
    for (const e of testEvents) expect(e.fields.phone).toBe('120363431210327603@g.us');
    expect(testEvents[0].path).toContain('/send/image');
    expect(testEvents[1].fields.message).toBe('JazakAllah khair, Test.');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.locator('#thanksStatus')).toContainText('Update saved');
    await page.getByRole('button', { name: 'Close Thank donors', exact: true }).click();
    await button.click();
    await expect(page.getByLabel('Caption', { exact: true })).toHaveValue(
      'Alhamdulillah, the case is complete.',
    );
    const before = (await (await request.get('/__test/events', { headers })).json()).events.length;
    await page.locator('#thanksSend').click();
    await expect
      .poll(
        async () => (await (await request.get('/__test/events', { headers })).json()).events.length,
      )
      .toBe(before + 2);
    const events = (await (await request.get('/__test/events', { headers })).json()).events.slice(
      before,
    );
    expect(events[0].path).toContain('/send/image');
    expect(events[0].fields.caption).toBe('Alhamdulillah, the case is complete.');
    expect(events[1].path).toContain('/send/message');
    expect(events[1].fields.message).toBe('JazakAllah khair, Supporter.');
    expect(events[0].fields.phone).toBe('1555123' + String(width).padStart(4, '0'));
    await expect
      .poll(async () => {
        const status = await (await request.get('/donor-thanks', { headers })).json();
        return status.recipients.find((r) => r.id === added.donor.id).state;
      })
      .toBe('Sent');
    await expect(page.locator('#donorThanksDialog')).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
}

test('Report exposes editable 5/10/20 Thanks donors pacing and endpoints require authentication', async ({
  page,
  request,
}) => {
  expect((await request.get('/donor-thanks')).status()).toBe(401);
  expect((await request.post('/donor-thanks', { data: { action: 'start' } })).status()).toBe(401);
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  await page.evaluate(() => document.querySelector('.report-open').click());
  const card = page.locator('.auto-card[data-control="thanks"]');
  await expect(card.getByRole('switch', { name: 'Thanks donors', exact: true })).toBeVisible();
  await card.locator('h4').click();
  await expect(card.locator('[name=gap_minutes]')).toHaveValue('5');
  await expect(card.locator('[name=batch_size]')).toHaveValue('10');
  await expect(card.locator('[name=rest_minutes]')).toHaveValue('20');
  await card.locator('[name=gap_minutes]').fill('6');
  await card.getByRole('button', { name: 'Save', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get('/donor-thanks', { headers })).json()).settings.gap_minutes,
    )
    .toBe(6);
});

for (const [mime, caption, suffix] of [
  ['video/mp4', 'Alhamdulillah, case completed.', '01'],
  ['video/mp4', '', '02'],
  ['application/pdf', 'Completion receipt.', '03'],
]) {
  test(`${mime} sends as one attachment ${caption ? 'with its caption' : 'without a caption'}`, async ({
    request,
  }) => {
    const phone = '155512398' + suffix;
    const added = await (
      await request.post('/donors', {
        headers,
        data: { action: 'add', name: 'Media supporter ' + suffix, phone },
      })
    ).json();
    await request.post('/donors', {
      headers,
      data: { action: 'update', id: added.donor.id, donated: true },
    });
    await request.post('/left', { headers, data: { left: 0 } });
    const raw =
      mime === 'video/mp4'
        ? Buffer.from([0, 0, 0, 20, ...Buffer.from('ftypisom0000')])
        : Buffer.from('%PDF-1.4\ncompletion');
    const upload = await (
      await request.post('/upload-image', {
        headers,
        data: { use: 'bulk', data: 'data:' + mime + ';base64,' + raw.toString('base64') },
      })
    ).json();
    let view = await (await request.get('/donor-thanks', { headers })).json();
    // The previous UI test edited its gap; changing media must not change timing.
    const saved = await request.post('/donor-thanks', {
      headers,
      data: {
        action: 'save',
        case_id: view.case_id,
        revision: view.revision,
        caption,
        message: '',
        attachment: upload.id,
        filename: 'Completion proof',
      },
    });
    expect(saved.ok()).toBe(true);
    view = await saved.json();
    const before = (await (await request.get('/__test/events', { headers })).json()).events.length;
    const start = await request.post('/donor-thanks', {
      headers,
      data: { action: 'start', case_id: view.case_id, revision: view.revision },
    });
    expect(start.ok()).toBe(true);
    await expect
      .poll(
        async () => (await (await request.get('/__test/events', { headers })).json()).events.length,
      )
      .toBe(before + 1);
    const event = (await (await request.get('/__test/events', { headers })).json()).events[before];
    expect(event.path).toContain(mime === 'video/mp4' ? '/send/video' : '/send/file');
    expect(event.fields.phone).toBe(phone);
    if (caption) expect(event.fields.caption).toBe(caption);
    else expect(event.fields.caption || '').toBe('');
  });
}
