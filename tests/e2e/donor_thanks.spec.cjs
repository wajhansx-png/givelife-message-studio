const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 241;
const headers = { Authorization: 'Bearer ' + KEY };
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
for (const width of [1440, 768, 390, 320, 280]) {
  test(`Thank donors composer and attached caption at ${width}px`, async ({ page, request }) => {
    const added = await (
      await request.post('/donors', {
        headers,
        data: {
          action: 'add',
          name: 'Supporter ' + width,
          phone: '1555123' + String(width).padStart(4, '0'),
        },
      })
    ).json();
    expect(added.donor).toBeTruthy();
    await request.post('/donors', {
      headers,
      data: { action: 'update', id: added.donor.id, donated: true },
    });
    await request.post('/left', { headers, data: { left: 0 } });
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/donors/donated');
    const button = page.getByRole('button', { name: 'Thank donors', exact: true });
    await expect(button).toBeVisible();
    const box = await button.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    await button.click();
    await expect(page.getByRole('dialog', { name: 'Thank donors', exact: true })).toBeVisible();
    const dialog = await page.locator('#donorThanksDialog').boundingBox();
    // A centered popup on phones, tablets and desktop (never a full-screen takeover).
    expect(dialog.x).toBeGreaterThanOrEqual(0);
    expect(dialog.y).toBeGreaterThanOrEqual(0);
    expect(dialog.width).toBeLessThanOrEqual(Math.min(width - 16, 724));
    expect(dialog.x + dialog.width).toBeLessThanOrEqual(width + 1);
    expect(dialog.y + dialog.height).toBeLessThanOrEqual(900 + 1);
    await expect(page.locator('.thanks-review')).toHaveCount(0); // no Preview section
    await expect(page.locator('.thanks-media .thanks-attach')).toHaveText(['+ Image', '+ Video']);
    await expect(page.locator('#thanksGapSel')).toBeVisible(); // timing is always shown
    // Start clean: an earlier width may have left attachments saved on the shared server.
    while ((await page.locator('.thanks-item').count()) > 0)
      await page.locator('#thanksRemove').click();
    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII=',
      'base64',
    );
    // Several files at once, and more later: no fixed limit of one image and one video.
    await page.locator('#thanksFile').setInputFiles([
      { name: 'proof.png', mimeType: 'image/png', buffer: png },
      { name: 'second.png', mimeType: 'image/png', buffer: png },
      { name: 'third.png', mimeType: 'image/png', buffer: png },
    ]);
    await expect(page.locator('#thanksStatus')).toContainText('Media ready');
    await expect(page.locator('.thanks-item')).toHaveCount(3);
    const chooser = page.waitForEvent('filechooser');
    await page.locator('#thanksAttachVid').click(); // a real tap on "Attach video" adds a fourth
    await (await chooser).setFiles({ name: 'fourth.png', mimeType: 'image/png', buffer: png });
    await expect(page.locator('.thanks-item')).toHaveCount(4);
    // Every caption is editable without an expansion step.
    await expect(page.locator('#thanksMediaSelect')).toBeVisible();
    await expect(page.locator('.thanks-item:not([hidden]) .thanks-field-label')).toHaveText('Caption');
    await expect(page.locator('#thanksStartLabel')).toHaveText('Start');
    for (const [n, text] of [
      [1, 'Alhamdulillah, the case is complete.'],
      [3, 'Third caption.'],
    ]) {
      await page.locator('#thanksMediaSelect').selectOption(String(n - 1));
      const item = page.locator('.thanks-item').nth(n - 1);

      await item.locator('textarea').fill(text);
    }
    await expect(page.locator('#thanksMessage')).toBeVisible();
    await page
      .locator('#donorThanksDialog')
      .getByLabel('Message', { exact: true })
      .fill('JazakAllah khair, {name}.');
    // Timing: four dropdowns of common choices; "Custom…" opens the exact minute / second boxes.
    for (const id of ['thanksGapSel', 'thanksVarySel', 'thanksBatchSel', 'thanksRestSel'])
      await expect(page.locator('#' + id)).toBeVisible();
    await expect(page.locator('[data-preset]')).toHaveCount(0);
    await expect(page.locator('#thanksGap')).toBeHidden(); // exact boxes only under Custom
    await expect(page.locator('#thanksBatchSel')).toHaveValue('10');
    await expect(page.locator('#thanksRestSel')).toHaveValue('1200');
    await page.locator('#thanksGapSel').selectOption('120');
    await page.locator('#thanksVarySel').selectOption('15');
    await page.locator('#thanksRestSel').selectOption('custom');
    await expect(page.locator('#thanksRest')).toBeVisible();
    await page.locator('#thanksRest').fill('1');
    await page.locator('#thanksRestSec').fill('45');
    // Test: the update goes to the GiveLife test group only, never to a donor.
    const beforeTest = (await (await request.get('/__test/events', { headers })).json()).events
      .length;
    await page.locator('#thanksTest').click();
    await expect(page.locator('#thanksStatus')).toContainText(
      'Test sent to the GiveLife test group',
    );
    const testEvents = (
      await (await request.get('/__test/events', { headers })).json()
    ).events.slice(beforeTest);
    expect(testEvents).toHaveLength(5); // four attachments, then the message
    for (const e of testEvents) expect(e.fields.phone).toBe('120363431210327603@g.us');
    expect(testEvents[0].path).toContain('/send/image');
    expect(testEvents.slice(0, 4).map((e) => e.fields.caption || '')).toEqual([
      'Alhamdulillah, the case is complete.',
      '',
      'Third caption.',
      '',
    ]);
    expect(testEvents[4].fields.message).toBe('JazakAllah khair, Test Bhai.');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.locator('#thanksStatus')).toContainText('Update saved');
    const saved = (await (await request.get('/donor-thanks', { headers })).json()).settings;
    expect([saved.gap_minutes, saved.gap_seconds, saved.vary_seconds, saved.rest_seconds]).toEqual([
      2, 0, 15, 45,
    ]);
    const cur = await (await request.get('/donor-thanks', { headers })).json();
    await request.post('/donor-thanks', {
      headers,
      data: {
        action: 'settings',
        case_id: cur.case_id,
        settings: {
          gap_minutes: 5,
          gap_seconds: 0,
          vary_seconds: 0,
          batch_size: 10,
          rest_minutes: 20,
          rest_seconds: 0,
        },
      },
    }); // back to the defaults for the next test
    await page.getByRole('button', { name: 'Close Thank donors', exact: true }).click();
    await button.click();
    await expect(page.locator('.thanks-item')).toHaveCount(4); // all four attachments came back
    await expect(page.locator('.thanks-item').nth(0).locator('textarea')).toHaveValue(
      'Alhamdulillah, the case is complete.',
    );
    await expect(page.locator('.thanks-item').nth(2).locator('textarea')).toHaveValue(
      'Third caption.',
    );
    const before = (await (await request.get('/__test/events', { headers })).json()).events.length;
    await page.locator('#thanksSwitch').click(); // the start toggle
    await expect
      .poll(
        async () => (await (await request.get('/__test/events', { headers })).json()).events.length,
      )
      .toBe(before + 5);
    const events = (await (await request.get('/__test/events', { headers })).json()).events.slice(
      before,
    );
    expect(events[0].path).toContain('/send/image');
    expect(events[0].fields.caption).toBe('Alhamdulillah, the case is complete.');
    expect(events.slice(0, 4).map((e) => e.fields.caption || '')).toEqual([
      'Alhamdulillah, the case is complete.',
      '',
      'Third caption.',
      '',
    ]); // each with its own caption, in order
    expect(events[4].path).toContain('/send/message');
    expect(events[4].fields.message).toBe('JazakAllah khair, Bhai.');
    expect(events[0].fields.phone).toBe('1555123' + String(width).padStart(4, '0'));
    await expect
      .poll(async () => {
        const status = await (await request.get('/donor-thanks', { headers })).json();
        return status.recipients.find((r) => r.id === added.donor.id).state;
      })
      .toBe('Sent');
    await expect(page.locator('#donorThanksDialog')).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  });
}

