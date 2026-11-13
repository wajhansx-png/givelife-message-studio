/* One page to run the whole case (/new). Fake WhatsApp only: nothing here can reach a real chat. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 401;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}`, reducedMotion: 'reduce' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
test.describe.configure({ mode: 'serial' });

async function open(page, width, height, hash = '#/case') {
  await page.setViewportSize({ width, height });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new' + hash);
  await expect(page.locator('#casePage')).toBeVisible();
  await expect(page.locator('.cr-row')).toHaveCount(5);
}
const inView = async (page, locator) => {
  const box = await locator.boundingBox();
  const vp = page.viewportSize();
  expect(box, 'not on screen').not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(-1);
  expect(box.y).toBeGreaterThanOrEqual(-1);
  expect(box.x + box.width).toBeLessThanOrEqual(vp.width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(vp.height + 1);
};

for (const [width, height] of [
  [320, 568],
  [360, 740],
  [375, 667],
  [390, 844],
  [844, 390],
  [1440, 900],
]) {
  test(`the case page shows the five rows and the three main buttons at ${width}x${height}`, async ({
    page,
  }) => {
    await open(page, width, height);
    await expect(page.locator('.cr-row .cr-name b')).toHaveText([
      'GiveLife Group',
      'Top Donors',
      'GIKI',
      'Volunteers',
      'Important Donors',
    ]);
    await expect(page.locator('#crNeedsSec')).toBeHidden(); // nothing needs you: no empty box
    /* every phone (even 320x568) and desktop: the whole page is on screen, nothing to scroll */
    expect(
      await page.locator('.cr-main').evaluate((e) => e.scrollHeight <= e.clientHeight + 1),
      'the page should not need scrolling',
    ).toBe(true);
    for (const id of ['#crSettings', '#crTools', '#crBack']) await inView(page, page.locator(id));
    await expect(page.locator('#casePage .cr-bar')).toBeHidden(); // no Start button: a row's switch starts it
    await expect(page.locator('.cr-row .cr-sw')).toHaveCount(5);
    for (const sw of await page.locator('.cr-row .cr-sw').all())
      await expect(sw).toHaveAttribute('aria-checked', 'false'); // nothing is on before you switch it on
    await expect(page.locator('#crPause')).toBeHidden(); // Pause all and Finish appear only while it runs
    await expect(page.locator('#crFinish')).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await inView(page, page.locator('#crPrepare'));
  });
}

test('the Case tab is the first tab, and Tools opens the existing tools and comes back', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new');
  const tabs = page.locator('#ui2Tabs .ui2-tab:visible');
  await expect(tabs.first()).toHaveText('Case');
  await tabs.first().click();
  await expect(page.locator('#casePage')).toBeVisible();
  await page.locator('#crTools').click();
  await expect(page.locator('#crMenu .cr-tool-h')).toHaveText(['Daily', 'Messages', 'Setup']);
  await expect(page.locator('#crMenu .cr-tool')).toContainText([
    'Donors',
    'Message and send',
    'Chat',
    'Notes',
    'Reports',
    'Message versions and tests',
    'Case Writer',
    'Settings',
  ]);
  await page.locator('#crMenu').getByRole('button', { name: 'Donors', exact: true }).click();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await page.locator('#donorMainBottom').click();
  await expect(page.locator('#donorsPage')).toBeHidden();
  await expect(page.locator('#casePage')).toBeVisible(); // back exactly where you were
});

test('switching a row on asks once; Cancel starts nothing and the switch snaps back', async ({
  page,
}) => {
  await open(page, 390, 844);
  const sw = page.locator('.cr-row[data-key="group"] .cr-sw');
  await sw.click();
  const sheet = page.locator('#caseSheet');
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('#csTitle')).toHaveText('Start GiveLife Group?');
  await expect(sheet.locator('.cr-sum-row').first()).toContainText('45 min');
  await expect(sw).toHaveAttribute('aria-checked', 'true'); // stays on while it asks
  await expect(sheet.locator('#csFoot button')).toHaveText(['Cancel', 'Start sending']); // Start on the right
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  await expect(sheet).toBeHidden();
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  const view = await api(port, '/case-run');
  expect(view.status).toBe('idle');
  const jobs = await api(port, '/donor-delivery');
  expect(['Starting', 'Sending', 'Waiting']).not.toContain(jobs.state);
  expect((await api(port, '/auto-controls')).controls.group.on).toBe(false);
});

