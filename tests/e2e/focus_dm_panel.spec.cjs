const { test, expect } = require('@playwright/test');
const { openPreview, showDm } = require('./helpers.cjs');
for (const width of [1440, 390])
  test(`DM focus keeps real sending controls ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    let sent;
    await page.route('**/send-custom', (route) => {
      sent = route.request().postDataJSON();
      return route.fulfill({ json: { code: 'SUCCESS' } });
    });
    await page.goto('/');
    await showDm(page);
    await openPreview(page);
    await expect(page.locator('#messageFocus .dm-send')).toBeVisible();
    await expect(page.locator('#focusFormatted')).not.toHaveText('');
    await expect(page.locator('#dmPhone')).toHaveCount(1);
    await page.locator('#focusEdit').click();
    await page.locator('#focusText').fill('Brother, thank you for helping this family.');
    await page.locator('#focusEdit').click();
    await expect(page.locator('#focusState')).toContainText('Saved');
    await page.locator('#dmName').fill('Ali');
    await page.locator('#dmPhone').fill('03001112222');
    await page.locator('#sendDm').click();
    await expect.poll(() => sent?.phone).toBe('923001112222');
    expect(sent.message).toContain('thank you for helping this family.');
    expect(sent.message).toContain('Ali Bhai');
    await page.screenshot({ path: `test-results/focus-dm-${width}.png` });
    await page.locator('#focusBack').click();
    await expect(page.locator('#messageFocus')).toBeHidden();
    await expect(page.locator('#sendDm')).toHaveCount(1);
    await page.getByRole('button', { name: 'Group messages', exact: true }).click();
    await expect(page.locator('#messageFocus .dm-send')).toHaveCount(0);
  });
