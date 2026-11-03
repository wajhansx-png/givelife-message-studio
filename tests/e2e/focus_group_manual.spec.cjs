const { test, expect } = require('@playwright/test');
test('Group opens editor; manual slots save and send from this screen', async ({
  page,
  request,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/');
  await page.getByRole('button', { name: 'Group messages', exact: true }).click();
  await expect(page.locator('#messageFocus .group-send')).toBeVisible();
  await expect(page.locator('#focusFormatted')).not.toHaveText('');
  await page.locator('#focusManual').click();
  await expect(page.getByRole('dialog', { name: 'Manual messages', exact: true })).toBeVisible();
  for (let i = 0; i < 10; i++) {
    await page.locator('#manualText').fill('Manually approved message ' + i);
    if (i < 9) await page.locator('#manualNext').click();
  }
  await page.locator('#manualSave').click();
  await expect(page.locator('#focusState')).toContainText('10 manual messages ready');
  const bank = await (
    await request.get('/focus-bank?kind=group', {
      headers: { Authorization: 'Bearer manual-fix-preview-key' },
    })
  ).json();
  expect(bank.items.length).toBe(10);
  await page.locator('#messageFocus [data-group="main"]').click();
  await expect
    .poll(async () => {
      const data = await (
        await request.get('/__test/events', {
          headers: { Authorization: 'Bearer manual-fix-preview-key' },
        })
      ).json();
      return data.events.filter((e) => e.fields.caption?.startsWith('Manually approved message'))
        .length;
    })
    .toBe(1);
  await page.locator('#focusBack').click();
  await expect(page.locator('#messageFocus')).toBeHidden();
});
