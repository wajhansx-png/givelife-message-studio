const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const { auditElements } = require('./element-audit.cjs');

const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 226;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}`, reducedMotion: 'reduce' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server && server.kill());

test('Volunteers hides the donor header and keeps its actions reachable across widths', async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await request.post('/volunteers', {
    headers: { Authorization: 'Bearer ' + KEY },
    data: { action: 'add', name: 'Muhammad Abdullah Khan', phone: '15551239998' },
  });
  await page.addInitScript((key) => {
    if (location.protocol === 'http:') localStorage.setItem('givelife-cloud-key', key);
  }, KEY);
  await page.goto('/new#/donors/volunteers');
  await expect(page.locator('.vol-row').first()).toBeVisible();

  for (const [width, height] of [
    [280, 653],
    [320, 568],
    [359, 740],
    [360, 740],
    [390, 844],
    [430, 932],
    [540, 780],
    [700, 900],
    [759, 900],
    [760, 900],
    [768, 1024],
    [899, 900],
    [900, 900],
    [1024, 900],
    [1440, 900],
    [1920, 1080],
    [844, 390],
    [390, 360],
  ]) {
    await page.setViewportSize({ width, height });
    if (width < 900) {
      await expect(page.locator('.donor-head'), `donor header at ${width}x${height}`).toBeHidden();
    } else {
      await expect(page.locator('.donor-head'), `donor header at ${width}x${height}`).toBeVisible();
    }
    await expect(page.locator('#donorSearch')).toBeHidden();
    await expect(page.getByRole('tablist', { name: 'Donor filters' })).toBeVisible();
    await expect(page.locator('.vol-back')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'DM all volunteers', exact: true }),
    ).toBeVisible();
    const audit = await auditElements(page, '#donorsPage');
    expect(audit.failures, `Volunteers at ${width}x${height}`).toEqual([]);

    await page.locator('.vol-add-panel > summary').click();
    await expect(page.getByLabel('Volunteer name', { exact: true })).toBeVisible();
    const addAudit = await auditElements(page, '.vol-add');
    expect(addAudit.failures, `Add volunteer at ${width}x${height}`).toEqual([]);
    await page.locator('.vol-add-panel > summary').click();
  }

  // Switching tabs must restore the donor controls, then hide them on return.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('[data-tab="all"]').click();
  await expect(page.getByRole('button', { name: 'Search donors', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Search donors', exact: true }).click();
  await expect(page.locator('#donorSearch')).toBeVisible();
  await page.locator('#donorSearch').press('Escape');
  await expect(page.locator('#donorSearch')).toBeHidden();
  await page.locator('[data-tab="volunteers"]').click();
  await expect(page.locator('.donor-head')).toBeHidden();
  await expect(page.locator('#donorSearch')).toBeHidden();
  await page.screenshot({ path: '/tmp/givelife-volunteers-mobile.png' });
  await page.locator('.vol-back').click();
  await expect(page.locator('#donorsPage')).toHaveAttribute('data-panel', 'all');
  await expect(page.getByRole('tab', { name: /All donors/ })).toHaveAttribute('aria-selected', 'true');
  expect(errors).toEqual([]);
});