test('saving settings never starts sending, and Important stays off until people are chosen', async ({
  page,
}) => {
  await open(page, 390, 844);
  await page.locator('.cr-row[data-key="top"] .cr-name b').click();
  const sheet = page.locator('#caseSheet');
  await sheet.getByRole('button', { name: 'Settings', exact: true }).click();
  const gap = sheet.locator('input[type=number]').first();
  await gap.fill('4');
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet).toBeHidden();
  await page.locator('.cr-row[data-key="top"] .cr-name b').click();
  await sheet.getByRole('button', { name: 'Settings', exact: true }).click();
  await expect(sheet.locator('input[type=number]').first()).toHaveValue('4');
  await sheet.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  expect((await api(port, '/case-run')).status).toBe('idle');
  expect((await api(port, '/auto-controls')).controls.group.on).toBe(false);
  const imp = page.locator('.cr-row[data-key="important"] .cr-sw');
  await imp.click(); // Important cannot be switched on before people are chosen
  await expect(page.locator('#crSay')).toContainText('Select the Important donors first');
  await expect(sheet).toBeVisible(); // it opens the people list to choose from
  await expect(sheet.getByRole('button', { name: 'Back to settings' })).toBeVisible();
  await sheet.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  await expect(imp).toHaveAttribute('aria-checked', 'false');
  expect((await api(port, '/case-run')).status).toBe('idle');
});

test('each row has a small settings icon that opens its timing in one tap, and it hides while sending', async ({
  page,
}) => {
  await open(page, 390, 844);
  await expect(page.locator('.cr-row .cr-gear')).toHaveCount(5);
  const box = await page.locator('.cr-row[data-key="top"] .cr-gear').boundingBox();
  expect(box.width).toBeGreaterThanOrEqual(40);
  expect(box.height).toBeGreaterThanOrEqual(40);
  await page.getByRole('button', { name: 'Edit timing: Top Donors' }).click();
  const sheet = page.locator('#caseSheet');
  await expect(sheet.locator('.cr-seg-b[data-on="1"]')).toHaveText('Settings');
  const gap = sheet.locator('input[type=number]').first();
  await expect(gap).toBeVisible();
  const v0 = Number(await gap.inputValue());
  await sheet.getByRole('button', { name: /^More: Minutes between DMs/ }).click();
  await expect(gap).toHaveValue(String(Math.min(10, v0 + 1)));
  for (let i = 0; i < 12; i++)
    await sheet.getByRole('button', { name: /^Less: Minutes between DMs/ }).click();
  await expect(gap).toHaveValue('1'); // stops at the lowest allowed value
  await sheet.getByRole('button', { name: 'People', exact: false }).first().click();
  await expect(sheet.getByRole('button', { name: 'Back to settings' })).toBeVisible();
  await sheet.getByRole('button', { name: 'Back to settings' }).click();
  await sheet.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  expect((await api(port, '/case-run')).status).toBe('idle'); // opening timing never starts anything
  // 320px phone: the row name stays on one line
  await page.setViewportSize({ width: 320, height: 568 });
  const names = page.locator('.cr-row .cr-name');
  for (let i = 0; i < 5; i++)
    expect((await names.nth(i).boundingBox()).height).toBeLessThan(50);
});