test('Report exposes editable 5/10/20 Thanks donors pacing and endpoints require authentication', async ({
  page,
  request,
}) => {
  expect((await request.get('/donor-thanks')).status()).toBe(401);
  expect((await request.post('/donor-thanks', { data: { action: 'start' } })).status()).toBe(401);
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  await page.evaluate(() => document.querySelector('.report-open').click());
  const card = page.locator('.auto-card[data-control="thanks"]');
  await expect(card.getByRole('switch', { name: 'Thanks donors', exact: true })).toBeVisible();
  await card.locator('h4').click();
  await expect(card.locator('[name=gap_minutes]')).toHaveValue('5');
  await expect(card.locator('[name=batch_size]')).toHaveValue('10');
  await expect(card.locator('[name=rest_minutes]')).toHaveValue('20');
  await card.locator('[name=gap_minutes]').fill('6');
  await card.getByRole('button', { name: 'Save', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get('/donor-thanks', { headers })).json()).settings.gap_minutes,
    )
    .toBe(6);
});

for (const [mime, caption, suffix] of [
  ['video/mp4', 'Alhamdulillah, case completed.', '01'],
  ['video/mp4', '', '02'],
  ['application/pdf', 'Completion receipt.', '03'],
]) {
  test(`${mime} sends as one attachment ${caption ? 'with its caption' : 'without a caption'}`, async ({
    request,
  }) => {
    const phone = '155512398' + suffix;
    const added = await (
      await request.post('/donors', {
        headers,
        data: { action: 'add', name: 'Media supporter ' + suffix, phone },
      })
    ).json();
    await request.post('/donors', {
      headers,
      data: { action: 'update', id: added.donor.id, donated: true },
    });
    await request.post('/left', { headers, data: { left: 0 } });
    const raw =
      mime === 'video/mp4'
        ? Buffer.from([0, 0, 0, 20, ...Buffer.from('ftypisom0000')])
        : Buffer.from('%PDF-1.4\ncompletion');
    const upload = await (
      await request.post('/upload-image', {
        headers,
        data: { use: 'bulk', data: 'data:' + mime + ';base64,' + raw.toString('base64') },
      })
    ).json();
    let view = await (await request.get('/donor-thanks', { headers })).json();
    // The previous UI test edited its gap; changing media must not change timing.
    const saved = await request.post('/donor-thanks', {
      headers,
      data: {
        action: 'save',
        case_id: view.case_id,
        revision: view.revision,
        caption,
        message: '',
        attachment: upload.id,
        filename: 'Completion proof',
      },
    });
    expect(saved.ok()).toBe(true);
    view = await saved.json();
    const before = (await (await request.get('/__test/events', { headers })).json()).events.length;
    const start = await request.post('/donor-thanks', {
      headers,
      data: { action: 'start', case_id: view.case_id, revision: view.revision },
    });
    expect(start.ok()).toBe(true);
    await expect
      .poll(
        async () => (await (await request.get('/__test/events', { headers })).json()).events.length,
      )
      .toBe(before + 1);
    const event = (await (await request.get('/__test/events', { headers })).json()).events[before];
    expect(event.path).toContain(mime === 'video/mp4' ? '/send/video' : '/send/file');
    expect(event.fields.phone).toBe(phone);
    if (caption) expect(event.fields.caption).toBe(caption);
    else expect(event.fields.caption || '').toBe('');
  });
}

