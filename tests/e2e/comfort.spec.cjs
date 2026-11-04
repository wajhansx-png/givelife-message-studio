const { test, expect } = require('@playwright/test');
const { openSettings, openDonorMessages, showDm } = require('./helpers.cjs');
const path = require('node:path');
const auth = { Authorization: 'Bearer manual-fix-preview-key' };
async function open(page, request, width = 1440, height = 900, theme = 'dark') {
  await page.setViewportSize({ width, height });
  await page.addInitScript((t) => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-theme', t);
  }, theme);
  await request.post('/__test/seed', {
    headers: auth,
    data: {
      reply:
        "I've updated the message. The saved caption is ready to review.\n\n*Rs. 25,000 left.* Your existing settings are unchanged.",
    },
  });
  await page.goto('/');
  await expect(page.locator('#leftChip')).toContainText('25,000');
  await page.evaluate(() => document.fonts.ready);
}
async function shot(page, name) {
  if (process.env.COMFORT_SHOTS)
    await page.screenshot({
      path: path.join(process.env.COMFORT_SHOTS, name + '.png'),
      fullPage: false,
    });
}
async function inside(page, locator) {
  await expect(locator).toBeVisible();
  const b = await locator.boundingBox();
  expect(b).not.toBeNull();
  expect(b.x).toBeGreaterThanOrEqual(-1);
  expect(b.y).toBeGreaterThanOrEqual(-1);
  expect(b.x + b.width).toBeLessThanOrEqual(page.viewportSize().width + 1);
  expect(b.y + b.height).toBeLessThanOrEqual(page.viewportSize().height + 1);
}
test('desktop reading column centers the reply and composer', async ({ page, request }) => {
  await open(page, request, 1600, 900);
  await expect(page.locator('#log .bot').last()).toContainText('ready to review');
  await shot(page, 'desktop-chat');
  const box = await page.locator('#log .bot').last().boundingBox(),
    pane = await page.locator('.talk').boundingBox(),
    input = await page.locator('#cmdForm').boundingBox();
  expect(Math.abs(box.x + box.width / 2 - (pane.x + pane.width / 2))).toBeLessThan(3);
  expect(Math.abs(input.x + input.width / 2 - (box.x + box.width / 2))).toBeLessThan(3);
  expect(box.width).toBeLessThanOrEqual(780);
  expect(box.width).toBeGreaterThan(200);
  expect(
    await page
      .locator('#log .bot')
      .last()
      .evaluate((el) => getComputedStyle(el).textAlign),
  ).toBe('left');
  await page.locator('#mainNavMore > summary').click();
  await expect(page.locator('#gear')).toBeVisible();
});
for (const [width, height, theme] of [
  [1440, 900, 'light'],
  [1024, 768, 'dark'],
  [768, 1024, 'light'],
  [390, 844, 'dark'],
  [320, 640, 'light'],
]) {
  test(`all workspaces remain usable ${width} ${theme}`, async ({ page, request }) => {
    await open(page, request, width, height, theme);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await shot(page, `${width}-${theme}-main`);
    await openSettings(page);
    await inside(page, page.locator('#set'));
    await shot(page, `${width}-${theme}-settings`);
    await page.locator('#setClose:visible, #setCloseBottom:visible').first().click();
    await page.locator('#openDonors').click();
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await inside(page, page.locator('#donorsPage'));
    await shot(page, `${width}-${theme}-donors`);
    await openDonorMessages(page);
    await expect(page.locator('#donorMessages')).toBeVisible();
    await shot(page, `${width}-${theme}-messages`);
    if (width >= 390)
      await expect
        .poll(() =>
          page.locator('.bank-preview').evaluate((el) => el.scrollHeight <= el.clientHeight + 2),
        )
        .toBe(true);
    await page.getByRole('button', { name: 'Back to donors', exact: true }).click();
    await page.locator('#donorMainBottom').click();
    await showDm(page);
    await page.locator('#sendMoreDonors').click();
    await inside(page, page.getByRole('dialog', { name: 'Bulk message', exact: true }));
  });
}
test('mobile chat keeps draft, closes keyboard after send and has a reachable return row', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 844);
  await page.route('**/assistant', (r) => r.fulfill({ json: { reply: 'Your request is ready.' } }));
  await page.locator('#chatOpen').click();
  await page.locator('#histCmd').fill('check a synthetic request');
  await page.locator('#histMain').click();
  await page.locator('#chatOpen').click();
  await expect(page.locator('#histCmd')).toHaveValue('check a synthetic request');
  await page.locator('#histForm .go').click();
  await expect(page.locator('#histCmd')).not.toBeFocused();
  const send = await page.locator('#histForm .go').boundingBox();
  expect(send.width).toBeGreaterThanOrEqual(48);
  expect(send.height).toBeGreaterThanOrEqual(48);
  await inside(page, page.locator('#histMain'));
  await shot(page, 'mobile-chat');
  await page.setViewportSize({ width: 390, height: 450 });
  await expect
    .poll(async () => {
      const b = await page.locator('#histForm .go').boundingBox();
      return b && b.y + b.height <= 451;
    })
    .toBe(true);
  await inside(page, page.locator('#histMain'));
});
test('mobile library selection beyond first ten survives reload', async ({ page, request }) => {
  await open(page, request, 390, 844);
  await page.locator('#openDonors').click();
  await openDonorMessages(page);
  for (let i = 0; i < 19; i++)
    await page.getByRole('button', { name: 'Next message', exact: true }).click();
  await expect(page.locator('.bank-detail header')).toContainText('Message 20');
  await page.reload();
  /* A refresh keeps the screen: Donors is still open on its Messages tab. */
  await expect(page.locator('.bank-current')).toHaveText('Message 20 of 20');
});
test('donor tabs support arrow keys without retaining stale search', async ({ page, request }) => {
  await open(page, request);
  await page.locator('#openDonors').click();
  await page.locator('#donorSearch').fill('not-a-donor');
  const all = page.locator('[data-tab=all]');
  await all.click();
  await expect(page.locator('#donorSearch')).toHaveValue('');
  await all.press('ArrowRight');
  await expect(page.locator('[data-tab=important]')).toBeFocused();
  await expect(page.locator('[data-tab=important]')).toHaveAttribute('aria-selected', 'true');
});
test('message library switches previews and preserves unsaved edits', async ({ page, request }) => {
  await open(page, request);
  await page.locator('#openDonors').click();
  await openDonorMessages(page);
  await page.getByRole('button', { name: 'Message 2', exact: true }).click();
  await expect(page.locator('.bank-detail header')).toContainText('Message 2');
  await page.locator('.bank-actions').getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Edit message 2', { exact: true }).fill('Synthetic edited caption.');
  await page.getByRole('button', { name: 'Message 1', exact: true }).click();
  await page.getByRole('button', { name: 'Message 2', exact: true }).click();
  await expect(page.getByLabel('Edit message 2', { exact: true })).toHaveValue(
    'Synthetic edited caption.',
  );
  await page.reload();
  await expect(page.getByLabel('Edit message 2', { exact: true })).toHaveValue(
    'Synthetic edited caption.',
  );
});
test('failed chat requests keep the typed draft without retrying', async ({ page, request }) => {
  await open(page, request);
  let calls = 0;
  await page.route('**/assistant', (r) => {
    calls++;
    return r.abort();
  });
  await page.locator('#cmd').fill('Please explain this synthetic campaign carefully.');
  await page.locator('#cmdForm .go').click();
  await expect(page.locator('#cmd')).toHaveValue(
    'Please explain this synthetic campaign carefully.',
  );
  expect(calls).toBe(1);
});
test('first use defaults to dark; light and device themes persist and update', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await openSettings(page);
  await page.locator('#theme [data-t=light]').click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('#set')).toBeVisible();
  await page.locator('#theme [data-t=system]').click();
  expect(await page.locator('html').evaluate((el) => getComputedStyle(el).colorScheme)).toBe(
    'light',
  );
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect
    .poll(() => page.locator('html').evaluate((el) => getComputedStyle(el).colorScheme))
    .toBe('dark');
});
test('typing during a slow save keeps newer text as an unsaved draft', async ({
  page,
  request,
}) => {
  await open(page, request);
  await page.locator('#openDonors').click();
  await openDonorMessages(page);
  let release, submitted;
  await page.route('**/donor-messages', async (route) => {
    if (route.request().method() === 'POST' && route.request().postDataJSON().id) {
      submitted = route.request().postDataJSON();
      await new Promise((resolve) => (release = resolve));
    }
    await route.continue();
  });
  await page.locator('.bank-actions').getByRole('button', { name: 'Edit', exact: true }).click();
  const editor = page.getByLabel('Edit message 1', { exact: true }),
    sentText = (await editor.inputValue()) + '\n\nSynthetic submitted A',
    newerText = sentText + '\nNewer draft B';
  await editor.fill(sentText);
  await page.locator('.bank-detail').getByRole('button', { name: 'Save', exact: true }).click();
  await expect.poll(() => !!submitted).toBe(true);
  await editor.fill(newerText);
  release();
  await expect(page.locator('#donorNotice')).toContainText('newer edits are still unsaved');
  await expect(editor).toHaveValue(newerText);
  const stored = await (await request.get('/donor-messages', { headers: auth })).json();
  expect(stored.items.find((item) => item.id === submitted.id).text).toBe(sentText);
  await page.reload();
  await expect(page.getByLabel('Edit message 1', { exact: true })).toHaveValue(newerText);
});
test('regeneration cannot be duplicated by switching message previews', async ({
  page,
  request,
}) => {
  await open(page, request);
  await page.locator('#openDonors').click();
  await openDonorMessages(page);
  let release,
    calls = 0;
  await page.route('**/donor-messages', async (route) => {
    if (
      route.request().method() === 'POST' &&
      route.request().postDataJSON().action === 'regenerate'
    ) {
      calls++;
      await new Promise((resolve) => (release = resolve));
    }
    await route.continue();
  });
  await page.getByRole('button', { name: 'Regenerate', exact: true }).click();
  await expect.poll(() => calls).toBe(1);
  await page.getByRole('button', { name: 'Message 2', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Regenerate', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('button', { name: 'Regenerate', exact: true })).toBeEnabled();
  expect(calls).toBe(1);
});
for (const width of [1440, 390])
  test(`secondary screens retain accessible exits at ${width}`, async ({ page, request }) => {
    await open(page, request, width, 844);
    await openSettings(page);
    await page.getByRole('button', { name: 'Change poster', exact: true }).click();
    await inside(page, page.locator('#posterDialog'));
    await shot(page, `${width}-poster`);
    await page.locator('#posterClose').click();
    await page.locator('#openMemory').click();
    await inside(page, page.locator('#memoryDialog'));
    await page.locator('#memoryClose').click();
    await page.locator('#setClose:visible, #setCloseBottom:visible').first().click();
    await page.locator('#whatsappConnection').click();
    const wa = page.getByRole('dialog', { name: 'WhatsApp connection', exact: true });
    await inside(page, wa);
    await shot(page, `${width}-whatsapp`);
    await page.locator('#waCloudClose').click();
    await page.locator('#openDonors').click();
    await page.locator('#donorAdd').click();
    await inside(page, page.locator('#donorAddDialog'));
    await shot(page, `${width}-add-donor`);
    await page.locator('#donorAddCancel').click();
    await page.locator('#donorMain:visible, #donorMainBottom:visible').first().click();
    if (width >= 900) await page.locator('#chatExpand').click();
    else await page.locator('#chatOpen').click();
    await inside(page, page.locator('#hist'));
    await shot(page, `${width}-history`);
  });
test('an empty message library explains how to recover', async ({ page, request }) => {
  await open(page, request);
  await page.route('**/donor-messages', (r) => r.fulfill({ json: { items: [] } }));
  await page.locator('#openDonors').click();
  await openDonorMessages(page);
  await expect(page.locator('#donorMessages')).toContainText('No saved messages yet');
  await expect(page.getByRole('button', { name: 'Regenerate', exact: true })).toBeEnabled();
});
for (const [width, height] of [
  [1280, 720],
  [1024, 768],
  [1024, 600],
])
  test(`all group controls fit the laptop ${width}x${height}`, async ({ page, request }) => {
    await open(page, request, width, height);
    for (const selector of ['.send-title h2', '[data-group=main]', '[data-test=group]', '#sendAll'])
      await inside(page, page.locator(selector).first());
    for (const button of await page.locator('#chips button').all()) await inside(page, button);
    expect(
      await page.locator('.action-rail').evaluate((el) => el.scrollHeight <= el.clientHeight + 2),
    ).toBe(true);
  });
for (const [width, height] of [
  [390, 700],
  [360, 640],
  [320, 568],
])
  test(`mobile Messages shows every full variant with Next ${width}x${height}`, async ({
    page,
    request,
  }) => {
    await page.route('**/donor-delivery', (r) =>
      r.fulfill({ json: { state: 'Completed', sent: 12, total: 12, receipts: [] } }),
    );
    await open(page, request, width, height);
    await page.locator('#openDonors').click();
    await openDonorMessages(page);
    await expect(page.locator('#donorSearch')).not.toBeVisible();
    await expect(page.locator('.donor-bottom')).not.toBeVisible();
    await expect(page.locator('#donorProgress')).not.toBeVisible();
    const total = 20;
    await expect(page.locator('.bank-mobile-picker')).toHaveCount(0);
    await expect(
      page.getByRole('button', { name: 'Previous message', exact: true }),
    ).toBeDisabled();
    for (let i = 0; i < total; i++) {
      await expect(page.locator('.bank-current')).toHaveText('Message ' + (i + 1) + ' of ' + total);
      await expect
        .poll(() =>
          page.locator('.bank-preview').evaluate((el) => el.scrollHeight <= el.clientHeight + 2),
        )
        .toBe(true);
      await inside(page, page.getByRole('button', { name: 'Next message', exact: true }));
      if (i === 0 || i === total - 1) await shot(page, `${width}x${height}-reader-${i + 1}`);
      if (i < total - 1)
        await page.getByRole('button', { name: 'Next message', exact: true }).click();
    }
    await expect(page.getByRole('button', { name: 'Next message', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Previous message', exact: true }).click();
    await expect(page.locator('.bank-current')).toHaveText(
      'Message ' + (total - 1) + ' of ' + total,
    );
  });
test('phone donor rows fit real-length names and confirmed DM labels', async ({
  page,
  request,
}) => {
  const base = await (await request.get('/donors', { headers: auth })).json();
  const items = Array.from({ length: 189 }, (_, i) => ({
    ...base.items[i % base.items.length],
    id: 'synthetic-' + i,
    name: 'Synthetic Community Donor ' + (i + 1),
    important: i < 12,
    delivery: 'Sent',
    donated: false,
    amount: 0,
  }));
  await page.route(/\/donors(\?.*)?$/, (r) =>
    r.fulfill({
      json: {
        ...base,
        items,
        counts: {
          all: 189,
          important: 12,
          donated: 0,
          not_donated: 189,
          not_contacted: 189,
          donated_amount: 0,
        },
      },
    }),
  );
  await page.route('**/donor-delivery', (r) =>
    r.fulfill({ json: { state: 'Completed', sent: 12, total: 12, receipts: [] } }),
  );
  await open(page, request, 390, 700);
  await page.locator('#openDonors').click();
  await expect(page.locator('#donorTotal')).toHaveText('189');
  expect((await page.locator('.donor-head').boundingBox()).height).toBeLessThanOrEqual(64);
  const row = page.locator('.donor-row').first();
  await expect(row.locator('.donor-amount')).not.toBeVisible();
  expect((await row.locator('.donor-name').boundingBox()).width).toBeGreaterThanOrEqual(110);
  expect(
    await row.locator('.donor-dm').evaluate((el) => el.scrollWidth <= el.clientWidth + 2),
  ).toBe(true);
  expect(
    await page.locator('#donorTable').evaluate((el) => el.scrollWidth <= el.clientWidth + 2),
  ).toBe(true);
  expect(
    await page.locator('#donorTable').evaluate((el) => {
      const b = el.getBoundingClientRect();
      return [...el.querySelectorAll('.donor-row')].filter((row) => {
        const r = row.getBoundingClientRect();
        return r.top >= b.top && r.bottom <= b.bottom;
      }).length;
    }),
  ).toBeGreaterThanOrEqual(9);
  await shot(page, 'phone-realistic-donors');
});
test('delivery refresh updates donor counts without replacing the active editor', async ({
  page,
  request,
}) => {
  // The app no longer creates sample DM templates on opening this screen.
  await page.route('**/donor-messages', (r) => r.fulfill({ json: { items: [{ id: 'layout-editable', text: 'Bhai, this is a synthetic saved DM.' }], generation: {} } }));
  let sent = 12;
  const base = await (await request.get('/donors', { headers: auth })).json();
  await page.route(/\/donors(\?.*)?$/, (r) =>
    r.fulfill({
      json: {
        ...base,
        items:
          sent === 13
            ? [
                ...base.items,
                { ...base.items[0], id: 'synthetic-new', name: 'Another synthetic donor' },
              ]
            : base.items,
      },
    }),
  );
  await page.route('**/donor-delivery', (r) =>
    r.fulfill({
      json: { state: sent === 12 ? 'Waiting' : 'Completed', sent, total: 13, receipts: [] },
    }),
  );
  await open(page, request);
  await page.locator('#openDonors').click();
  await openDonorMessages(page);
  await page.locator('.bank-actions').getByRole('button', { name: 'Edit', exact: true }).click();
  const editor = page.getByLabel('Edit message 1', { exact: true });
  await editor.fill('Draft must survive a delivery refresh.');
  sent = 13;
  await expect(page.locator('#donorTotal')).toHaveText(String(base.items.length + 1));
  await expect(editor).toBeFocused();
  await expect(editor).toHaveValue('Draft must survive a delivery refresh.');
});
