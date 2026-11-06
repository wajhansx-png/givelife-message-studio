const { test, expect } = require('@playwright/test');
/* Send DMs modal: one compact screen. Requests are captured and answered locally, nothing is sent. */
for (const [width, height] of [
  [320, 568],
  [375, 667],
  [430, 932],
  [768, 1024],
  [1280, 800],
])
  test(`Send DMs modal is one simple screen at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
    });
    const posts = [];
    await page.route('**/donor-delivery', async (route) => {
      if (route.request().method() === 'POST') {
        posts.push(route.request().postDataJSON());
        return route.fulfill({
          json: { reply: 'Started', job: { id: 'fake', state: 'Starting', total: 1, sent: 0 } },
        });
      }
      return route.continue();
    });
    await page.goto('/#/donors/important');
    await expect(page.locator('.donor-row').first()).toBeVisible();
    await page.locator('#donorSendImportant').click();
    const modal = page.locator('#donorBatchPicker');
    await expect(modal).toBeVisible();
    const fit = await modal.evaluate((d) => {
      const r = d.getBoundingClientRect();
      const start = document.getElementById('batchStart').getBoundingClientRect();
      return {
        scroll: d.scrollHeight > d.clientHeight + 1,
        inside: r.top >= 0 && r.bottom <= innerHeight && start.bottom <= innerHeight,
      };
    });
    expect(fit.scroll).toBe(false);
    expect(fit.inside).toBe(true);
    // Presets: one pressed, custom field hidden until Custom is chosen.
    await expect(modal.locator('.batch-gap-btn[data-gap="4"]')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.locator('#batchGapCustom')).toBeHidden();
    await modal.locator('.batch-gap-btn[data-gap="6"]').click();
    await expect(page.locator('#batchPlan')).toContainText('Wait 6 min between each');
    await modal.locator('.batch-gap-btn[data-gap="custom"]').click();
    await expect(page.locator('#batchGapCustom')).toBeVisible();
    await page.locator('#batchGap').fill('25');
    await page.locator('#batchGapUnit').selectOption('1');
    await expect(page.locator('#batchPlan')).toContainText('Wait 25 sec between each');
    await page.locator('#batchPoster').uncheck();
    await expect(page.locator('#batchPlan')).toContainText('Poster off');
    // Escape and Cancel close without sending.
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden();
    await page.locator('#donorSendImportant').click();
    await page.locator('#batchCancel').click();
    await expect(modal).toBeHidden();
    expect(posts).toHaveLength(0);
    // Start sends exactly the chosen settings.
    await page.locator('#donorSendImportant').click();
    await expect(page.locator('#batchPoster')).not.toBeChecked(); // one poster setting, remembered
    await page.locator('#batchPoster').check();
    await modal.locator('.batch-gap-btn[data-gap="2"]').click();
    await page.locator('#batchStart').click();
    await expect.poll(() => posts.length).toBeGreaterThan(0);
    expect(posts[0].gap_seconds).toBe(120);
    expect(posts[0].poster).toBe(true);
    expect(posts[0].scope).toBe('important');
  });
