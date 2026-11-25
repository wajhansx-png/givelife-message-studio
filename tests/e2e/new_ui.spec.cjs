const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const { auditElements } = require('./element-audit.cjs');

/* The redesign is the main link ("/", also /new). The previous page is kept unchanged at /old. Fake WhatsApp only: nothing is sent. */
const PORT = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 204;
let server;
test.use({ baseURL: `http://127.0.0.1:${PORT}` });
test.describe.configure({ mode: 'default' });
test.beforeAll(async () => (server = await startOwnServer(PORT)));
test.afterAll(() => server && server.kill());

const WIDTHS = [
  280, 299, 300, 320, 359, 360, 380, 390, 430, 540, 700, 768, 899, 900, 1024, 1280, 1440, 1920,
];
const open = async (page, path, width, height) => {
  await page.setViewportSize({
    width,
    height: height || (width >= 900 ? 900 : width < 400 ? 740 : 1024),
  });
  await page.addInitScript((k) => {
    localStorage.setItem('givelife-cloud-key', k);
    localStorage.setItem('givelife-theme', 'dark');
    localStorage.removeItem('givelife-last-route'); // each test starts on the page it asks for
  }, KEY);
  await page.goto(path);
};

test('/new reopens where you left: closing on Notes and opening the app again shows Notes; Back goes to the main page', async ({
  browser,
  baseURL,
}) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 740 } });
  await ctx.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  const first = await ctx.newPage();
  await first.goto(baseURL + '/new');
  await first.locator('.ui2-tab[data-tab="notes"]').click();
  await expect(first.locator('#foundationNotes')).toBeVisible();
  await first.close();
  const again = await ctx.newPage();
  await again.goto(baseURL + '/new');
  await expect(again.locator('#foundationNotes')).toBeVisible();
  await expect.poll(() => again.evaluate(() => location.hash)).toBe('#/notes');
  await again.goBack();
  await expect(again.locator('#foundationNotes')).toBeHidden();
  await ctx.close();
});

test('the main link "/" is the new design, /new is the same page, and the previous page is kept at /old', async ({ request }) => {
  const old = await (await request.get('/old')).text();
  expect(old).not.toContain('new-ui.css');
  expect(old).not.toContain('ui2');
  const fresh = await (await request.get('/new')).text();
  expect(fresh).toContain('/new-ui.css');
  expect(fresh).toContain('class="nomsg ui2"');
  const main = await (await request.get('/')).text();
  expect(main).toBe(fresh); // the main link is the new design
  expect((await request.get('/new/')).status()).toBe(200);
  expect((await request.head('/')).status()).toBe(200);
  const css = await request.get('/new-ui.css');
  expect(css.status()).toBe(200);
  const text = await css.text();
  expect(text).not.toContain('@U');
  expect(text).toContain('body.ui2');
  expect((await request.get('/new/')).status()).toBe(200);
});

test('/donor search treats SQL syntax as literal text (read-only)', async ({ request }) => {
  const payload = encodeURIComponent("' OR 1=1--");
  const response = await request.get(`/donors?tab=all&q=${payload}`, {
    headers: { Authorization: `Bearer ${KEY}` },
  });
  expect(response.status()).toBe(200);
  expect((await response.json()).items).toEqual([]);
});

for (const width of WIDTHS) {
  test(`/new fits ${width}px: no sideways scroll, nothing off-screen (main, donors, reader)`, async ({
    page,
  }) => {
    await open(page, '/new', width);
    await expect(page.locator('.app')).toBeVisible();
    for (const hash of ['', '#/donors/all', '#/preview']) {
      await page.evaluate((h) => (location.hash = h), hash);
      await page.waitForTimeout(700);
      if (hash === '#/donors/all') await expect(page.locator('.donor-row').first()).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        `page scrolls sideways at ${width}px on "${hash}"`,
      ).toBe(true);
      const root =
        hash === '#/donors/all' ? '#donorsPage' : hash === '#/preview' ? '#messageFocus' : '.app';
      const audit = await auditElements(page, root);
      const bad = (audit.failures || []).filter(
        (f) => !/scrolling-container/.test(JSON.stringify(f)),
      );
      expect(bad, `${root} at ${width}px`).toEqual([]);
    }
  });
}

for (const width of [280, 320, 360, 390, 430, 768]) {
  test(`/new at ${width}px: one bottom bar (Message, Donors, Chat, More); More opens a sheet fully on screen`, async ({
    page,
  }) => {
    await open(page, '/new', width);
    const tabs = page.locator('#ui2Tabs');
    await expect(tabs).toBeVisible();
    await expect(tabs.locator('.ui2-tab:visible')).toHaveText([
      /Notes/,
      /Message/,
      /Donors/,
      /Chat/,
      /More/,
    ]);
    const bar = await tabs.boundingBox();
    const send = await page.locator('#btnGivelife').boundingBox();
    // phone: below the send buttons (thumb reach); tablet: at the top like iPad apps
    if (width < 600) expect(bar.y).toBeGreaterThan(send.y);
    else expect(bar.y).toBeLessThan(send.y);
    await tabs.locator('[data-tab="more"]').click();
    const sheet = page.locator('#ui2Sheet');
    await expect(sheet).toBeVisible();
    // one list: Settings · Report · Reply, then amount · New case · Case · Case page, then Giki 1 · Giki 2 (Notes is a tab)
    await expect(sheet.locator('.ui2-tile')).toHaveCount(9);
    await expect(sheet.locator('.ui2-tile').last()).toHaveText(/Giki 2/);
    // the Giki tile: its own colour, and it opens /giki
    const giki = sheet.locator('#ui2GikiTile');
    await expect(giki).toBeVisible();
    expect(await giki.evaluate((b) => getComputedStyle(b).backgroundImage)).toContain('gradient');
    await expect(sheet.locator('.ui2-sheet-x')).toBeVisible(); // a cross closes it
    await sheet.locator('.ui2-sheet-x').click();
    await expect(sheet).toBeHidden();
    await tabs.locator('[data-tab="more"]').click();
    const b = await sheet.boundingBox();
    expect(b.x).toBeGreaterThanOrEqual(-0.5);
    expect(b.x + b.width).toBeLessThanOrEqual(width + 0.5);
    expect(b.y + b.height).toBeLessThanOrEqual((await page.viewportSize()).height + 0.5);
    const g = await sheet.locator('#ui2GikiTile').boundingBox();
    expect(g.y + g.height).toBeLessThanOrEqual((await page.viewportSize()).height + 0.5); // reachable
    await sheet.locator('#ui2GikiTile').click();
    await expect(page).toHaveURL(/\/giki/);
  });
}

for (const width of [280, 320, 360, 390]) {
  test(`/new donors at ${width}px: every tab can be scrolled into view and rows keep 40px targets`, async ({
    page,
  }) => {
    await open(page, '/new#/donors/all', width);
    await expect(page.locator('.donor-row').first()).toBeVisible();
    const out = await page.evaluate(() => {
      const bad = [];
      for (const t of document.querySelectorAll('.donor-tabs > [role=tab]')) {
        t.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
        const r = t.getBoundingClientRect();
        if (r.left < -1 || r.right > innerWidth + 1) bad.push(t.getAttribute('aria-label'));
      }
      return bad;
    });
    expect(out).toEqual([]);
    const row = page.locator('.donor-row').first();
    const small = [];
    for (const sel of ['.donor-star', '.donor-dm', '.donor-status', 'details > summary']) {
      const b = await row.locator(sel).first().boundingBox();
      if (width >= 300 ? Math.min(b.width, b.height) < 34 : Math.min(b.width, b.height) < 28)
        small.push(sel);
    }
    expect(small).toEqual([]);
  });
}

