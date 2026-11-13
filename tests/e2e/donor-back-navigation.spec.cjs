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
for (const base of ['/old', '/new/']) {
  for (const width of [320, 1440]) {
    test(`${base} ${width}: modal closing consumes history and Back leaves once`, async ({
      page,
    }) => {
      test.setTimeout(60000);
      await setup(page, base, width);
      await donors(page, base);
      for (const [opener, dialog, closer] of [
        ['#donorAdd', '#donorAddDialog', '#donorAddCancel'],
        ['#donorBulk', '#donorPasteDialog', '#pasteCancel'],
        ['#donorPace', '#donorBatchPicker', '#batchCancel'],
      ]) {
        for (const how of ['button', 'escape', 'browser']) {
          await page.locator('.donor-tabs [data-tab=important]').click();
          const tab = opener === '#donorPace' ? 'important' : 'donated';
          await page.locator('.donor-tabs [data-tab=' + tab + ']').click();
          await reveal(page, opener);
          await expect(page.locator(dialog)).toBeVisible();
          if (how === 'button') await page.locator(closer).click();
          else if (how === 'escape') await page.keyboard.press('Escape');
          else await page.goBack();
          await expect(page.locator(dialog)).toBeHidden();
          await expect(page).toHaveURL(new RegExp('#/donors/' + tab + '$'));
          await page.goBack();
          await expect(page.locator('#donorsPage')).toBeHidden();
          await page.goForward();
          await expect(page.locator('#donorsPage')).toBeVisible();
          await expect(page).toHaveURL(new RegExp('#/donors/' + tab + '$'));
        }
      }
      await page.locator('#donorMainBottom').click();
      await expect(page.locator('#donorsPage')).toBeHidden();
      // Back must not reopen the screen that was just closed.
      expect(await page.evaluate(() => location.hash)).toBe('');
      await page.goForward();
      await expect(page.locator('#donorsPage')).toBeVisible();
    });
  }
  test(`${base}: direct child link, refresh, Top tab and rapid Back`, async ({ page }) => {
    await setup(page, base, 390, '#/donors/top/add');
    await expect(page.locator('#donorAddDialog')).toBeVisible();
    await page.reload();
    await page.locator('#donorAddCancel').click();
    await expect(page).toHaveURL(/#\/donors\/top$/);
    await page.locator('#donorMainBottom').click();
    await expect(page.locator('#donorsPage')).toBeHidden();
    await donors(page, base);
    await reveal(page, '#donorAdd');
    await page.locator('#donorAddCancel').click();
    await page.evaluate(() => {
      document.getElementById('donorMainBottom').click();
      document.getElementById('donorMainBottom').click();
    });
    await expect(page.locator('#donorsPage')).toBeHidden();
    await expect(page).not.toHaveURL(/donors/);
  });
}
for (const base of ['/old', '/new/']) {
  test(`${base}: child closing preserves original screen and missing Back events recover`, async ({
    page,
  }) => {
    await setup(page, base);
    // Exercise a non-Home caller using the same controller as in-app navigation.
    await page.evaluate(() => {
      Nav.go('preview');
      renderNav();
      window.DonorHub.open();
    });
    await page.locator('.donor-tabs [data-tab=top]').click();
    await reveal(page, '#donorNumbers');
    await expect(page.locator('#donorNumbersDialog')).toBeVisible();
    await page.locator('#numbersCancel').click();
    await expect(page).toHaveURL(/#\/donors\/top$/);
    await page.locator('#donorMainBottom').click();
    await expect(page).toHaveURL(/#\/preview$/);
    await expect(page.locator('#donorsPage')).toBeHidden();
    await page.evaluate(() => {
      Nav.go('');
      renderNav();
      window.DonorHub.open();
    });
    await page.evaluate(() => {
      window.history.back = () => {};
    });
    await page.locator('#donorMainBottom').click();
    await expect(page).not.toHaveURL(/donors/);
    await expect.poll(() => page.evaluate(() => !!Nav.pending)).toBe(false);
  });
  test(`${base}: Thank donors and base message close before parent, with no late reopen`, async ({
    page,
  }) => {
    await setup(page, base);
    await donors(page, base);
    await page.locator('.donor-tabs [data-tab=donated]').click();
    await page.evaluate(() => window.DonorThanks.open());
    await expect(page.locator('#donorThanksDialog')).toBeVisible();
    await page.locator('#thanksClose').click();
    await expect(page).toHaveURL(/#\/donors\/donated$/);
    await page.locator('#donorMainBottom').click();
    await expect(page.locator('#donorsPage')).toBeHidden();
    await donors(page, base);
    await page.evaluate(() => window.DonorHub.openBaseMessage());
    await expect(page.locator('#baseMessageDialog')).toBeVisible();
    await page.goBack();
    await expect(page.locator('#baseMessageDialog')).toBeHidden();
    await page.locator('#donorMainBottom').click();
    await expect(page.locator('#donorsPage')).toBeHidden();
    await donors(page, base);
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    await page.route('**/donor-thanks', async (route) => {
      await gate;
      await route.continue();
    });
    await page.evaluate(() => {
      void window.DonorThanks.open();
    });
    await page.locator('#donorMainBottom').click();
    release();
    await expect(page.locator('#donorsPage')).toBeHidden();
    await expect(page.locator('#donorThanksDialog')).toBeHidden();
  });
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
for (const base of ['/old', '/new/']) {
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
