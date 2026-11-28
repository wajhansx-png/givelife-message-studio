const { test, expect } = require('@playwright/test');
const { openSettings, openDonorMessages, showPreview, showDm } = require('./helpers.cjs');
const auth = { Authorization: 'Bearer manual-fix-preview-key' };
const LONG = Array.from(
  { length: 7 },
  (_, i) =>
    `Part ${i + 1}: this is what is actually in place right now. Schedules: #f2c3c664 pending at 10:00 AM PKT to resume GiveLife main. Groups: GiveLife Foundation every 45 minutes. Balance: Rs. 15,000 left.`,
).join('\n\n');
async function open(page, request, width, height, reply) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => {
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    localStorage.setItem('givelife-theme', 'dark');
    localStorage.removeItem('givelife-last-route');
  });
  await request.post('/__test/seed', { headers: auth, data: { reply: reply || 'Ready.' } });
  await page.goto('/new');
  await expect(page.locator('#leftChip')).toContainText('25,000');
}
test('bulk paste shows when every number will be sent before anything starts', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 844);
  await showDm(page); // the DM composer has no tab button any more
  await page.locator('#sendMoreDonors').click();
  await page.locator('#pastePeople').fill('Ali 03001234567\n03011234567\n1. Sara - 0302 1234567');
  await expect(page.locator('#pastePlan li')).toHaveCount(4);
  await expect(page.locator('#pasteNext')).toHaveText('DM all 3');
  await expect(page.locator('#pastePlan li').nth(1)).toContainText('Donor 2');
  await page.locator('#pasteNext').click();
  await expect(page.locator('#pastePeople')).toBeHidden();
  await expect(page.locator('#pastePlan li').first()).toContainText('Ali');
  await expect(page.locator('#pastePlan li').first()).toContainText('Now');
  await expect(page.locator('#pastePlan li').nth(1)).toContainText('Donor 2');
  await expect(page.locator('#pastePlan li').nth(2)).toContainText('Sara');
  await expect(page.locator('#pastePlan .plan-total')).toContainText('All 3 done by about');
  const textOnScreen = await page.locator('#pastePlan').innerText();
  expect(textOnScreen).not.toMatch(/0300|1234567/);
  const gap2 = await page.locator('#pastePlan li').nth(1).locator('.plan-when').innerText();
  await page.locator('#pasteGap').selectOption('8');
  await expect
    .poll(() => page.locator('#pastePlan li').nth(1).locator('.plan-when').innerText())
    .not.toBe(gap2);
  await expect(page.locator('#pasteStart')).toBeEnabled();
  await page.locator('#pasteBack').click();
  await expect(page.locator('#pastePeople')).toBeVisible();
});
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

test('poster upload shows real progress, stays open until confirmed, and then closes', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 844);
  let finishUpload;
  let authorized = false;
  await page.route('**/upload-image', async (route) => {
    authorized = route.request().headers()['authorization'] === 'Bearer manual-fix-preview-key';
    await new Promise((resolve) => {
      finishUpload = resolve;
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'poster' }),
    });
  });
  await page.evaluate(() => window.DonorHub.openPoster());
  await page
    .locator('#posterFile')
    .setInputFiles({ name: 'poster.png', mimeType: 'image/png', buffer: PNG });
  await expect(page.locator('#posterSave')).toBeEnabled();
  await page.locator('#posterSave').click();
  await expect(page.locator('#posterProgress')).toBeVisible();
  await expect(page.locator('#posterClose')).toBeDisabled();
  await expect(page.locator('#posterDialog')).toBeVisible();
  await expect.poll(() => !!finishUpload).toBe(true);
  expect(authorized).toBe(true);
  await expect(page.locator('#posterProgressText')).toContainText(/Uploading|saving securely/); // real progress, never a fake timer
  finishUpload();
  await expect(page.locator('#posterDialog')).not.toBeVisible({ timeout: 8000 });
  await expect(page.locator('#donorNotice')).toContainText('Poster saved for groups and DMs.');
});

test('a video chosen as the Poster is refused with a clear message', async ({ page, request }) => {
  await open(page, request, 390, 844);
  await page.evaluate(() => window.DonorHub.openPoster());
  await page.locator('#posterFile').setInputFiles({
    name: 'sample.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.concat([Buffer.from([0, 0, 0, 24]), Buffer.from('ftypmp42'), Buffer.alloc(512)]),
  });
  await expect(page.locator('#posterNote')).toContainText('Poster must be a picture');
  await expect(page.locator('#posterSave')).toBeDisabled();
});

