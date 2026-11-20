/* Desktop Message home (owner's pick): the menu down the left, the whole message in the middle at a small reading
   size with no scroll inside it, and Send + the other groups right beside it, level with the message. Phones are
   not touched. Fake WhatsApp only: nothing is sent. */
const { test, expect } = require('@playwright/test');

const LONG =
  "<div><b>A mother has folded her hands for her little girl's life. Mirha's lungs are close to failing.</b></div>" +
  '<div><i>Mirha is just 2. Her lungs are badly affected, and one serious chest infection after another keeps hitting her. Every single breath is hard for her, and her life is at risk.</i></div>' +
  '<div><b>She needs 2 oxygen cylinders, and she needs them right away.</b></div>' +
  '<div>Rs. 18,000 LEFT</div><div><b><i>Only 9 people giving Rs. 2,000, or 1000 rs from 26 people, and her life can be helped</i></b></div>' +
  '<div><b>Easypaisa ONLY</b><br>03097458815<br><b>Wajdan Khan (GiveLife Foundation account)</b></div>';

async function open(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'));
  await page.goto('/new');
  await expect(page.locator('#groupPreview')).toBeVisible();
}

for (const [width, height] of [[900, 600], [1024, 600], [1280, 720], [1366, 768], [1920, 1080], [980, 2000]])
  test(`desktop home ${width}x${height}: menu left, full message, Send beside it`, async ({ page }) => {
    await open(page, width, height);
    await page.evaluate((m) => (document.getElementById('groupPreview').innerHTML = m), LONG);
    await page.waitForTimeout(200);
    const tabs = await page.locator('#ui2Tabs').boundingBox();
    const card = await page.locator('#card').boundingBox();
    const send = await page.locator('#btnGivelife').boundingBox();
    expect(tabs.x).toBeLessThan(20); // the menu is on the left edge
    expect(tabs.x + tabs.width).toBeLessThanOrEqual(card.x);
    expect(send.x).toBeGreaterThanOrEqual(card.x + card.width); // Send is beside the message
    expect(send.x - (card.x + card.width)).toBeLessThan(60);
    expect(Math.abs(send.y - card.y)).toBeLessThan(60); // level with the message: read down, look right
    expect(card.y + card.height).toBeLessThanOrEqual(height); // the whole message is on the screen
    const r = await page.evaluate(() => {
      const chat = document.getElementById('chat');
      return {
        inner: chat.scrollHeight - chat.clientHeight,
        page: document.documentElement.scrollHeight - innerHeight,
        size: parseFloat(getComputedStyle(document.getElementById('groupPreview')).fontSize),
      };
    });
    expect(r.inner).toBeLessThanOrEqual(1); // no scroll inside the message
    expect(r.page).toBeLessThanOrEqual(1);
    expect(r.size).toBeGreaterThanOrEqual(11); // small, quick to read, never tiny
    expect(r.size).toBeLessThanOrEqual(14);
    await expect(page.locator('#btnFree')).toBeVisible(); // other groups shown, not hidden behind a menu
    await expect(page.locator('#sendAll')).toBeVisible();
    for (const sel of ['#btnGivelife', '#btnFree', '#sendAll', '#ui2Later']) {
      const b = await page.locator(sel).boundingBox();
      expect(b.height, sel).toBeGreaterThanOrEqual(40);
      expect(b.height, sel).toBeLessThanOrEqual(46);
    }
  });

test('a message line stays short enough to read fast on a wide screen', async ({ page }) => {
  await open(page, 1920, 1080);
  const card = await page.locator('#card').boundingBox();
  expect(card.width).toBeLessThanOrEqual(700);
});

for (const width of [390, 768])
  test(`phone and tablet keep the bottom menu at ${width}px`, async ({ page }) => {
    await open(page, width, 844);
    const tabs = await page.locator('#ui2Tabs').boundingBox();
    expect(tabs.y).toBeGreaterThan(600);
  });