test('/new desktop: the donor edit panel opens on top and its Close button can be clicked', async ({
  page,
}) => {
  for (const width of [768, 1024, 1440]) {
    await open(page, '/new#/donors/all', width);
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.locator('summary[aria-label^="Manage"]').nth(2).click();
    const close = page.locator('.donor-row details[open] button', { hasText: 'Close' }).first();
    await expect(close).toBeVisible();
    const onTop = await close.evaluate((b) => {
      const r = b.getBoundingClientRect();
      const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return t === b || b.contains(t);
    });
    expect(onTop, `Close is covered at ${width}px`).toBe(true);
    await close.click();
    await expect(page.locator('.donor-row details[open]')).toHaveCount(0);
  }
});

test('/new desktop reader: the message with its buttons right under it; editing shows bold as bold', async ({
  page,
}) => {
  await open(page, '/new#/preview', 1440);
  const bubble = await page.locator('#focusFormatted').boundingBox();
  const copy = await page.locator('#focusCopy').boundingBox();
  // Copy · Edit · Save base · ⋯ sit on the message, bottom right (owner's layout)
  expect(copy.y).toBeGreaterThan(bubble.y + bubble.height / 2);
  expect(copy.y + copy.height).toBeLessThanOrEqual(bubble.y + bubble.height + 1);
  expect(copy.x + copy.width).toBeLessThanOrEqual(bubble.x + bubble.width + 1);
  await page.locator('#focusEdit').click();
  const live = page.locator('#ui2Live');
  await expect(live).toBeVisible();
  await expect(page.locator('#ui2Float')).toBeVisible();
  expect((await live.boundingBox()).height).toBeGreaterThan(200);
  const before = await page.locator('#focusText').inputValue();
  await live.evaluate((e) => e.dispatchEvent(new Event('input')));
  expect(await page.locator('#focusText').inputValue()).toBe(before); // round trip keeps the text exactly
});

test('/new reader: tapping a line or the B/I bar while editing keeps editing open', async ({
  page,
}) => {
  await open(page, '/new#/preview', 390);
  await page.locator('#focusEdit').click();
  const live = page.locator('#ui2Live');
  await expect(live).toBeVisible();
  await live.click({ position: { x: 40, y: 30 } });
  await expect(live).toBeVisible();
  await page.locator('#ui2Float [data-cmd="bold"]').click();
  await expect(live).toBeVisible();
  await expect(page.locator('#ui2Float')).toBeVisible();
});

