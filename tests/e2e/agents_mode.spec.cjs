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

const LONG = `*Today is the last day to return this borrowed money.* 💔

_When little Yousaf was buried, the cost was taken as a loan. His parents must hand it back today. That loan is still open._

* Rs. 17,500 is still needed to close this debt.

The Prophet ﷺ said: “Charity extinguishes sins as water extinguishes fire.” (Sunan al-Tirmidhi 2616)

* *Only 10 people giving Rs. 2,000, or 20 people giving Rs. 1,000, and it is finished.* 🤲

03097458815
EASYPAISA ONLY – Wajdan Khan (GiveLife Foundation account)

— GiveLife Foundation`;

// The page gets a pending Writer draft from the server, before it loads.
const withDraft = (page, text, extra = {}) =>
  page.route('**/api/agents', async (route) => {
    const res = await route.fetch();
    const d = await res.json();
    if (route.request().method() === 'POST' && extra.onPost) extra.onPost(route.request());
    const saved = extra.saved?.();
    d.chat = [
      { who: 'you', agent: 'writer', text: 'Write a group message', id: 'a', at: 1 },
      {
        who: 'writer',
        agent: 'writer',
        id: 'b',
        at: 2,
        text: extra.reply ?? 'Here is a version.',
        draft: { id: 'd1', kind: 'group', text, ...(saved ? { saved: 'group' } : {}) },
      },
    ];
    d.pending = saved ? '' : 'd1';
    await route.fulfill({ response: res, json: d });
  });

for (const [w, h] of [
  [390, 844],
  [360, 640],
  [320, 568],
  [1280, 720],
]) {
  test(`draft card fits one screen with no scroll, buttons in view (${w}x${h})`, async ({
    page,
  }) => {
    await withDraft(page, LONG);
    await open(page, w, h);
    await page.locator('#list .agent', { hasText: 'Writer' }).click();
    const card = page.locator('.wa-bubble');
    await expect(card).toBeVisible();
    await expect(card.locator('strong').first()).toContainText('Today is the last day'); // *bold* shows as bold
    await expect(card).not.toContainText('*Today');
    await page.waitForTimeout(400);
    const m = await page.evaluate(() => {
      const bubble = document.querySelector('.wa-bubble');
      const c = bubble.getBoundingClientRect();
      const b = document.querySelector('.choices').getBoundingClientRect();
      const a = document.querySelector('#ask').getBoundingClientRect();
      return {
        scrolls: bubble.scrollHeight > bubble.clientHeight + 1,
        cardTop: c.top,
        btnBottom: b.bottom,
        askTop: a.top,
        over: document.documentElement.scrollWidth > innerWidth + 1,
      };
    });
    expect(m.scrolls).toBe(false);
    expect(m.cardTop).toBeGreaterThanOrEqual(0);
    expect(m.btnBottom).toBeLessThanOrEqual(m.askTop + 1); // card and buttons are all visible above the input
    expect(m.over).toBe(false);
  });
}

test('Approve sends a plain word; a saved draft then shows as saved', async ({ page }) => {
  const sent = [];
  let saved = false;
  await withDraft(page, '*Hook* line', {
    reply: '',
    saved: () => saved,
    onPost: (req) => {
      sent.push(JSON.parse(req.postData()).text);
      saved = true;
    },
  });
  await open(page, 390, 844);
  await page.locator('#list .agent', { hasText: 'Writer' }).click();
  await expect(page.getByRole('button', { name: 'Approve ✓' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Next option →' })).toBeVisible();
  await page.getByRole('button', { name: 'Approve ✓' }).click();
  await expect(page.locator('.saved')).toContainText('Saved as your Group message');
  await expect(page.locator('.choices')).toHaveCount(0);
  expect(sent[0]).toBe('Approved');
});
