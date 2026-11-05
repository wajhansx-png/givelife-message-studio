const { test, expect } = require('@playwright/test');

for (const [theme, bg, textColor] of [
  ['dark', 'rgb(36, 39, 53)', 'rgb(240, 243, 251)'],
  ['light', 'rgb(255, 255, 255)', 'rgb(27, 37, 55)'],
]) {
  for (const [width, height] of [
    [1440, 900],
    [390, 844],
  ]) {
    test(
      'native case dropdown readable in ' + theme + ' at ' + width + 'x' + height,
      async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.addInitScript((value) => {
          localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
          localStorage.setItem('givelife-theme', value);
        }, theme);
        await page.goto('/');
        await expect(page.locator('#caseSelect option[value="__new"]')).toHaveText(/New case/);
        await expect(page.locator('#caseSelect option[value="__rename"]')).toHaveText(/Rename/);
        await page.locator('#mainNavMore > summary').click();
        const colors = await page.locator('#caseSelect').evaluate((select) => {
          const el = document.documentElement;
          el.dataset.theme = window.localStorage.getItem('givelife-theme');
          const option = select.querySelector('option[value="__rename"]');
          const cs = getComputedStyle(option),
            sc = getComputedStyle(select);
          return {
            background: cs.backgroundColor,
            color: cs.color,
            scheme: sc.colorScheme,
            disabled: option.disabled,
            selectorHeight: select.getBoundingClientRect().height,
          };
        });
        expect(colors.background).toBe(bg);
        expect(colors.color).toBe(textColor);
        expect(colors.scheme).toBe(theme);
        expect(colors.disabled).toBe(false);
        expect(colors.selectorHeight).toBeGreaterThanOrEqual(40);
        await page.locator('#caseSelect').focus();
        await expect(page.locator('#caseSelect')).toBeFocused();
      },
    );
  }
}
test('canceling New case does not change the saved current case', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/');
  await expect(page.locator('#caseSelect option[value="__new"]')).toBeAttached();
  await page.locator('#mainNavMore > summary').click();
  const old = await page.locator('#caseSelect').inputValue();
  page.on('dialog', (dialog) => dialog.dismiss());
  await page.locator('#caseSelect').selectOption('__new');
  await expect.poll(() => page.locator('#caseSelect').inputValue()).toBe(old);
});
