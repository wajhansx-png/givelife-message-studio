const { test, expect } = require('@playwright/test');
async function setup(page, base, width = 390, route = '') {
  await page.setViewportSize({ width, height: 844 });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto(base + route);
}
async function donors(page, base) {
  await page.locator(base === '/new/' ? '#ui2Tabs [data-tab=donors]' : '#openDonors').click();
  await expect(page.locator('#donorsPage')).toBeVisible();
}
async function reveal(page, selector) {
  // Gap is hidden by the existing compact dock at some widths. Exercise
  // its real handler without changing layout as part of this navigation fix.
  if (selector === '#donorPace') return page.locator(selector).evaluate((button) => button.click());
  if (!(await page.locator(selector).isVisible())) {
    const menu = selector === '#donorPace' ? '#ui2Options > summary' : '#donorNavMore > summary';
    if (await page.locator(menu).count()) await page.locator(menu).click();
  }
  await page.locator(selector).click();
}
test('Base message direct link restores its lazily-created dialog', async ({ page }) => {
  await setup(page, '/new/', 390, '#/donors/messages/base');
  await expect(page.locator('#baseMessageDialog')).toBeVisible();
  await expect(page.locator('#baseMessageText')).not.toHaveValue('');
  await page.reload();
  await expect(page.locator('#baseMessageDialog')).toBeVisible();
  await expect(page.locator('#baseMessageText')).not.toHaveValue('');
  await page.locator('#baseMessageCancel').click();
  await expect(page).toHaveURL(/#\/donors\/messages$/);
});
test('Volunteer timing without a prepared draft returns safely to Volunteers', async ({ page }) => {
  await setup(page, '/new/', 390, '#/donors/volunteers/volunteer_timing');
  await expect(page).toHaveURL(/#\/donors\/volunteers$/);
  await expect(page.locator('#volTimingDialog')).toBeHidden();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/#\/donors\/volunteers$/);
});
for (const base of ['/new', '/new/']) {
  for (const [route, dialog, close, parent] of [
    ['donors/important/notes', '#foundationNotes', '#notesBack', 'donors/important'],
    ['donors/top/resume', '#donorResumeDialog', '#donorResumeClose', 'donors/top'],
    ['settings/poster', '#posterDialog', '#posterClose', 'settings'],
  ]) {
    test(`${base}: ${route} closes to its parent with usable focus`, async ({ page }) => {
      await setup(page, base, 390, '#/' + route);
      await expect(page.locator(dialog)).toBeVisible();
      await page.locator(close).click();
      await expect(page).toHaveURL(new RegExp('#/' + parent + '$'));
      await expect(page.locator(dialog)).toBeHidden();
      expect(await page.evaluate(() => !document.activeElement.closest('dialog:not([open])'))).toBe(
        true,
      );
      if (parent.startsWith('donors/')) {
        await page.locator('#donorMainBottom').click();
        await expect(page.locator('#donorsPage')).toBeHidden();
      }
    });
  }
}
