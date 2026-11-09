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

test('/new chat chips only fill the box and never send, and the chat fits every phone width', async ({
  page,
}) => {
  const sent = [];
  await page.route('**/*', (r) => {
    if (r.request().method() === 'POST' && /send|chat|command|reply/i.test(r.request().url()))
      sent.push(r.request().url());
    return r.continue();
  });
  for (const width of [280, 320, 360, 390, 768, 1440]) {
    await open(page, '/new#/chat', width);
    const form = page.locator('#histForm');
    await expect(form).toBeVisible();
    const chips = page.locator('#hist .ui2-chips button');
    await expect(chips).toHaveCount(3);
    await chips.nth(1).click();
    await expect(page.locator('#histForm textarea')).toHaveValue('send all');
    expect(sent, 'a chip must never send').toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    const back = await page.locator('#histMain, #histClose').first().boundingBox();
    const last = await chips.nth(2).boundingBox();
    if (back && last && width < 900) {
      const clash = !(
        last.x + last.width <= back.x + 1 ||
        last.y + last.height <= back.y ||
        last.y >= back.y + back.height
      );
      expect(clash, `chip under the Back button at ${width}px`).toBe(false);
    }
  }
});

test('/new on a computer opens in the reader; Back returns to the chat; a phone stays on the main screen', async ({
  page,
}) => {
  await open(page, '/new', 1440);
  await expect(page.locator('#messageFocus')).toBeVisible();
  await expect(page.locator('#btnGivelife')).toBeVisible();
  expect(await page.evaluate(() => location.hash)).toBe('#/preview');
  await page.locator('#focusBack').click();
  await expect(page.locator('#messageFocus')).toBeHidden();
  await page.waitForTimeout(900); // it must not jump back into the reader
  expect(await page.evaluate(() => location.hash)).not.toBe('#/preview');
  await open(page, '/new', 390);
  await page.waitForTimeout(900);
  await expect(page.locator('#messageFocus')).toBeHidden();
  expect(await page.evaluate(() => location.hash)).toBe('');
});
