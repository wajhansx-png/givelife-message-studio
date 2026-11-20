/* Home on a computer, and on a phone in "desktop site" mode (about 980 x 2000): the message card hugs its message
   (it was a 1700px box around 300px of text), the text is read at 18px, and "Reconnect WhatsApp" never runs into Auto. */
const { test, expect } = require('@playwright/test');

async function open(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'));
  await page.goto('/new');
  await expect(page.locator('#groupPreview')).toBeVisible();
}

for (const [width, height] of [[980, 2000], [900, 1200], [1920, 1080]])
  test(`tall screen ${width}x${height}: the card fits its message and the text is large`, async ({ page }) => {
    await open(page, width, height);
    const card = await page.locator('#card').boundingBox();
    const msg = await page.locator('#groupPreview').boundingBox();
    expect(card.height).toBeLessThan(msg.height + 220); // no big empty box around the message
    const size = await page.locator('#groupPreview').evaluate((e) => parseFloat(getComputedStyle(e).fontSize));
    expect(size).toBeGreaterThanOrEqual(17);
    const send = await page.locator('#btnGivelife').boundingBox();
    expect(send.y).toBeGreaterThan(card.y + card.height - 1); // Send sits right under the card
    expect(send.y - (card.y + card.height)).toBeLessThan(40);
  });

for (const [width, height] of [[1280, 800], [1440, 900]])
  test(`normal desktop ${width}x${height} keeps the full-height card`, async ({ page }) => {
    await open(page, width, height);
    const card = await page.locator('#card').boundingBox();
    expect(card.height).toBeGreaterThan(height * 0.6);
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
