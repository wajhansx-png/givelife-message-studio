const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 203;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => {
  server = await startOwnServer(port);
  await api(port, '/donor-messages', { action: 'follow_up', text: 'Synthetic saved follow-up' });
  await api(port, '/volunteers', { action: 'message', text: 'Synthetic saved share message' });
});
test.afterAll(() => server?.kill());
async function open(page, width = 390) {
  await page.setViewportSize({ width, height: 740 });
  await page.addInitScript(key => localStorage.setItem('givelife-cloud-key', key), KEY);
  await page.goto('/new/');
  await page.evaluate(() => window.GiveLifeReport.open());
  await expect(page.locator('.auto-card')).toHaveCount(5);
}
for (const width of [320, 390, 768, 1440]) {
  test(`every automation setting is visible, editable and saved at ${width}`, async ({ page }) => {
    await open(page, width);
    const controls = (await api(port, '/auto-controls')).controls;
    const before = (await api(port, '/__test/events')).events.length;
    for (const c of Object.values(controls)) {
      const card = page.locator(`.auto-card[data-control="${c.id}"]`);
      const gear = card.locator('.auto-edit');
      await expect(gear).toBeVisible();
      const box = await gear.boundingBox();
      expect(box.width).toBeGreaterThanOrEqual(40);
      await gear.click();
      const dialog = card.locator('.auto-settings-dialog');
      await expect(dialog).toBeVisible();
      const bounds = await dialog.boundingBox();
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1);
      const saved = {};
      for (const f of c.fields) {
        const input = dialog.locator(`[name="${f.key}"]`);
        await expect(input).toBeVisible();
        if (f.type === 'check') { await input.setChecked(!c.settings[f.key]); saved[f.key] = !c.settings[f.key]; }
        else if (f.type === 'number') { const n = Math.min(f.max, Math.max(f.min, Number(c.settings[f.key]) || f.min) + 1); await input.fill(String(n)); saved[f.key] = n; }
      }
      await dialog.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(dialog).toBeHidden();
      const after = (await api(port, '/auto-controls')).controls[c.id];
      expect(after.on).toBe(false);
      for (const [key, value] of Object.entries(saved)) expect(after.settings[key]).toBe(value);
      await gear.click();
      for (const [key, value] of Object.entries(saved)) {
        const input = dialog.locator(`[name="${key}"]`);
        if (typeof value === 'boolean') expect(await input.isChecked()).toBe(value);
        else await expect(input).toHaveValue(String(value));
      }
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(gear).toBeFocused();
    }
    expect((await api(port, '/__test/events')).events.length).toBe(before);
  });
}
test('failed save preserves draft and blocks repeated taps while saving', async ({ page }) => {
  await open(page);
  const card = page.locator('.auto-card[data-control="important"]');
  await card.locator('.auto-edit').click();
  const dialog = card.locator('.auto-settings-dialog');
  await dialog.locator('[name=count]').fill('7');
  let release, posts = 0;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/auto-controls', async route => {
    if (route.request().method() === 'POST') { posts++; await gate; return route.fulfill({status:503,json:{error:'Save unavailable'}}); }
    return route.continue();
  });
  const save = dialog.getByRole('button', { name: 'Save', exact:true });
  await save.click();
  await expect(save).toBeDisabled();
  await save.evaluate(button => button.click());
  release();
  await expect(dialog.locator('.auto-error')).toContainText('Save unavailable');
  await expect(dialog.locator('[name=count]')).toHaveValue('7');
  await expect(save).toBeEnabled();
  expect(posts).toBe(1);
});
test('HTTP errors show unavailable instead of false zero counts', async ({ page }) => {
  await page.route('**/autopilot', route => route.fulfill({status:503,json:{error:'offline'}}));
  await open(page);
  await expect(page.locator('#reportGroups')).toHaveText('—');
  await expect(page.locator('#reportGroupsSub')).toContainText('Unavailable');
});
test('toggle gives immediate feedback, blocks duplicate starts and restores OFF on failure', async ({ page }) => {
  await open(page);
  let release, posts = 0;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/auto-controls', async route => {
    if (route.request().method() === 'POST') {
      posts++; await gate;
      return route.fulfill({status:503,json:{error:'WhatsApp unavailable'}});
    }
    return route.continue();
  });
  const toggle = page.locator('[data-control=group] .auto-switch');
  await toggle.click();
  await expect(toggle).toHaveText('Starting…');
  await expect(toggle).toBeDisabled();
  await toggle.evaluate(button => button.click());
  release();
  await expect(toggle).toHaveText('OFF');
  await expect(toggle).toHaveAttribute('aria-checked','false');
  await expect(toggle).toBeEnabled();
  await expect(page.locator('#autoMsg')).toContainText('WhatsApp unavailable');
  expect(posts).toBe(1);
});
test('Cancel keeps saved settings, and server rejects invalid timing without hiding the error', async ({ page }) => {
  await open(page);
  const card = page.locator('[data-control=important]');
  const gear = card.locator('.auto-edit');
  const previous = (await api(port, '/auto-controls')).controls.important.settings.count;
  await gear.click();
  const dialog = card.locator('.auto-settings-dialog');
  await dialog.locator('[name=count]').fill('7');
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  await gear.click();
  await expect(dialog.locator('[name=count]')).toHaveValue(String(previous));
  await dialog.locator('[name=gap_minutes]').fill('99');
  await dialog.locator('form').evaluate(form => { form.noValidate=true; });
  await dialog.getByRole('button',{name:'Save',exact:true}).click();
  await expect(dialog.locator('.auto-error')).toContainText('choose');
  await expect(dialog.locator('[name=gap_minutes]')).toHaveValue('99');
});
test('settings dialog contains its fields and actions on a short phone screen', async ({ page }) => {
  await open(page);
  await page.setViewportSize({width:390,height:520});
  const card = page.locator('[data-control=thanks]');
  await card.locator('.auto-edit').click();
  const dialog = card.locator('.auto-settings-dialog');
  const box = await dialog.boundingBox();
  const form = await dialog.locator('form').boundingBox();
  expect(form.y).toBeGreaterThanOrEqual(box.y);
  expect(form.y + form.height).toBeLessThanOrEqual(box.y + box.height + 1);
  for (const button of await dialog.locator('button').all()) {
    const bounds = await button.boundingBox();
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(520);
  }
});
test('stalled save times out, restores draft and allows Cancel', async ({ page }) => {
  await open(page);
  await page.clock.install();
  const card = page.locator('[data-control=important]');
  await card.locator('.auto-edit').click();
  const dialog = card.locator('.auto-settings-dialog');
  await dialog.locator('[name=count]').fill('7');
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/auto-controls', async route => {
    if (route.request().method() === 'POST') { await gate; return route.fulfill({status:503,json:{error:'offline'}}).catch(()=>{}); }
    return route.continue();
  });
  try {
    await dialog.getByRole('button',{name:'Save',exact:true}).click();
    await page.clock.fastForward(16000);
    await expect(dialog.locator('.auto-error')).toContainText('Timed out');
    await expect(dialog.locator('[name=count]')).toHaveValue('7');
    await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
    await expect(dialog).toBeHidden();
  } finally { release(); }
});
