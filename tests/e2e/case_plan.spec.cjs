const { test, expect } = require('@playwright/test');
const key = 'manual-fix-preview-key';
const facts = {
  name: 'Yousaf',
  age: '2',
  what_happened: 'has passed away',
  money_for: 'Janazah, kafan and burial fees',
  deadline: 'Janazah at 4 PM tomorrow',
};
test.beforeEach(async ({ page }) => {
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), key);
});
for (const [width, height] of [
  [1280, 800],
  [390, 700],
  [320, 568],
]) {
  test(`case plan page: facts, checked messages, approve, stop ${width}x${height}`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width, height });
    // reset any earlier plan in the fake store, then use only the fake app
    await request.post('/api/case-plan', {
      headers: { Authorization: 'Bearer ' + key },
      data: { action: 'stop' },
      failOnStatusCode: false,
    });
    await request.post('/api/case-plan', {
      headers: { Authorization: 'Bearer ' + key },
      data: { action: 'clear' },
      failOnStatusCode: false,
    });
    const sends = [];
    page.on('request', (r) => {
      if (r.method() === 'POST' && !r.url().includes('/api/case-plan')) sends.push(r.url());
    });
    await page.goto('/case-plan');
    await expect(page.locator('#planState')).toHaveText(/No case plan yet|Ready|Waiting/);
    await expect(page.locator('#factsForm')).toBeVisible();
    // A bad fact is refused with a plain reason and nothing is saved.
    await page.fill('[name=name]', 'Yousaf');
    await page.fill('[name=age]', '2');
    await page.fill('[name=what_happened]', 'has passed away');
    await page.fill('[name=money_for]', 'Janazah * fees');
    await page.getByRole('button', { name: 'Make messages' }).click();
    await expect(page.locator('#feedback')).toContainText('short and plain');
    await page.fill('[name=money_for]', facts.money_for);
    await page.fill('[name=deadline]', facts.deadline);
    await page.getByRole('button', { name: 'Make messages' }).click();
    await expect(page.locator('#planState')).toHaveText('Waiting for your approval');
    const cards = page.locator('.msg');
    await expect(cards).toHaveCount(2);
    await expect(page.locator('.msg .ok')).toHaveCount(2);
    await expect(cards.nth(0)).toContainText('Just 13 kind people donating Rs. 2,000 or 25 people');
    await expect(page.locator('#planNote')).toContainText('rounds up'); // Rs. 25,000 is not a multiple of 2,000
    await expect(cards.nth(1)).toContainText('نبی کریم');
    // No horizontal scroll and 44px tap targets at every width.
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    for (const b of await page.locator('#actions button:visible').all()) {
      expect((await b.boundingBox()).height).toBeGreaterThanOrEqual(44);
    }
    if (width <= 720) {
      const back = await page.locator('a.back').boundingBox();
      for (const b of await page.locator('#actions button:visible').all()) {
        const r = await b.boundingBox();
        const apart =
          r.x + r.width <= back.x || r.y + r.height <= back.y || back.x + back.width <= r.x;
        expect(apart, 'action buttons must not sit under the floating Back button').toBe(true);
      }
    }
    const approve = page.getByRole('button', { name: 'Approve and start' });
    await expect(approve).toBeVisible();
    const box = await approve.boundingBox();
    expect(box.y + box.height).toBeLessThanOrEqual(height + 1); // reachable without scrolling away
    await approve.click();
    await expect(page.locator('#planState')).toContainText('Running: Normal message');
    await expect(page.locator('#factsForm')).toBeHidden();
    page.once('dialog', (d) => d.accept());
    await page.getByRole('button', { name: 'Stop' }).click();
    await expect(page.locator('#planState')).toHaveText('Stopped');
    await expect(page.locator('#planDetail')).toContainText('Stopped by the owner');
    await page.screenshot({ path: `test-results/case-plan-${width}.png` });
    // Nothing but case-plan calls was made: no message left the page.
    expect(sends).toEqual([]);
  });
}
test('case plan page asks for the access key when it is missing', async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem('givelife-cloud-key'));
  await page.goto('/case-plan');
  await expect(page.getByRole('dialog', { name: 'Open your GiveLife case plan' })).toBeVisible();
});
