/* The options the owner uses every day are in front, not hidden in More. Computer: Giki 1, Giki 2 and Thank donors are
   items in the left menu. Phone: Giki 1 and Giki 2 are two small buttons just above the bottom bar (the bar keeps its
   five buttons), and the message is still fully visible. Fake WhatsApp only: nothing is sent. */
const { test, expect } = require('@playwright/test');

async function open(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'));
  await page.goto('/new');
  await expect(page.locator('#groupPreview')).toBeVisible();
  await expect(page.locator('.ui2-tab[data-tab="message"]')).toBeVisible();
}

const LONG =
  "<div><b>A mother has folded her hands for her little girl's life. Mirha's lungs are close to failing.</b></div>" +
  '<div><i>Mirha is just 2. Her lungs are badly affected, and one serious chest infection after another keeps hitting her. Every single breath is hard for her, and her life is at risk.</i></div>' +
  '<div><b>She needs 2 oxygen cylinders, and she needs them right away.</b></div><div>Rs. 18,000 LEFT</div>' +
  '<div><b>Easypaisa ONLY</b><br>03097458815<br><b>Wajdan Khan (GiveLife Foundation account)</b></div>';

for (const [width, height] of [[1280, 720], [1920, 1080]])
  test(`computer ${width}: Giki 1, Giki 2 and Thank donors are in the left menu`, async ({ page }) => {
    await open(page, width, height);
    // top to bottom, the way the owner sees the menu
    const shown = await page.locator('#ui2Tabs .ui2-tab:visible').evaluateAll((els) =>
      els.map((e) => ({ t: e.innerText.trim(), y: e.getBoundingClientRect().y })).sort((a, b) => a.y - b.y),
    );
    const names = shown.map((x) => x.t);
    for (const want of ['Message', 'Case', 'Giki 1', 'Giki 2', 'Donors', 'Thank donors', 'Chat', 'Report', 'Notes'])
      expect(names, want).toContain(want);
    // Giki sits right after Case, before Donors
    expect(names.indexOf('Giki 1')).toBe(names.indexOf('Case') + 1);
    expect(names.indexOf('Giki 2')).toBe(names.indexOf('Giki 1') + 1);
    // the small phone row is not shown on a computer
    await expect(page.locator('#ui2Tabs .ui2-quick')).toBeHidden();
    // every menu button is fully on the screen (no scroll to reach it)
    for (const b of await page.locator('#ui2Tabs .ui2-tab:visible').all()) {
      const r = await b.boundingBox();
      expect(r.y + r.height).toBeLessThanOrEqual(height);
    }
  });

for (const [width, height] of [[390, 844], [360, 740], [320, 568]])
  test(`phone ${width}: two small Giki buttons above the bar, bar keeps five buttons, message fully visible`, async ({ page }) => {
    await open(page, width, height);
    await page.evaluate((m) => (document.getElementById('groupPreview').innerHTML = m), LONG);
    await page.waitForTimeout(200);
    const bar = await page.locator('#ui2Tabs .ui2-tab:visible').allInnerTexts();
    expect(bar.map((t) => t.trim())).toEqual(['Notes', 'Message', 'Donors', 'Chat', 'More']);
    const chips = page.locator('#ui2Tabs .ui2-chip');
    await expect(chips).toHaveText(['Giki 1', 'Giki 2']);
    const tabs = await page.locator('#ui2Tabs .ui2-tab[data-tab="message"]').boundingBox();
    for (const c of await chips.all()) {
      const r = await c.boundingBox();
      expect(r.y + r.height, 'chip is above the bar').toBeLessThanOrEqual(tabs.y + 1);
      expect(r.height).toBeLessThanOrEqual(40); // small
      expect(r.x).toBeGreaterThanOrEqual(0);
      expect(r.x + r.width).toBeLessThanOrEqual(width);
    }
    // the whole message is still visible: nothing scrolls inside it or on the page
    const m = await page.evaluate(() => {
      const chat = document.getElementById('chat');
      return { inner: chat.scrollHeight - chat.clientHeight, page: document.documentElement.scrollHeight - innerHeight };
    });
    expect(m.inner).toBeLessThanOrEqual(1);
    expect(m.page).toBeLessThanOrEqual(1);
  });

test('phone: a Giki button opens that Giki page', async ({ page }) => {
  await open(page, 390, 844);
  await Promise.all([page.waitForURL(/\/giki$/), page.locator('#ui2Tabs .ui2-chip', { hasText: 'Giki 1' }).click()]);
});

/* Phone: the message is in the middle of its card (top to bottom) so the eyes do not have to look up to the top edge. */
test('phone: a short message is in the exact middle of its card, and a long one fills it from the top', async ({ page }) => {
  await open(page, 390, 844);
  const gaps = () =>
    page.evaluate(() => {
      const c = document.getElementById('chat').getBoundingClientRect();
      const g = document.getElementById('groupPreview').getBoundingClientRect();
      return { above: g.top - c.top, below: c.bottom - g.bottom, scroll: document.getElementById('chat').scrollHeight - document.getElementById('chat').clientHeight };
    });
  await page.evaluate(() => (document.getElementById('groupPreview').innerHTML = '<div><b>Short message.</b></div><div>Rs. 18,000 LEFT</div>'));
  await expect.poll(async () => Math.abs((await gaps()).above - (await gaps()).below)).toBeLessThan(3);
  expect((await gaps()).above).toBeGreaterThan(100);
  // a long message: starts at the top, nothing is cut off
  await page.evaluate((m) => (document.getElementById('groupPreview').innerHTML = m), LONG.repeat(4));
  await expect.poll(async () => (await gaps()).above).toBeLessThan(3);
  // the strip kept for the refresh and next buttons is still there, so the last line is never under them
  expect(await page.locator('#chat').evaluate((n) => parseFloat(getComputedStyle(n).paddingBottom))).toBeGreaterThanOrEqual(46);
  // and back to short again: centred again (the card follows the message as it changes)
  await page.evaluate(() => (document.getElementById('groupPreview').innerHTML = '<div><b>Short again.</b></div>'));
  await expect.poll(async () => Math.abs((await gaps()).above - (await gaps()).below)).toBeLessThan(3);
});

test('computer: the message position is not changed', async ({ page }) => {
  await open(page, 1280, 720);
  await page.evaluate(() => (document.getElementById('groupPreview').innerHTML = '<div><b>Short message.</b></div>'));
  await page.waitForTimeout(300);
  await expect(page.locator('#chat')).not.toHaveClass(/ui2-short/);
});
