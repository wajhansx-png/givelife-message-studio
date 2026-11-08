const { test, expect } = require('@playwright/test');
const { showPreview, showDm } = require('./helpers.cjs');
const { startOwnServer, KEY } = require('./own_server.cjs');

/* The four message buttons at the top of the Group and DM editors. Scripted writer, private fake server. */
const PORT = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 201;
let server;
test.use({ baseURL: `http://127.0.0.1:${PORT}` });
test.beforeAll(async () => (server = await startOwnServer(PORT)));
test.afterAll(() => server && server.kill());

async function open(page, kind) {
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/');
  if (kind === 'dm') await showDm(page);
  await showPreview(page);
  await expect(page.locator('#focusFormatted')).not.toHaveText('');
}
const button = (page, name) =>
  page.locator('.focus-styles').getByRole('button', { name, exact: true });
const urdu = /[؀-ۿ]/;

for (const kind of ['group', 'dm'])
  for (const width of [1440, 390, 320])
    test(`four compact buttons, ${kind} editor, ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await open(page, kind);
      for (const name of ['Urdu + English', 'More Trigger', 'English', 'English Trigger']) {
        const box = await button(page, name).boundingBox();
        expect(box, name).not.toBeNull();
        expect(box.height).toBeLessThanOrEqual(48);
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width);
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBe(true);
    });

for (const kind of ['group', 'dm'])
  test(`${kind}: all four buttons write the required message, stay editable and save`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page, kind);
    const text = page.locator('#focusText');
    await page.locator('#focusEdit').click();
    const original = await text.inputValue();

    await button(page, 'Urdu + English').click();
    await expect(page.locator('#focusState')).toContainText('Written');
    const a = await text.inputValue();
    const paras = a.split('\n\n');
    expect(paras[0]).toMatch(/^\*[^*\n]+\*$/); // bold first line
    expect(paras[0]).toMatch(urdu); // in Urdu
    expect(paras[1]).toMatch(/^_.+ 💔_$/); // italic English ending 💔
    expect(a).toMatch(/\n🔴 Rs\. 25,000 LEFT\n/); // live amount
    expect(a).toContain('• *_Just 5 people donating Rs. 5,000 can help '); // 5 x 5,000 covers 25,000
    expect(a).toMatch(/_\* 🤲/);
    expect(a).toContain('03097458815'); // the saved account
    expect(a.trimEnd()).toMatch(/GiveLife Foundation$/);
    expect(a).toMatch(/(سورۃ|صحیح|سنن)/); // a referenced verse or hadith

    // It stays editable and Undo brings the old text back.
    await text.press('Control+z');
    await expect(text).toHaveValue(original);
    await text.press('Control+Shift+z');
    await expect(text).toHaveValue(a);

    await button(page, 'More Trigger').click();
    await expect(page.locator('#focusState')).toContainText('More Trigger');
    const b = await text.inputValue();
    expect(b).not.toBe(a);
    expect(b.split('\n\n')[0]).not.toBe(paras[0]); // a different hook
    expect(b.split('\n\n')[2]).not.toBe(paras[2]); // and a different verse
    expect(b).toMatch(/🔴 Rs\. 25,000 LEFT/);

    await button(page, 'English').click();
    await expect(page.locator('#focusState')).toContainText('Written: English');
    const c = await text.inputValue();
    expect(c).not.toMatch(urdu); // fully English
    expect(c).toMatch(/Allah says:|The Prophet/);
    expect(c.split('\n\n')[0]).toMatch(/^\*[^*\n]+\*$/);

    await button(page, 'English Trigger').click();
    await expect(page.locator('#focusState')).toContainText('English Trigger');
    const d = await text.inputValue();
    expect(d).not.toMatch(urdu);
    expect(d.split('\n\n')[0]).not.toBe(c.split('\n\n')[0]);

    // No opening repeats today.
    const openings = [paras[0], b.split('\n\n')[0], c.split('\n\n')[0], d.split('\n\n')[0]];
    expect(new Set(openings).size).toBe(4);

    // It is a normal editable draft: change a word, press Done, and it is saved by the existing path.
    await text.fill(d.replace('LEFT', 'LEFT ONLY'));
    await page.locator('#focusEdit').click();
    await expect(page.locator('#focusState')).toContainText('Saved');
    const saved = await (
      await request.get('/drafts', { headers: { Authorization: 'Bearer ' + KEY } })
    ).json();
    expect(saved[kind]).toContain('LEFT ONLY');
    expect(saved[kind]).toContain(openings[3].replace(/^\*|\*$/g, ''));
    await page.reload();
    await expect(page.locator('#focusFormatted')).toContainText('LEFT ONLY');
  });

test('a failed write leaves the text alone, says why, and the buttons work again', async ({
  page,
}) => {
  await open(page, 'group');
  await page.locator('#focusEdit').click();
  const text = page.locator('#focusText');
  const before = await text.inputValue();
  await page.route('**/message-style', (r) =>
    r.fulfill({
      status: 503,
      json: { error: 'AI is not connected, so nothing was written. Your message is unchanged.' },
    }),
  );
  await button(page, 'English').click();
  await expect(page.locator('#focusState')).toContainText('AI is not connected');
  await expect(text).toHaveValue(before);
  for (const name of ['Urdu + English', 'More Trigger', 'English', 'English Trigger'])
    await expect(button(page, name)).toBeEnabled();
});

test('only one write at a time: the buttons are locked while one is running', async ({ page }) => {
  await open(page, 'group');
  let calls = 0,
    release;
  const gate = new Promise((r) => (release = r));
  await page.route('**/message-style', async (r) => {
    calls++;
    await gate;
    await r.continue();
  });
  await button(page, 'English').click();
  await expect(button(page, 'More Trigger')).toBeDisabled();
  await button(page, 'English')
    .click({ force: true, timeout: 1000 })
    .catch(() => {});
  release();
  await expect(page.locator('#focusState')).toContainText('Written');
  expect(calls).toBe(1);
});

test('a finished case is refused with a clear message', async ({ page }) => {
  await open(page, 'group');
  await page.locator('#focusEdit').click();
  const before = await page.locator('#focusText').inputValue();
  await page.route('**/message-style', (r) =>
    r.fulfill({
      status: 400,
      json: { error: 'The case is complete (Rs. 0 left). Nothing was written.' },
    }),
  );
  await button(page, 'Urdu + English').click();
  await expect(page.locator('#focusState')).toContainText('The case is complete');
  await expect(page.locator('#focusText')).toHaveValue(before);
});
