const { test, expect } = require('@playwright/test');

test('agents page: Manager first, real agent replies, Manual/Auto, every agent renders', async ({
  page,
}) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/agents');
  await expect(page.locator('#list .agent').first()).toContainText('Manager');
  await expect(page.locator('#modeManual')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#modeAuto').click();
  await expect(page.locator('#modeAuto')).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(page.locator('#modeAuto')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#inp').fill('ask all agents for their progress');
  await page.locator('#ask .send').click();
  const names = [
    'Writer',
    'Checker',
    'Group Poster',
    'DM Guard',
    'Reply Reader',
    'Volunteer Guide',
    'Case Plan',
  ];
  for (const n of names)
    await expect(page.locator('#thread .bubble b', { hasText: n }).first()).toBeVisible();
  for (const n of names) {
    await page.locator('#list .agent', { hasText: n }).click();
    await expect(page.locator('#name')).toHaveText(n);
  }
  await page.locator('#list .agent', { hasText: 'Writer' }).click();
  await page.locator('#inp').fill('hi');
  await page.locator('#inp').press('Enter');
  await expect(page.locator('#thread .bubble.them').last()).toContainText('AI is not connected'); // real reply, no fake text
  await page.reload();
  await expect(page.locator('#thread .bubble', { hasText: 'hi' }).first()).toBeVisible(); // saved conversation
  await page.locator('#modeManual').click();
  await expect(page.locator('#modeManual')).toHaveAttribute('aria-pressed', 'true');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
  expect(errors).toEqual([]);
});

test('agents page fits a phone', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/agents');
  await expect(page.locator('#list .agent').first()).toBeVisible();
  await expect(page.locator('#ask .send')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
});
