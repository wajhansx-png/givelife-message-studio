const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 213;
const headers = { Authorization: 'Bearer ' + KEY };
let server;
test.use({ baseURL: `http://127.0.0.1:${port}`, reducedMotion: 'reduce' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server && server.kill());

for (const width of [1440, 1024, 768, 390, 320]) {
  test(`volunteer case and share actions at ${width}px`, async ({ page, request }) => {
    const name = `Volunteer ${width}`;
    await request.post('/volunteers', {
      headers,
      data: { action: 'add', name, phone: `1555123${width.toString().padStart(4, '0')}` },
    });
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
    await page.goto('/#/donors/volunteers');
    await expect(page.locator('.vol-heading')).toContainText('Volunteers');
    await expect(page.locator('.donor-head')).toBeHidden();
    await expect(page.locator('.donor-bottom')).toBeHidden();
    await expect(page.getByRole('button', { name: 'Stop DMs', exact: true })).toBeHidden();
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
    const people = await page.locator('.vol-people').boundingBox();
    const message = await page.locator('.vol-msg').boundingBox();
    if (width >= 760) expect(message.x + message.width).toBeLessThanOrEqual(people.x);
    else expect(message.y + message.height).toBeLessThanOrEqual(people.y);

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
    // DM Share must ignore the case poster option, including its checked default.
    await expect(page.locator('#volPoster')).toBeChecked();
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
  await page.locator('#volPoster').check();
  const events = async () =>
    (await (await request.get('/__test/events', { headers })).json()).events;
  await page.getByRole('button', { name: 'DM Case to Sara', exact: true }).click();
  await expect.poll(async () => (await events()).length).toBe(1);
  expect((await events())[0].fields).toMatchObject({ phone: '15551239001', caption: caseText });
  expect((await events())[0].path).toContain('/send/image');
  await expect(page.locator('#volProgress')).toContainText('1 sent', { timeout: 10000 });
  await page.locator('#volMessage').fill('Please share this case, {name}.');
  await expect(page.locator('#volPoster')).toBeChecked();
  await page.getByRole('button', { name: 'DM Share to Sara', exact: true }).click();
  await expect.poll(async () => (await events()).length).toBe(2);
  expect((await events())[1].fields).toMatchObject({
    phone: '15551239001',
    message: 'Please share this case, Sara.',
  });
  expect((await events())[1].path).toContain('/send/message');
  expect((await events())[1].fields).not.toHaveProperty('image');
});

test('empty page, add volunteer and save a share message on a small phone', async ({
  page,
  request,
}) => {
  const data = await (await request.get('/volunteers', { headers })).json();
  for (const person of data.items) {
    await request.post('/volunteers', { headers, data: { action: 'delete', id: person.id } });
  }
  await page.setViewportSize({ width: 320, height: 700 });
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/#/donors/volunteers');
  await expect(page.getByText('No volunteers yet.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'DM all volunteers', exact: true })).toBeDisabled();
  await expect(page.locator('#volName')).toBeHidden();
  await page.locator('.vol-add-panel > summary').click();
  await page.getByLabel('Volunteer name', { exact: true }).fill('Muhammad Abdullah Khan');
  await page.getByLabel('Volunteer WhatsApp number').fill('15551239991');
  await page
    .locator('.vol-add')
    .getByRole('button', { name: '+ Add volunteer', exact: true })
    .click();
  await expect(page.locator('.vol-count')).toHaveText('1');
  await page.locator('.vol-add-panel > summary').click();
  await expect(page.locator('.vol-name')).toHaveText('1. Muhammad Abdullah Khan');
  await page.locator('#volPoster').uncheck();
  await page.locator('#volMessage').fill('Please share this update, {name}.');
  await expect(page.getByRole('button', { name: 'DM all volunteers', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Save message', exact: true }).click();
  await expect(page.locator('#volPoster')).not.toBeChecked();
  await page.reload();
  await expect(page.locator('#volMessage')).toHaveValue('Please share this update, {name}.');
  await expect(page.locator('.donor-bottom')).toBeHidden();
  await page.getByRole('button', { name: 'Back to main screen', exact: true }).click();
  await expect(page.locator('#donorsPage')).not.toBeVisible();
});

test('delivery refresh keeps the message draft, caret and case poster choice', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/#/donors/volunteers');
  await page.getByRole('button', { name: 'DM all volunteers', exact: true }).click();
  await page.getByLabel('Start sending', { exact: true }).selectOption('3600');
  await page.getByRole('button', { name: 'Schedule DMs', exact: true }).click();
  await expect(page.locator('#volProgress')).toContainText('Scheduled');
  await expect(page.getByRole('button', { name: 'DM all volunteers', exact: true })).toBeHidden();
  await expect(page.locator('.vol-row .vol-case').first()).toBeDisabled();
  await expect(page.locator('.vol-row .vol-share').first()).toBeDisabled();
  await page.locator('#volPoster').uncheck();
  await page.locator('#volMessage').fill('Keep this unsaved message and cursor.');
  await page.locator('#volMessage').evaluate((e) => e.setSelectionRange(7, 7));
  const oldField = await page.locator('#volMessage').elementHandle();
  await expect.poll(() => oldField.evaluate((e) => e.isConnected)).toBe(false);
  await expect(page.locator('#volMessage')).toBeFocused();
  await expect(page.locator('#volMessage')).toHaveValue('Keep this unsaved message and cursor.');
  expect(await page.locator('#volMessage').evaluate((e) => e.selectionStart)).toBe(7);
  await expect(page.locator('#volPoster')).not.toBeChecked();
  await page.getByRole('button', { name: 'Stop DMs', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Stop DMs', exact: true })).toBeHidden();
  await expect(page.getByRole('button', { name: 'DM all volunteers', exact: true })).toBeVisible();
});

test('long volunteer lists keep the message and dock reachable, with unclipped Manage actions', async ({
  page,
  request,
}) => {
  for (let i = 0; i < 36; i++) {
    await request.post('/volunteers', {
      headers,
      data: {
        action: 'add',
        name: `Directory volunteer ${String(i).padStart(2, '0')}`,
        phone: `15551234${String(i).padStart(3, '0')}`,
      },
    });
  }
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/#/donors/volunteers');
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 700 });
    const list = page.locator('.vol-list');
    await expect.poll(() => list.evaluate((e) => e.scrollHeight > e.clientHeight)).toBe(true);
    await page.locator('.vol-row').last().scrollIntoViewIfNeeded();
    const message = await page.locator('#volMessage').boundingBox();
    const dock = await page.locator('.vol-foot').boundingBox();
    expect(message.y).toBeGreaterThanOrEqual(0);
    expect(message.y + message.height).toBeLessThanOrEqual(dock.y);
    expect(dock.y + dock.height).toBeLessThanOrEqual(700);
    const last = page.locator('.vol-row').last();
    await last.getByRole('button', { name: /^Manage / }).click();
    const menu = page.locator('.vol-manage-menu:popover-open');
    await expect(menu.getByRole('button', { name: 'Rename', exact: true })).toBeVisible();
    const remove = menu.getByRole('button', { name: 'Remove', exact: true });
    const box = await remove.boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(700);
    expect(
      await remove.evaluate((e) => {
        const r = e.getBoundingClientRect();
        return e.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
      }),
    ).toBe(true);
    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  }
});

test('phone keyboard leaves the message and shared dock usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/#/donors/volunteers');
  await page.locator('#volMessage').fill('An unsaved share request while the keyboard is open.');
  await page.setViewportSize({ width: 390, height: 360 });
  await expect(page.locator('#volMessage')).toBeFocused();
  const message = await page.locator('#volMessage').boundingBox();
  const dock = await page.locator('.vol-foot').boundingBox();
  expect(message.y + message.height).toBeLessThanOrEqual(dock.y);
  expect(dock.y + dock.height).toBeLessThanOrEqual(360);
  await page.getByRole('button', { name: 'Save message', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save message', exact: true })).toBeDisabled();
});