for (const width of [900, 980, 1280])
  test(`"Reconnect WhatsApp" does not touch Auto at ${width}px, even in a crowded bar`, async ({ page }) => {
    await open(page, width, 900);
    const r = await page.evaluate(() => {
      const wa = document.getElementById('whatsappConnection'), live = document.getElementById('live');
      wa.dataset.state = 'offline';
      wa.parentElement.style.maxWidth = '560px';
      const a = wa.getBoundingClientRect(), l = live.getBoundingClientRect();
      return { right: a.right, left: l.left, scroll: wa.scrollWidth, client: wa.clientWidth };
    });
    expect(r.right).toBeLessThanOrEqual(r.left + 1);
    expect(r.scroll).toBeLessThanOrEqual(r.client + 1);
  });

test('‹ › show each saved version and come back to the base; Send follows the version on screen', async ({ page }) => {
  await open(page, 1280, 800);
  await page.evaluate(async () => {
    const post = (b) =>
      fetch('/focus-bank', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind: 'group', ...b }) });
    const d = await (await fetch('/focus-bank?kind=group')).json();
    if (!d.revision) await post({ action: 'save', text: d.source || document.getElementById('group').value });
    await post({ action: 'manual', messages: ['First version. Rs. 25,000 needed.', 'Second version. Rs. 25,000 needed.'] });
  });
  const msg = page.locator('#groupPreview');
  const base = await msg.textContent();
  await page.locator('#homeNext').click();
  await expect(msg).toContainText('First version');
  expect(await page.evaluate(() => window.focusShownVersion)).toContain('First version');
  await page.locator('#homeNext').click();
  await expect(msg).toContainText('Second version');
  await page.locator('#homeNext').click();
  expect(await msg.textContent()).toBe(base);
  expect(await page.evaluate(() => window.focusShownVersion)).toBe('');
  await page.locator('#homePrev').click(); // back from the base goes to the last version
  await expect(msg).toContainText('Second version');
  // only the two arrows under the message, icons only, in the middle
  const tools = page.locator('#card .tools');
  await expect(tools.locator('button:visible, summary:visible')).toHaveCount(2);
  const card = await page.locator('#card').boundingBox();
  const nav = await page.locator('#ui2VerNav').boundingBox();
  expect(Math.abs(nav.x + nav.width / 2 - (card.x + card.width / 2))).toBeLessThan(12);
  expect((await page.locator('#homeNext').innerText()).trim()).toBe('');
});

test('Copy, Edit and More are small icons inside the message; Copy copies, Edit edits', async ({ browser }) => {
  const ctx = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  await open(page, 1280, 800);
  const bubble = await page.locator('#groupPreview').boundingBox();
  for (const sel of ['#copy', '#edit', '#card .overflow-tools > summary']) {
    const b = await page.locator(sel).boundingBox();
    expect(b.x, sel).toBeGreaterThan(bubble.x);
    expect(b.x + b.width, sel).toBeLessThanOrEqual(bubble.x + bubble.width + 1);
    expect(b.y + b.height, sel).toBeLessThanOrEqual(bubble.y + bubble.height + 1);
    expect(b.width, sel).toBeLessThanOrEqual(34); // an icon, not a word button
  }
  await page.locator('#copy').click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('Yousuf');
  await page.locator('#edit').click();
  await expect(page.locator('#edit')).toHaveAttribute('data-state', 'done');
  await page.locator('#edit').click();
  await expect(page.locator('#edit')).not.toHaveAttribute('data-state', 'done');
  await page.locator('#card .overflow-tools > summary').click();
  await expect(page.getByRole('button', { name: 'Change poster' })).toBeVisible();
  await ctx.close();
});

test('the menu folds with Hide and opens with Show (remembered)', async ({ page }) => {
  await open(page, 1280, 800);
  const wide = (await page.locator('#ui2Tabs').boundingBox()).width;
  await page.locator('#ui2RailHide').click();
  const narrow = (await page.locator('#ui2Tabs').boundingBox()).width;
  expect(narrow).toBeLessThan(70);
  expect(wide).toBeGreaterThan(150);
  await page.reload();
  await expect(page.locator('#ui2RailHide')).toHaveAttribute('aria-label', 'Show the menu');
  await page.locator('#ui2RailHide').click();
  expect((await page.locator('#ui2Tabs').boundingBox()).width).toBeGreaterThan(150);
});
