const { test, expect } = require('@playwright/test');
const headers = { Authorization: 'Bearer manual-fix-preview-key' };

test('mobile donor tabs center the selection and let the user scroll the strip', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 740 });
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    window.tabScrolls = [];
    const scrollTo = Element.prototype.scrollTo;
    Element.prototype.scrollTo = function (...args) {
      if (this.classList.contains('donor-tabs')) window.tabScrolls.push(args[0]);
      return scrollTo.apply(this, args);
    };
  });
  await page.goto('/#/donors/all');
  const strip = page.locator('.donor-tabs');
  const top = strip.locator('[data-tab=top]');
  await expect(page.locator('#donorRows .donor-row').first()).toBeVisible();
  const fits = (tab) =>
    tab.evaluate((el) => {
      const box = el.getBoundingClientRect();
      const parent = el.parentElement.getBoundingClientRect();
      return box.left >= parent.left - 1 && box.right <= parent.right + 1;
    });
  const offsetFromCenter = (tab) =>
    tab.evaluate((el) => {
      const box = el.getBoundingClientRect();
      const parent = el.parentElement.getBoundingClientRect();
      return Math.abs(box.left + box.width / 2 - (parent.left + parent.width / 2));
    });
  expect(await fits(top)).toBe(true);
  expect(await offsetFromCenter(top)).toBeGreaterThan(20);
  const scrolls = () => page.evaluate(() => window.tabScrolls.length);
  await page.evaluate(() => {
    window.tabScrolls.length = 0;
  });
  await top.click();
  await expect(top).toHaveAttribute('aria-selected', 'true');
  await expect.poll(() => offsetFromCenter(top)).toBeLessThan(2);
  expect(await scrolls()).toBe(1);

  const clipped = strip.locator('[data-tab=not_contacted]');
  expect(await fits(clipped)).toBe(false);
  // Use the app click path without Playwright pre-scrolling the target.
  await clipped.evaluate((el) => el.click());
  await expect(clipped).toHaveAttribute('aria-selected', 'true');
  await expect.poll(() => offsetFromCenter(clipped)).toBeLessThan(2);
  expect(await scrolls()).toBe(2);

  const swipeToStart = async () => {
    await strip.hover();
    await page.mouse.wheel(-1000, 0);
    await expect.poll(() => strip.evaluate((el) => el.scrollLeft)).toBe(0);
  };
  // Volunteers widens the strip. From the start it still has to scroll to reach the last tab.
  await swipeToStart();
  const last = strip.locator('[data-tab=volunteers]');
  expect(await fits(last)).toBe(false);
  await last.evaluate((el) => el.click());
  await expect(last).toHaveAttribute('aria-selected', 'true');
  await expect.poll(() => fits(last)).toBe(true);
  expect(await scrolls()).toBe(3);

  await swipeToStart();
  await expect(last).toHaveAttribute('aria-selected', 'true');
  expect(await scrolls()).toBe(3);
});

test('returning to Messages while it loads reuses the request', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 740 });
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-follow-up', '0');
  });
  await page.goto('/#/donors/all');
  await expect(page.locator('#donorRows .donor-row').first()).toBeVisible();
  let requests = 0;
  let release;
  const ready = new Promise((resolve) => {
    release = resolve;
  });
  await page.route('**/donor-messages', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    requests++;
    await ready;
    await route.continue();
  });
  try {
    const messages = page.locator('#donorMessagesTab');
    await messages.evaluate((b) => b.click());
    await expect.poll(() => requests).toBe(1);
    await page.locator('.donor-tabs [data-tab=all]').evaluate((b) => b.click());
    await messages.evaluate((b) => b.click());
    await expect(page.locator('#donorMessages')).toContainText('Loading saved message variants');
  } finally {
    release();
  }
  await expect(page.locator('#donorMessages .bank-detail')).toBeVisible();
  expect(requests).toBe(1);
});

