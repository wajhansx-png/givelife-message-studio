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
    await expect(page.locator('.cr-row b')).toHaveText([
      'GiveLife Group',
      'Top Donors',
      'GIKI',
      'Volunteers',
      'Important Donors',
    ]);
    await expect(page.locator('#crStatus')).toHaveText('Not started');
    await expect(page.locator('#crMeta')).toContainText('Left');
    if (width !== 320)
      /* every common phone and desktop: the whole page is on screen, nothing to scroll */
      expect(
        await page.locator('.cr-main').evaluate((e) => e.scrollHeight <= e.clientHeight + 1),
        'the page should not need scrolling',
      ).toBe(true);
    for (const id of ['#crStart', '#crPause', '#crFinish']) await inView(page, page.locator(id));
    await expect(page.locator('#crStart')).toBeEnabled();
    await expect(page.locator('#crPause')).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    for (const row of await page.locator('.cr-row').all())
      await expect(row.locator('.cr-line')).toContainText(/Sent|Posted/);
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
  await expect(page.locator('#crMenu .cr-tool')).toContainText([
    'Donors',
    'Messages (versions, edit, test)',
    'Case Writer',
    'Notes',
    'Chat',
    'Reports',
    'Settings',
  ]);
  await page.locator('#crMenu').getByRole('button', { name: 'Donors', exact: true }).click();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await page.locator('#donorMainBottom').click();
  await expect(page.locator('#donorsPage')).toBeHidden();
  await expect(page.locator('#casePage')).toBeVisible(); // back exactly where you were
});

test('Start case shows one summary; cancelling starts nothing', async ({ page }) => {
  await open(page, 390, 844);
  await page.locator('#crStart').click();
  const sheet = page.locator('#caseSheet');
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('.cr-sum-row')).toHaveCount(5);
  await expect(sheet.locator('.cr-sum-row').first()).toContainText('Every 45 min');
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  await expect(sheet).toBeHidden();
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
  const gap = sheet.locator('input[type=number]').first();
  await gap.fill('4');
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet).toBeHidden();
  await page.locator('.cr-row[data-key="top"] .cr-name b').click();
  await expect(sheet.locator('input[type=number]').first()).toHaveValue('4');
  await sheet.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  expect((await api(port, '/case-run')).status).toBe('idle');
  expect((await api(port, '/auto-controls')).controls.group.on).toBe(false);
  await page.locator('.cr-row[data-key="important"] .cr-name b').click();
  await sheet.locator('input[type=checkbox]').first().check(); // include
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet.locator('#csError')).toContainText('Select the Important donors first');
});

test('approve once, run, pause all, resume and finish; reopening lands on the case page', async ({
  page,
}) => {
  await api(port, '/case-run', {
    action: 'plan',
    plan: { giki: { enabled: false }, volunteers: { enabled: false } },
  });
  await open(page, 390, 844);
  await page.locator('#crStart').click();
  await page.getByRole('button', { name: 'Approve and start' }).click();
  await expect(page.locator('#crStatus')).toHaveText('Running');
  await expect(page.locator('#crPause')).toBeEnabled();
  await expect(page.locator('#crStart')).toBeDisabled();
  expect((await api(port, '/auto-controls')).controls.group.on).toBe(true);
  await expect(page.locator('.cr-row[data-key="group"] .cr-pill')).toHaveText('Running');

  await page.goto('/new'); // reopening the app while a case runs
  await expect(page.locator('#casePage')).toBeVisible();
  expect(await page.evaluate(() => location.hash)).toBe('#/case');

  await page.locator('#crPause').click();
  await expect(page.locator('#crStatus')).toHaveText('Paused');
  await expect(page.locator('#crStart')).toHaveText('Resume case');
  expect((await api(port, '/auto-controls')).controls.group.on).toBe(false);
  await page.locator('#crStart').click();
  await expect(page.locator('#crStatus')).toHaveText('Running');

  await page.locator('#crFinish').click();
  await expect(page.locator('#caseSheet')).toContainText('Confirmed so far');
  expect((await api(port, '/case-run')).status).toBe('running'); // asking changes nothing
  await page.locator('#caseSheet').getByRole('button', { name: 'Finish case' }).click();
  await expect(page.locator('#crStatus')).toHaveText('Finished');
  await expect(page.locator('#crDone')).toBeVisible();
  await expect(page.locator('#crStart')).toBeDisabled();
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
  await expect(page.locator('.cr-empty')).toHaveText('Nothing needs you.');
});

test('one page controls the amount, the case and WhatsApp, and Tools reaches every other tool', async ({
  page,
}) => {
  await open(page, 390, 844);
  await page.locator('#crMeta').click();
  const sheet = page.locator('#caseSheet');
  await sheet.locator('input[type=number]').fill('19000');
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('#crMeta')).toContainText('Left Rs. 19,000');
  expect((await api(port, '/case-run')).case.left).toBe(19000);
  await page.locator('#crName').click();
  await expect(sheet.locator('select option')).not.toHaveCount(0);
  await expect(sheet.getByRole('button', { name: 'Start new case' })).toBeVisible();
  await sheet.locator('#csFoot').getByRole('button', { name: 'Close' }).click();
  await page.locator('#crTools').click();
  await expect(page.locator('#crMenu .cr-tool')).toContainText([
    'Donors',
    'Volunteers and their sharing request',
    'Thank donors',
    'Auto replies',
    'Resume group messages',
    'WhatsApp connection',
    'Reports',
    'Settings',
  ]);
  await page.locator('#caseSheet #csFoot').getByRole('button', { name: 'Close' }).click();
  await page.locator('#crWa').click();
  await expect(page.locator('#whatsappDialog')).toBeVisible();
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
