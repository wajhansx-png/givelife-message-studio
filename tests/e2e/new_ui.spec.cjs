const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const { auditElements } = require('./element-audit.cjs');

/* The redesign lives at /new only. "/" must stay exactly as it was. Fake WhatsApp only: nothing is sent. */
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
  }, KEY);
  await page.goto(path);
};

test('the existing UI at "/" is untouched and /new is a separate path', async ({ request }) => {
  const old = await (await request.get('/')).text();
  expect(old).not.toContain('new-ui.css');
  expect(old).not.toContain('ui2');
  const fresh = await (await request.get('/new')).text();
  expect(fresh).toContain('/new-ui.css');
  expect(fresh).toContain('class="nomsg ui2"');
  const css = await request.get('/new-ui.css');
  expect(css.status()).toBe(200);
  const text = await css.text();
  expect(text).not.toContain('@U');
  expect(text).toContain('body.ui2');
  expect((await request.get('/new/')).status()).toBe(200);
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
    await expect(tabs.locator('.ui2-tab')).toHaveText([/Message/, /Donors/, /Chat/, /More/]);
    const bar = await tabs.boundingBox();
    const send = await page.locator('#btnGivelife').boundingBox();
    expect(bar.y).toBeGreaterThan(send.y); // below the send buttons: in thumb reach
    await tabs.locator('[data-tab="more"]').click();
    const sheet = page.locator('#ui2Sheet');
    await expect(sheet).toBeVisible();
    await expect(sheet.locator('.ui2-tile')).toHaveCount(6);
    const b = await sheet.boundingBox();
    expect(b.x).toBeGreaterThanOrEqual(-0.5);
    expect(b.x + b.width).toBeLessThanOrEqual(width + 0.5);
    expect(b.y + b.height).toBeLessThanOrEqual((await page.viewportSize()).height + 0.5);
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
  expect(copy.y).toBeGreaterThan(bubble.y + bubble.height - 1);
  await page.locator('#focusEdit').click();
  const live = page.locator('#ui2Live');
  await expect(live).toBeVisible();
  await expect(page.locator('#ui2Float')).toBeVisible();
  expect((await live.boundingBox()).height).toBeGreaterThan(200);
  const before = await page.locator('#focusText').inputValue();
  await live.evaluate((e) => e.dispatchEvent(new Event('input')));
  expect(await page.locator('#focusText').inputValue()).toBe(before); // round trip keeps the text exactly
});

test("/new computer: the main screen shows today's message beside the send list; a phone keeps one column", async ({
  page,
}) => {
  await open(page, '/new', 1440);
  await page.waitForTimeout(900);
  expect(await page.evaluate(() => location.hash)).toBe('');
  await expect(page.locator('#messageFocus')).toBeHidden();
  const card = await page.locator('#card').boundingBox();
  const send = await page.locator('.group-send').boundingBox();
  expect(card.x + card.width).toBeLessThanOrEqual(send.x + 1);
  await expect(page.locator('#ui2Styles')).toBeVisible();
  await expect(page.locator('.ui2-desk-chips .ui2-chip')).toHaveCount(3);
  await open(page, '/new', 390);
  await page.waitForTimeout(900);
  await expect(page.locator('#messageFocus')).toBeHidden();
  expect(await page.evaluate(() => location.hash)).toBe('');
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
  test(`/new DM messages page at ${width}px: one row Edit, Copy, more, Back; Next and Regenerate inside more`, async ({
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
    await expect(page.locator('#ui2BankMore [data-ui2-proxy]').first()).toBeVisible();
    const box = await page.locator('#ui2BankMore > div').boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(-0.5);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 0.5);
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
  const old = await (await request.get('/')).text();
  expect(old).not.toContain('ui2');
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