test('start one row, switch rows on and off on their own, pause all, resume and finish', async ({
  page,
}) => {
  await open(page, 390, 844);
  const sheet = page.locator('#caseSheet');
  const sw = (key) => page.locator(`.cr-row[data-key="${key}"] .cr-sw`);
  const row = async (key) => (await api(port, '/case-run')).rows.find((r) => r.key === key);
  await sw('group').click();
  await page.getByRole('button', { name: 'Start sending' }).click();
  await expect(page.locator('#crPause')).toBeVisible();
  await expect(page.locator('#crResume')).toBeHidden();
  await expect(sw('group')).toHaveAttribute('aria-checked', 'true');
  expect((await api(port, '/auto-controls')).controls.group.on).toBe(true);

  /* each switch is its own control: the group row goes off and on, the case keeps running */
  await sw('group').click();
  await expect(sw('group')).toHaveAttribute('aria-checked', 'false');
  await expect.poll(async () => (await api(port, '/auto-controls')).controls.group.on).toBe(false);
  expect((await api(port, '/case-run')).status).toBe('running');
  await sw('group').click();
  await expect(sw('group')).toHaveAttribute('aria-checked', 'true');
  await expect.poll(async () => (await api(port, '/auto-controls')).controls.group.on).toBe(true);

  /* a row that was never approved asks first, says why when nobody is waiting, and snaps back */
  await sw('top').click();
  await expect(sheet).toContainText('No one is waiting in Top Donors.');
  await expect(sheet.getByRole('button', { name: 'Start sending' })).toHaveCount(0);
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  await expect(sw('top')).toHaveAttribute('aria-checked', 'false');
  expect((await row('top')).state).toBe('off');

  await page.goto('/new'); // reopening the app while a case runs
  await expect(page.locator('#casePage')).toBeVisible();
  expect(await page.evaluate(() => location.hash)).toBe('#/case');

  await page.locator('#crPause').click();
  await expect(page.locator('#crResume')).toHaveText('Resume all');
  await expect.poll(async () => (await api(port, '/case-run')).status).toBe('paused');
  await expect.poll(async () => (await api(port, '/auto-controls')).controls.group.on).toBe(false);
  await sw('group').click(); // switching one row on while paused runs only that row
  await expect(page.locator('#crPause')).toBeVisible();
  await expect.poll(async () => (await api(port, '/case-run')).status).toBe('running');
  await page.locator('#crPause').click();
  await page.locator('#crResume').click();
  await expect(page.locator('#crPause')).toBeVisible();
  expect((await api(port, '/case-run')).status).toBe('running');

  await page.locator('#crFinish').click();
  await expect(sheet).toContainText('Confirmed so far');
  expect((await api(port, '/case-run')).status).toBe('running'); // asking changes nothing
  await sheet.getByRole('button', { name: 'Finish case' }).click();
  await expect(page.locator('#crDone')).toBeVisible();
  await expect(page.locator('#crResume')).toBeHidden();
  await expect(page.locator('#crFinish')).toBeHidden();
  expect((await api(port, '/case-run')).status).toBe('finished');
  expect((await api(port, '/auto-controls')).controls.group.on).toBe(false);
});

test('Needs you: a payment claim is confirmed once with the amount the owner types', async ({
  page,
}) => {
  const claim = {
    id: 'pay:1',
    type: 'payment',
    title: 'Ali Raza says they donated',
    name: 'Ali Raza',
    text: 'Done bhai, sent 2000',
    actions: ['check_payment', 'not_paid'],
  };
  const seen = [];
  let view = null;
  await page.route('**/case-run', async (route) => {
    if (route.request().method() === 'POST') {
      seen.push(route.request().postDataJSON());
      view = { ...view, needs: [] };
      return route.fulfill({ json: view });
    }
    const real = await (await route.fetch()).json();
    view = view || { ...real, needs: [claim] };
    return route.fulfill({ json: view });
  });
  await open(page, 390, 844);
  await expect(page.locator('.cr-need')).toHaveCount(1);
  await expect(page.locator('#crNeedsN')).toHaveText('1');
  await page.getByRole('button', { name: 'Check payment' }).click();
  const sheet = page.locator('#caseSheet');
  await expect(sheet).toContainText('This is only a claim');
  await sheet.locator('input[type=number]').fill('2000');
  await sheet.getByRole('button', { name: 'Confirm payment' }).click();
  await expect(sheet).toBeHidden();
  expect(seen).toEqual([{ action: 'need', id: 'pay:1', op: 'check_payment', amount: 2000 }]);
  await expect(page.locator('.cr-need')).toHaveCount(0);
  await expect(page.locator('#crNeedsSec')).toBeHidden();
});