test('Donated tab: the start toggle and Test sit in the one thanks row, and only on that tab', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await expect(page.locator('#thanksTabSwitch')).toBeVisible();
  await expect(page.locator('#thanksTabTest')).toBeVisible();
  const row = await page.locator('.thanks-tab-row').boundingBox();
  for (const sel of ['#thanksTabSwitch', '#thanksTabTest']) {
    const b = await page.locator(sel).boundingBox();
    expect(b.y, sel).toBeGreaterThanOrEqual(row.y - 1);
    expect(b.y + b.height, sel).toBeLessThanOrEqual(row.y + row.height + 1);
    expect(b.x + b.width, sel).toBeLessThanOrEqual(390);
  }
  await page.locator('.donor-tabs [data-tab="all"]').click();
  await expect(page.locator('#thanksTabSwitch')).toBeHidden();
});

test('an open tab says "New version ready" when the server has been updated, and Refresh reloads', async ({
  page,
}) => {
  let version = 'abc1234';
  await page.route('**/health', (route) => route.fulfill({ json: { ok: true, version } }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  await expect(page.locator('#updateBar')).toHaveCount(0);
  version = 'def5678';
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(page.locator('#updateBar')).toContainText('New version ready');
  const box = await page.locator('#updateBar button').boundingBox();
  expect(box.height).toBeGreaterThanOrEqual(40);
  await Promise.all([page.waitForEvent('load'), page.locator('#updateBar button').click()]);
  await expect(page.locator('#updateBar')).toHaveCount(0);
});

test('start shows immediately while saving, then restores on failure', async ({ page, request }) => {
  const added = await (await request.post('/donors', {
    headers,
    data: { action: 'add', name: 'Toggle Test', phone: '15551239991' },
  })).json();
  await request.post('/donors', { headers, data: { action: 'update', id: added.donor.id, donated: true } });
  await request.post('/left', { headers, data: { left: 0 } });
  await page.addInitScript(k => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await page.getByRole('button', { name: 'Thank donors', exact: true }).click();
  await page.locator('#thanksMessage').fill('Thank you.');
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/donor-thanks', async (route) => {
    const req = route.request();
    if (req.method() === 'POST' && req.postDataJSON()?.action === 'save') {
      await gate;
      return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({error:'Save failed'}) });
    }
    return route.continue();
  });
  await page.locator('#thanksSwitch').click();
  await expect(page.locator('#thanksSwitch')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#thanksSwitch')).toBeDisabled();
  await expect(page.locator('#thanksStartLabel')).toHaveText('Starting…');
  release();
  await expect(page.locator('#thanksStatus')).toHaveText('Save failed');
  await expect(page.locator('#thanksSwitch')).toHaveAttribute('aria-checked', 'false');
  await expect(page.locator('#thanksSwitch')).toBeEnabled();
});

