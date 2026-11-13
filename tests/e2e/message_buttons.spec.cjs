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
    test(`three compact buttons, ${kind} editor, ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await open(page, kind);
      for (const name of ['Urdu + English', 'English', 'Trigger']) {
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
  test(`${kind}: the buttons write the required message, stay editable and save`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page, kind);
    const text = page.locator('#focusText'); // hidden while previewing; its value is the draft

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

    await expect(text).toBeHidden(); // the preview stays a preview: no keyboard

    // Trigger works on the language that is picked: Urdu + English stays on, Trigger lights up.
    await expect(button(page, 'Urdu + English')).toHaveAttribute('aria-pressed', 'true');
    await expect(button(page, 'Trigger')).toHaveAttribute('aria-pressed', 'false');
    await button(page, 'Trigger').click();
    await expect(page.locator('#focusState')).toContainText('Written: Urdu + English Trigger');
    await expect(button(page, 'Urdu + English')).toHaveAttribute('aria-pressed', 'true');
    await expect(button(page, 'Trigger')).toHaveAttribute('aria-pressed', 'true');
    const b = await text.inputValue();
    expect(b).not.toBe(a);
    expect(b.split('\n\n')[0]).not.toBe(paras[0]); // a different hook
    expect(b.split('\n\n')[2]).not.toBe(paras[2]); // and a different verse
    expect(b).toMatch(/🔴 Rs\. 25,000 LEFT/);

    await button(page, 'Trigger').click(); // Trigger off again
    await expect(page.locator('#focusState')).toContainText('Written: Urdu + English.');
    await expect(button(page, 'Trigger')).toHaveAttribute('aria-pressed', 'false');
    await button(page, 'English').click(); // English, plain
    await expect(page.locator('#focusState')).toContainText('Written: English.');
    await expect(button(page, 'English')).toHaveAttribute('aria-pressed', 'true');
    await expect(button(page, 'Urdu + English')).toHaveAttribute('aria-pressed', 'false');
    const c = await text.inputValue();
    expect(c).not.toMatch(urdu); // fully English
    expect(c).toMatch(/Allah says:|The Prophet/);
    expect(c.split('\n\n')[0]).toMatch(/^\*[^*\n]+\*$/);

    await button(page, 'Trigger').click(); // English becomes English Trigger
    await expect(page.locator('#focusState')).toContainText('Written: English Trigger');
    await expect(button(page, 'English')).toHaveAttribute('aria-pressed', 'true');
    await expect(button(page, 'Trigger')).toHaveAttribute('aria-pressed', 'true');
    const d = await text.inputValue();
    expect(d).not.toMatch(urdu);
    expect(d.split('\n\n')[0]).not.toBe(c.split('\n\n')[0]);

    // No opening repeats today.
    const openings = [paras[0], b.split('\n\n')[0], c.split('\n\n')[0], d.split('\n\n')[0]];
    expect(new Set(openings).size).toBe(4);

    // It is a normal editable draft: Edit, change a word, Done, and it is saved by the existing path.
    await page.locator('#focusEdit').click();
    await expect(text).toBeVisible();
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

for (const kind of ['group', 'dm'])
  for (const width of [390, 1440])
    test(`${kind} ${width}px: a button fills the PREVIEW, no edit mode, no keyboard, saved only on Save Base`, async ({
      page,
      request,
    }) => {
      await page.setViewportSize({ width, height: 800 });
      await open(page, kind);
      const drafts = () =>
        request
          .get('/drafts', { headers: { Authorization: 'Bearer ' + KEY } })
          .then((r) => r.json());
      const savedBefore = (await drafts())[kind];
      const before = await page.locator('#focusFormatted').innerText();
      for (const name of ['English', 'Trigger']) {
        await button(page, name).click();
        await expect(page.locator('#focusState')).toContainText('Written');
        // Still the read-only preview: the text box stays hidden and nothing is focused (no phone keyboard).
        await expect(page.locator('#focusText')).toBeHidden();
        await expect(page.locator('#focusFormatted')).toBeVisible();
        expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe('TEXTAREA');
        await expect(page.locator('#focusEdit')).toHaveText('Edit');
      }
      const now = await page.locator('#focusFormatted').innerText();
      expect(now).not.toBe(before);
      expect(now).toContain('Rs. 25,000 LEFT');
      await expect(page.locator('#focusFormatted strong').first()).toBeVisible(); // real bold, not *stars*
      await expect(page.locator('#focusVersion')).toContainText('not saved');
      // The preview still fits the screen (no scrolling box, nothing cut off).
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBe(true);
      const fits = await page
        .locator('#focusFormatted')
        .evaluate((n) => n.scrollHeight <= n.clientHeight + 3);
      expect(fits).toBe(true);
      // Not saved yet.
      expect((await drafts())[kind]).toBe(savedBefore);
      // Save Base keeps it.
      await page.locator('#focusSave').click();
      await page.locator('#focusBaseSave').click();
      await expect(page.locator('#focusState')).toContainText('Saved base message');
      expect((await drafts())[kind]).toContain('🔴 Rs. 25,000 LEFT');
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
  for (const name of ['Urdu + English', 'English', 'Trigger'])
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
  await expect(button(page, 'Trigger')).toBeDisabled();
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

for (const width of [320, 390, 768, 1440])
  test(`button row is responsive at ${width}px: a clean grid on phones, one row on desktop`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    await open(page, 'group');
    const boxes = [];
    for (const name of ['Urdu + English', 'English', 'Trigger'])
      boxes.push(await button(page, name).boundingBox());
    for (const b of boxes) {
      expect(b.x).toBeGreaterThanOrEqual(0);
      expect(b.x + b.width).toBeLessThanOrEqual(width);
    }
    // No label is cut off.
    for (const name of ['Urdu + English', 'English', 'Trigger'])
      expect(await button(page, name).evaluate((n) => n.scrollWidth <= n.clientWidth + 1)).toBe(
        true,
      );
    if (width <= 899) {
      expect(new Set(boxes.map((b) => Math.round(b.y))).size).toBe(1); // one row of three, no sideways scroll
      expect(boxes[0].height).toBeGreaterThanOrEqual(36);
    } else {
      expect(new Set(boxes.map((b) => Math.round(b.y))).size).toBe(1);
    }
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
      await r.fulfill({ json: { text: '*Hook ' + body.style + '*\n\n🔴 Rs. 25,000 LEFT', left: 25000 } });
    });
    await page.goto('/new#/preview');
    await expect(page.locator('#focusFormatted')).not.toHaveText('');
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
    await chips.nth(2).click(); // Trigger -> English Trigger
    await expect(page.locator('#focusFormatted')).toContainText('Hook en_more');
    expect(await pressed()).toEqual(['false', 'true', 'true']);
    await chips.nth(0).click(); // Urdu + English keeps Trigger on
    await expect(page.locator('#focusFormatted')).toContainText('Hook ur_en_more');
    expect(await pressed()).toEqual(['true', 'false', 'true']);
    await chips.nth(2).click(); // Trigger off
    await expect(page.locator('#focusFormatted')).toContainText(/Hook ur_en(?!_)/);
    expect(await pressed()).toEqual(['true', 'false', 'false']);
    expect(asked).toEqual(['en', 'en_more', 'ur_en_more', 'ur_en']);
  });

test('/new desktop: the chips on the Message card write the same way and show the choice', async ({
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
  const card = page.locator('#ui2Styles button');
  await expect(card).toHaveText(['Urdu + English', 'English', 'Trigger']);
  await card.nth(1).click();
  await expect(page.locator('#messageFocus')).toBeVisible();
  await expect.poll(() => asked.length).toBe(1);
  await expect(page.locator('#messageFocus .focus-styles button').nth(1)).toHaveAttribute('aria-pressed', 'true');
  await expect(card.nth(1)).toHaveAttribute('aria-pressed', 'true');
  expect(asked).toEqual(['en']);
});
