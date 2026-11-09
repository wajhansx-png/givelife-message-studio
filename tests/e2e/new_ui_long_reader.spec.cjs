const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 219;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server && server.kill());
const caption =
  `*Yousuf's father borrowed money for his little son's Janazah. He still owes Rs. 4,000 and cannot clear it alone.* 💔\n\nAllah says:\n"Who will lend Allah a good loan, so that He multiplies it for him many times?"\n(Surah Al-Baqarah 2:245)\n\n🔴 *Rs. 4,000 LEFT*\n\n*Just 4 people donating Rs. 1,000 can help this grieving father today.*\n\n` +
  Array.from(
    { length: 10 },
    (_, i) =>
      `Sample paragraph ${i + 1}: The complete saved message must remain readable without clipping or a horizontal scrollbar.`,
  ).join('\n\n') +
  '\n\nReference: ' +
  'x'.repeat(180);
for (const [width, height] of [
  [320, 568],
  [390, 844],
  [768, 1024],
  [1440, 900],
  [1920, 890],
]) {
  test(`long Preview caption wraps and its dock follows the content ${width}px`, async ({
    page,
    request,
  }) => {
    await request.post('/__test/seed', {
      headers: { Authorization: 'Bearer ' + KEY },
      data: { group: caption },
    });
    await page.setViewportSize({ width, height });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/preview');
    const formatted = page.locator('#focusFormatted');
    await expect(formatted).toContainText('Reference:');
    const metrics = await formatted.evaluate((e) => ({
      w: e.clientWidth,
      sw: e.scrollWidth,
      h: e.clientHeight,
      sh: e.scrollHeight,
    }));
    expect(metrics.sw).toBeLessThanOrEqual(metrics.w + 1);
    expect(metrics.sh).toBeLessThanOrEqual(metrics.h + 1);
    if (width < 900)
      await page.locator('#messageFocus').evaluate((e) => (e.scrollTop = e.scrollHeight));
    const paper = await page.locator('.focus-paper').boundingBox();
    const dock = await page.locator('.ui2-reader-dock').boundingBox();
    expect(dock.y).toBeGreaterThanOrEqual(paper.y + paper.height - 1);
    expect(dock.y - paper.y - paper.height).toBeLessThan(140);
    await page.locator('#focusBack').click();
    await expect(page.locator('#messageFocus')).toBeHidden();
  });
}
for (const width of [320, 390, 768, 1440]) {
  test(`home dots actions stay reachable and Donors never opens Volunteers ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/donors/volunteers');
    await expect(page.locator('#donorVolunteers')).toBeVisible();
    await page.goto('/new');
    await expect(page.locator('#donorsPage')).toBeHidden();
    await expect(page.locator('#main-workspace .talk')).toBeHidden();
    await expect(page.locator('#cmdForm')).toBeHidden();
    const captionBox = await page.locator('#groupPreview').boundingBox();
    const actionsBox = await page.locator('.ui2-home-message-actions').boundingBox();
    expect(actionsBox.y - captionBox.y - captionBox.height).toBeLessThan(50);
    if (width >= 900) await expect(page.locator('#ui2ChatOpen')).toBeVisible();
    const summary = page.locator('#ui2HomeMore > summary');
    await summary.click();
    const panel = page.locator('#ui2HomeMore > div');
    const box = await panel.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    for (const button of await panel.locator('button').all()) {
      expect(
        await button.evaluate((e) => {
          const r = e.getBoundingClientRect();
          const at = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
          return at === e || e.contains(at);
        }),
      ).toBe(true);
    }
    await summary.press('Escape');
    await expect(panel).toBeHidden();
    await expect(summary).toBeFocused();
    await summary.click();
    await page.mouse.click(2, 2);
    await expect(panel).toBeHidden();
    await summary.click();
    const saved = await page.locator('#group').inputValue();
    await panel.getByRole('button', { name: 'Copy message', exact: true }).click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(saved);
    await summary.click();
    await panel.getByRole('button', { name: 'Change poster', exact: true }).click();
    await expect(page.locator('#posterDialog')).toBeVisible();
    await page.locator('#posterClose').click();
    await summary.click();
    await panel.getByRole('button', { name: 'Preview / edit', exact: true }).click();
    await expect(page.locator('#messageFocus')).toBeVisible();
    await page.locator('#focusBack').click();
    await (
      width < 900 ? page.locator('#ui2Tabs [data-tab=donors]') : page.locator('#railDonors')
    ).click();
    await expect(page).toHaveURL(/#\/donors\/all$/);
    await expect(page.locator('#donorTable')).toBeVisible();
    await expect(page.locator('.donor-tabs [data-tab=all]')).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
}