test('poster saving errors remain visible and retry can complete', async ({ page, request }) => {
  await open(page, request, 390, 844);
  let attempts = 0;
  await page.route('**/upload-image', async (route) => {
    attempts++;
    await route.fulfill({
      status: attempts === 1 ? 503 : 200,
      contentType: 'application/json',
      body: JSON.stringify(
        attempts === 1 ? { error: 'Storage temporarily unavailable' } : { id: 'poster' },
      ),
    });
  });
  await page.evaluate(() => window.DonorHub.openPoster());
  await page
    .locator('#posterFile')
    .setInputFiles({ name: 'poster.png', mimeType: 'image/png', buffer: PNG });
  await page.locator('#posterSave').click();
  await expect(page.locator('#posterNote')).toContainText('Storage temporarily unavailable');
  await expect(page.locator('#posterDialog')).toBeVisible();
  await expect(page.locator('#posterSave')).toBeEnabled();
  await page.locator('#posterSave').click();
  await expect(page.locator('#posterDialog')).not.toBeVisible({ timeout: 8000 });
  expect(attempts).toBe(2);
});

test('on a very wide screen the groups box stays close to the centre of the screen', async ({
  page,
  request,
}) => {
  await open(page, request, 1920, 1000);
  const rail = await page.locator('.action-rail').boundingBox();
  expect(rail.x).toBeLessThan(960 + 300);
  expect(rail.x + rail.width).toBeLessThan(960 + 620);
});

