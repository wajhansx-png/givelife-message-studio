const { test, expect } = require('@playwright/test');
const { showDm } = require('./helpers.cjs');
const auth = { Authorization: 'Bearer manual-fix-preview-key' };
test('pasted DM modal validates, deduplicates and starts the first personalized DM', async ({
  page,
  request,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/');
  await showDm(page);
  await page.getByRole('button', { name: 'Send to more donors', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Bulk message', exact: true });
  await expect(modal).toBeVisible();
  await page
    .getByLabel('Numbers and names', { exact: true })
    .fill('03001112222, Ali\nAyesha, 03012223333\n+923001112222, Ali duplicate');
  await expect(page.locator('#pasteResult')).toContainText('2 recipients');
  await expect(page.locator('#pasteResult')).not.toContainText('1112222');
  await expect(page.getByRole('button', { name: 'DM all 2', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'DM all 2', exact: true }).click();
  await page.getByLabel('Gap between DMs', { exact: true }).selectOption('3');
  await expect(page.getByRole('button', { name: 'Start DMs now', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Start DMs now', exact: true }).dblclick();
  await expect(page.locator('#donorsPage')).toBeVisible();
  await expect
    .poll(async () => {
      const r = await request.get('/donor-delivery', { headers: auth });
      return (await r.json()).sent;
    })
    .toBe(1);
  const status = await (await request.get('/donor-delivery', { headers: auth })).json();
  expect(status.total).toBe(2);
  expect(status.gap_seconds).toBe(180);
  const events = await (await request.get('/__test/events', { headers: auth })).json();
  expect(events.events.filter((e) => e.fields.phone === '923001112222').length).toBe(1);
  expect(events.events.find((e) => e.fields.phone === '923001112222').fields.caption).toMatch(
    /^Ali Bhai/,
  );
  await request.post('/donor-delivery', { headers: auth, data: { stop: true } });
});
test('private APIs reject missing authentication and invalid origins', async ({ request }) => {
  expect((await request.get('/donors')).status()).toBe(401);
  expect(
    (
      await request.post('/donor-paste', { data: { action: 'preview', text: '03001234567, Ali' } })
    ).status(),
  ).toBe(401);
  expect(
    (
      await request.post('/donor-paste', {
        headers: { ...auth, Origin: 'https://untrusted.invalid' },
        data: { action: 'preview', text: '03001234567, Ali' },
      })
    ).status(),
  ).toBe(403);
});

test('bulk PDF is uploaded privately and sent with exact personalized caption', async ({
  page,
  request,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/#/donors/all');
  await page.locator('#donorNavMore summary').click();
  await page.locator('#donorBulk').click();
  await page.locator('#pastePeople').fill('03001112224, Ali');
  await expect(page.locator('#pasteNext')).toBeEnabled();
  await page.locator('#pasteNext').click();
  await page.locator('#pasteMessage').fill('Hi {name}, here is the report.');
  await page.locator('#pasteMedia').setInputFiles({
    name: 'report.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4\nSynthetic report'),
  });
  await expect(page.locator('#pasteMediaNote')).toContainText('ready');
  await expect(page.locator('#pastePoster')).not.toBeChecked();
  await page.locator('#pasteStart').click();
  await expect
    .poll(async () => {
      const r = await request.get('/__test/events', { headers: auth });
      const d = await r.json();
      return d.events.some(
        (e) => e.path === '/send/file' && e.fields.caption === 'Hi Ali, here is the report.',
      );
    })
    .toBe(true);
});

for (const width of [1440, 390])
  test(`simple batch controls and custom bulk text ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/');
    await expect(page.locator('.brandbar #donorNotesShortcut')).toBeVisible();
    await page.locator('.brandbar #donorNotesShortcut').click();
    await expect(page.locator('#foundationNotes')).toBeVisible();
    await page.goto('/#/donors/important');
    await page.locator('#donorSendImportant').click();
    const batch = page.locator('#donorBatchPicker');
    await expect(batch).toBeVisible();
    await page.locator('#batchCount').fill('60');
    await page.locator('#batchLimit').selectOption('10');
    await expect(page.locator('#batchPlan')).toContainText('6 batches');
    await expect(page.locator('#batchLimit')).toBeVisible();
    await page.locator('#batchCancel').click();
    await page.locator('#donorNavMore summary').click();
    await page.locator('#donorBulk').click();
    await page.locator('#pastePeople').fill('03001112223, Ali');
    await expect(page.locator('#pasteNext')).toBeEnabled();
    await page.locator('#pasteNext').click();
    await page.locator('#pasteMessage').fill('Hi {name}, thank you for your help.');
    await page.locator('#pastePoster').uncheck();
    await page.locator('#pasteGap').selectOption('3');
    await page.screenshot({ path: `test-results/bulk-custom-${width}.png` });
    await page.locator('#pasteStart').click();
    await expect
      .poll(async () => {
        const r = await request.get('/__test/events', { headers: auth });
        const d = await r.json();
        return d.events.some(
          (e) =>
            e.fields.phone === '923001112223' &&
            e.fields.message === 'Hi Ali, thank you for your help.',
        );
      })
      .toBe(true);
  });
