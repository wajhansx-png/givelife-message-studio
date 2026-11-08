const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');

/* Reports > Auto. Fake WhatsApp only: the DMs below go to a local fake gateway. */
const PORT = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 202;
let server;
test.use({ baseURL: `http://127.0.0.1:${PORT}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(PORT)));
test.afterAll(async () => {
  if (server) {
    for (const control of ['important', 'donor_dm', 'group'])
      await api(PORT, '/auto-controls', { control, on: false }).catch(() => {});
    server.kill();
  }
});

async function openReport(page) {
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  page.on('dialog', (d) => d.accept());
  await page.goto('/');
  await page.locator('.report-open').click();
  await expect(page.locator('.auto-card')).toHaveCount(3);
}
const card = (page, id) => page.locator(`.auto-card[data-control="${id}"]`);
const stat = (page, id, name) => card(page, id).locator(`[data-stat="${name}"] dd`);
const events = async () =>
  (await api(PORT, '/__test/events')).events.filter((e) => /send/.test(e.path));

test('three controls, all OFF at first, each with its numbers and Edit Settings', async ({
  page,
}) => {
  await openReport(page);
  const names = {
    group: 'Group Auto',
    donor_dm: 'DM Top Donors',
    important: 'DM Important Donors',
  };
  for (const id of ['group', 'donor_dm', 'important']) {
    await expect(card(page, id).locator('h4')).toHaveText(names[id]);
    await expect(card(page, id).locator('.auto-switch')).toHaveText('OFF');
    await expect(card(page, id).locator('.auto-switch')).toHaveAttribute('aria-checked', 'false');
    for (const s of ['recipients', 'sent', 'pending', 'next'])
      await expect(stat(page, id, s)).toBeVisible();
    await expect(card(page, id).getByRole('button', { name: 'Edit Settings' })).toBeVisible();
  }
  expect(await events()).toHaveLength(0); // opening the page sent nothing
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
});

test('Group Auto switches the existing Auto engine on and off', async ({ page }) => {
  await openReport(page);
  await card(page, 'group').locator('.auto-switch').click();
  await expect(card(page, 'group').locator('.auto-switch')).toHaveText('ON');
  expect((await api(PORT, '/autopilot')).on).toBe(true);
  await card(page, 'group').getByRole('button', { name: 'Edit Settings' }).click();
  await card(page, 'group').locator('input[name="main_every"]').fill('30');
  await card(page, 'group').locator('input[name="freelance_every"]').fill('45');
  await card(page, 'group').getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('#autoMsg')).toContainText('Saved');
  await expect(card(page, 'group').locator('.auto-switch')).toHaveText('ON'); // not restarted
  await card(page, 'group').locator('.auto-switch').click();
  await expect(card(page, 'group').locator('.auto-switch')).toHaveText('OFF');
  expect((await api(PORT, '/autopilot')).on).toBe(false);
});

test('DM Important Donors: owner picks the count, it sends at once, shows live numbers, edits live, blocks overlap, stops', async ({
  page,
}) => {
  await openReport(page);
  const important = card(page, 'important');
  await important.getByRole('button', { name: 'Edit Settings' }).click();
  await important.locator('input[name="count"]').fill('3');
  await important.getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('#autoMsg')).toContainText('Saved');
  expect(await events()).toHaveLength(0); // saving settings sends nothing

  await important.locator('.auto-switch').click(); // explicit owner activation (the confirm was accepted)
  await expect(important.locator('.auto-switch')).toHaveText('ON');
  await expect(stat(page, 'important', 'recipients')).toHaveText('3');
  await expect(stat(page, 'important', 'sent')).toHaveText('1', { timeout: 15000 });
  await expect(stat(page, 'important', 'pending')).toHaveText('2');
  await expect(stat(page, 'important', 'next')).not.toHaveText('—');
  const first = await events();
  expect(first.length).toBeGreaterThanOrEqual(1);

  // The other DM control cannot start while this one owns the queue.
  await card(page, 'donor_dm').locator('.auto-switch').click();
  await expect(page.locator('#autoMsg')).toContainText('DM Important Donors is sending now');
  await expect(card(page, 'donor_dm').locator('.auto-switch')).toHaveText('OFF');

  // Live edit: same batch, nothing re-sent.
  const jobBefore = (await api(PORT, '/donor-delivery')).id;
  await important.getByRole('button', { name: 'Edit Settings' }).click();
  await important.locator('input[name="gap_minutes"]').fill('5');
  await important.getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('#autoMsg')).toContainText('nothing was restarted');
  await expect(important.locator('.auto-switch')).toHaveText('ON');
  const after = await api(PORT, '/donor-delivery');
  expect(after.id).toBe(jobBefore);
  expect(after.gap_seconds).toBe(300);
  expect((await events()).length).toBe(first.length);

  // The server owns the run: reloading (or closing) the page changes nothing.
  await page.reload();
  await page
    .locator('.report-open')
    .click()
    .catch(() => {});
  await expect(card(page, 'important').locator('.auto-switch')).toHaveText('ON');
  expect((await api(PORT, '/donor-delivery')).id).toBe(jobBefore);

  // Nobody is messaged twice.
  const phones = (await events()).map((e) => e.fields.phone);
  expect(new Set(phones).size).toBe(phones.length);

  // OFF stops it; the rest is kept.
  await card(page, 'important').locator('.auto-switch').click();
  await expect(card(page, 'important').locator('.auto-switch')).toHaveText('OFF', {
    timeout: 15000,
  });
  await expect(stat(page, 'important', 'pending')).toHaveText('2');
  await page.waitForTimeout(1500);
  expect((await events()).length).toBe(first.length); // nothing more went out
});

test('DM Top Donors messages only Top donors, and only when switched ON', async ({ page }) => {
  // Three fresh donors become Important and then Top (a Top donor is always Important too).
  const fresh = (await api(PORT, '/donors?tab=all')).items.filter((d) => !d.important).slice(0, 3);
  expect(fresh).toHaveLength(3);
  for (const d of fresh) {
    await api(PORT, '/donors', { action: 'update', id: d.id, important: true });
    await api(PORT, '/donors', { action: 'update', id: d.id, top_donor: true });
  }
  await openReport(page);
  await expect(card(page, 'donor_dm').locator('h4')).toHaveText('DM Top Donors');
  await expect(card(page, 'donor_dm').locator('.auto-switch')).toHaveText('OFF');
  const before = (await events()).length;
  await card(page, 'donor_dm').locator('.auto-switch').click();
  await expect(card(page, 'donor_dm').locator('.auto-switch')).toHaveText('ON');
  await expect(stat(page, 'donor_dm', 'recipients')).toHaveText('3'); // the Top list only
  await expect(stat(page, 'donor_dm', 'sent')).not.toHaveText('0', { timeout: 15000 });
  await card(page, 'donor_dm').locator('.auto-switch').click();
  await expect(card(page, 'donor_dm').locator('.auto-switch')).toHaveText('OFF', {
    timeout: 15000,
  });
  const phones = (await events()).map((e) => e.fields.phone);
  expect(new Set(phones).size).toBe(phones.length);
  expect(phones.length).toBeGreaterThan(before);
  expect(phones.length - before).toBeLessThanOrEqual(3); // never beyond the 3 Top donors
});

test('bad settings are refused in the form and change nothing', async ({ page }) => {
  await openReport(page);
  const important = card(page, 'important');
  await important.getByRole('button', { name: 'Edit Settings' }).click();
  await important.locator('input[name="gap_minutes"]').fill('99');
  await important.locator('form').evaluate((f) => f.setAttribute('novalidate', ''));
  await important.getByRole('button', { name: 'Save' }).click();
  await expect(important.locator('.auto-error')).toContainText('choose');
});

for (const width of [1440, 390, 320])
  test(`Reports page fits ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 });
    await openReport(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    const box = await page.locator('.report-card').boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    for (const sw of await page.locator('.auto-switch').all()) {
      const b = await sw.boundingBox();
      expect(b.height).toBeGreaterThanOrEqual(36);
    }
  });
