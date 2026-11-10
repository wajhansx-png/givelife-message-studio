const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 247;
let server;
test.use({
  baseURL: `http://127.0.0.1:${port}`,
  permissions: ['clipboard-read', 'clipboard-write'],
});
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
for (const width of [900, 1440, 1920]) {
  test(`desktop DM actions work at ${width}px and revert to phone controls`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/donors/messages');
    const root = page.locator('#donorMessages');
    await expect(root.locator('.ui2-desktop-regenerate')).toBeVisible();
    await expect(root.locator('.ui2-desktop-next')).toBeVisible();
    await expect(root.locator('.ui2-bank-nav')).toBeHidden();
    await expect(root.locator('.bank-copy')).toBeHidden();
    const pencil = root.getByRole('button', { name: 'Edit message', exact: true });
    await expect(pencil).toBeVisible();
    expect(await pencil.evaluate((e) => !!e.closest('.bank-preview'))).toBe(true);
    const text = await root.locator('.bank-detail textarea').inputValue();
    const copy = root.getByRole('button', { name: 'Copy message', exact: true });
    await copy.click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(text);
    const preview = await root.locator('.bank-preview').boundingBox(),
      icon = await copy.boundingBox();
    expect(icon.y).toBeGreaterThanOrEqual(preview.y + preview.height - 1);
    await pencil.click();
    const input = root.locator('.bank-detail textarea');
    await expect(input).toBeVisible();
    await input.fill(text + '\n\nPlease share this appeal.');
    await root.getByRole('button', { name: 'Save message', exact: true }).click();
    await expect(input).toBeHidden();
    await expect(root.locator('.bank-preview')).toContainText('Please share this appeal.');
    await root.locator('.ui2-desktop-next').click();
    await expect(root.locator('.bank-current')).toContainText('Message 2');
    let generated = 0;
    await page.route('**/donor-messages', async (route) => {
      if (
        route.request().method() === 'POST' &&
        route.request().postDataJSON().action === 'regenerate'
      ) {
        generated++;
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Test regeneration request received.' }),
        });
      } else await route.continue();
    });
    page.on('dialog', (d) => d.accept());
    await root.locator('.ui2-desktop-regenerate').click();
    await expect.poll(() => generated).toBe(1);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(root.locator('.ui2-desktop-msg-control')).toHaveCount(0);
    await expect(root.locator('.bank-actions > .bank-copy')).toBeVisible();
    await expect(root.locator('.bank-actions > [data-bank-save-id]')).toBeVisible();
    await expect(root.locator('.ui2-bank-nav')).toBeVisible();
    const ys = await root
      .locator('.bank-actions > :is(button,details)')
      .evaluateAll((es) =>
        es.filter((e) => e.checkVisibility()).map((e) => Math.round(e.getBoundingClientRect().y)),
      );
    expect(ys).toHaveLength(4);
    expect(new Set(ys).size).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
}
