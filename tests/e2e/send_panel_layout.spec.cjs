const { test, expect } = require('@playwright/test');
const auth = { Authorization: 'Bearer manual-fix-preview-key' };
async function openPanel(page, request, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await request.post('/__test/seed', {
    headers: auth,
    data: { reply: 'The saved caption is ready.' },
  });
  await page.goto('/');
  await expect(page.locator('#leftChip')).toContainText('25,000');
  await page.evaluate(() => document.fonts.ready);
}
for (const [width, height] of [
  [1920, 890],
  [1440, 900],
  [1280, 720],
  [1024, 600],
  [768, 1024],
  [390, 700],
  [320, 568],
]) {
  test(`sending panel stays readable and reachable ${width}x${height}`, async ({
    page,
    request,
  }) => {
    await openPanel(page, request, width, height);
    const rail = page.locator('.action-rail');
    const send = page.locator('.action-rail .group-send');
    await expect(send).toBeVisible();
    if (width >= 900) {
      const top = (await send.boundingBox()).y - (await rail.boundingBox()).y;
      expect(top, 'send panel must start near the top, not float halfway down').toBeLessThan(32);
    }
    for (const selector of ['.gb-timer', '#btnFreePick']) {
      for (const b of await send.locator(selector).all()) {
        const r = await b.boundingBox();
        expect(r.width, 'timer and group picker need an easy tap target').toBeGreaterThanOrEqual(
          44,
        );
        expect(r.height).toBeGreaterThanOrEqual(44);
      }
    }
    await page.screenshot({ path: `test-results/send-panel-default-${width}.png` });
    // Paint a saved schedule locally. No scheduling or sending request is made.
    await page.evaluate(() =>
      paintTimers({
        main: {
          id: 'layout-main',
          due_at: new Date(2026, 10, 4, 11, 45).getTime() / 1000,
          delay: 15,
        },
        free: {
          id: 'layout-free',
          due_at: new Date(2026, 10, 4, 11, 45).getTime() / 1000,
          delay: 30,
        },
      }),
    );
    for (const selector of ['#btnGivelife', '#btnFree', '#sendAll', '.test-row']) {
      const label = send.locator(selector + ' .gb-name');
      expect(
        await label.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
        'group name must remain fully readable with a saved clock',
      ).toBe(true);
    }
    await send.locator('[data-timer=main]').click();
    await send.locator('[data-timer=free]').click();
    await send.locator('#btnFreePick').click();
    await expect(send.locator('#dropFree')).toBeVisible();
    const drop = await send.locator('#dropFree').boundingBox();
    const row = await send.locator('#btnFree').locator('..').boundingBox();
    expect(Math.abs(drop.width - row.width), 'dropdown should use the whole row').toBeLessThan(2);
    if (width >= 900) {
      expect((await send.boundingBox()).y).toBeGreaterThanOrEqual((await rail.boundingBox()).y);
    }
    for (const b of await send.locator('.delay-pill').all()) {
      expect((await b.boundingBox()).height).toBeGreaterThanOrEqual(44);
      expect(
        await b.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
        'timer text must fit its preset',
      ).toBe(true);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/send-panel-${width}.png` });
  });
}
