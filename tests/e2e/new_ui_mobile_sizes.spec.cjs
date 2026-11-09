const { test, expect } = require('@playwright/test');
const routes = [
  ['', '.app'],
  ['preview', '#messageFocus'],
  ['chat', '#hist'],
  ['notes', '#foundationNotes'],
  ['settings', '#set'],
  ['settings/memory', '#memoryDialog'],
  ['settings/poster', '#posterDialog'],
  ['keyboard', '#keyboardDialog'],
  ['whatsapp', '#whatsappDialog'],
  ...[
    'all',
    'important',
    'top',
    'donated',
    'not_donated',
    'not_contacted',
    'volunteers',
    'messages',
  ].map((tab) => ['donors/' + tab, '#donorsPage']),
  ...[
    ['add', '#donorAddDialog'],
    ['bulk', '#donorPasteDialog'],
    ['pace', '#donorBatchPicker'],
    ['notes', '#foundationNotes'],
  ].map(([tab, selector]) => ['donors/all/' + tab, selector]),
];
for (const [width, height] of [
  [280, 480],
  [320, 480],
  [320, 568],
  [360, 640],
  [375, 667],
  [390, 844],
  [414, 896],
  [430, 932],
  [568, 320],
  [667, 375],
  [768, 1024],
]) {
  test(`studio routes and message tabs fit ${width}x${height}`, async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize({ width, height });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    for (const [route, selector] of routes) {
      await page.goto('/new' + (route ? '#/' + route : ''));
      const root = page.locator(selector);
      await expect(root, route || 'home').toBeVisible();
      const box = await root.boundingBox();
      expect(box.x, route).toBeGreaterThanOrEqual(-1);
      expect(box.x + box.width, route).toBeLessThanOrEqual(width + 1);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        route,
      ).toBe(true);
      if (route === 'donors/messages') {
        await page.getByRole('tab', { name: 'Follow-up', exact: true }).click();
        await expect(page.locator('.bank-followup-panel textarea')).toBeVisible();
        await page.getByRole('tab', { name: 'DM messages', exact: true }).click();
        await page.getByRole('button', { name: 'Write Case', exact: true }).click();
        const dialog = page.getByRole('dialog', { name: 'Write Case', exact: true });
        await expect(dialog).toBeVisible();
        const d = await dialog.boundingBox();
        expect(d.x).toBeGreaterThanOrEqual(-1);
        expect(d.x + d.width).toBeLessThanOrEqual(width + 1);
        expect(d.y).toBeGreaterThanOrEqual(-1);
        expect(d.y + d.height).toBeLessThanOrEqual(height + 1);
      }
    }
    expect(errors).toEqual([]);
  });
}
