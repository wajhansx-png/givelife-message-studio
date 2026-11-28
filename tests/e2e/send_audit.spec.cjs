/* Send audit, through the real buttons: a donor row's DM button posts exactly one id, a rapid double tap sends once,
   and the fake WhatsApp log shows the right account, chat and text. Fake WhatsApp only: nothing real is sent. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 520;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
test.describe.configure({ mode: 'serial' });

const events = async () =>
  (
    await (
      await fetch(`http://127.0.0.1:${port}/__test/events`, {
        headers: { Authorization: 'Bearer ' + KEY },
      })
    ).json()
  ).events;
const dmSends = async () =>
  (await events()).filter((e) => /\/send\/(image|message)/.test(e.path) && !e.device);
const phoneOf = (e) => String(e.fields.phone || '').replace(/@.*/, '');

let people = [];
async function openAll(page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/all');
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page.locator('#donorRows .donor-dm').first()).toBeVisible();
}

test('seed three donors', async () => {
  for (const [name, phone] of [
    ['Zeta First', '0300 5550001'],
    ['Alpha Second', '0300 5550002'],
    ['Mid Third', '0300 5550003'],
  ]) {
    await api(port, '/donors', { action: 'add', name, phone });
  }
  const list = await api(port, '/donors?tab=all');
  people = list.items.filter((d) => /^(Zeta First|Alpha Second|Mid Third)$/.test(d.name));
  expect(people.length).toBe(3);
});

test('the DM button of the SECOND row posts exactly that one id and messages only that person', async ({
  page,
}) => {
  await openAll(page);
  const posts = [];
  page.on('request', (r) => {
    if (r.url().endsWith('/donor-send')) posts.push(JSON.parse(r.postData() || '{}'));
  });
  const rows = page.locator('#donorRows > *');
  const target = rows.filter({ hasText: 'Alpha Second' }).first();
  await target.locator('.donor-dm').click();
  await expect.poll(async () => (await dmSends()).length).toBeGreaterThan(0);
  expect(posts.length).toBe(1);
  expect(Object.keys(posts[0]).includes('ids')).toBe(false);
  const wanted = people.find((d) => d.name === 'Alpha Second');
  expect(posts[0].id).toBe(wanted.id);
  const sends = await dmSends();
  expect(sends.length).toBe(1);
  expect(phoneOf(sends[0])).toContain('3005550002'.slice(-9));
  const text = String(sends[0].fields.caption || sends[0].fields.message || '');
  expect(text.length).toBeGreaterThan(100);
  expect(text).not.toContain('{name}');
  // saved receipt: that person is Sent (saved a moment after WhatsApp answers), the other two are untouched
  await expect
    .poll(
      async () =>
        (await api(port, '/donors?tab=all')).items.find((d) => d.name === 'Alpha Second').delivery,
    )
    .toBe('Sent');
  const after = (await api(port, '/donors?tab=all')).items;
  const by = Object.fromEntries(after.map((d) => [d.name, d]));
  expect(by['Alpha Second'].delivery).toBe('Sent');
  expect(['Not contacted', 'Not sent', undefined]).toContain(by['Zeta First'].delivery);
  expect(['Not contacted', 'Not sent', undefined]).toContain(by['Mid Third'].delivery);
});

test('a rapid double tap on another row sends that person once', async ({ page }) => {
  await openAll(page);
  const before = (await dmSends()).length;
  const posts = [];
  page.on('request', (r) => {
    if (r.url().endsWith('/donor-send')) posts.push(JSON.parse(r.postData() || '{}'));
  });
  const button = page
    .locator('#donorRows > *')
    .filter({ hasText: 'Mid Third' })
    .first()
    .locator('.donor-dm');
  await button.dblclick({ delay: 5 });
  await expect.poll(async () => (await dmSends()).length).toBe(before + 1);
  await page.waitForTimeout(800);
  expect((await dmSends()).length).toBe(before + 1); // nothing more arrives later
  expect(new Set(posts.map((p) => p.request_id)).size).toBe(posts.length); // each tap its own request id
  expect(posts.every((p) => p.id === people.find((d) => d.name === 'Mid Third').id)).toBe(true);
});

test('the same request id sent twice by the server route messages the person once', async () => {
  const target = people.find((d) => d.name === 'Zeta First');
  const before = (await dmSends()).length;
  const body = { id: target.id, request_id: 'audit-click-0001', poster: true };
  const [a, b] = await Promise.all([
    api(port, '/donor-send', body),
    api(port, '/donor-send', body),
  ]);
  expect([a.code, b.code].filter((c) => c === 'SUCCESS').length).toBeGreaterThanOrEqual(1);
  expect((await dmSends()).length).toBe(before + 1);
});
