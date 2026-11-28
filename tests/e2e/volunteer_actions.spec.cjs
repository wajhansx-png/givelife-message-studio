const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 213;
const headers = { Authorization: 'Bearer ' + KEY };
let server;
test.use({ baseURL: `http://127.0.0.1:${port}`, reducedMotion: 'reduce' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server && server.kill());

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
  await page.goto('/new#/donors/volunteers');
  const events = async () =>
    (await (await request.get('/__test/events', { headers })).json()).events;
  await page.getByRole('button', { name: 'DM Case to Sara', exact: true }).click();
  await expect.poll(async () => (await events()).length).toBe(1);
  expect((await events())[0].fields).toMatchObject({ phone: '15551239001', caption: caseText });
  expect((await events())[0].path).toContain('/send/image');
  await expect(page.locator('#volProgress')).toContainText('1 sent', { timeout: 10000 });
  await page.locator('#volMessage').fill('Please share this case, {name}.');
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
  await page.goto('/new#/donors/volunteers');
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
  await page.locator('#volMessage').fill('Please share this update, {name}.');
  await expect(page.getByRole('button', { name: 'DM all volunteers', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Save message', exact: true }).click();
  await expect(page.locator('#donorVolunteers input[type=checkbox]')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('#volMessage')).toHaveValue('Please share this update, {name}.');
  await expect(page.locator('.donor-bottom')).toBeHidden();
  await page.locator('.vol-back').click();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page.getByRole('tablist', { name: 'Donor filters' })).toBeVisible();
  await expect(page.locator('#donorsPage')).toHaveAttribute('data-panel', 'all');
  await page.locator('[data-tab="volunteers"]').click();
  await expect(page.locator('#volMessage')).toHaveValue('Please share this update, {name}.');
});

test('delivery refresh keeps the message draft and caret without a poster checkbox', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/new#/donors/volunteers');
  await page.getByRole('button', { name: 'DM all volunteers', exact: true }).click();
  await page.getByLabel('Start sending', { exact: true }).selectOption('3600');
  await page.getByRole('button', { name: 'Schedule DMs', exact: true }).click();
  await expect(page.locator('#volProgress')).toContainText('Scheduled');
  await expect(page.getByRole('button', { name: 'DM all volunteers', exact: true })).toBeHidden();
  await expect(page.locator('.vol-row .vol-case').first()).toBeDisabled();
  await expect(page.locator('.vol-row .vol-share').first()).toBeDisabled();
  await page.locator('#volMessage').fill('Keep this unsaved message and cursor.');
  await page.locator('#volMessage').evaluate((e) => e.setSelectionRange(7, 7));
  const oldField = await page.locator('#volMessage').elementHandle();
  await expect.poll(() => oldField.evaluate((e) => e.isConnected)).toBe(false);
  await expect(page.locator('#volMessage')).toBeFocused();
  await expect(page.locator('#volMessage')).toHaveValue('Keep this unsaved message and cursor.');
  expect(await page.locator('#volMessage').evaluate((e) => e.selectionStart)).toBe(7);
  await expect(page.locator('#donorVolunteers input[type=checkbox]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Stop DMs', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Stop DMs', exact: true })).toBeHidden();
  await expect(page.getByRole('button', { name: 'DM all volunteers', exact: true })).toBeVisible();
});

test('phone keyboard leaves the message and shared dock usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/new#/donors/volunteers');
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
