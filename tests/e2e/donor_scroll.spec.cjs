const { test, expect } = require('@playwright/test');
const headers = { Authorization: 'Bearer manual-fix-preview-key' };
for (const width of [1440, 390])
  test(`favourite keeps donor list scroll after save at ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 700 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    const all = (await (await request.get('/donors?tab=all', { headers })).json()).items;
    for (let i = all.length; i < 80; i++)
      await request.post('/donors', {
        headers,
        data: {
          action: 'add',
          name: 'Scroll donor ' + String(i).padStart(3, '0'),
          phone: '1555' + String(1230000 + i),
        },
      });
    await page.goto('/#/donors/all');
    await expect(page.locator('#donorRows .donor-row')).toHaveCount(80);
    await page.locator('#donorTable').evaluate((el) => (el.scrollTop = 1600));
    const before = await page.locator('#donorTable').evaluate((el) => el.scrollTop);
    expect(before).toBeGreaterThan(500);
    const target = await page.locator('#donorTable').evaluate(
      (el) =>
        [...el.querySelectorAll('.donor-row')].find((row) => {
          const r = row.getBoundingClientRect(),
            box = el.getBoundingClientRect();
          return r.top > box.top + 50 && r.bottom < box.bottom - 10;
        })?.dataset.donorId,
    );
    expect(target).toBeTruthy();
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/donors') && r.request().method() === 'POST',
    );
    /* Tap the star where a person sees it. locator.click() first runs Playwright's own scroll-into-view while the
       rows settle, which moves the list itself and hides what the app really does. */
    const star = page.locator(`[data-donor-id="${target}"] .donor-star`);
    const box = await star.boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    expect((await saved).ok()).toBe(true);
    await expect
      .poll(() => page.locator('#donorTable').evaluate((el) => el.scrollTop))
      .toBe(before);
    await page.waitForTimeout(250);
    expect(await page.locator('#donorTable').evaluate((el) => el.scrollTop)).toBe(before);
  });
