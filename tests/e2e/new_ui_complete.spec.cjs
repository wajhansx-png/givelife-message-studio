const { test, expect } = require('@playwright/test');
const widths = [320, 390, 768, 1024, 1440, 1920];
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
  ].map((t) => ['donors/' + t, '#donorsPage']),
  ...[
    ['add', '#donorAddDialog'],
    ['bulk', '#donorPasteDialog'],
    ['pace', '#donorBatchPicker'],
    ['notes', '#foundationNotes'],
  ].map(([s, r]) => ['donors/all/' + s, r]),
];
test.beforeEach(async ({ page }) =>
  page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-theme', 'dark');
  }),
);
async function fits(page, selector) {
  const box = await page.locator(selector).boundingBox();
  expect(box, selector).not.toBeNull();
  expect(box.x, selector).toBeGreaterThanOrEqual(-1);
  expect(box.x + box.width, selector).toBeLessThanOrEqual(page.viewportSize().width + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
}
for (const width of widths) {
  test(`every /new route loads and fits at ${width}px`, async ({ page }) => {
    test.setTimeout(90000);
    await page.setViewportSize({ width, height: width === 320 ? 568 : 900 });
    const errors = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    for (const [route, root] of routes) {
      await page.goto('/new' + (route ? '#/' + route : ''));
      await expect(page.locator(root), route || 'home').toBeVisible();
      await fits(page, root);
      if (['donors/messages', 'donors/volunteers'].includes(route))
        await expect(page.locator('.donor-bottom')).toBeHidden();
      if (route === 'notes') {
        if (await page.locator('#notesPassword').isVisible()) {
          await page.locator('#notesPassword').fill('test-preview-only-pin');
          await page.locator('#notesUnlockButton').click();
        }
        await expect(page.locator('#notesEditor')).toBeVisible();
        await fits(page, '#notesTools');
        expect((await page.locator('#notesTools').boundingBox()).width).toBeLessThanOrEqual(400);
        expect(
          await page.locator('#notesTools').evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
        ).toBe(true);
      }
    }
    expect(errors).toEqual([]);
  });
  test(`follow-up and third DM message stay usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 320 ? 568 : 900 });
    await page.route('**/donor-messages', async (route) => {
      if (route.request().method() !== 'GET') return route.continue();
      const response = await route.fetch();
      const data = await response.json();
      const first = data.items[0];
      data.items = Array.from({ length: 3 }, (_, i) => ({
        ...first,
        id: 'audit-message-' + i,
        text: first.text || first.message || 'A sample message.',
      }));
      return route.fulfill({ response, json: data });
    });
    await page.goto('/new#/donors/messages');
    await expect(page.locator('.bank-preview').first()).toBeVisible();
    await expect(page.locator('.bank-followup-panel')).toBeHidden();
    for (let step = 0; step < 2; step++) {
      if (!(await page.locator('#ui2BankMore').evaluate((e) => e.open)))
        await page.locator('#ui2BankMore > summary').click();
      await page
        .locator('#ui2BankMore')
        .getByRole('button', { name: 'Next ›', exact: true })
        .click();
    }
    await expect(page.locator('.bank-current')).toContainText('Message 3');
    await fits(page, '.bank-detail');
    await page.getByRole('tab', { name: 'Follow-up', exact: true }).click();
    await expect(page.locator('.bank-followup-panel')).toBeVisible();
    const text = page.locator('.bank-followup-panel textarea');
    await fits(page, '.bank-followup-panel textarea');
    await text.fill('Please help if you can, {name}.');
    await page.getByRole('button', { name: 'Save follow-up', exact: true }).click();
    await expect(page.locator('#donorNotice')).toContainText(/saved/i);
    await page.reload();
    await page.getByRole('tab', { name: 'Follow-up', exact: true }).click();
    await expect(text).toHaveValue('Please help if you can, {name}.');
    await page.getByRole('button', { name: 'Back to donors', exact: false }).click();
    await expect(page.locator('#donorTable')).toBeVisible();
  });
  test(`compact donor Options and bounded amount at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/new#/donors/all');
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.locator('#ui2Options > summary').click();
    await fits(page, '.ui2-options-panel');
    expect((await page.locator('.ui2-options-panel').boundingBox()).width).toBeLessThanOrEqual(260);
    for (const id of ['donorAuto', 'donorRowPoster', 'donorFollowUpOpt'])
      await expect(page.locator('#ui2Options #' + id)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('#ui2Options')).not.toHaveAttribute('open', '');
    if (width >= 900) {
      const amount = page.locator('.donor-amount').first();
      await page.locator('.donor-row').first().hover();
      expect((await amount.boundingBox()).width).toBeLessThanOrEqual(110);
    }
  });
  test(`DM progress covers idle, starting, sending, waiting, completion at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    let state = 'Idle';
    await page.route('**/donor-delivery', (r) =>
      r.fulfill({
        json: {
          state,
          sent: 2,
          total: 5,
          original_total: 5,
          pending: 3,
          paused: false,
          receipts: [],
          scope: 'important',
        },
      }),
    );
    for (const next of ['Idle', 'Starting', 'Sending', 'Waiting', 'Completed']) {
      state = next;
      await page.goto('/new?state=' + next + '#/donors/all');
      await expect(page.locator('#donorProgress')).toHaveAttribute(
        'data-active',
        String(['Starting', 'Sending', 'Waiting'].includes(next)),
      );
      if (['Starting', 'Sending', 'Waiting'].includes(next)) {
        await expect(page.locator('#ui2DmSending')).toBeVisible();
        await expect(page.locator('#ui2DmSending')).toContainText(next + ': 2 of 5 sent');
        await expect(page.locator('#donorToggle')).toHaveAttribute('aria-busy', 'true');
        await expect(page.locator('#donorSendImportant')).toBeHidden();
        await expect(page.locator('#ui2Options > summary')).toBeVisible();
        await expect(page.locator('#donorMainBottom')).toBeVisible();
        await fits(page, '.donor-bottom');
        for (const selector of [
          '#ui2Options > summary',
          '#donorToggle',
          '#donorMainBottom',
          '#ui2DmSending',
        ]) {
          await expect
            .poll(
              () =>
                page.locator(selector).evaluate((e) => {
                  const r = e.getBoundingClientRect();
                  const at = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                  return at === e || e.contains(at);
                }),
              { message: selector + ' must not be covered' },
            )
            .toBe(true);
        }
      } else {
        await expect(page.locator('#ui2DmSending')).toBeHidden();
        await expect(page.locator('#donorToggle')).toBeHidden();
      }
    }
  });
}
test('home has message controls and Chat opens on its own screen', async ({ page }) => {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/new');
    await expect(page.locator('#main-workspace .talk')).toBeHidden();
    await expect(page.locator('#ui2HomeNext')).toBeVisible();
    await expect(page.locator('#ui2HomeTest')).toBeVisible();
    await (
      width < 900 ? page.locator('#ui2Tabs [data-tab=chat]') : page.locator('#ui2ChatOpen')
    ).click();
    await expect(page.locator('#hist')).toBeVisible();
    expect(page.url()).toContain('#/chat');
    await page.reload();
    await expect(page.locator('#hist')).toBeVisible();
  }
});
test('nested Top route returns to its own filter', async ({ page }) => {
  await page.goto('/new#/donors/top/pace');
  await expect(page.locator('#donorBatchPicker')).toBeVisible();
  await page.locator('#batchCancel').click();
  await expect(page).toHaveURL(/#\/donors\/top$/);
  await expect(page.locator('.donor-tabs [data-tab=top]')).toHaveAttribute('aria-selected', 'true');
});
test('group finder waits for research data before enabling its actions', async ({ page }) => {
  let release;
  const pending = new Promise((resolve) => (release = resolve));
  await page.route('**/api/group-finder?*', async (route) => {
    await pending;
    await route.continue();
  });
  await page.goto('/new/group-finder');
  await expect(page.locator('#importOpen')).toBeDisabled();
  await expect(page.locator('#targetsOpen')).toBeDisabled();
  await expect(page.locator('#findGroups')).toBeDisabled();
  release();
  await expect(page.locator('#importOpen')).toBeEnabled();
  await page.locator('#importOpen').click();
  await expect(page.locator('#importDialog')).toBeVisible();
});
for (const width of [320, 390, 768, 1440]) {
  test(`secondary screens and menus fit at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: width === 320 ? 568 : 900 });
    const auth = { Authorization: 'Bearer manual-fix-preview-key' };
    await request.post('/__test/seed', { headers: auth, data: { reply: 'Audit sample reply' } });
    const panels = [
      ['', '.report-open', '.report-dialog'],
      ['', '.reply-open', '.replies-dialog'],
      ['', '.resume-open', '.resume-groups-dialog'],
      ['donors/all', '#donorNumbers', '#donorNumbersDialog'],
      ['preview', '#focusManual', '#manualMessages'],
      ['preview', '#focusSave', '#focusBaseDialog'],
    ];
    for (const [route, trigger, root] of panels) {
      await page.goto('/new' + (route ? '#/' + route : ''));
      // Exercise the original opener, including actions normally reached through More.
      await page
        .locator(trigger)
        .first()
        .evaluate((e) => e.click());
      await expect(page.locator(root)).toBeVisible();
      await fits(page, root);
    }
    await page.goto('/new#/donors/all');
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.locator('.donor-row').first().locator('.donor-more > summary').click();
    await fits(page, '.donor-more[open] > div');
    await page.goto('/new/group-finder');
    await expect(page.locator('#findGroups')).toBeVisible();
    await fits(page, 'body');
    await page.locator('#importOpen').click();
    await expect(page.locator('dialog[open]')).toBeVisible();
    await fits(page, 'dialog[open]');
  });
}
for (const width of [320, 390, 1440]) {
  test(`Notes saves and locks; remaining dialog frames fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/new#/notes');
    if (await page.locator('#notesPassword').isVisible()) {
      await page.locator('#notesPassword').fill('test-preview-only-pin');
      await page.locator('#notesUnlockButton').click();
    }
    await expect(page.locator('#notesEditor')).toBeVisible();
    await page.locator('#notesEditor').fill('Sample notes for the responsive UI review.');
    await expect(page.locator('#notesSync')).toHaveText('Saved', { timeout: 10000 });
    await page.reload();
    if (await page.locator('#notesPassword').isVisible()) {
      await page.locator('#notesPassword').fill('test-preview-only-pin');
      await page.locator('#notesUnlockButton').click();
    }
    await expect(page.locator('#notesEditor')).toContainText('Sample notes');
    await page.locator('#notesLock').click();
    await expect(page.locator('#notesLocked')).toBeVisible();
    await page.goto('/new');
    // These dormant dialogs are also checked as components, separate from navigation coverage.
    for (const id of ['feedbackDialog', 'donorResumeDialog', 'volTimingDialog']) {
      await page.locator('#' + id).evaluate((e) => e.showModal());
      await fits(page, '#' + id);
      await page.locator('#' + id).evaluate((e) => e.close());
    }
  });
}
test('the full phone caption is unmasked, and Next/Test show in-progress states', async ({
  page,
  request,
}) => {
  const message = Array.from({ length: 14 }, (_, i) => 'Sample caption line ' + i + '.').join('\n');
  await request.post('/__test/seed', {
    headers: { Authorization: 'Bearer manual-fix-preview-key' },
    data: { group: message },
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/new');
  await expect(page.locator('#groupPreview')).toContainText('Sample caption line 13.');
  expect(await page.locator('#card').evaluate((e) => getComputedStyle(e).maskImage)).toBe('none');
  const caption = await page.locator('#groupPreview').boundingBox();
  const actions = await page.locator('#ui2HomeNext').boundingBox();
  expect(actions.y).toBeGreaterThanOrEqual(caption.y + caption.height - 1);

  expect(await page.locator('#chat').evaluate((e) => e.scrollHeight <= e.clientHeight + 1)).toBe(
    true,
  );
  await page.route('**/next-message', async (r) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await r.fulfill({ json: { message: 'The next sample caption.' } });
  });
  await page.locator('#ui2HomeNext').click();
  await expect(page.locator('#ui2HomeNext')).toBeDisabled();
  await expect(page.locator('#groupPreview')).toContainText('The next sample caption.');
  const sent = [];
  await page.route('**/test', async (r) => {
    sent.push(r.request().postDataJSON());
    await new Promise((resolve) => setTimeout(resolve, 500));
    await r.fulfill({ json: { code: 'SUCCESS' } });
  });
  await page.locator('#ui2HomeTest').click();
  await expect(page.locator('#ui2HomeTest')).toHaveAttribute('aria-busy', 'true');
  await expect(page.locator('#ui2HomeTest')).toBeEnabled();
  expect(sent).toHaveLength(1);
  expect(sent[0].message).toBe('The next sample caption.');
});
test('paused donor DMs keep Resume and its schedule reachable across widths', async ({ page }) => {
  await page.route('**/donor-delivery', (r) =>
    r.fulfill({
      json: {
        state: 'Stopped',
        sent: 2,
        total: 5,
        pending: 3,
        paused: true,
        receipts: [],
        scope: 'important',
      },
    }),
  );
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/new?resume=' + width + '#/donors/all');
    await expect(page.locator('#donorToggle')).toHaveText('Resume DMs');
    await expect(page.locator('#donorToggle')).toBeVisible();
    await expect(page.locator('#donorSendImportant')).toBeHidden();
    await page.locator('#donorToggle').click();
    await expect(page.locator('#donorResumeDialog')).toBeVisible();
    await page.locator('#donorResumeSchedule').click();
    await expect(page.locator('#donorResumeDate')).toBeVisible();
    await fits(page, '#donorResumeDialog');
    await page.locator('#donorResumeClose').click();
  }
});
test('volunteers own their sending controls and timing screen', async ({ page, request }) => {
  await request.post('/volunteers', {
    headers: { Authorization: 'Bearer manual-fix-preview-key' },
    data: { action: 'add', name: 'UI review volunteer', phone: '15551230999' },
  });
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/new?volunteer=' + width + '#/donors/volunteers');
    await expect(page.locator('.donor-bottom')).toBeHidden();
    await page.locator('#volMessage').fill('Sample sharing request for this review.');
    await page.getByRole('button', { name: 'DM all volunteers', exact: true }).click();
    await expect(page.locator('#volTimingDialog')).toBeVisible();
    await page.locator('#volStartDelay').selectOption('3600');
    await expect(page.locator('#volTimingStart')).toHaveText('Schedule DMs');
    await fits(page, '#volTimingDialog');
    await page.locator('#volTimingCancel').click();
  }
});