test('donated tab toggle shows starting and rolls back on start failure', async ({ page, request }) => {
  const added = await (await request.post('/donors', {
    headers, data: { action: 'add', name: 'Tab test', phone: '15551239992' },
  })).json();
  await request.post('/donors', { headers, data: { action: 'update', id: added.donor.id, donated: true } });
  await request.post('/left', { headers, data: { left: 0 } });
  const initial = await (await request.get('/donor-thanks', { headers })).json();
  await request.post('/donor-thanks', {headers, data: {
    action: 'save', case_id: initial.case_id, revision: initial.revision, media: [], message: 'Thank you.'
  }});
  await page.addInitScript(k => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await expect(page.locator('#thanksTabSwitch')).toBeEnabled();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/donor-thanks', async route => {
    if (route.request().method() === 'POST' && route.request().postDataJSON()?.action === 'start') {
      await gate;
      return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({error:'Start failed'}) });
    }
    return route.continue();
  });
  await page.locator('#thanksTabSwitch').click();
  await expect(page.locator('#thanksTabSwitch')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#thanksTabLabel')).toHaveText('Starting…');
  release();
  await expect(page.locator('#thanksRowStatus')).toHaveText('Start failed');
  await expect(page.locator('#thanksTabSwitch')).toHaveAttribute('aria-checked', 'false');
});

test('test button responds immediately and reports a failed test', async ({ page }) => {
  await page.setViewportSize({width:320,height:740});
  await page.addInitScript(k => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await page.getByRole('button', { name: 'Thank donors', exact: true }).click();
  await page.locator('#thanksMessage').fill('Thank you.');
  let release, calls = 0;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/donor-thanks', async route => {
    if (route.request().method() === 'POST' && route.request().postDataJSON()?.action === 'test') {
      calls++;
      await gate;
      return route.fulfill({status:400, contentType:'application/json', body:JSON.stringify({error:'Test failed'})});
    }
    return route.continue();
  });
  await page.locator('#thanksTest').click();
  await expect(page.locator('#thanksTest')).toHaveText('Testing…');
  await expect(page.locator('#thanksTest')).toBeDisabled();
  for (const button of await page.locator('#donorThanksDialog footer button').all()) {
    const rect = await button.boundingBox();
    expect(rect.x).toBeGreaterThanOrEqual(0);
    expect(rect.x + rect.width).toBeLessThanOrEqual(320);
  }
  await expect(page.locator('#thanksStatus')).toHaveText('Sending test…');
  release();
  await expect(page.locator('#thanksStatus')).toHaveText('Test failed');
  await expect(page.locator('#thanksTest')).toHaveText('Test');
  expect(calls).toBe(1);
});

