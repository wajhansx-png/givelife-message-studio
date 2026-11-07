const { test, expect } = require('@playwright/test');
/* Phone polish: full donor names, whole message visible in a small preview, compact Send DMs, expand icon in header. */
for (const [width, height] of [
  [320, 568],
  [375, 667],
  [411, 890],
  [430, 932],
])
  test(`phone polish at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    await page.route('**/donors?**', async (route) => {
      const res = await route.fetch();
      const json = await res.json();
      if (json.items)
        json.items.forEach((d, i) => {
          d.name = i % 2 ? 'Syed Muhammad Abdullah Khan' : 'Sohaib Donor New';
          d.follow_up_state = 'Sent';
          d.top_donor = i % 2 === 0;
        });
      return route.fulfill({ response: res, json });
    });
    await page.goto('/#/donors/all');
    await expect(page.locator('.donor-row').first()).toBeVisible();
    const rows = await page.evaluate(() =>
      [...document.querySelectorAll('.donor-row')].slice(0, 6).map((r) => {
        const n = r.querySelector('.donor-name');
        const over = [...r.querySelectorAll('*')].some(
          (e) =>
            e.getBoundingClientRect().width && e.getBoundingClientRect().right > innerWidth + 1,
        );
        return {
          full: n.scrollHeight <= n.clientHeight + 1 && n.scrollWidth <= n.clientWidth + 1,
          over,
          h: r.getBoundingClientRect().height,
        };
      }),
    );
    for (const r of rows) {
      expect(r.full).toBe(true);
      expect(r.over).toBe(false);
      expect(r.h).toBeLessThan(130);
    }
    expect(await page.evaluate(() => !!document.querySelector('.donor-title #donorExpand'))).toBe(
      true,
    );
    // Send DMs: compact, nothing hidden, More options starts collapsed every time.
    await page.locator('#donorSendImportant').click();
    const modal = page.locator('#donorBatchPicker');
    await expect(modal).toBeVisible();
    // Every option is visible at once: no hidden "More options".
    await expect(modal.locator('#batchPause')).toBeVisible();
    await expect(modal.locator('#batchIncl')).toBeVisible();
    await expect(modal.locator('#batchRandom')).toBeVisible();
    expect(await modal.evaluate((d) => d.querySelectorAll('details').length)).toBe(0);
    const half = await modal.evaluate((d) => d.getBoundingClientRect().height / innerHeight);
    if (height >= 800) expect(half).toBeLessThan(0.55);
    const fit = await modal.evaluate((d) => {
      const r = d.getBoundingClientRect();
      const s = document.getElementById('batchStart').getBoundingClientRect();
      return d.scrollHeight <= d.clientHeight + 1 && r.top >= 0 && s.bottom <= innerHeight;
    });
    expect(fit).toBe(true);
    await page.keyboard.press('Escape');
    // Group preview: the whole message is visible without scrolling.
    await page.goto('/#/preview');
    await expect(page.locator('#focusFormatted')).toBeVisible();
    await expect
      .poll(() =>
        page.locator('#focusFormatted').evaluate((e) => e.scrollHeight <= e.clientHeight + 2),
      )
      .toBe(true);
    // DM Messages: same.
    await page.goto('/#/donors/messages');
    await expect(page.locator('.bank-preview').first()).toBeVisible();
    // A 568px-tall screen cannot show a long DM at a readable size: only enforce on taller phones.
    if (height >= 640)
      await expect
        .poll(() =>
          page
            .locator('.bank-detail .bank-preview')
            .evaluate((e) => e.scrollHeight <= e.clientHeight + 2),
        )
        .toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