test('one page controls the amount, the case and WhatsApp, and Tools reaches every other tool', async ({
  page,
}) => {
  await open(page, 390, 844);
  const sheet = page.locator('#caseSheet');
  const settings = () => page.locator('#crSettings').click();
  const row = (name) => sheet.locator('.cr-li', { hasText: name });
  await settings();
  await row('Amount left').getByRole('button', { name: 'Change' }).click();
  await sheet.locator('input[type=number]').fill('19000');
  await sheet.getByRole('button', { name: 'Save' }).click();
  expect((await api(port, '/case-run')).case.left).toBe(19000);
  await settings();
  await expect(row('Amount left')).toContainText('Rs. 19,000');
  await row('Case').getByRole('button', { name: 'Change' }).click();
  await expect(sheet.locator('select option')).not.toHaveCount(0);
  await expect(sheet.getByRole('button', { name: 'Start new case' })).toBeVisible();
  await sheet.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  await page.locator('#crTools').click();
  await expect(page.locator('#crMenu .cr-tool')).toContainText([
    'Donors',
    'Thank donors',
    'Reports',
    'Volunteers',
    'Auto replies',
    'WhatsApp connection',
    'Resume group messages',
    'Settings',
  ]);
  await page.locator('#caseSheet #csFoot').getByRole('button', { name: 'Close' }).click();
  await page.locator('#crWa').click();
  await expect(page.locator('#whatsappDialog')).toBeVisible();
  await page.evaluate(() => document.getElementById('whatsappDialog').close());
  // every Settings line is there, nothing to look for elsewhere
  await settings();
  await expect(sheet.locator('.cr-li b')).toHaveText([
    'Case',
    'Amount left',
    'Poster',
    'Sending times',
    'Auto replies',
    'WhatsApp',
    'App settings',
  ]);
});

test('Prepare case: edit, Save Base, Next, Test 3 versions and Looks right, all in one panel', async ({
  page,
}) => {
  await open(page, 390, 844);
  await page.locator('#crPrepare').click();
  const sheet = page.locator('#caseSheet');
  await expect(sheet.locator('.cr-prep')).toHaveCount(5);
  await expect(sheet.locator('.cr-prep summary b')).toHaveText([
    'Case',
    'Poster',
    'GiveLife Group message',
    'Donor message',
    'Volunteers sharing request',
  ]);
  const group = sheet.locator('.cr-prep[data-k="group"]');
  if (!(await group.evaluate((e) => e.open))) await group.locator('summary').click();
  const text = group.locator('textarea');
  await expect(text).not.toHaveValue('');
  await group.getByRole('button', { name: 'Next' }).click();
  await expect(group.locator('[role=status]')).toContainText(/Version \d+ of \d+|No versions yet/);
  await group.getByRole('button', { name: 'Test 3 versions' }).click();
  await expect(group.locator('[role=status]')).toContainText('Sent 3 versions', { timeout: 20000 });
  await group.getByRole('button', { name: 'Looks right' }).click();
  await expect(group.locator('summary .cr-pill')).toHaveText('Ready');
  expect((await api(port, '/case-run')).checks.group).toBe('ok');

  const vol = sheet.locator('.cr-prep[data-k="volunteers"]');
  await vol.locator('summary').click();
  await expect(vol.locator('textarea')).toHaveAttribute('placeholder', '');
  await vol.locator('textarea').fill('Please share this case in your groups.');
  await vol.getByRole('button', { name: 'Save Base' }).click();
  await expect(vol.locator('[role=status]')).toHaveText('Saved.');
  expect((await api(port, '/volunteers')).message).toBe('Please share this case in your groups.');
  const before = (await api(port, '/case-run')).status;
  expect(['idle', 'finished']).toContain(before); // preparing never starts sending
  expect(['Starting', 'Sending', 'Waiting']).not.toContain(
    (await api(port, '/donor-delivery')).state,
  );
});

test('GiveLife Group shows ON when the main page Auto is ON, and its switch turns that Auto OFF', async ({
  page,
}) => {
  await api(port, '/autopilot', { on: false });
  await api(port, '/cases', { action: 'new', name: 'Live mirror case', left: 30000 }); // an idle case (earlier tests finished theirs)
  await open(page, 390, 740);
  const row = page.locator('.cr-row[data-key="group"]');
  const sw = row.locator('.cr-sw');
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await expect(row.locator('.cr-live-line')).toHaveCount(0);
  // The owner switches Auto ON on the main page: the open Case page follows (it refreshes every few seconds).
  await api(port, '/autopilot', { on: true });
  await expect(sw).toHaveAttribute('aria-checked', 'true', { timeout: 8000 });
  await expect(row.locator('.cr-live-line')).toContainText('main page');
  // Other rows are not touched.
  await expect(page.locator('.cr-row[data-key="top"] .cr-sw')).toHaveAttribute('aria-checked', 'false');
  // Switching it OFF here switches the real Auto OFF (it overwrites).
  await sw.click();
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await expect.poll(async () => (await api(port, '/autopilot')).on).toBe(false);
  await expect(row.locator('.cr-live-line')).toHaveCount(0);
});