test('donated tab test responds immediately while the request is pending', async ({page, request}) => {
  const data = await (await request.get('/donor-thanks', {headers})).json();
  await request.post('/donor-thanks', {headers, data:{action:'save', case_id:data.case_id, revision:data.revision, media:[], message:'Thank you.'}});
  await page.addInitScript(k => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await expect(page.locator('#thanksTabTest')).toBeEnabled();
  let release;
  const gate = new Promise(resolve => {release = resolve;});
  await page.route('**/donor-thanks', async route => {
    if (route.request().method() === 'POST' && route.request().postDataJSON()?.action === 'test') {
      await gate;
      return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Test failed'})});
    }
    return route.continue();
  });
  await page.locator('#thanksTabTest').click();
  await expect(page.locator('#thanksTabTest')).toHaveText('Testing…');
  await expect(page.locator('#thanksTabTest')).toBeDisabled();
  release();
  await expect(page.locator('#thanksRowStatus')).toHaveText('Test failed');
  await expect(page.locator('#thanksTabTest')).toHaveText('Test');
});

test('caption and message stay visible above the footer on a short screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 420 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await page.getByRole('button', { name: 'Thank donors', exact: true }).click();
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII=',
    'base64',
  );
  await page
    .locator('#thanksFile')
    .setInputFiles({ name: 'proof.png', mimeType: 'image/png', buffer: png });
  await expect(page.locator('.thanks-capd textarea')).toBeVisible();
  await page
    .locator('#thanksMessage')
    .fill('A longer message that keeps an unsaved status visible.');
  await page.locator('#thanksMessage').blur();
  const withinEditor = async (selector) =>
    page.locator(selector).evaluate((el) => {
      const box = el.getBoundingClientRect();
      const area = el.closest('.thanks-body').getBoundingClientRect();
      const footer = document.querySelector('#donorThanksDialog footer').getBoundingClientRect();
      return box.top >= area.top - 1 && box.bottom <= area.bottom + 1 && box.bottom <= footer.top;
    });
  await page.locator('#thanksMessage').fill('');
  await page.locator('#thanksMessage').fill('An extra message for the donor.');
  await expect.poll(() => withinEditor('#thanksMessage')).toBe(true);
  for (const selector of ['#thanksMessage', '.thanks-capd textarea']) {
    await page.locator(selector).focus();
    await expect.poll(() => withinEditor(selector)).toBe(true);
  }
  await expect(page.locator('#thanksClose')).toBeInViewport();
});

for (const view of ['dialog', 'tab']) {
  test(view + ' stop responds immediately and restores state after a failed stop', async ({ page, request }) => {
    const saved = await (await request.get('/donor-thanks', { headers })).json();
    let fakeOn = true, fail = true, release;
    let gate = new Promise(resolve => { release = resolve; });
    await page.route('**/donor-thanks', async route => {
      if (route.request().method() === 'GET')
        return route.fulfill({ json: { ...saved, on: fakeOn } });
      if (route.request().postDataJSON()?.action === 'stop') {
        await gate;
        if (fail)
          return route.fulfill({ status: 400, json: { error: 'Stop was not confirmed' } });
        fakeOn = false;
        return route.fulfill({ json: { ...saved, on: false } });
      }
      return route.continue();
    });
    await page.addInitScript(k => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/donors/donated');
    if (view === 'dialog')
      await page.getByRole('button', { name: 'Thank donors', exact: true }).click();
    const toggle = page.locator(view === 'dialog' ? '#thanksSwitch' : '#thanksTabSwitch');
    const label = page.locator(view === 'dialog' ? '#thanksStartLabel' : '#thanksTabLabel');
    const status = page.locator(view === 'dialog' ? '#thanksStatus' : '#thanksRowStatus');
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await expect(toggle).toBeDisabled();
    await expect(label).toHaveText('Stopping…');
    release();
    await expect(status).toHaveText('Stop was not confirmed');
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await expect(toggle).toBeEnabled();
    fail = false;
    gate = new Promise(resolve => { release = resolve; });
    await toggle.click();
    await expect(label).toHaveText('Stopping…');
    release();
    await expect(status).toContainText('Paused');
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
  });
}

test('Test avoids an unchanged timing write and persists a changed pace', async ({ page }) => {
  const actions = [];
  await page.route('**/donor-thanks', async route => {
    if (route.request().method() === 'POST') {
      const action = route.request().postDataJSON().action;
      actions.push(action);
      if (action === 'test')
        return route.fulfill({ json: { reply: 'Test confirmed' } });
    }
    return route.continue();
  });
  await page.addInitScript(k => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  await page.getByRole('button', { name: 'Thank donors', exact: true }).click();
  await page.locator('#thanksMessage').fill('Thank you, {name}.');
  await page.locator('#thanksTest').click();
  await expect(page.locator('#thanksStatus')).toHaveText('Test confirmed');
  expect(actions).toEqual(['save', 'test']);
  actions.length = 0;
  const next = await page.locator('#thanksGapSel').inputValue() === '120' ? '180' : '120';
  await page.locator('#thanksGapSel').selectOption(next);
  await page.locator('#thanksTest').click();
  await expect(page.locator('#thanksStatus')).toHaveText('Test confirmed');
  expect(actions).toEqual(['save', 'settings', 'test']);
});
