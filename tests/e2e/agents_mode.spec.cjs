const { test, expect } = require('@playwright/test');
const NAMES = [
  'Manager',
  'Writer',
  'Checker',
  'Group Poster',
  'DM Guard',
  'Reply Reader',
  'Volunteer Guide',
  'Case Plan',
];
const open = async (page, width = 1280, height = 800) => {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/agents');
};

test('agents page: all agents on top, real replies, Auto switch, no extra text', async ({
  page,
}) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await open(page);
  for (const n of NAMES) await expect(page.locator('#list .agent', { hasText: n })).toBeVisible();
  await expect(page.getByText('Manager passes your message')).toHaveCount(0);
  const auto = page.locator('#modeAuto');
  await expect(auto).toHaveAttribute('aria-checked', 'false');
  await auto.click();
  await expect(auto).toHaveAttribute('aria-checked', 'true');
  await page.reload();
  await expect(auto).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#ask .send')).toBeDisabled();
  await page.locator('#inp').fill('ask all agents for their progress');
  await expect(page.locator('#ask .send')).toBeEnabled();
  await page.locator('#inp').press('Enter');
  for (const n of NAMES.slice(1))
    await expect(page.locator('#thread .who', { hasText: n }).first()).toBeVisible();
  for (const n of NAMES.slice(1)) {
    await page.locator('#list .agent', { hasText: n }).click();
    await expect(page.locator('#name')).toHaveText(n);
    await expect(page.locator('#inp')).toHaveAttribute('placeholder', 'Message ' + n);
  }
  await page.locator('#list .agent', { hasText: 'Writer' }).click();
  await page.locator('#inp').fill('hi');
  await page.locator('#ask .send').click();
  await expect(page.locator('#thread .bubble.them').last()).toContainText('AI is not connected');
  await page.reload();
  await expect(page.locator('#thread .bubble.me', { hasText: 'hi' }).first()).toBeVisible();
  await auto.click();
  await expect(auto).toHaveAttribute('aria-checked', 'false');
  expect(errors).toEqual([]);
});

test('replies render bold and lists, show typing first, never raw ** marks', async ({ page }) => {
  await open(page, 390, 844);
  await page.route('**/api/agents', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    const res = await route.fetch();
    const d = await res.json();
    await new Promise((r) => setTimeout(r, 800));
    d.messages = [
      { who: 'you', agent: 'manager', text: 'Hi', id: 'a' },
      {
        who: 'manager',
        agent: 'manager',
        text: "Hi! Here's where things stand:\n\n- **Writer:** Group 3 versions\n- **DM Guard:** DMs on",
        id: 'b',
      },
    ];
    d.chat = [...(d.chat || []), ...d.messages];
    await route.fulfill({ response: res, json: d });
  });
  await page.locator('#inp').fill('Hi');
  await page.locator('#ask .send').click();
  await expect(page.locator('#thread .dots')).toBeVisible(); // typing indicator while waiting
  const reply = page.locator('#thread .bubble.them').last();
  await expect(reply.locator('strong', { hasText: 'Writer:' })).toBeVisible();
  await expect(reply).not.toContainText('**');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
  await expect(page.locator('#ask .send')).toBeInViewport();
});