// The Team screen was retired from the interface (its saved data is kept), so this check no longer applies.
test.skip('team over WhatsApp: tasks in the screen, a natural first message, his reply shows up to check, verified', async ({
  page,
  request,
}) => {
  const auth = { Authorization: 'Bearer manual-fix-preview-key' };
  const post = (data) => request.post('/__test/seed', { headers: auth, data });
  const events = async () =>
    (await (await request.get('/__test/events', { headers: auth })).json()).events.filter(
      (e) => e.path === '/send/message',
    );
  await open(page, request, 1440, 800);
  await page.locator('#openTeam').click();
  await expect(page.locator('.team-setup')).toBeVisible();
  await page.locator('.team-setup input[name=team_name]').fill('Bilal Ahmed');
  await page.locator('.team-setup input[name=team_phone]').fill('03001234567');
  await page.locator('.team-setup .primary').click();
  await expect(page.locator('.team-big')).toContainText('No tasks yet');
  await page.getByRole('button', { name: '+ Add tasks' }).click();
  await page
    .locator('#teamText')
    .fill('1) Post in the 3 groups\n2) Update the sheet\nDeadline in 4 hours');
  await page.getByRole('button', { name: 'Plan the tasks' }).click();
  await expect(
    page.locator('.team-page').getByText('Nothing is sent until you press Start'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Start tasks' }).click();
  await expect(page.locator('.team-big')).toContainText('0 of 2 done');
  const before = (await events()).length;
  await page.waitForTimeout(1500);
  await post({ team_tick: true });
  await post({ team_tick: true });
  const sent = (await events()).slice(before);
  expect(sent.length, 'the first message goes once, even after two ticks').toBe(1);
  expect(sent[0].fields.phone).toBe('923001234567');
  expect(sent[0].fields.message).toContain('Post in the 3 groups');
  expect(sent[0].fields.message).not.toMatch(/Task #|Reply "|bot/i);
  expect(sent[0].fields.message).toMatch(/^Assalam o alaikum Bilal,/);
  await post({ incoming: 'posted in the groups, done https://example.com/p', team_tick: true });
  await expect(page.locator('.team-review')).toContainText('Post in the 3 groups', {
    timeout: 12000,
  });
  await expect(page.locator('.team-review')).toContainText('Proof');
  await page
    .locator('.team-review')
    .getByRole('button', { name: /Verified/ })
    .click();
  await expect(page.locator('.team-big')).toContainText('1 of 2 done');
  const cmd = async (text) =>
    (await request.post('/command', { headers: auth, data: { text } })).json();
  expect((await cmd('team status')).reply).toContain('1 of 2 done');
  expect((await cmd('hello how are you')).reply || '').not.toContain('of 2 done');
});

// The Team screen was retired from the interface (its saved data is kept), so this check no longer applies.
test.skip('team screen is one screen with no scrolling at every size, even with a lot of data', async ({
  page,
  request,
}) => {
  const auth = { Authorization: 'Bearer manual-fix-preview-key' };
  const sizes = [
    [1920, 900],
    [1440, 800],
    [1280, 720],
    [1024, 600],
    [768, 1024],
    [412, 915],
    [390, 844],
    [360, 640],
    [320, 568],
  ];
  for (const demo of [
    [[0, 'Waiting']],
    [
      [1, 'Reported'],
      [2, 'Asked'],
      [1, 'Done'],
    ],
    [
      [8, 'Reported'],
      [14, 'Asked'],
      [3, 'Late'],
      [5, 'Done'],
    ],
  ]) {
    for (const [w, h] of sizes) {
      await open(page, request, w, h);
      await request.post('/__test/seed', { headers: auth, data: { team_demo: demo } });
      await page.locator('#openTeam').click();
      await expect(page.locator('.team-page')).toBeVisible();
      await page.waitForTimeout(350);
      const m = await page.evaluate(() => {
        const b = document.querySelector('.team-body'),
          s = document.querySelector('.team-shell'),
          f = document.querySelector('.team-foot');
        const r = f.getBoundingClientRect();
        const bad = [...document.querySelectorAll('.team-page button')]
          .filter(
            (x) =>
              x.offsetParent &&
              (x.getBoundingClientRect().height < 43 ||
                x.getBoundingClientRect().right > innerWidth + 1 ||
                x.getBoundingClientRect().left < -1),
          )
          .map((x) => x.textContent.trim() + ':' + Math.round(x.getBoundingClientRect().height));
        return {
          fit: b.scrollHeight <= b.clientHeight + 1,
          x:
            document.documentElement.scrollWidth > innerWidth + 1 ||
            s.scrollWidth > s.clientWidth + 1,
          footIn: r.bottom <= innerHeight + 1 && r.top >= 0,
          bad,
          add: !!document.querySelector('.team-add') || !!document.querySelector('#teamText'),
        };
      });
      expect(m.fit, `${w}x${h} ${JSON.stringify(demo)}: nothing to scroll`).toBe(true);
      expect(m.x, `${w}x${h}: no sideways scroll`).toBe(false);
      expect(m.footIn, `${w}x${h}: Back is on screen`).toBe(true);
      expect(m.bad, `${w}x${h}: every button is 44px tall and inside`).toEqual([]);
      expect(m.add, `${w}x${h}: the add button stays`).toBe(true);
      await page.locator('.team-back').click();
    }
  }
  await open(page, request, 390, 700);
  await request.post('/__test/seed', { headers: auth, data: { team_demo: [[2, 'Asked']] } });
  await page.locator('#openTeam').click();
  await page.getByRole('button', { name: '+ Add tasks' }).click();
  await page
    .locator('#teamText')
    .fill(
      Array.from({ length: 20 }, (_, i) => 'Task number ' + (i + 1) + ' with some words').join(
        '\n',
      ) + '\ndeadline tomorrow 9pm',
    );
  await page.getByRole('button', { name: 'Plan the tasks' }).click();
  await expect(page.getByRole('button', { name: 'Start tasks' })).toBeVisible();
  const fit = await page.evaluate(() => {
    const b = document.querySelector('.team-body');
    return b.scrollHeight <= b.clientHeight + 1;
  });
  expect(fit, 'a 20-task plan preview also fits one screen').toBe(true);
});

// The Team screen was retired from the interface (its saved data is kept), so this check no longer applies.
test.skip('team screen keeps the focused field (and the phone keyboard) when the window resizes or refreshes', async ({
  page,
  request,
}) => {
  await open(page, request, 390, 700);
  await request.post('/__test/seed', { headers: auth, data: { team_demo: [[1, 'Asked']] } });
  await page.locator('#openTeam').click();
  await page.getByRole('button', { name: '+ Add tasks' }).click();
  const box = page.locator('#teamText');
  await box.click();
  await box.fill('Post in groups');
  await page.setViewportSize({ width: 390, height: 380 });
  await page.waitForTimeout(400); // what the keyboard does
  await page.evaluate(() => window.dispatchEvent(new Event('resize')));
  await page.waitForTimeout(400);
  expect(await page.evaluate(() => document.activeElement?.id)).toBe('teamText');
  expect(await box.inputValue()).toBe('Post in groups');
  await page.waitForTimeout(9500); // past one automatic refresh
  expect(await page.evaluate(() => document.activeElement?.id)).toBe('teamText');
  expect(await box.inputValue()).toBe('Post in groups');
});

// The Team screen was retired from the interface (its saved data is kept), so this check no longer applies.
test.skip('team: a planning error is visible inside the Team screen, and quiet hours are an optional switch in Settings', async ({
  page,
  request,
}) => {
  await page.route('**/team', (route) =>
    route.request().method() === 'POST' && route.request().postDataJSON()?.action === 'plan'
      ? route.fulfill({ status: 400, json: { error: 'The deadline must be in the future.' } })
      : route.continue(),
  );
  await open(page, request, 390, 700);
  await request.post('/__test/seed', { headers: auth, data: { team_demo: [[1, 'Asked']] } });
  await page.locator('#openTeam').click();
  await page.getByRole('button', { name: '+ Add tasks' }).click();
  await page.locator('#teamText').fill('Do the thing');
  await page.getByRole('button', { name: 'Plan the tasks' }).click();
  const err = page.locator('.team-page .team-error');
  await expect(err).toBeVisible();
  await expect(err).toContainText('deadline');
  const box = await err.boundingBox();
  expect(box.y).toBeGreaterThan(0);
  expect(box.y + box.height).toBeLessThan(700);
  await page.locator('.team-back').click();
  await openSettings(page);
  const sw = page.locator('#teamQuietOn');
  await expect(sw).not.toBeChecked();
  await sw.check();
  await expect
    .poll(async () => (await (await request.get('/team', { headers: auth })).json()).quiet)
    .toEqual([23, 7]);
  await sw.uncheck();
  await expect
    .poll(async () => (await (await request.get('/team', { headers: auth })).json()).quiet)
    .toBeNull();
});
