const { test, expect } = require('@playwright/test');
const { showPreview, showDm } = require('./helpers.cjs');
const { startOwnServer, KEY } = require('./own_server.cjs');

/* The message buttons (Urdu + English, English, Trigger) at the top of the Group and DM editors. Scripted writer, private fake server. */
const PORT = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 201;
let server;
test.use({ baseURL: `http://127.0.0.1:${PORT}` });
test.beforeAll(async () => (server = await startOwnServer(PORT)));
test.afterAll(() => server && server.kill());

async function open(page, kind) {
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  if (kind === 'dm') await showDm(page);
  await showPreview(page);
  await expect(page.locator('#focusFormatted')).not.toHaveText('');
}
const button = (page, name) =>
  page.locator('.focus-styles').getByRole('button', { name, exact: true });
const urdu = /[؀-ۿ]/;

/* Each button works on the message ON SCREEN (the server rewrites that message in place; tested in
   tests/test_message_styles.py). Here: the request carries the shown message, the answer shows as an unsaved
   preview, and it is a normal editable draft. */
const scripted = async (page, asked) =>
  page.route('**/message-style', async (r) => {
    const body = r.request().postDataJSON();
    asked.push(body);
    const ur = body.style.startsWith('ur');
    await r.fulfill({
      json: {
        text:
          (ur ? '*آج اس خاندان کی مدد کریں*' : '*Help this family today*') +
          ' ' +
          body.style +
          ' ' +
          Date.now() +
          '\n\n_Same message, rewritten._ 💔\n\n🔴 Rs. 25,000 LEFT\n\n*03097458815*\nEASYPAISA ONLY (Wajdan Khan)',
      },
    });
  });

/* /new (the phone reader): three chips fit in one row, and Trigger works on the language that is picked. */
for (const width of [320, 390, 1440])
  test(`/new ${width}px: English writes English, then Trigger makes that English a Trigger one`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: width < 900 ? 800 : 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    const asked = [];
    await page.route('**/message-style', async (r) => {
      const body = r.request().postDataJSON();
      asked.push(body.style);
      await r.fulfill({
        json: { text: '*Hook ' + body.style + '*\n\n🔴 Rs. 25,000 LEFT', left: 25000 },
      });
    });
    await page.goto('/new#/preview');
    await expect(page.locator('#focusFormatted')).not.toHaveText('');
    // the rewrite buttons are in front, one tap each (no More needed)
    const chips = page.locator('#messageFocus .focus-styles button');
    await expect(chips).toHaveText(['Urdu + English', 'English', 'Trigger']);
    // One row, nothing cut off, nothing to scroll sideways.
    const row = await page.locator('#messageFocus .focus-styles').evaluate((n) => ({
      cut: n.scrollWidth > n.clientWidth + 1,
      ys: [...n.children].map((c) => Math.round(c.getBoundingClientRect().y)),
    }));
    expect(row.cut).toBe(false);
    expect(new Set(row.ys).size).toBe(1);
    const pressed = () => chips.evaluateAll((l) => l.map((b) => b.getAttribute('aria-pressed')));
    expect(await pressed()).toEqual(['false', 'false', 'false']);

    await chips.nth(1).click(); // English
    await expect(page.locator('#focusFormatted')).toContainText(/Hook en(?!_)/);
    expect(await pressed()).toEqual(['false', 'true', 'false']);
    await chips.nth(2).click(); // Trigger -> the English on screen, triggered (an action: it does not stay on)
    await expect(page.locator('#focusFormatted')).toContainText('Hook en_more');
    expect(await pressed()).toEqual(['false', 'true', 'false']);
    await chips.nth(0).click(); // Urdu + English is plain again: nothing stays triggered
    await expect(page.locator('#focusFormatted')).toContainText(/Hook ur_en(?!_)/);
    expect(await pressed()).toEqual(['true', 'false', 'false']);
    expect(asked).toEqual(['en', 'en_more', 'ur_en']);
  });

test('/new desktop: Rewrite opens the message page and English writes the same way and shows the choice', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  const asked = [];
  await page.route('**/message-style', async (r) => {
    asked.push(r.request().postDataJSON().style);
    await r.fulfill({ json: { text: '*Hook*\n\n🔴 Rs. 25,000 LEFT', left: 25000 } });
  });
  await page.goto('/new');
  // minimal main screen: the rewrite buttons live on the message page that Rewrite opens
  await page.locator('#ui2GnavMain .ui2-rewrite').click();
  await expect(page.locator('#messageFocus')).toBeVisible();
  await page.locator('#ui2RewriteRow [data-lang="en"]').click();
  await expect.poll(() => asked.length).toBe(1);
  await expect(page.locator('#messageFocus .focus-styles button').nth(1)).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(asked).toEqual(['en']);
});

/* Style fix: the same words in the owner's structure. Nothing new is written; nothing is saved until Save Base. */
const PLAIN_MSG = [
  'آپ کے ایک قدم سے ایک غمزدہ باپ کا بوجھ ہلکا ہو سکتا ہے',
  'Yousaf was only 2 years old. His father borrowed money for the Janazah. Only Rs. 2,000 is left. 💔',
  'Rs. 2,000 LEFT',
  '- Just 2 people donating Rs. 1,000 can help this grieving father. 🤲',
  '03097458815\nEASYPAISA ONLY (Wajdan Khan)\n\n— GiveLife Foundation',
].join('\n\n');

test('Style fix endpoint: bold hook, italic story, formatted lines; same words; idempotent; empty is refused', async ({
  request,
}) => {
  const H = { Authorization: 'Bearer ' + KEY };
  const r = await request.post('/style-fix', {
    headers: H,
    data: { text: PLAIN_MSG, kind: 'group' },
  });
  expect(r.status()).toBe(200);
  const d = await r.json();
  const parts = d.text.split('\n\n');
  expect(parts[0]).toBe('*آپ کے ایک قدم سے ایک غمزدہ باپ کا بوجھ ہلکا ہو سکتا ہے*');
  expect(parts[1]).toMatch(/^_Yousaf was only 2 years old\..* 💔_$/);
  expect(parts).toContain('🔴 Rs. 2,000 LEFT');
  expect(parts).toContain(
    '• *_Just 2 people donating Rs. 1,000 can help this grieving father._* 🤲',
  );
  expect(d.changed).toBe(true);
  const words = (t) => t.replace(/[*_]/g, '').match(/[\p{L}\p{N}]+/gu);
  expect(words(d.text)).toEqual(words(PLAIN_MSG)); // not one word changed
  const again = await (
    await request.post('/style-fix', { headers: H, data: { text: d.text, kind: 'group' } })
  ).json();
  expect(again.changed).toBe(false);
  expect(again.text).toBe(d.text);
  const empty = await request.post('/style-fix', {
    headers: H,
    data: { text: '  ', kind: 'group' },
  });
  expect(empty.status()).toBe(400);
});

test('/new desktop: Style fix on the message page fixes the message', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  const posted = [];
  await page.route('**/style-fix', async (r) => {
    posted.push(r.request().postDataJSON());
    await r.continue();
  });
  await page.goto('/new');
  await page.locator('#ui2GnavMain .ui2-rewrite').click();
  await expect(page.locator('#messageFocus')).toBeVisible();
  const fix = page.locator('#focusStyleFix');
  await expect(fix).toBeVisible();
  expect(await fix.getAttribute('aria-pressed')).toBeNull(); // an action, not a choice
  await fix.click();
  await expect.poll(() => posted.length).toBe(1);
});
