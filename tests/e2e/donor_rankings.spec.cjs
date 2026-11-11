const { test, expect } = require('@playwright/test');
const headers = { Authorization: 'Bearer manual-fix-preview-key' };
for (const width of [1440, 390, 320])
  test(`ranked donor lists and compact resume ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    const all = (await (await request.get('/donors?tab=all', { headers })).json()).items;
    for (const d of all.filter((d) => d.important || d.top_donor))
      await request.post('/donors', {
        headers,
        data: { action: 'update', id: d.id, important: false, top_donor: false },
      });
    const picked = all.slice(0, 3).reverse();
    for (const d of picked)
      await request.post('/donors', {
        headers,
        data: { action: 'update', id: d.id, important: true },
      });
    await page.goto('/#/donors/important');
    await expect(page.locator('#donorRows .donor-row')).toHaveCount(3);
    expect(await page.locator('#donorRows .donor-name').allTextContents()).toEqual(
      picked.map((d) => d.name),
    );
    for (const d of [picked[2], picked[0]]) {
      const row = page.locator(`[data-donor-id="${d.id}"]`);
      const chip = row.locator('.donor-top-chip');
      if (await chip.isVisible()) await chip.click();
      else {
        await row.locator('summary').click();
        await row.getByRole('button', { name: 'Add to Top donors', exact: true }).click();
      }
      await expect(row.locator('summary')).toBeVisible();
    }
    await page.getByRole('tab', { name: /^Top donors/ }).click();
    await expect(page.locator('#donorRows .donor-row')).toHaveCount(2);
    expect(await page.locator('#donorRows .donor-name').allTextContents()).toEqual([
      picked[2].name,
      picked[0].name,
    ]);
    await expect(page.locator('#donorSendImportant')).toHaveText('DM Top donors');
    await page.locator('#donorSendImportant').click();
    await expect(page.locator('#batchCount')).toHaveValue('2');
    await page.locator('#batchCancel').click();
    await expect(page).toHaveURL(/#\/donors\/top$/);
    await page.reload();
    await page.waitForFunction(() => !document.documentElement.dataset.uiBoot);
    await expect(page.getByRole('tab', { name: /^Top donors/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(page.locator('#donorRows .donor-row')).toHaveCount(2);
    const ranked = [picked[2], picked[0]],
      searched = [...ranked].sort((a, b) => b.name.length - a.name.length)[0];
    await page.locator('#donorSearch').fill(searched.name);
    await expect(page.locator('#donorRows .donor-row')).toHaveCount(1);
    await expect(page.locator('#donorRows .donor-name')).toHaveAttribute(
      'data-rank',
      String(ranked.findIndex((d) => d.id === searched.id) + 1),
    );
    await page.locator('#donorSearch').fill('');
    await request.post('/donor-delivery', { headers, data: { stop: true } });
    await page.reload();
    await page.waitForFunction(() => !document.documentElement.dataset.uiBoot);
    await expect(page.locator('#donorToggle')).toHaveText('Resume DMs');
    await expect(page.locator('.donor-shell > #donorResumeStatus')).toHaveCount(0);
    await page.locator('#donorToggle').click();
    await expect(page.locator('#donorResumeDialog')).toBeVisible();
    await expect(page.locator('#donorResumeNow')).toBeVisible();
    await page.locator('#donorResumeClose').click();
    await expect(page.locator('#donorResumeDialog')).toBeHidden();
    await page.waitForTimeout(250);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/ranked-donors-${width}.png` });
  });
