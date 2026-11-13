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
      /Case/,
      /Message/,
      /Donors/,
      /Chat/,
      /More/,
    ]);
    const bar = await tabs.boundingBox();
    const send = await page.locator('#btnGivelife').boundingBox();
    expect(bar.y).toBeGreaterThan(send.y); // below the send buttons: in thumb reach
    await tabs.locator('[data-tab="more"]').click();
    const sheet = page.locator('#ui2Sheet');
    await expect(sheet).toBeVisible();
    await expect(sheet.locator('.ui2-tile')).toHaveCount(8); // Case page + New case + the six tiles
    await expect(sheet.locator('.ui2-sheet-x')).toBeVisible(); // a cross closes it
    await sheet.locator('.ui2-sheet-x').click();
    await expect(sheet).toBeHidden();
    await tabs.locator('[data-tab="more"]').click();
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

test('/new computer: every option is one clear button in the bottom bar, and nothing is shown twice', async ({
  page,
}) => {
  await open(page, '/new', 1440, 900);
  const bar = page.locator('#ui2Tabs');
  await expect(bar).toBeVisible();
  await expect(bar.locator('.ui2-tab')).toHaveText([
    /Case/,
    /Message/,
    /Donors/,
    /Chat/,
    /Notes/,
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
    expect(r.height).toBeGreaterThanOrEqual(56);
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
  expect(Math.abs(t.x + t.width / 2 - 720)).toBeLessThan(40);
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
    ['chat', '#histMain'],
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

test('/new phone: Chat has no top bar and Back sits near the thumb', async ({ page }) => {
  await open(page, '/new#/chat', 390);
  await expect(page.locator('#hist')).toBeVisible();
  await expect(page.locator('#hist > header')).toBeHidden();
  const back = await page.locator('#histMain').boundingBox();
  expect(back.y).toBeGreaterThan(740 * 0.6);
  await page.locator('#histMain').click();
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
  await expect(page.locator('#donorDeselectAll')).toBeHidden(); // only on the Important tab
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
  await expect(page.locator('.ui2-bank-nav > button')).toHaveCount(2);
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

test('/new phone: Regenerate and Next sit inside the green message (small, right) and in the reader', async ({
  page,
}) => {
  await open(page, '/new', 390);
  const card = await page.locator('#card').boundingBox();
  const nav = await page.locator('#ui2GnavMain').boundingBox();
  // Inside the message card, bottom right: no row under the message any more, so the message keeps that height.
  await expect(page.locator('#card #ui2GnavMain')).toHaveCount(1);
  expect(nav.x).toBeGreaterThan(card.x + card.width / 2);
  expect(nav.x + nav.width).toBeLessThanOrEqual(card.x + card.width + 0.5);
  expect(nav.y + nav.height).toBeLessThanOrEqual(card.y + card.height + 0.5);
  expect(nav.y).toBeGreaterThanOrEqual(card.y);
  await expect(page.locator('#ui2GnavMain .ui2-gbtn')).toHaveText(['Regenerate', 'Next']);
  for (const [i, name] of ['Regenerate', 'Next'].entries()) {
    const b = page.locator('#ui2GnavMain .ui2-gbtn').nth(i);
    await expect(b).toHaveAccessibleName(name);
    const box = await b.boundingBox();
    expect(box.width).toBeGreaterThanOrEqual(40);
    expect(box.height).toBeGreaterThanOrEqual(40);
    expect(box.width).toBeLessThanOrEqual(48); // small
  }
  // The message text is not under the buttons: its last line can scroll clear of them.
  expect(
    await page.locator('#card #chat').evaluate((n) => parseFloat(getComputedStyle(n).paddingBottom)),
  ).toBeGreaterThanOrEqual(46);
  // Tapping a button must not also open the reader (the card itself opens it).
  await page.locator('#ui2GnavMain .ui2-gnext').click(); // presses the real New wording button
  await expect(page.locator('#messageFocus')).toBeHidden();
  await open(page, '/new#/preview', 390);
  await expect(page.locator('#ui2GnavReader .ui2-gbtn')).toHaveText(['Regenerate', 'Next']);
  await page.locator('#ui2GnavReader .ui2-gnext').click();
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
  await expect(tabs).toHaveText(['Case', 'Message', 'Donors', 'Chat', 'More']);
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
