const { test, expect } = require('@playwright/test');

// Uses the isolated fake app backend. No WhatsApp messages are sent.
// A saved message is shown at a comfortable fixed size (18px desktop, 17px phone, 1.6 line height).
// Only a message too long for the screen shrinks, never below 13px, and never when the window just resizes.
for (const [width, height, largest] of [
  [1440, 900, 18],
  [390, 844, 17],
]) {
  test('Donor Messages uses stable eye-comfort typography ' + width, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/#/donors/messages');
    const preview = page.locator('.bank-detail .bank-preview');
    await expect(preview).toBeVisible();
    const metrics = () =>
      preview.evaluate((el) => {
        const cs = getComputedStyle(el);
        return { size: parseFloat(cs.fontSize), line: parseFloat(cs.lineHeight) };
      });
    const first = await metrics();
    expect(first.size).toBeGreaterThanOrEqual(13);
    expect(first.size).toBeLessThanOrEqual(largest);
    expect(Math.abs(first.line / first.size - 1.6)).toBeLessThan(0.02);
    await page.setViewportSize({ width: width + 12, height });
    await expect.poll(async () => (await metrics()).size).toBe(first.size);
    await page.locator('.bank-actions [data-bank-save-id]').click();
    const edit = page.locator('.bank-detail textarea');
    await expect(edit).toBeVisible();
    expect(
      parseFloat(await edit.evaluate((el) => getComputedStyle(el).fontSize)),
    ).toBeGreaterThanOrEqual(16);
  });
}
