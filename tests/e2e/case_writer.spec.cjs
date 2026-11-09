const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 225;
const headers = { Authorization: 'Bearer ' + KEY };
let server;
test.use({ baseURL: `http://127.0.0.1:${port}`, reducedMotion: 'reduce' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server && server.kill());

async function open(page, width = 390) {
  await page.setViewportSize({ width, height: 844 });
  await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/#/donors/messages');
  await page.getByRole('button', { name: 'Write Case', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Write Case', exact: true })).toBeVisible();
}

for (const width of [1440, 390, 320]) {
  test(`case notes, regeneration and edited output persist at ${width}px`, async ({
    page,
    request,
  }) => {
    await open(page, width);
    const details = page.getByLabel('Case details', { exact: true });
    const output = page.locator('#caseWriterMessage');
    const note = `A helpless father needs help repaying money borrowed for his family. People are coming to his home asking for it. Review ${width}.`;
    await details.fill(note);
    await page.getByLabel('Writing style', { exact: true }).selectOption('en');
    await page.locator('#caseWriterGenerate').click();
    await expect(output).toHaveValue(/Rs\. 25,000 LEFT/);
    const original = await output.inputValue();
    const updated = note + ' The family cannot repay the loan alone.';
    await details.fill(updated);
    await expect(output).toHaveValue(original);
    await expect(page.getByRole('button', { name: 'Use message', exact: true })).toBeDisabled();
    await page.locator('#caseWriterGenerate').click();
    await expect(output).not.toHaveValue(original);
    const edited = (await output.inputValue()) + '\n\nPlease share this appeal with a friend.';
    await output.fill(edited);
    await page.locator('#caseWriterBack').click();
    await page.getByRole('button', { name: 'Write Case', exact: true }).click();
    await expect(details).toHaveValue(updated);
    await expect(output).toHaveValue(edited);
    await page.reload();
    await page.getByRole('button', { name: 'Write Case', exact: true }).click();
    await expect(details).toHaveValue(updated);
    await expect(output).toHaveValue(edited);
    const status = await (await request.get('/case-message', { headers })).json();
    expect(status.saved_messages).toBeGreaterThan(2);
    const bounds = await page.locator('#caseWriterDialog').boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await page.getByRole('button', { name: 'Use message', exact: true }).click();
    await expect(page.locator('#caseWriterDialog')).not.toBeVisible();
    const bank = await (await request.get('/donor-messages', { headers })).json();
    expect(bank.items[0].text).toBe(edited);
    const events = await (await request.get('/__test/events', { headers })).json();
    expect(events.events).toHaveLength(0);
  });
}

test('notes remain editable while writing and an older result cannot erase them', async ({
  page,
}) => {
  await open(page);
  await page.getByLabel('Case details', { exact: true }).fill('The original family case notes.');
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let started;
  const writing = new Promise((resolve) => {
    started = resolve;
  });
  await page.route('**/case-message', async (route) => {
    if (
      route.request().method() === 'POST' &&
      route.request().postDataJSON().action === 'generate'
    ) {
      started();
      await gate;
    }
    await route.continue();
  });
  await page.locator('#caseWriterGenerate').click();
  await writing;
  const details = page.getByLabel('Case details', { exact: true });
  await expect(details).toBeEditable();
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith('/case-message') &&
      r.request().method() === 'POST' &&
      r.request().postDataJSON().action === 'save',
  );
  await details.fill('Newer details typed while the writer is busy.');
  await saved;
  release();
  await expect(page.locator('#caseWriterStatus')).toContainText('changed');
  await expect(details).toHaveValue('Newer details typed while the writer is busy.');
  await expect(page.locator('#caseWriterGenerate')).toBeEnabled();
});

test('case writing endpoints require the studio access key', async ({ request }) => {
  expect((await request.get('/case-message')).status()).toBe(401);
  expect(
    (
      await request.post('/case-message', { data: { action: 'generate', details: 'Test' } })
    ).status(),
  ).toBe(401);
});

for (const [width, height] of [
  [568, 320],
  [667, 375],
]) {
  test(`case writer controls remain reachable in landscape ${width}x${height}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
    await page.goto('/new#/donors/messages');
    await page.getByRole('button', { name: 'Write Case', exact: true }).click();
    await page
      .getByLabel('Case details', { exact: true })
      .fill('A family needs help repaying a loan.');
    await page.locator('#caseWriterGenerate').click();
    await expect(page.locator('#caseWriterMessage')).not.toHaveValue('');
    const workspace = await page.locator('.case-writer-workspace').boundingBox();
    const footer = await page.locator('#caseWriterDialog footer').boundingBox();
    expect(footer.y).toBeGreaterThanOrEqual(workspace.y + workspace.height);
    await page.getByRole('button', { name: 'Use message', exact: true }).click();
    await expect(page.locator('#caseWriterDialog')).toBeHidden();
  });
}
