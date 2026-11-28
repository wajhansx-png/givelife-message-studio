/* Message screen (owner's layout): every button does its real job. Copy · Edit · Save base · ⋯ More on the message;
   ‹ › (and swipe on phones); English · Urdu + English · Trigger · Style fix; Generate · Test · Back.
   Fake WhatsApp and fake AI only: nothing is sent anywhere real. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 733;
let server;
test.use({
  baseURL: `http://127.0.0.1:${port}`,
  permissions: ['clipboard-read', 'clipboard-write'],
});
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
const BASE =
  '*Base wording* of the case. Please help today. Rs. 5,000 needed. Easypaisa ONLY 03097458815';
const V1 =
  '*Second wording* of the case. Please help today. Rs. 5,000 needed. Easypaisa ONLY 03097458815';
const V2 =
  '*Third wording* of the case. Please help today. Rs. 5,000 needed. Easypaisa ONLY 03097458815';
test.beforeEach(async () => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await api(port, '/focus-bank', { kind: 'group', action: 'manual', messages: [V1, V2] });
});

async function open(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await expect(page.locator('#focusFormatted')).toBeVisible();
  await expect(page.locator('#ui2MsgTools')).toBeVisible();
}
const posts = (page) => {
  const list = [];
  page.on('request', (r) => r.method() === 'POST' && list.push(new URL(r.url()).pathname));
  return list;
};
const label = (page) => page.locator('#ui2Swipe .ui2-ver').innerText();
const idle = (page) =>
  expect(page.locator('#messageFocus .ui2-gen-btn')).toBeEnabled({ timeout: 20000 });

for (const [width, height] of [
  [390, 844],
  [1280, 800],
])
  test(`${width}: the buttons are where the owner put them, in that order`, async ({ page }) => {
    await open(page, width, height);
    const names = (sel) =>
      page.locator(sel).evaluateAll((els) =>
        els
          .filter((e) => e.getBoundingClientRect().width > 0)
          .sort((a, b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x)
          .map((e) => (e.getAttribute('aria-label') || e.innerText).trim()),
      );
    expect(
      await names('#ui2MsgTools > :is(button, details) , #ui2MsgTools > details > summary'),
    ).toEqual(expect.arrayContaining(['Copy', 'Edit', 'Save base']));
    const tools = await names('#ui2MsgTools > button, #ui2MsgTools > details');
    expect(tools.slice(0, 3)).toEqual(['Copy', 'Edit', 'Save base']);
    // one capsule [Copy · Edit · Save · More]: icon with a short word under it, all four the same size, one line
    const tops = [];
    for (const sel of [
      '#focusCopy',
      '#focusEdit',
      '#ui2MsgTools .ui2-base-btn',
      '#ui2MsgTools .focus-rail-more > summary',
    ]) {
      const b = await page.locator(sel).boundingBox();
      expect(b.width, sel).toBeGreaterThanOrEqual(38);
      expect(b.height, sel).toBe(50);
      expect(
        await page.locator(sel).evaluate((e) => parseFloat(getComputedStyle(e).fontSize)),
        sel,
      ).toBe(11);
      tops.push(Math.round(b.y));
    }
    expect(new Set(tops).size).toBe(1);
    expect(
      await page
        .locator('#ui2MsgTools .ui2-base-btn')
        .evaluate((e) => getComputedStyle(e, '::after').content),
    ).toBe('"Save"');
    expect((await page.locator('#ui2Swipe').boundingBox()).height).toBe(50); // ‹ 3/5 › capsule: same height
    expect(await names('#ui2RewriteRow button')).toEqual(
      ['English', 'Urdu + English', 'Trigger', 'Style fix'], // a phone shows "Urdu+Eng" for the same button
    );
    const dock = await names(
      '#messageFocus .ui2-reader-dock > :is(.ui2-gen-btn, #focusTest, #focusBack)',
    );
    expect(dock.length).toBe(3);
    expect(dock[1]).toBe('Test');
    expect(dock[2]).toMatch(/Back/); // Back is right-most
    // one Back only, no words-plus-icon clutter on the rewrites
    expect(await page.locator('#messageFocus button:visible', { hasText: 'Back' }).count()).toBe(1);
    const dockBox = await page.locator('#messageFocus .ui2-reader-dock').boundingBox();
    if (width >= 900) {
      // computer: the bottom buttons are centred
      const gen = await page.locator('#messageFocus .ui2-gen-btn').boundingBox();
      const back = await page.locator('#focusBack').boundingBox();
      expect(Math.abs((gen.x + back.x + back.width) / 2 - width / 2)).toBeLessThan(3);
    } else {
      expect(dockBox.y + dockBox.height).toBeGreaterThan(height - 2); // phone: at the very bottom (thumb)
    }
  });

for (const [width, height] of [
  [390, 844],
  [1280, 800],
])
  test(`${width}: Copy, Edit, More, Generate, ‹ ›, Save base, rewrites, Test and Back all work`, async ({
    page,
  }) => {
    await open(page, width, height);
    const sent = posts(page);
    // Copy copies the message on screen
    await page.locator('#focusCopy').click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toContain('03097458815');
    // Edit opens the editor; pressing it again closes it
    const editing = () =>
      page.evaluate(() =>
        ['focusText', 'ui2Live'].some((id) => {
          const e = document.getElementById(id);
          return e && !e.hidden && e.getBoundingClientRect().height > 0;
        }),
      );
    await page.locator('#focusEdit').click();
    await expect.poll(editing).toBe(true);
    await page.locator('#focusEdit').click();
    if (await page.locator('#focusBaseDialog[open]').count())
      await page.locator('#focusBaseCancel').click();
    await expect.poll(editing).toBe(false);
    // ⋯ More opens fully on the screen, with Save Base, Generate 5 and the files
    await page.locator('#ui2MsgTools .focus-rail-more > summary').click();
    const list = page.locator('#ui2MsgTools .focus-rail-more > div');
    await expect(list).toBeVisible();
    const box = await list.boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(-1);
    expect(box.y + box.height).toBeLessThanOrEqual(height + 1);
    await expect(list.locator('#ui2ReaderExtras')).toHaveCount(1);
    await page.keyboard.press('Escape');
    await page
      .locator('#ui2MsgTools .focus-rail-more > summary')
      .click({ force: true })
      .catch(() => {});
    await page.evaluate(
      () => (document.querySelector('#ui2MsgTools .focus-rail-more').open = false),
    );
    // Generate writes new versions (fake AI); then ‹ › step through them
    await page.locator('#ui2Swipe .ui2-swipe-next').click();
    await expect(page.locator('#focusFormatted')).toContainText('Second wording');
    await page.locator('#ui2Swipe .ui2-swipe-prev').click();
    await expect(page.locator('#focusFormatted')).toContainText('Base wording');
    // Save base (💾) asks to make the version on screen the base (Cancel keeps everything)
    await page.locator('#ui2Swipe .ui2-swipe-next').click();
    await page.locator('#ui2MsgTools .ui2-base-btn').click();
    await expect(page.locator('#focusBaseDialog')).toBeVisible();
    await page.locator('#focusBaseCancel').click();
    // Generate asks the server for a fresh 5 versions
    const bank = [];
    await page.route('**/focus-bank', async (route) => {
      if (route.request().method() === 'POST')
        bank.push(JSON.parse(route.request().postData() || '{}').action);
      await route.continue();
    });
    await page.locator('#messageFocus .ui2-gen-btn').click();
    await expect.poll(() => bank).toContain('regenerate');
    // each rewrite button asks for a new message
    for (const sel of [
      '[data-lang="en"]',
      '[data-lang="ur"]',
      '[data-trigger]',
      '#focusStyleFix',
    ]) {
      await idle(page);
      await expect(page.locator('#ui2RewriteRow ' + sel)).toBeEnabled({ timeout: 20000 });
      const n = sent.length;
      await page.locator('#ui2RewriteRow ' + sel).click();
      await expect.poll(() => sent.length, { message: sel }).toBeGreaterThan(n);
    }
    // Test with a new, unsaved text on screen does not send it (it would have to replace the base): it says why
    await idle(page);
    const t = sent.length;
    if (
      (await page.locator('#focusVersion').textContent()).includes('not saved') ||
      (await page.locator('#ui2Swipe .ui2-ver').textContent()).includes('not saved')
    ) {
      await page.locator('#focusTest').click();
      await expect(page.locator('#ui2Note')).toContainText('not saved yet');
      await page.locator('#ui2MsgTools .ui2-base-btn').click(); // the owner keeps it: Save base
      await page.locator('#focusBaseSave').click();
      await expect(page.locator('#focusBaseDialog')).toBeHidden();
      await idle(page);
    }
    // Test goes to the test group (fake WhatsApp)
    await page.locator('#focusTest').click();
    await expect.poll(() => sent.slice(t).join(' ')).toMatch(/send|test/i);
    // Back closes the screen
    await page.locator('#focusBack').click();
    await expect(page.locator('#messageFocus')).toBeHidden();
  });

test('phone: a swipe on the message changes the version; computer: a mouse drag does not', async ({
  page,
}) => {
  await open(page, 390, 844);
  await expect.poll(() => label(page)).toMatch(/\d/);
  const swipe = async () => {
    const b = await page.locator('#focusFormatted').boundingBox();
    await page.mouse.move(b.x + b.width * 0.8, b.y + 60);
    await page.mouse.down();
    await page.mouse.move(b.x + b.width * 0.3, b.y + 62, { steps: 8 });
    await page.mouse.up();
  };
  let was = await label(page);
  await swipe();
  await expect.poll(() => label(page)).not.toBe(was);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.waitForTimeout(300);
  was = await label(page);
  await swipe();
  await page.waitForTimeout(500);
  expect(await label(page)).toBe(was);
});
