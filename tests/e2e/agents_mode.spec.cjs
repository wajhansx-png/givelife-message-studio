const { test, expect } = require('@playwright/test');

test('agents page: Manual/Auto toggle switches the real mode and every agent still renders', async ({
  page,
}) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/agents');
  const manual = page.locator('#modeManual');
  const auto = page.locator('#modeAuto');
  await expect(manual).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#modeText')).toContainText('Manual');
  await auto.click();
  await expect(auto).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#modeText')).toContainText('Auto:');
  await page.reload();
  await expect(auto).toHaveAttribute('aria-pressed', 'true');
  for (const name of [
    'Group Poster',
    'Writer',
    'Reply Reader',
    'DM Sender',
    'Volunteers',
    'Case Plan',
  ]) {
    await page.locator('#list .agent', { hasText: name }).click();
    await expect(page.locator('#name')).toHaveText(name);
  }
  await page.locator('#list .agent', { hasText: 'Writer' }).click();
  await expect(page.locator('#rules')).toBeHidden();
  await page.locator('#inp').fill('hi');
  await page.locator('#ask .send').click();
  await expect(page.locator('#answer')).toBeVisible();
  await expect(page.locator('#ansQ')).toHaveText('You: hi');
  await expect(page.locator('#ansText')).not.toHaveText('Thinking…', { timeout: 15000 });
  await expect(page.locator('#msg')).not.toContainText('Not saved');
  await manual.click();
  await expect(manual).toHaveAttribute('aria-pressed', 'true');
  await expect(manual).toBeEnabled();
  expect(errors).toEqual([]);
});
