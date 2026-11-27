/* Desktop: the left menu stays beside Case, Donors, Chat and Report (only Notes covers it). A page sits to the right of
   the menu, the menu button for it is lit, a click on another menu button switches pages (one page open at a time), and
   Message goes home. Phones keep their own bottom bar and full-width pages. Fake WhatsApp only: nothing is sent. */
const { test, expect } = require('@playwright/test');

async function open(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/new');
  await expect(page.locator('#groupPreview')).toBeVisible();
  await expect(page.locator('.ui2-tab[data-tab="message"]')).toBeVisible();
}

/* a real mouse click at the middle of a menu button, the way the owner does it (a modal page's backdrop is on top) */
async function tap(page, tab) {
  const r = await page.locator(`.ui2-tab[data-tab="${tab}"]`).boundingBox();
  await page.mouse.click(r.x + r.width / 2, r.y + r.height / 2);
}

const PAGES = {
  case: '#casePage',
  donors: '#donorsPage',
  chat: '#hist',
  report: 'dialog.report-dialog',
};

async function state(page) {
  return page.evaluate((pages) => {
    const menu = document.querySelector('.app > .foot').getBoundingClientRect();
    const open = Object.entries(pages)
      .filter(([, q]) => document.querySelector(q)?.open)
      .map(([k]) => k);
    const box = open.length ? document.querySelector(pages[open[0]]).getBoundingClientRect() : null;
    return {
      open,
      menuRight: menu.right,
      boxLeft: box && box.left,
      boxRight: box && box.right,
      lit: [...document.querySelectorAll('.ui2-tab')]
        .filter((t) => t.getAttribute('aria-current') === 'true')
        .map((t) => t.dataset.tab),
      innerWidth,
    };
  }, PAGES);
}

for (const [width, height] of [
  [1280, 720],
  [1920, 1080],
])
  test(`desktop ${width}: the menu stays beside each page, and its button switches pages`, async ({
    page,
  }) => {
    await open(page, width, height);
    for (const key of ['case', 'donors', 'chat', 'report', 'case', 'chat', 'donors']) {
      await tap(page, key);
      await expect.poll(async () => (await state(page)).open, { message: key }).toEqual([key]);
      const s = await state(page);
      expect(s.lit, `${key} is lit`).toEqual([key]);
      expect(s.boxLeft, `${key} starts after the menu`).toBeGreaterThanOrEqual(s.menuRight - 1);
      if (key !== 'chat')
        await expect // the page slides in: measure once it has settled
          .poll(async () => Math.abs((await state(page)).boxRight - s.innerWidth), {
            message: `${key} reaches the right edge`,
          })
          .toBeLessThan(2);
    }
    await tap(page, 'message');
    await expect.poll(async () => (await state(page)).open).toEqual([]);
    expect((await state(page)).lit).toEqual(['message']);
    await expect(page.locator('#btnGivelife')).toBeVisible();
  });

test('Notes still covers the whole screen, and the menu comes back after it', async ({ page }) => {
  await open(page, 1280, 720);
  await tap(page, 'notes');
  await expect(page.locator('#foundationNotes')).toBeVisible();
  await expect
    .poll(async () => (await page.locator('#foundationNotes').boundingBox()).x)
    .toBeLessThan(2);
  await page.keyboard.press('Escape');
  await expect(page.locator('#foundationNotes')).toBeHidden();
  await tap(page, 'case');
  await expect.poll(async () => (await state(page)).open).toEqual(['case']);
});

test('Settings lights its menu button', async ({ page }) => {
  await open(page, 1280, 720);
  await tap(page, 'settings');
  await expect(page.locator('#set')).toBeVisible();
  expect((await state(page)).lit).toEqual(['settings']);
});

test('phones: pages stay full width (no menu offset)', async ({ page }) => {
  await open(page, 390, 800);
  await page.evaluate(() => document.querySelector('#openDonors').click());
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect
    .poll(async () => (await page.locator('#donorsPage').boundingBox()).x)
    .toBeLessThan(2);
  const box = await page.locator('#donorsPage').boundingBox();
  expect(Math.abs(box.width - 390)).toBeLessThan(2);
});