for (const width of [1440, 390])
  test(`favourite keeps donor list scroll after save at ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 700 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    const all = (await (await request.get('/donors?tab=all', { headers })).json()).items;
    for (let i = all.length; i < 80; i++)
      await request.post('/donors', {
        headers,
        data: {
          action: 'add',
          name: 'Scroll donor ' + String(i).padStart(3, '0'),
          phone: '1555' + String(1230000 + i),
        },
      });
    await page.goto('/new#/donors/all');
    const table = page.locator('#donorTable');
    const rows = table.locator('.donor-row');
    await expect(rows.first()).toBeVisible();
    if (width === 390) {
      await page.evaluate(
        () =>
          new Promise((resolve) => {
            let left = 15;
            function frame() {
              if (--left) requestAnimationFrame(frame);
              else resolve();
            }
            requestAnimationFrame(frame);
          }),
      );
      expect(await rows.count()).toBeLessThan(80);
    }
    await expect
      .poll(async () => {
        await table.evaluate((el) => (el.scrollTop = el.scrollHeight));
        return rows.count();
      })
      .toBe(80);
    await table.evaluate((el) => (el.scrollTop = 1600));
    const before = await table.evaluate((el) => el.scrollTop);
    expect(before).toBeGreaterThan(500);
    const target = await page.locator('#donorTable').evaluate(
      (el) =>
        [...el.querySelectorAll('.donor-row')].find((row) => {
          const r = row.getBoundingClientRect(),
            box = el.getBoundingClientRect();
          return r.top > box.top + 50 && r.bottom < box.bottom - 10;
        })?.dataset.donorId,
    );
    expect(target).toBeTruthy();
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/donors') && r.request().method() === 'POST',
    );
    /* Tap the star where a person sees it. locator.click() first runs Playwright's own scroll-into-view while the
       rows settle, which moves the list itself and hides what the app really does. */
    const star = page.locator(`[data-donor-id="${target}"] .donor-star`);
    const box = await star.boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    expect((await saved).ok()).toBe(true);
    await expect
      .poll(() => page.locator('#donorTable').evaluate((el) => el.scrollTop))
      .toBe(before);
    await page.waitForTimeout(250);
    expect(await page.locator('#donorTable').evaluate((el) => el.scrollTop)).toBe(before);
  });

test('one ArrowRight press activates a donor tab once', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/#/donors/all');
  const tabs = page.locator('.donor-tabs');
  const important = tabs.locator('[data-tab=important]');
  await important.evaluate((button) => {
    button.addEventListener('click', () => {
      button.dataset.clicks = Number(button.dataset.clicks || 0) + 1;
    });
  });
  await tabs.locator('[data-tab=all]').focus();
  await page.keyboard.press('ArrowRight');
  await expect(important).toHaveAttribute('data-clicks', '1');
  await expect(tabs.locator('[data-tab=important]')).toBeFocused();
  await expect(page).toHaveURL(/#\/donors\/important$/);
});

test('a failed overlapping donor refresh reports the error and can be retried', async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/#/donors/all');
  await expect(page.locator('#donorRows .donor-row').first()).toBeVisible();
  let release;
  const hold = new Promise((resolve) => (release = resolve));
  let requested = false;
  await page.route('**/donors?tab=all', async (route) => {
    requested = true;
    await hold;
    await route.fulfill({ status: 503, json: { error: 'Donor list temporarily unavailable' } });
  });
  await page.evaluate(() => {
    window.donorRefreshes = Promise.allSettled([
      window.DonorHub.refresh(true),
      window.DonorHub.refresh(true),
    ]);
  });
  try {
    await expect.poll(() => requested).toBe(true);
  } finally {
    release();
  }
  const statuses = await page.evaluate(async () =>
    (await window.donorRefreshes).map((r) => r.status),
  );
  expect(statuses).toEqual(['fulfilled', 'fulfilled']);
  await expect(page.locator('#donorNotice')).toContainText('Donor list temporarily unavailable');
  await page.unroute('**/donors?tab=all');
  await page.evaluate(() => window.DonorHub.refresh(true));
  await expect(page.locator('#donorRows .donor-row').first()).toBeVisible();
});

test('a delayed donor list cannot undo a saved star', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/#/donors/all');
  const row = page.locator('#donorRows .donor-row').first();
  await expect(row).toBeVisible();
  const id = await row.getAttribute('data-donor-id');
  const star = page.locator(`[data-donor-id="${id}"] .donor-star`);
  const expected = (await star.getAttribute('aria-pressed')) === 'true' ? 'false' : 'true';
  let release;
  const hold = new Promise((resolve) => (release = resolve));
  let captured = false;
  await page.route('**/donors?tab=all', async (route) => {
    const response = await route.fetch();
    captured = true;
    await hold;
    await route.fulfill({ response });
  });
  await page.evaluate(() => {
    window.pendingDonorRefresh = window.DonorHub.refresh(true);
  });
  try {
    await expect.poll(() => captured).toBe(true);
    const response = page.waitForResponse((r) => {
      return new URL(r.url()).pathname === '/donors' && r.request().method() === 'POST';
    });
    await star.click();
    expect((await response).ok()).toBe(true);
    await expect(star).toHaveAttribute('aria-pressed', expected);
  } finally {
    release();
  }
  await page.evaluate(() => window.pendingDonorRefresh);
  await expect(star).toHaveAttribute('aria-pressed', expected);
});
