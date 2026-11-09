const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 213;
const headers = { Authorization: 'Bearer ' + KEY };
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server && server.kill());

for (const width of [1440, 390, 320]) {
  test(`volunteer case and share actions at ${width}px`, async ({ page, request }) => {
    const name = `Volunteer ${width}`;
    await request.post('/volunteers', {
      headers,
      data: { action: 'add', name, phone: `1555123${width.toString().padStart(4, '0')}` },
    });
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
    await page.goto('/#/donors/volunteers');
    const row = page.locator('.vol-row').filter({ hasText: name });
    const caseButton = row.getByRole('button', { name: `DM Case to ${name}`, exact: true });
    const shareButton = row.getByRole('button', { name: `DM Share to ${name}`, exact: true });
    await expect(caseButton).toHaveText('DM Case');
    await expect(shareButton).toHaveText('DM Share');
    const boxes = await Promise.all(
      [row.locator('.vol-name'), caseButton, shareButton].map((l) => l.boundingBox()),
    );
    expect(boxes[0].x + boxes[0].width).toBeLessThanOrEqual(boxes[1].x);
    expect(boxes[1].x + boxes[1].width).toBeLessThanOrEqual(boxes[2].x);
    expect(boxes[2].x + boxes[2].width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );

    const actions = [];
    await page.route('**/volunteers', async (route) => {
      const body = route.request().method() === 'POST' && route.request().postDataJSON();
      if (body && ['send_one', 'send_case'].includes(body.action)) {
        actions.push(body);
        return route.fulfill({ json: { job: { state: 'Starting' } } });
      }
      return route.continue();
    });
    await page.locator('#volMessage').fill('');
    await shareButton.click();
    await expect(page.locator('#volMessage')).toBeFocused();
    expect(actions).toHaveLength(0);
    await caseButton.click();
    await expect.poll(() => actions.length).toBe(1);
    expect(actions[0].action).toBe('send_case');
    await page.locator('#volMessage').fill('A new unsaved sharing request.');
    await page.locator('#volPoster').uncheck();
    await shareButton.click();
    await expect.poll(() => actions.length).toBe(2);
    expect(actions[1]).toMatchObject({
      action: 'send_one',
      id: actions[0].id,
      text: 'A new unsaved sharing request.',
      poster: false,
    });
    expect(actions[1].request_id).not.toBe(actions[0].request_id);
  });
}

test('case and unsaved share text reach only the selected volunteer through fake WhatsApp', async ({
  page,
  request,
}) => {
  const name = 'Sara';
  await request.post('/volunteers', {
    headers,
    data: { action: 'add', name, phone: '15551239001' },
  });
  const caseText = '*Current case*\n\nRs. 25,000 left.';
  await request.post('/__test/seed', { headers, data: { group: caseText } });
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/#/donors/volunteers');
  await page.locator('#volPoster').uncheck();
  const events = async () =>
    (await (await request.get('/__test/events', { headers })).json()).events;
  await page.getByRole('button', { name: 'DM Case to Sara', exact: true }).click();
  await expect.poll(async () => (await events()).length).toBe(1);
  expect((await events())[0].fields).toMatchObject({ phone: '15551239001', message: caseText });
  await expect(page.locator('#volProgress')).toContainText('1 sent');
  await page.locator('#volMessage').fill('Please share this case, {name}.');
  await page.locator('#volPoster').uncheck();
  await page.getByRole('button', { name: 'DM Share to Sara', exact: true }).click();
  await expect.poll(async () => (await events()).length).toBe(2);
  expect((await events())[1].fields).toMatchObject({
    phone: '15551239001',
    message: 'Please share this case, Sara.',
  });
});