test("/new computer: today's message and the send controls share one centered column", async ({
  page,
}) => {
  await open(page, '/new', 1440);
  await page.waitForTimeout(900);
  expect(await page.evaluate(() => location.hash)).toBe('');
  await expect(page.locator('#messageFocus')).toBeHidden();
  await expect(page.locator('#chat')).toBeInViewport();
  await expect(page.locator('#card .tools #copy')).toBeVisible();
  const edit = page.locator('#card .tools #edit');
  await edit.click();
  await expect(page.locator('#groupPreview')).toBeEditable();
  await expect(page.locator('#messageFocus')).toBeHidden();
  await edit.click();
  await page.locator('#card .overflow-tools > summary').click();
  await expect(page.locator('#card #fresh')).toBeVisible();
  await page.locator('#card #hideMsg').click();
  await expect(page.locator('#card')).toBeHidden();
  await page.locator('#showMsg').click();
  await expect(page.locator('#chat')).toBeVisible();
  await page.keyboard.press('d');
  await expect(page.locator('#dmPreview')).toBeVisible();
  await expect(page.locator('#sendDm')).toBeVisible();
  await expect(page.locator('#btnGivelife')).toBeHidden();
  await page.locator('#ui2Tabs [data-tab="message"]').click();
  await expect(page.locator('#groupPreview')).toBeVisible();
  await expect(page.locator('#sendDm')).toBeHidden();
  const card = await page.locator('#card').boundingBox();
  const send = await page.locator('.group-send').boundingBox();
  expect(send.y).toBeGreaterThanOrEqual(card.y + card.height - 1);
  expect(Math.abs(card.x - send.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(card.width - send.width)).toBeLessThanOrEqual(1);
  await expect(page.locator('#main-workspace .talk')).toBeHidden(); // chat is its own screen
  await expect(page.locator('#ui2Tabs [data-tab="chat"]')).toBeVisible();
  await page.locator('#ui2Tabs [data-tab="chat"]').click();
  await expect(page.locator('#hist')).toBeVisible();
  await page.locator('#histClose').click();
  await open(page, '/new', 390);
  await page.waitForTimeout(900);
  await expect(page.locator('#messageFocus')).toBeHidden();
  expect(await page.evaluate(() => location.hash)).toBe('');
});

test('/new compact group dock keeps its controls reachable at every tested width', async ({
  page,
}) => {
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  const main = page.locator('#btnGivelife');
  const other = page.getByRole('button', { name: 'Timer & groups', exact: true }); // opens other groups + Timer
  const testGroup = page.getByRole('button', { name: 'Send to Test group', exact: true });
  const free = page.locator('#btnFree');
  const all = page.locator('#sendAll');
  const picker = page.getByRole('button', { name: 'Choose group', exact: true });
  await expect(main).toContainText('Send to GiveLife');
  for (const [width, height] of [
    [240, 420],
    [260, 480],
    [280, 480],
    [300, 620],
    [320, 568],
    [360, 740],
    [390, 844],
    [430, 650],
    [540, 640],
    [768, 1024],
    [844, 390],
    [1024, 540],
    [1440, 900],
    [1920, 1080],
  ]) {
    await page.setViewportSize({ width, height });
    const fits = (box) =>
      box &&
      box.x >= 0 &&
      box.y >= 0 &&
      box.x + box.width <= width + 1 &&
      box.y + box.height <= height + 1;
    const chat = await page.locator('#chat').boundingBox();
    expect(fits(chat) && chat.height >= 90, `preview at ${width} × ${height}`).toBe(true);
    for (const id of ['#whatsappConnection', '#leftChip', '#auto', '#ui2Tabs'])
      expect(fits(await page.locator(id).boundingBox()), `${id} at ${width} × ${height}`).toBe(
        true,
      );
    if (width < 900) {
      const [wa, amount, auto] = await Promise.all(
        ['#whatsappConnection', '#leftChip', '#auto'].map((id) => page.locator(id).boundingBox()),
      );
      expect(wa.x + wa.width).toBeLessThanOrEqual(amount.x);
      expect(amount.x + amount.width).toBeLessThanOrEqual(auto.x);
      for (const control of [wa, amount, auto]) {
        expect(control.width).toBeGreaterThanOrEqual(44);
        expect(control.height).toBeGreaterThanOrEqual(44);
      }
      if (width >= 360)
        expect(Math.abs(amount.x + amount.width / 2 - width / 2)).toBeLessThanOrEqual(2);
    }
    await expect(free, `${width}px`).toBeHidden();
    await expect(all).toBeHidden();
    const [primary, ...secondary] = await Promise.all([main, other, testGroup].map((el) => el.boundingBox()));
    expect(fits(primary), `GiveLife at ${width} × ${height}`).toBe(true);
    expect(secondary.every((b) => fits(b) && b.height >= 40)).toBe(true);
    // one row on phones and computers; a tablet stacks them beside the message
    if (width < 600 || width >= 900) expect(new Set(secondary.map((b) => Math.round(b.y))).size).toBe(1);
    await other.click();
    await expect(free).toBeVisible();
    await expect(all).toBeVisible();
    await expect(picker).toBeVisible();
    if ([240, 1440].includes(width)) {
      await picker.click();
      await expect(page.locator('#dropFree button').first()).toBeVisible();
      await expect(picker).toHaveAttribute('aria-expanded', 'true');
      await page.keyboard.press('Escape');
      await expect(page.locator('#dropFree')).toBeHidden();
      await expect(picker).toBeFocused();
    }
    // the same click also shows the Timer
    await expect(page.locator('#timerMain .delay-pill').first()).toBeVisible();
    await expect(page.locator('#timerFree .delay-pill').last()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await page.keyboard.press('Escape');
    await expect(page.locator('#ui2LaterPanel')).toBeHidden();
  }
});

test('/new Message dock keeps each send tied to its original destination', async ({ page }) => {
  await open(page, '/new', 390);
  const sends = [];
  await page.route('**/send-group', async (route) => {
    sends.push(route.request().postDataJSON());
    await route.fulfill({ status: 409, json: { error: 'Simulated send failure' } });
  });
  await page.route('**/test', async (route) => {
    sends.push({ ...route.request().postDataJSON(), group: 'test' });
    await route.fulfill({ json: { code: 'SUCCESS' } });
  });
  const other = page.locator('#ui2GroupPicker');
  const groupStatus = page.locator('#groupStatus');
  await page.waitForFunction(() => draftsReady);
  await expect(page.locator('#groupPreview')).not.toBeEmpty();
  const message = await page.locator('#group').inputValue();
  for (const [selector, group] of [
    ['#btnGivelife', 'main'],
    ['#btnFree', 'free'],
    ['#sendAll', 'all'],
    ['#dropFree [data-group="community"]', 'community'],
  ]) {
    if (group !== 'main' && (await other.getAttribute('aria-expanded')) === 'false')
      await other.click();
    if (group === 'community') await page.locator('#btnFreePick').click();
    await page.locator(selector).click();
    if (group === 'main') await expect(page.locator('#btnGivelife .ui2-undo')).toContainText('Undo'); // 5 s to undo first
    await expect.poll(() => sends.at(-1)?.group, { timeout: 10000 }).toBe(group);
    await expect(groupStatus).toContainText('Simulated send failure');
    expect(sends.at(-1)).toMatchObject({ group, message });
  }
  await page.getByRole('button', { name: 'Send to Test group', exact: true }).click();
  await expect(page.locator('.test-row .gb-progress')).toHaveText('✓ Sent');
  expect(sends.map((item) => item.group)).toEqual(['main', 'free', 'all', 'community', 'test']);
  expect(sends.at(-1)).toMatchObject({ group: 'test', message });
});

test('/new computer: every option is one clear button in the bottom bar, and nothing is shown twice', async ({
  page,
}) => {
  await open(page, '/new', 1440, 900);
  const bar = page.locator('#ui2Tabs');
  await expect(bar).toBeVisible();
  await expect(bar.locator('.ui2-tab')).toHaveText([
    /Notes/,
    /Case/,
    /Message/,
    /Giki 1/,
    /Giki 2/,
    /Donors/,
    /Thank donors/,
    /Chat/,
    /Report/,
    /Settings/,
    /More/,
  ]);
  await expect(bar.locator('[data-tab="message"]')).toHaveAttribute('aria-current', 'true');
  const box = await bar.boundingBox();
  expect(box.y + box.height).toBeLessThanOrEqual(900);
  expect(box.y).toBeGreaterThan(600); // at the bottom
  for (const b of await bar.locator('.ui2-tab').all()) {
    const r = await b.boundingBox();
    expect(r.height).toBeGreaterThanOrEqual(44);
    expect(r.width).toBeGreaterThanOrEqual(110);
    await expect(b.locator('svg')).toHaveCount(1); // one icon above the word (the owner asked for icons; the word stays)
  }
  // The same options are not on the screen twice.
  for (const dup of [
    '#donorNotesShortcut',
    '.report-open',
    '#mainNavMore',
    '#ui2TopChat',
    '#railDonors',
  ])
    await expect(page.locator(dup).first(), dup).toBeHidden();
  await expect(page.locator('.brandbar #leftChip')).toBeVisible(); // the status stays on top
  for (const [tab, screen] of [
    ['donors', '#donorsPage'],
    ['chat', '#hist'],
    ['notes', '#foundationNotes'],
    ['report', '.report-dialog'],
    ['settings', '#set'],
    ['more', '#ui2Sheet'],
  ]) {
    await open(page, '/new', 1440, 900);
    await page.locator(`#ui2Tabs [data-tab="${tab}"]`).click();
    await expect(page.locator(screen).first(), tab).toBeVisible();
    if (tab === 'report') {
      await page.locator('#reportClose').click();
      await expect(page.locator(screen)).toBeHidden();
    }
  }
});

for (const width of [280, 320, 360, 390, 430, 768, 1440]) {
  test(`/new reader at ${width}px: every visible button inside the screen, no sideways scroll`, async ({
    page,
  }) => {
    await open(page, '/new#/preview', width);
    await expect(page.locator('#messageFocus')).toBeVisible();
    for (const sel of ['#focusEdit', '#focusTest', '#focusCopy', '#focusBack', '#focusNext']) {
      const el = page.locator(sel).first();
      if (!(await el.isVisible())) continue;
      const bb = await el.boundingBox();
      expect(bb.x, sel).toBeGreaterThanOrEqual(-0.5);
      expect(bb.x + bb.width, sel).toBeLessThanOrEqual(width + 0.5);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
}

for (const width of [280, 360, 430, 1440]) {
  test(`/new DM messages page at ${width}px: one row Edit, Copy, more, Back; Next and Regenerate in their own row`, async ({
    page,
  }) => {
    await open(page, '/new#/donors/messages', width);
    await expect(page.locator('#donorMessages .bank-line').first()).toBeVisible();
    const fs = await page
      .locator('#donorMessages .bank-line')
      .first()
      .evaluate((e) => parseFloat(getComputedStyle(e).fontSize));
    expect(fs).toBeGreaterThanOrEqual(12);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    const ys = await page
      .locator('#donorMessages .bank-actions > :is(button, details)')
      .evaluateAll((bs) =>
        bs.filter((b) => b.checkVisibility()).map((b) => Math.round(b.getBoundingClientRect().y)),
      );
    expect(ys.length).toBe(4);
    expect(new Set(ys).size).toBe(1); // one row
    await page.locator('#ui2BankMore > summary').click();
    if (width >= 900) await expect(page.locator('.ui2-desktop-regenerate')).toBeVisible();
    else await expect(page.locator('.ui2-bank-nav [data-ui2-proxy]').first()).toBeVisible();
    const box = await page.locator('#ui2BankMore > div').boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(-0.5);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 0.5);
  });
}

for (const width of [280, 390, 768, 899]) {
  test(`/new DM messages at ${width}px: batch dock stays hidden and Back to donors works`, async ({
    page,
  }) => {
    await open(page, '/new#/donors/messages', width);
    await expect(page.locator('#donorMessages .bank-line').first()).toBeVisible();

    // Simulate a persisted batch-status panel so the list-only dock cannot mask this control.
    await page.evaluate(() => {
      document.querySelector('#donorProgress').hidden = false;
      document.querySelector('#donorProgressShow').hidden = false;
      document.querySelector('#donorBatchList').hidden = false;
    });
    for (const selector of [
      '.donor-bottom',
      '#donorProgress',
      '#donorProgressShow',
      '#donorBatchList',
    ])
      await expect(page.locator(`#donorsPage ${selector}`)).toBeHidden();

    const back = page.locator('#donorMessages .bank-back-bottom');
    await expect(back).toBeVisible();
    const clickable = await back.evaluate((button) => {
      const r = button.getBoundingClientRect();
      const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return top === button || button.contains(top);
    });
    expect(clickable, `Back is covered at ${width}px`).toBe(true);
    await back.click();
    await expect(page.locator('.donor-row').first()).toBeVisible();
    expect(await page.evaluate(() => location.hash)).toBe('#/donors/all');
  });
}

test('/new Settings is grouped under four headings; the switches explain themselves', async ({
  page,
}) => {
  for (const width of [280, 390, 1440]) {
    await open(page, '/new#/settings', width);
    await expect(page.locator('#set')).toBeVisible();
    await expect(page.locator('.ui2-set-head')).toHaveText([
      'Look',
      'Sending safety',
      'Tools',
      'WhatsApp',
    ]);
    await expect(page.locator('#swDm').locator('xpath=ancestor::label//small')).toContainText(
      'by itself',
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  }
});

test('/new Stop DMs is hidden while idle, and the existing page still has it', async ({
  page,
  request,
}) => {
  await open(page, '/new#/donors/all', 1440);
  await expect(page.locator('#donorSendImportant')).toBeVisible();
  await expect(page.locator('#donorToggle')).toBeHidden();
  const old = await (await request.get('/old')).text();
  expect(old).not.toContain('ui2'); // the previous page is unchanged
});

test('/new phone: tapping the donated circle shows a tick, and tapping again clears it', async ({
  page,
}) => {
  for (const width of [280, 360, 430]) {
    await open(page, '/new#/donors/all', width);
    const status = page.locator('.donor-status').nth(5);
    await expect(status).toHaveAttribute('aria-pressed', 'false');
    await status.click();
    await expect(status).toHaveAttribute('aria-pressed', 'true');
    const mark = await status.evaluate((e) => getComputedStyle(e, '::before').content);
    expect(mark).toContain('\u2713');
    const box = await status.boundingBox();
    expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(width >= 300 ? 34 : 28);
    await status.click();
    await expect(status).toHaveAttribute('aria-pressed', 'false');
  }
});

test('/new computer: Back on the left, DM ★ Important (N) in the middle, Options on the right; phones are unchanged', async ({
  page,
}) => {
  await open(page, '/new#/donors/all', 1440);
  const opt = page.locator('#ui2Options > summary');
  await expect(opt).toBeVisible();
  const o = await opt.boundingBox();
  const dm = await page.locator('#donorSendImportant').boundingBox();
  const back = await page.locator('#donorMainBottom').boundingBox();
  expect(back.x).toBeLessThan(dm.x);
  expect(dm.x).toBeLessThan(o.x);
  expect(
    await page
      .locator('#donorSendImportant')
      .evaluate((e) => getComputedStyle(e, '::after').content),
  ).toMatch(/\(\d+\)/);
  await opt.click();
  await expect(page.locator('#ui2Options #donorAuto')).toBeVisible();
  await expect(page.locator('#ui2Options #donorRowPoster')).toBeVisible();
  const panel = await page.locator('.ui2-options-panel').boundingBox();
  expect(panel.x).toBeGreaterThanOrEqual(0);
  expect(panel.x + panel.width).toBeLessThanOrEqual(1440);
  expect(panel.y).toBeGreaterThanOrEqual(0);
  await page.setViewportSize({ width: 700, height: 900 }); // shrinking puts the controls back where they were
  await page.waitForTimeout(500);
  await expect(page.locator('#ui2Options')).toHaveCount(0);
  await expect(
    page.locator('.donor-bottom > #donorAuto, .donor-bottom > label[for="donorAuto"]').first(),
  ).toHaveCount(1);
  await open(page, '/new#/donors/all', 390);
  await expect(page.locator('#ui2Options')).toHaveCount(0);
});

test('/new DM speed dialog: How fast, four wait times and a summary; the rest folded under More options', async ({
  page,
}) => {
  for (const width of [280, 360, 768, 1440]) {
    await open(page, '/new#/donors/all', width);
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.locator('#donorSendImportant').click();
    const picker = page.locator('#donorBatchPicker');
    await expect(picker.locator('.ui2-speed-btn')).toHaveText(['Slow', 'Normal', 'Fast']);
    await expect(picker.locator('.batch-gap-btn:visible')).toHaveCount(4);
    await expect(picker.locator('#ui2SpeedSum')).toContainText('per batch, then rest');
    await expect(picker.locator('#batchLimit')).toBeHidden();
    await picker.locator('#ui2SpeedMore > summary').click();
    await expect(picker.locator('label[for="batchLimit"]')).toHaveText('DMs in each batch');
    await expect(picker.locator('label[for="batchPause"]')).toHaveText('Rest between batches');
    for (const sel of [
      '#batchCount',
      '#batchLimit',
      '#batchPause',
      '#batchPoster',
      '#batchFollowUp',
      '#batchIncl',
      '#batchRandom',
      '#batchStart',
      '#batchCancel',
    ])
      await expect(picker.locator(sel).first(), sel + ' at ' + width).toBeVisible();
    await picker.locator('.ui2-speed-btn', { hasText: 'Slow' }).click();
    await expect(picker.locator('#batchLimit')).toHaveValue('10');
    await expect(picker.locator('#ui2SpeedSum')).toHaveText('10 per batch, then rest 30 min');
    const box = await picker.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(-0.5);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 0.5);
    await picker.locator('#batchCancel').click();
  }
});

test('/new computer: Options items do not overlap and stay inside the screen', async ({ page }) => {
  await open(page, '/new#/donors/all', 1440);
  await page.locator('#ui2Options > summary').click();
  const boxes = await page.locator('.ui2-options-panel > *').evaluateAll((els) =>
    els.map((e) => {
      const r = e.getBoundingClientRect();
      return [r.x, r.y, r.right, r.bottom];
    }),
  );
  expect(boxes.length).toBeGreaterThanOrEqual(4);
  for (let i = 0; i < boxes.length; i++) {
    expect(boxes[i][0]).toBeGreaterThanOrEqual(0);
    expect(boxes[i][2]).toBeLessThanOrEqual(1440);
    if (i) expect(boxes[i][1]).toBeGreaterThanOrEqual(boxes[i - 1][3] - 1); // no overlap with the one above
  }
});

test('/new computer: donor list is centred and narrow, with a short amount box', async ({
  page,
}) => {
  await open(page, '/new#/donors/all', 1440);
  const t = await page.locator('#donorTable').boundingBox();
  expect(t.width).toBeLessThanOrEqual(761);
  // the left menu stays beside the page, so the list is centred in the space to the right of it
  const side = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ui2-side')) || 0);
  expect(side).toBeGreaterThan(100);
  expect(Math.abs(t.x + t.width / 2 - (side + 1440) / 2)).toBeLessThan(40);
  await page.locator('.donor-row .donor-status').first().click();
  const amt = await page.locator('.donor-row .donor-amount').first().boundingBox();
  expect(amt.width).toBeLessThanOrEqual(110);
});

test('/new Notes: tool buttons are small, centred and fully on screen (no scroll)', async ({
  page,
}) => {
  for (const [w, h] of [
    [1920, 890],
    [1366, 650],
    [390, 740],
  ]) {
    await page.setViewportSize({ width: w, height: h });
    await page.addInitScript((k) => {
      localStorage.setItem('givelife-cloud-key', k);
      localStorage.setItem('givelife-theme', 'dark');
    }, KEY);
    await page.goto('/new#/notes');
    const pw = page.locator('#notesUnlockForm input[type=password]');
    if (await pw.isVisible().catch(() => false)) {
      await pw.fill('test-preview-only-pin');
      await pw.press('Enter');
    }
    const bar = page.locator('#notesTools');
    await expect(bar).toBeVisible();
    const b = await bar.boundingBox();
    expect(b.y + b.height).toBeLessThanOrEqual(h + 0.5);
    expect(b.width).toBeLessThan(w > 700 ? 420 : w);
    const sc = await bar.evaluate((e) => e.scrollWidth <= e.clientWidth + 1);
    expect(sc).toBe(true);
  }
});

for (const width of [280, 320, 412]) {
  test(`/new phone donors at ${width}px: title, search, Msgs and Add never overlap; hide chips get their own row`, async ({
    page,
  }) => {
    await open(page, '/new#/donors/important', width);
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.evaluate(() => {
      const h = document.getElementById('donorHideSent');
      h.hidden = false;
      h.textContent = 'Showing contacted · Hide';
    });
    const boxes = await page.evaluate(() =>
      [
        '.donor-title h1',
        '#ui2DonorSearch',
        '.donor-msgs',
        '.ui2-add-menu > summary',
        '#donorHideSent',
        '#donorDeselectAll',
      ]
        .map((s) => document.querySelector(s))
        .map((e) => {
          const r = e.getBoundingClientRect();
          return [r.x, r.y, r.right, r.bottom];
        }),
    );
    for (let i = 0; i < boxes.length; i++)
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i],
          b = boxes[j];
        const overlap = a[0] < b[2] - 1 && b[0] < a[2] - 1 && a[1] < b[3] - 1 && b[1] < a[3] - 1;
        expect(overlap, `boxes ${i} and ${j} overlap at ${width}px`).toBe(false);
      }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
}

test('/new Back on Volunteers returns to the donor list with tabs visible', async ({ page }) => {
  await open(page, '/new#/donors/volunteers', 390);
  await expect(page.locator('#donorsPage')).toBeVisible();
  await page.locator('#donorsPage .vol-back:visible').first().click();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page.locator('#donorsPage')).toHaveAttribute('data-panel', 'all');
  await expect(page.locator('.donor-tabs')).toBeVisible();
});

for (const width of [280, 390, 1440]) {
  test(`/new Volunteers at ${width}px: dark list like the other tabs, name readable, bottom bar DM all / Add / Back in one row`, async ({
    page,
  }) => {
    await open(page, '/new#/donors/volunteers', width);
    await expect(page.locator('#donorVolunteers')).toBeVisible();
    if (!(await page.locator('.vol-row').count())) {
      await page.locator('.vol-add-panel > summary').click();
      await page.fill('#volName', 'Wajdan');
      await page.fill('#volPhone', '+923001234567');
      await page.locator('.vol-add button.primary').click();
      await expect(page.locator('.vol-row').first()).toBeVisible();
    }
    await expect(page.locator('.vol-row .vol-name').first()).toBeVisible();
    await expect
      .poll(() =>
        page
          .locator('.vol-row .vol-name')
          .first()
          .evaluate((e) => e.getBoundingClientRect().width),
      )
      .toBeGreaterThan(60);
    const bg = await page
      .locator('#donorVolunteers .vol-list')
      .evaluate((e) => getComputedStyle(e).backgroundColor);
    expect(bg).toBe('rgb(0, 0, 0)');
    const ys = await page
      .locator('#donorVolunteers .vol-foot > :is(.vol-back, .send-donors, .vol-add-panel)')
      .evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().y)));
    expect(new Set(ys).size).toBe(1);
    const back = await page.locator('#donorVolunteers .vol-back').boundingBox();
    const dm = await page.locator('#donorVolunteers .send-donors').boundingBox();
    if (width < 900)
      expect(back.x).toBeGreaterThan(dm.x); // phone: Back is the far-right arrow on every donor tab
    else expect(back.x).toBeLessThan(dm.x);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
}

test('/new phone Back gesture: when the browser closes a screen itself, the address follows (no dead Back)', async ({
  page,
}) => {
  for (const [tab, id] of [
    ['chat', 'hist'],
    ['donors', 'donorsPage'],
  ]) {
    await open(page, '/new', 390);
    await page.locator(`.ui2-tab[data-tab="${tab}"]`).click();
    await expect(page.locator('#' + id)).toBeVisible();
    await page.evaluate((i) => document.getElementById(i).close(), id); // Android Chrome's Back gesture
    await expect.poll(() => page.evaluate(() => location.hash)).toBe('');
  }
});

test('/new on-screen Back leaves no stale history entry, so the phone Back never "does nothing"', async ({
  page,
}) => {
  await open(page, '/new', 390);
  await page.evaluate(() => window.history.pushState({ marker: 1 }, '', location.pathname + '#/'));
  await page.evaluate(() => window.history.replaceState({ marker: 1 }, '', location.pathname));
  for (const [tab, back] of [
    ['chat', '#histClose'],
    ['donors', '#donorMainBottom'],
    ['card', '#focusBack'],
  ]) {
    if (tab === 'card') await page.locator('#card').click();
    else await page.locator(`.ui2-tab[data-tab="${tab}"]`).click();
    await page.waitForTimeout(400);
    await page
      .locator(back + ':visible')
      .first()
      .click();
    await expect.poll(() => page.evaluate(() => location.hash)).toBe('');
    // Back on the very entry we started from: nothing piled up after it.
    await expect
      .poll(() => page.evaluate(() => window.history.state && window.history.state.marker), {
        message: tab,
      })
      .toBe(1);
  }
});

test('/new phone: tapping anywhere on the Auto row switches Auto', async ({ page }) => {
  await open(page, '/new', 390);
  const before = await page.locator('#auto').getAttribute('aria-checked');
  const box = await page.locator('#live').boundingBox();
  await page.mouse.click(box.x + 20, box.y + box.height / 2);
  await expect.poll(() => page.locator('#auto').getAttribute('aria-checked')).not.toBe(before);
  await page.mouse.click(box.x + 20, box.y + box.height / 2); // switch it back
});

test('/new phone: Chat has one Back at the top left, money left beside it, and three quick buttons', async ({ page }) => {
  await open(page, '/new#/chat', 390);
  await expect(page.locator('#hist')).toBeVisible();
  await expect(page.locator('#hist > header')).toBeVisible();
  await expect(page.locator('#histMain')).toBeHidden(); // no second Back in the middle
  await expect(page.locator('#ui2HistLeft')).toContainText('left');
  await expect(page.locator('#ui2HistChips .ui2-chip')).toHaveText(['Amount left', 'New wording', 'Send all']);
  const back = await page.locator('#histClose').boundingBox();
  expect(back.y).toBeLessThan(80);
  expect(back.x).toBeLessThan(60);
  await page.locator('#histClose').click();
  await expect(page.locator('#hist')).toBeHidden();
});

test('/new phone donors: one control row below the list: tabs, search icon and a ⋯ menu', async ({
  page,
}) => {
  await open(page, '/new#/donors/all', 390);
  await expect(page.locator('.donor-row').first()).toBeVisible();
  const table = await page.locator('#donorTable').boundingBox();
  const tabs = await page.locator('.donor-tabs').boundingBox();
  const search = await page.locator('#ui2DonorSearch').boundingBox();
  const more = await page.locator('#donorNavMore > summary').boundingBox();
  expect(tabs.y).toBeGreaterThan(table.y);
  await expect(page.locator('.donor-head')).toBeHidden(); // no separate Search / + Add row any more
  await expect(page.locator('#donorHideRow')).toBeHidden(); // and no empty reserved row
  for (const box of [search, more]) {
    expect(Math.abs(box.y - tabs.y)).toBeLessThanOrEqual(4); // same row as the tabs
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
  }
  expect(search.x).toBeGreaterThanOrEqual(tabs.x + tabs.width - 1);
  expect(more.x).toBeGreaterThan(search.x);
  expect(table.y + table.height).toBeLessThanOrEqual(tabs.y); // the list ends where the row starts
});

test('/new phone donors: search opens over the tabs without moving the list, filters, and closes', async ({
  page,
}) => {
  await open(page, '/new#/donors/all', 390);
  await expect(page.locator('.donor-row').first()).toBeVisible();
  await page.waitForTimeout(700); // the screen has finished sliding in
  const before = await page.locator('#donorTable').boundingBox();
  const rows = await page.locator('.donor-row').count();
  await page.locator('#ui2DonorSearch').click();
  await expect(page.locator('#donorSearch')).toBeVisible();
  await expect(page.locator('#donorSearch')).toBeFocused();
  const field = await page.locator('#donorSearch').boundingBox();
  const tabs = await page.locator('.donor-tabs').boundingBox();
  expect(Math.abs(field.y - tabs.y)).toBeLessThanOrEqual(4); // opens in the tabs row
  await page.locator('#donorSearch').fill('Demo donor 2');
  await expect(page.locator('.donor-row')).toHaveCount(2);
  const during = await page.locator('#donorTable').boundingBox();
  expect(during.y).toBe(before.y);
  expect(during.height).toBe(before.height); // never pushed
  await page.locator('#ui2DonorSearch').click(); // now a ×: clears and closes
  await expect(page.locator('#donorSearch')).toBeHidden();
  await expect(page.locator('.donor-row')).toHaveCount(rows);
});

test('/new phone donors: the ⋯ menu holds Add numbers, Add one donor, Bulk and the Important chips', async ({
  page,
}) => {
  await open(page, '/new#/donors/all', 390);
  await expect(page.locator('.donor-row').first()).toBeVisible();
  await page.locator('#donorNavMore > summary').click();
  for (const id of ['#donorNumbers', '#donorAdd', '#donorBulk'])
    await expect(page.locator(id)).toBeVisible();
  await expect(page.locator('#donorDeselectAll')).toBeHidden(); // only on Important, Top donors and Donated
  const panel = await page.locator('#donorNavMore .compact-nav-panel').boundingBox();
  const bar = await page.locator('.donor-tabs').boundingBox();
  expect(panel.y + panel.height).toBeLessThanOrEqual(bar.y + 1); // opens upward, over the list (browser rectangles differ by a subpixel)
  expect(panel.x).toBeGreaterThanOrEqual(0);
  await page.locator('#donorAdd').click();
  await expect(page.locator('#donorAddDialog')).toBeVisible();
  await page.locator('#donorAddCancel').click();
  await page.locator('.donor-tabs [data-tab="important"]').click();
  await page.locator('#donorNavMore > summary').click();
  await expect(page.locator('#donorDeselectAll')).toBeVisible();
  const chip = await page.locator('#donorDeselectAll').boundingBox();
  expect(chip.height).toBeGreaterThanOrEqual(44);
});

test('/new phone donors: the tab you are on is always in view; Volunteers uses the full tab row', async ({
  page,
}) => {
  for (const tab of ['volunteers', 'donated', 'all']) {
    await open(page, '/new#/donors/' + tab, 390);
    await expect(page.locator(`.donor-tabs [data-tab="${tab}"]`)).toBeInViewport({ ratio: 0.95 });
  }
  await page.locator('.donor-tabs [data-tab="volunteers"]').click();
  await expect(page.locator('#donorVolunteers')).toBeVisible();
  await expect(page.locator('#ui2DonorSearch')).toBeHidden(); // Volunteers has its own + Add dock
  await expect(page.locator('#donorNavMore')).toBeHidden();
  const tabs = await page.locator('.donor-tabs').boundingBox();
  expect(tabs.x + tabs.width).toBeGreaterThan(390 - 16); // the tabs use the whole row
});

test('/new phone DM messages: the message takes the free height; every button is together at the bottom', async ({
  page,
}) => {
  await open(page, '/new#/donors/messages', 390, 844);
  await expect(page.locator('#donorMessages .bank-line').first()).toBeVisible();
  const card = await page.locator('#donorMessages .bank-detail').boundingBox();
  const actions = await page.locator('#donorMessages .bank-actions').boundingBox();
  const follow = await page.locator('#donorMessages .bank-followup').boundingBox();
  expect(card.height).toBeGreaterThan(844 * 0.5);
  expect(follow.y - (actions.y + actions.height)).toBeLessThanOrEqual(24); // no empty gap above the bar
  expect(
    await page
      .locator('#donorMessages .bank-detail')
      .evaluate((e) => e.scrollHeight <= e.clientHeight + 1),
  ).toBe(true);
});

test('/new phone DM messages: no top bar, whole message shown, Next/Regenerate row, tabs at the bottom', async ({
  page,
}) => {
  await open(page, '/new#/donors/messages', 390);
  await expect(page.locator('#donorMessages .bank-line').first()).toBeVisible();
  await expect(page.locator('#donorsPage .donor-head')).toBeHidden();
  const prev = page.locator('#donorMessages .bank-preview');
  expect(await prev.evaluate((e) => e.scrollHeight <= e.clientHeight + 1)).toBe(true);
  const navigation = page.locator('.ui2-bank-nav');
  await expect(navigation.getByRole('button', { name: '‹ Previous', exact: true })).toBeDisabled();
  await expect(navigation.getByRole('button', { name: 'Next ›', exact: true })).toBeEnabled();
  const tabs = await page.locator('#donorMessages .bank-followup').boundingBox();
  const actions = await page.locator('#donorMessages .bank-actions').boundingBox();
  expect(tabs.y).toBeGreaterThan(actions.y);
});

for (const [w, h] of [
  [412, 890],
  [360, 700],
  [280, 600],
]) {
  test(`/new phone donors at ${w}px: every tab keeps tabs, tools and the bottom bar in exactly the same place`, async ({
    page,
  }) => {
    await open(page, '/new#/donors/all', w, h);
    await expect(page.locator('.donor-row').first()).toBeVisible();
    const seen = [];
    for (const t of ['all', 'important', 'top', 'donated', 'not_contacted', 'volunteers', 'all']) {
      await page.locator(`.donor-tabs [data-tab="${t}"]`).click();
      await page.waitForTimeout(350);
      seen.push(
        await page.evaluate(() => {
          const y = (e) => Math.round(e.getBoundingClientRect().y);
          const bar = [...document.querySelectorAll('.donor-bottom, .vol-foot')].find((e) =>
            e.checkVisibility(),
          );
          return [
            y(document.querySelector('.donor-tabs')),
            y(document.querySelector('.donor-head')),
            y(bar),
            Math.round(bar.getBoundingClientRect().height),
          ].join(',');
        }),
      );
    }
    expect(new Set(seen).size, seen.join(' | ')).toBe(1);
  });
}

test('/new phone: Rewrite and ‹ › sit under the green message at the thumb spot; Rewrite opens the reader', async ({
  page,
}) => {
  await open(page, '/new', 390);
  const msg = await page.locator('#groupPreview').boundingBox();
  const nav = await page.locator('#ui2GnavMain').boundingBox();
  const pill = await page.locator('#ui2VerNav').boundingBox();
  const send = await page.locator('.group-send').boundingBox();
  // under the message, just above Test group; ‹ › in the middle of the width (owner's resting thumb), not at the edge
  expect(nav.y).toBeGreaterThanOrEqual(msg.y + msg.height - 0.5);
  expect(nav.y + nav.height).toBeLessThanOrEqual(send.y + 0.5);
  expect(pill.x + pill.width / 2).toBeGreaterThan(390 * 0.4);
  expect(pill.x + pill.width).toBeLessThan(390 * 0.8);
  const rewrite = page.locator('#ui2GnavMain .ui2-rewrite');
  await expect(rewrite).toHaveText('Rewrite');
  await expect(page.locator('#ui2GnavMain #ui2VerNav #homePrev')).toBeVisible();
  await expect(page.locator('#ui2GnavMain #ui2VerNav #homeNext')).toBeVisible();
  for (const sel of ['.ui2-rewrite', '#homePrev', '#homeNext'])
    expect((await page.locator('#ui2GnavMain ' + sel).boundingBox()).height, sel).toBeGreaterThanOrEqual(44);
  // the last line of text is never under the buttons
  const textBottom = await page.evaluate(() => {
    const lines = document.querySelectorAll('#groupPreview .wa-line');
    return lines[lines.length - 1].getBoundingClientRect().bottom;
  });
  expect(textBottom).toBeLessThanOrEqual(nav.y + 0.5);
  await rewrite.click();
  await expect(page.locator('#messageFocus')).toBeVisible();
  await open(page, '/new#/preview', 390);
  // In the reader (owner's layout): ‹ version ›, the rewrites and Generate · Test · Back all in the lower part (thumb);
  // Copy · Edit · ⋯ sit on the message.
  await expect(page.locator('#ui2GnavReader')).toBeHidden();
  await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText(/^(Original|Base)/);
  // minimal layout: ‹ › are a small pill inside the message (bottom right, thumb side); the rewrite bar sits low
  const msgBox = await page.locator('#focusFormatted').boundingBox();
  for (const sel of ['#ui2Swipe .ui2-swipe-prev', '#ui2Swipe .ui2-swipe-next']) {
    const box = await page.locator(sel).boundingBox();
    expect(box.height, sel).toBeGreaterThanOrEqual(32);
    expect(box.y + box.height, sel).toBeLessThanOrEqual(msgBox.y + msgBox.height + 1);
  }
  const rw = await page.locator('#ui2RewriteRow [data-lang="en"]').boundingBox();
  expect(rw.height).toBeGreaterThanOrEqual(36);
  expect(rw.y).toBeGreaterThan(844 * 0.6);
  await expect(page.locator('#messageFocus .ui2-reader-dock > :is(.ui2-gen-btn, #focusTest, #focusBack)')).toHaveCount(3);
  await expect(page.locator('#ui2MsgTools > :is(#focusCopy, #focusEdit, .ui2-base-btn, .focus-rail-more)')).toHaveCount(4);
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await expect(page.locator('#messageFocus')).toBeVisible();
});

test('/new phone donors: Back is the same far-right arrow on every tab', async ({ page }) => {
  await open(page, '/new#/donors/all', 390);
  const xs = [];
  for (const t of ['all', 'important', 'top', 'volunteers']) {
    await page.locator(`.donor-tabs [data-tab="${t}"]`).click();
    await page.waitForTimeout(350);
    xs.push(
      await page.evaluate(() => {
        const b = [...document.querySelectorAll('#donorMainBottom, .vol-back')].find((e) =>
          e.checkVisibility(),
        );
        const r = b.getBoundingClientRect();
        return Math.round(r.x) + ',' + Math.round(r.width);
      }),
    );
  }
  expect(new Set(xs).size, xs.join(' | ')).toBe(1);
});

for (const width of [280, 360, 412]) {
  test(`/new phone donors at ${width}px: a Msgs button sits in the bottom bar on every tab and opens DM messages`, async ({
    page,
  }) => {
    await open(page, '/new#/donors/all', width, 760);
    await expect(page.locator('.donor-row').first()).toBeVisible();
    for (const t of ['all', 'important', 'top', 'volunteers']) {
      await page.locator(`.donor-tabs [data-tab="${t}"]`).click();
      await page.waitForTimeout(350);
      const m = page.locator('#donorsPage .ui2-msgs-bottom:visible').first();
      await expect(m, t).toBeVisible();
      const b = await m.boundingBox();
      const bar = await page.evaluate(() => {
        const e = [...document.querySelectorAll('.donor-bottom, .vol-foot')].find((x) =>
          x.checkVisibility(),
        );
        const r = e.getBoundingClientRect();
        return [r.y, r.bottom];
      });
      expect(b.y, t).toBeGreaterThanOrEqual(bar[0] - 1);
      expect(b.y + b.height, t).toBeLessThanOrEqual(bar[1] + 1);
      expect(b.x + b.width, t).toBeLessThanOrEqual(width);
    }
    await expect(page.locator('#donorsPage .donor-head .donor-message-tablist')).toBeHidden();
    await page.locator('#donorsPage .ui2-msgs-bottom:visible').first().click();
    await expect(page.locator('#donorMessages')).toBeVisible();
  });
}

for (const width of [390, 1440, 1920]) {
  test(`/new Volunteers shares the donor theme and header at ${width}px`, async ({ page }) => {
    await open(page, '/new#/donors/all', width);
    await page.waitForFunction(() =>
      document
        .getAnimations()
        .every((a) => a.playState !== 'running' || a.effect?.getTiming().iterations === Infinity),
    ); // opening slide done
    const shell = page.locator('#donorsPage');
    const theme = await shell.evaluate((e) => getComputedStyle(e).backgroundColor);
    const header = await page.locator('.donor-head').boundingBox();
    const backTheme = await page
      .locator('#donorMainBottom')
      .evaluate((e) => getComputedStyle(e).backgroundColor);
    const sendTheme = await page
      .locator('#donorSendImportant')
      .evaluate((e) => getComputedStyle(e).backgroundImage);
    await page.locator('.donor-tabs [data-tab="volunteers"]').click();
    await expect(page.locator('#donorVolunteers')).toBeVisible();
    if (header) await expect(page.locator('.donor-head')).toBeVisible();
    expect(await shell.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe(theme);
    const volunteerHeader = await page.locator('.donor-head').boundingBox();
    if (header) {
      expect(Math.abs(volunteerHeader.y - header.y)).toBeLessThan(2);
      expect(Math.abs(volunteerHeader.width - header.width)).toBeLessThan(2);
    }
    expect(
      await page.locator('.vol-back').evaluate((e) => getComputedStyle(e).backgroundColor),
    ).toBe(backTheme);
    expect(
      await page
        .locator('.vol-foot .send-donors')
        .evaluate((e) => getComputedStyle(e).backgroundImage),
    ).toBe(sendTheme);
    if (width >= 900) {
      const list = await page.locator('.vol-people').boundingBox();
      const message = await page.locator('.vol-msg').boundingBox();
      expect(Math.abs(list.width - message.width)).toBeLessThan(2);
      await page.locator('#donorNavMore > summary').click();
      await expect(page.getByLabel('Volunteer name', { exact: true })).toBeVisible();
    }
  });
}

test('/new phone: every button in the bottom bar has an icon above its word', async ({ page }) => {
  await open(page, '/new', 390);
  const tabs = page.locator('#ui2Tabs .ui2-tab:visible');
  await expect(tabs).toHaveText(['Notes', 'Message', 'Donors', 'Chat', 'More']);
  for (let i = 0; i < 5; i++) {
    const t = tabs.nth(i);
    await expect(t.locator('svg')).toHaveCount(1);
    const [icon, word] = await Promise.all([t.locator('svg').boundingBox(), t.locator('span').boundingBox()]);
    expect(icon.y + icon.height).toBeLessThanOrEqual(word.y + 1); // icon above the word
    expect(icon.width).toBeGreaterThanOrEqual(18);
    expect((await t.boundingBox()).height).toBeGreaterThanOrEqual(44);
  }
  // Names stay plain words for screen readers (the icon is decoration).
  await expect(page.getByRole('button', { name: 'Donors', exact: true }).first()).toBeVisible();
});

test('/new More: New case asks for a name and an amount, keeps Important and Top, and saves nothing until Start', async ({
  page,
}) => {
  await open(page, '/new', 390);
  const posts = [];
  await page.route('**/cases', async (r) => {
    if (r.request().method() === 'POST') {
      posts.push(r.request().postDataJSON());
      await r.fulfill({ json: { reply: 'ok', cases: [], current: 'x' } });
    } else await r.continue();
  });
  await page.locator('#ui2Tabs [data-tab="more"]').click();
  const tile = page.locator('#ui2Sheet button.ui2-tile', { hasText: 'New case' });
  await expect(tile).toBeVisible();
  await expect(tile).toContainText('Important & Top stay');
  await tile.click();
  const sheet = page.locator('#ui2NewCase');
  await expect(sheet).toBeVisible();
  // The sheet is solid (the page behind never shows through) and sits at the bottom, in thumb reach.
  expect(await sheet.evaluate((n) => getComputedStyle(n).backgroundColor)).not.toBe('rgba(0, 0, 0, 0)');
  const box = await sheet.boundingBox();
  expect(box.y + box.height).toBeGreaterThan(page.viewportSize().height - 2);
  await expect(sheet.locator('.ui2-nc-note')).toContainText('Important and Top donors stay the same');
  // Empty or wrong input says why and sends nothing.
  await sheet.getByRole('button', { name: 'Start new case' }).click();
  await expect(sheet.locator('.ui2-nc-err')).toContainText('case name');
  await page.locator('#ui2NcName').fill('Affan family');
  await page.locator('#ui2NcLeft').fill('abc');
  await sheet.getByRole('button', { name: 'Start new case' }).click();
  await expect(sheet.locator('.ui2-nc-err')).toContainText('how much money');
  expect(posts).toEqual([]);
  // Cancel leaves everything alone.
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  await expect(sheet).toBeHidden();
  expect(posts).toEqual([]);
  // Start sends the name, the amount and keep_lists: true.
  await page.locator('#ui2Tabs [data-tab="more"]').click();
  await page.locator('#ui2Sheet button.ui2-tile', { hasText: 'New case' }).click();
  await page.locator('#ui2NcName').fill('Affan family');
  await page.locator('#ui2NcLeft').fill('50,000');
  await Promise.all([
    page.waitForEvent('load'),
    sheet.getByRole('button', { name: 'Start new case' }).click(),
  ]);
  expect(posts).toEqual([{ action: 'new', name: 'Affan family', left: 50000, keep_lists: true }]);
});

test('/new More: the old "New case from zero" choice opens the same form, not three browser pop-ups', async ({
  page,
}) => {
  await open(page, '/new', 390);
  let dialogs = 0;
  page.on('dialog', (d) => (dialogs++, d.dismiss()));
  await page.waitForTimeout(800);
  await page.locator('#caseSelect').evaluate((sel) => {
    sel.value = '__new'; // the real choice in the Case list (the select itself is inside the More menu)
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await expect(page.locator('#ui2NewCase')).toBeVisible();
  expect(dialogs).toBe(0);
});

for (const width of [320, 360, 390, 430])
  test(`/new Later panel at ${width}px: timers are real buttons, one line per group, nothing off-screen`, async ({
    page,
  }) => {
    await open(page, '/new', width, 709);
    await page.locator('#ui2GroupPicker').click(); // Timer & groups opens the other groups and the Timer
    const panel = page.locator('#ui2LaterPanel');
    await expect(panel).toBeVisible();
    const lines = await panel.locator('.ui2-later-line').count();
    expect(lines).toBeGreaterThanOrEqual(2);
    for (let i = 0; i < lines; i++) {
      const pills = panel.locator('.ui2-later-line').nth(i).locator('.delay-pill');
      expect(await pills.count()).toBeGreaterThanOrEqual(4);
      const boxes = await pills.evaluateAll((l) =>
        l.map((n) => {
          const r = n.getBoundingClientRect();
          return { x: r.x, y: Math.round(r.y), w: r.width, h: r.height };
        }),
      );
      expect(new Set(boxes.map((b) => b.y)).size).toBe(1); // the timers share one line
      for (const b of boxes) {
        expect(b.w).toBeGreaterThanOrEqual(38); // was 16-31px wide
        expect(b.h).toBeGreaterThanOrEqual(44);
        expect(b.x).toBeGreaterThanOrEqual(0);
        expect(b.x + b.w).toBeLessThanOrEqual(width + 0.5);
      }
    }
    const pb = await panel.boundingBox();
    expect(pb.height).toBeLessThan(135); // two lines, not two stacked blocks
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });

test('/new Later timers: tapping the chosen time again deselects it at once, and a slow refresh that started earlier cannot bring it back', async ({
  page,
}) => {
  await open(page, '/new', 390, 709);
  await page.locator('#ui2GroupPicker').click(); // Timer & groups
  const pill = page
    .locator('#ui2LaterPanel .ui2-later-line')
    .first()
    .locator('.delay-pill', { hasText: '45m' });
  await pill.click();
  await expect(pill).toHaveAttribute('aria-pressed', 'true');
  await page.waitForFunction(() => !autoPolling); // no refresh in flight
  // A status refresh whose answer is slow: the server builds it now (the timer is still scheduled), it arrives later.
  let held = false,
    delivered = false;
  await page.route('**/autopilot', async (r) => {
    if (held) return r.continue();
    held = true;
    const answer = await r.fetch();
    await new Promise((done) => setTimeout(done, 1600));
    await r.fulfill({ response: answer });
    delivered = true;
  });
  await page.evaluate(() => {
    pollAuto(); // not awaited: the refresh stays in flight while we tap
  });
  await page.waitForTimeout(300);
  await pill.click(); // deselect while that refresh is on its way
  await expect(pill).toHaveAttribute('aria-pressed', 'false', { timeout: 400 }); // at once, not after the server
  await expect.poll(() => delivered, { timeout: 5000 }).toBe(true); // the old answer has arrived
  await page.waitForTimeout(150);
  // No retrying here: the pill must not have flipped back, even for a moment.
  expect(await pill.getAttribute('aria-pressed')).toBe('false');
  await expect(pill).not.toHaveClass(/is-pending/);
});

test('/new phone reader: swipe the message left for the next version, right for the one before', async ({ page, request }) => {
  const headers = { Authorization: 'Bearer manual-fix-preview-key' };
  await open(page, '/new#/preview', 390); // opening the reader saves the original message
  await expect(page.locator('#focusFormatted')).not.toHaveText('');
  await expect.poll(async () => (await (await request.get('/focus-bank?kind=group', { headers })).json()).source || '').not.toBe('');
  // ten versions that differ only in their last line (a version must keep the message's first line)
  const { source } = await (await request.get('/focus-bank?kind=group', { headers })).json();
  const messages = Array.from({ length: 10 }, (_, k) => source.replace(/\n([^\n]*)$/, `\n(swipe ${k + 1}) $1`));
  const made = await request.post('/focus-bank', { headers, data: { kind: 'group', action: 'manual', messages } });
  expect(made.ok(), await made.text()).toBe(true);
  expect((await made.json()).items.length).toBe(10);
  await page.reload();

  await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText('Base +10');
  const cdp = await page.context().newCDPSession(page);
  const box = await page.locator('#focusFormatted').boundingBox();
  const y = box.y + box.height / 2;
  const swipe = async (from, to) => {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: from, y }] });
    for (let i = 1; i <= 8; i++)
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: from + ((to - from) * i) / 8, y }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForTimeout(500); // the slide-in finishes before the next swipe
  };
  await swipe(320, 80);
  await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText('1/10');
  await expect(page.locator('#focusFormatted')).toContainText('(swipe 1)');
  await swipe(320, 80);
  await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText('2/10');
  await swipe(80, 320);
  await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText('1/10');
  // a short drag snaps back and changes nothing
  await swipe(200, 182); // 18px: under both the 40px distance and the 20px flick
  await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText('1/10');
});
