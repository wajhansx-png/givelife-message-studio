const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
fs.mkdirSync('mobile-screenshots', { recursive: true });
const { openDonorMessages } = require('./helpers.cjs');

// The local preview server contains synthetic donors and cannot send real WhatsApp messages.
const AUTH = { Authorization: 'Bearer manual-fix-preview-key' };

async function openDonors(page, request, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-theme', 'dark');
  });
  await request.post('/__test/seed', { headers: AUTH, data: { reply: 'Ready.' } });
  await page.goto('/');
  await page.locator('#openDonors').click();
  await expect(page.locator('.donor-row').first()).toBeVisible();
}

async function assertInside(page, selectors, width, height) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    await expect(locator, selector).toBeVisible();
    const r = await locator.boundingBox();
    expect(r, selector + ' has a bounding box').not.toBeNull();
    expect(r.x, selector + ' stays on-screen left').toBeGreaterThanOrEqual(-1);
    expect(r.x + r.width, selector + ' stays on-screen right').toBeLessThanOrEqual(width + 1);
    expect(r.y + r.height, selector + ' stays on-screen vertically').toBeLessThanOrEqual(height + 2);
  }
}

for (const [width, height] of [
  [320, 568],
  [360, 740],
  [390, 844],
  [430, 932],
  [560, 780],
]) {
  test('Donors phone layout fits ' + width + 'px without hiding actions', async ({
    page,
    request,
  }, testInfo) => {
    await openDonors(page, request, width, height);
    if (width === 320) {
      const controls = await page.evaluate(() =>
        ['donorBulk', 'donorMessagesTab', 'donorSendAll', 'donorSendImportant', 'donorTest', 'donorToggle', 'donorMainBottom'].map((id) => {
          const el = document.getElementById(id);
          const r = el.getBoundingClientRect();
          const parent = el.parentElement;
          return { id, hidden: el.hidden, display: getComputedStyle(el).display,
            parent: parent?.className, parentDisplay: parent ? getComputedStyle(parent).display : '',
            x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
        }),
      );
      console.log('Donors mobile control geometry:', JSON.stringify(controls));
    }
    await assertInside(page, [
      '#donorMessagesTab',
      '#donorBulk',
      '#donorAdd',
      '#donorSearch',
      '#donorSendImportant',
      '#donorNavMore > summary',
      '#donorToggle',
      '#donorMainBottom',
      '.donor-row .donor-star',
      '.donor-row .donor-dm',
      '.donor-row .donor-status',
      '.donor-row .donor-amount',
      '.donor-row .donor-more > summary',
    ], width, height);
    await expect(page.locator('#donorSendAll')).toBeHidden();
    await page.locator('#donorNavMore > summary').click();
    await expect(page.locator('#donorTest')).toBeVisible();
    await expect(page.locator('.donor-poster-toggle')).toBeVisible();
    await page.locator('#donorNavMore > summary').click();
    expect(await page.locator('#donorTable').evaluate(
      (el) => el.scrollWidth <= el.clientWidth + 2,
    )).toBe(true);
    expect(await page.locator('#donorTable').evaluate(
      (el) => el.scrollHeight > el.clientHeight,
    )).toBe(true);
    const tabs = await page.locator('.donor-tabs [data-tab]').evaluateAll(
      (els) => els.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left, right: r.right, width: r.width, height: r.height };
      }),
    );
    expect(tabs).toHaveLength(6);
    for (const t of tabs) {
      expect(t.x).toBeGreaterThanOrEqual(-1);
      expect(t.right).toBeLessThanOrEqual(width + 1);
      expect(t.height).toBeGreaterThanOrEqual(40);
    }
    await testInfo.attach('donors-list-' + width + '.png', {
      body: await page.locator('#donorsPage').screenshot({ path: 'mobile-screenshots/donors-list-' + width + '.png' }),
      contentType: 'image/png',
    });

    await openDonorMessages(page);
    await expect(page.locator('.bank-detail')).toBeVisible();
    expect(await page.locator('.bank-detail').evaluate(
      (el) => el.getBoundingClientRect().width,
    )).toBeGreaterThan(width - 35);
    expect(await page.locator('.bank-workspace').evaluate(
      (el) => el.scrollWidth <= el.clientWidth + 2,
    )).toBe(true);
    await testInfo.attach('donors-messages-' + width + '.png', {
      body: await page.locator('#donorsPage').screenshot({ path: 'mobile-screenshots/donors-messages-' + width + '.png' }),
      contentType: 'image/png',
    });
    await page.locator('.bank-back-bottom').scrollIntoViewIfNeeded();
    await page.locator('.bank-back-bottom').click();
    await page.locator('[data-tab=volunteers]').click();
    await expect(page.locator('#donorVolunteers')).toBeVisible();
    await expect(page.locator('#donorTable')).toBeHidden();
    await expect(page.locator('.donor-bottom')).toBeHidden();
    await assertInside(page, ['#volName', '#volPhone'], width, height);
    await testInfo.attach('donors-volunteers-' + width + '.png', {
      body: await page.locator('#donorsPage').screenshot({ path: 'mobile-screenshots/donors-volunteers-' + width + '.png' }),
      contentType: 'image/png',
    });
  });
}

test('Donor row editor stays inside a narrow phone and the keyboard can be used', async ({
  page,
  request,
}, testInfo) => {
  await openDonors(page, request, 320, 568);
  await page.locator('.donor-row .donor-more > summary').first().click();
  const menu = page.locator('.donor-row .donor-more[open] > div').first();
  await expect(menu).toBeVisible();
  const r = await menu.boundingBox();
  expect(r.x).toBeGreaterThanOrEqual(0);
  expect(r.x + r.width).toBeLessThanOrEqual(321);
  expect(r.y).toBeGreaterThanOrEqual(0);
  expect(r.y + r.height).toBeLessThanOrEqual(569);
  await testInfo.attach('donors-row-editor-320.png', {
    body: await page.locator('#donorsPage').screenshot({ path: 'mobile-screenshots/donors-row-editor-320.png' }),
    contentType: 'image/png',
  });
  await page.locator('.donor-row .donor-menu-close').first().click();
  await page.locator('#donorAdd').click();
  await expect(page.locator('#donorAddDialog')).toBeVisible();
  await page.setViewportSize({ width: 320, height: 420 });
  await page.locator('#donorNewName').focus();
  await page.locator('#donorAddSave').scrollIntoViewIfNeeded();
  await expect(page.locator('#donorAddSave')).toBeVisible();
  await testInfo.attach('donors-add-keyboard-320.png', {
    body: await page.screenshot({ path: 'mobile-screenshots/donors-add-keyboard-320.png' }),
    contentType: 'image/png',
  });
});
