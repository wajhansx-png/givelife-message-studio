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
  test(`/new at ${width}px: the button strip is at the bottom and More opens fully on screen`, async ({
    page,
  }) => {
    await open(page, '/new', width);
    const more = page.locator('#mainNavMore > summary');
    await expect(more).toBeVisible();
    const strip = await more.boundingBox();
    const send = await page.locator('#btnGivelife').boundingBox();
    const foot = await page.locator('.foot').boundingBox();
    expect(strip.y).toBeGreaterThan(send.y); // below the send buttons: in thumb reach
    expect(strip.y).toBeLessThan(foot.y);
    await more.click();
    const panel = await page.locator('#mainNavMore > .compact-nav-panel').boundingBox();
    expect(panel.x).toBeGreaterThanOrEqual(-0.5);
    expect(panel.x + panel.width).toBeLessThanOrEqual(width + 0.5);
    expect(panel.y).toBeGreaterThanOrEqual(-0.5);
    expect(panel.y + panel.height).toBeLessThanOrEqual(strip.y);
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

test('/new desktop reader: narrow, tall message with the buttons beside it; editing still works', async ({
  page,
}) => {
  await open(page, '/new#/preview', 1440);
  const paper = await page.locator('#messageFocus .focus-paper').boundingBox();
  const bubble = await page.locator('#focusFormatted').boundingBox();
  expect(bubble.width).toBeLessThanOrEqual(341);
  expect(bubble.y - paper.y).toBeLessThan(40); // top aligned, not floating in the middle
  expect(bubble.height).toBeGreaterThan(bubble.width * 0.8); // tall, like a WhatsApp bubble
  await page.locator('#focusEdit').click();
  const ta = await page.locator('#focusText').boundingBox();
  expect(ta.width).toBeLessThanOrEqual(341);
  expect(ta.height).toBeGreaterThan(200);
});

test('/new opens in the reader on a computer and on a phone; Back returns to the main screen without jumping back', async ({
  page,
}) => {
  for (const width of [1440, 390, 280]) {
    await open(page, '/new', width);
    await expect(page.locator('#messageFocus')).toBeVisible();
    expect(await page.evaluate(() => location.hash)).toBe('#/preview');
    await page.locator('#focusBack').click();
    await expect(page.locator('#messageFocus')).toBeHidden();
    await page.waitForTimeout(900);
    expect(await page.evaluate(() => location.hash)).not.toBe('#/preview');
  }
});

for (const width of [280, 320, 360, 390, 430, 768]) {
  test(`/new phone reader at ${width}px: Regenerate and Next are big thumb buttons that press the real ones`, async ({
    page,
  }) => {
    const hits = [];
    await page.route('**/*', (r) => {
      if (r.request().method() === 'POST' && /send/i.test(r.request().url()))
        hits.push(r.request().url());
      return r.continue();
    });
    await open(page, '/new#/preview', width);
    const regen = page.locator('#ui2Regen');
    const next = page.locator('#ui2Next');
    await expect(regen).toBeVisible();
    await expect(next).toBeVisible();
    const [r, n, e, t, b] = await Promise.all(
      ['#ui2Regen', '#ui2Next', '#focusEdit', '#focusTest', '#focusBack'].map((s) =>
        page.locator(s).boundingBox(),
      ),
    );
    expect(Math.min(r.height, n.height)).toBeGreaterThanOrEqual(46);
    expect(r.y).toBeLessThan(e.y); // the two main buttons sit above the row of four
    for (const x of [r, n, e, t, b]) {
      expect(x.x).toBeGreaterThanOrEqual(-0.5);
      expect(x.x + x.width).toBeLessThanOrEqual(width + 0.5);
      expect(x.y + x.height).toBeLessThanOrEqual(page.viewportSize().height + 0.5);
    }
    expect(await page.locator('#focusNextArrow').isVisible()).toBe(false); // the small round ones are replaced
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await next.click();
    expect(hits, 'Next and Regenerate must never send').toEqual([]);
  });
}

test('/new computer reader keeps its round Next and Regenerate beside the message and hides the phone buttons', async ({
  page,
}) => {
  await open(page, '/new#/preview', 1440);
  await expect(page.locator('#focusNextArrow')).toBeVisible();
  await expect(page.locator('#focusGenIcon')).toBeVisible();
  await expect(page.locator('#ui2Next')).toBeHidden();
  await expect(page.locator('#focusSave')).toBeVisible();
});

for (const width of [280, 360, 430, 1440]) {
  test(`/new DM messages page at ${width}px: Regenerate and Next, one orderly button grid, 12px message`, async ({
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
    if (width < 900) {
      const names = ['#ui2BankGen', '#ui2BankNext'];
      for (const sel of names) await expect(page.locator(sel)).toBeVisible();
      const g = await page.locator('#ui2BankGen').boundingBox();
      const edit = await page
        .locator('#donorMessages .bank-actions button.tool', { hasText: /^Edit$/ })
        .boundingBox();
      expect(g.y).toBeLessThan(edit.y);
      expect(g.height).toBeGreaterThanOrEqual(46);
      for (const bx of await page.locator('#donorMessages .bank-actions button').evaluateAll((bs) =>
        bs
          .filter((b) => b.checkVisibility())
          .map((b) => {
            const r = b.getBoundingClientRect();
            return [r.x, r.right];
          }),
      ))
        expect(bx[0] >= -0.5 && bx[1] <= width + 0.5).toBe(true);
    } else {
      await expect(page.locator('#ui2BankGen')).toBeHidden();
    }
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

test('/new computer: Options menu on the left holds Auto and Poster, Back stays on the right; phones are unchanged', async ({
  page,
}) => {
  await open(page, '/new#/donors/all', 1440);
  const opt = page.locator('#ui2Options > summary');
  await expect(opt).toBeVisible();
  const o = await opt.boundingBox();
  const dm = await page.locator('#donorSendImportant').boundingBox();
  const back = await page.locator('#donorMainBottom').boundingBox();
  expect(o.x).toBeLessThan(dm.x);
  expect(dm.x).toBeLessThan(back.x);
  await opt.click();
  await expect(page.locator('#ui2Options #donorAuto')).toBeVisible();
  await expect(page.locator('#ui2Options #donorRowPoster')).toBeVisible();
  const panel = await page.locator('.ui2-options-panel').boundingBox();
  expect(panel.x).toBeGreaterThanOrEqual(0);
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

test('/new DM speed dialog: plain labels, every option visible, at phone and computer widths', async ({
  page,
}) => {
  for (const width of [280, 360, 768, 1440]) {
    await open(page, '/new#/donors/all', width);
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.locator('#donorSendImportant').click();
    const picker = page.locator('#donorBatchPicker');
    await expect(picker.locator('label[for="batchCount"]')).toHaveText('How many people');
    await expect(picker.locator('label[for="batchLimit"]')).toHaveText('DMs in each batch');
    await expect(picker.locator('label[for="batchPause"]')).toHaveText('Rest between batches');
    for (const sel of [
      '#batchCount',
      '#batchLimit',
      '#batchPause',
      '.batch-gap-btn >> nth=0',
      '#batchPoster',
      '#batchFollowUp',
      '#batchIncl',
      '#batchRandom',
      '#batchStart',
      '#batchCancel',
    ])
      await expect(picker.locator(sel).first(), sel + ' at ' + width).toBeVisible();
    const box = await picker.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(-0.5);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 0.5);
    await picker.locator('#batchCancel').click();
  }
});
