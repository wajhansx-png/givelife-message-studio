const { test, expect } = require('@playwright/test');
/* A donor with a follow-up line must still show the name (it once collapsed to 0 px), the
   "Send with follow-up" checkbox must not sit on the filter tabs, and tab labels stay whole. */
for (const [width, height] of [
  [1920, 1000],
  [1280, 800],
  [1024, 768],
  [768, 1024],
  [390, 844],
  [320, 568],
])
  test(`names, checkbox and tabs at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    await page.goto('/old#/donors/all');
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.evaluate(() =>
      document.querySelectorAll('.donor-row').forEach((row) => {
        row.dataset.fu = 'Sent';
        const line = document.createElement('small');
        line.className = 'donor-fu';
        line.textContent = 'Follow-up: sent';
        row.querySelector('.donor-identity').append(line);
      }),
    );
    const m = await page.evaluate(() => {
      const rect = (el) => el.getBoundingClientRect();
      const name = rect(document.querySelector('.donor-row .donor-name'));
      const opt = rect(document.querySelector('.donor-fu-opt'));
      const tabs = document.querySelector('.donor-tabs');
      const t = rect(tabs);
      const tabButtons = [...tabs.children].map((b) => {
        const range = document.createRange();
        range.selectNodeContents(b);
        const text = range.getBoundingClientRect();
        const box = rect(b);
        return text.left >= box.left - 1 && text.right <= box.right + 1;
      });
      return {
        nameWidth: name.width,
        overlap: !(
          opt.bottom <= t.top ||
          opt.top >= t.bottom ||
          opt.right <= t.left ||
          opt.left >= t.right
        ),
        tabsFit: tabButtons.every(Boolean),
        pageOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      };
    });
    expect(m.nameWidth).toBeGreaterThan(55);
    expect(m.overlap).toBe(false);
    expect(m.tabsFit).toBe(true);
    expect(m.pageOverflow).toBe(false);
  });
