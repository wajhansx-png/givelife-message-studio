const { test, expect } = require('@playwright/test');

// Reproduces the supplied Samsung screenshot: 393 CSS px at 1.5 device scale.
const message = `*Only 2 hours until Yousaf's Janazah. Can you be one of the 19 people helping? 💔*\n\nHis family needs help for Kafan, grave digging and burial fees.\n\nاللہ تعالیٰ فرماتا ہے:\n"اور نیکی کے کاموں میں ایک دوسرے کی مدد کرو۔"\n(سورۃ المائدہ: 2)\n\n*Rs. 39,000 still needed*\n\n${'The remaining funeral arrangements need to be covered.\n\n'.repeat(24)}Easypaisa / JazzCash — Wajdan Khan\n0309 7458815`;

for (const [width, height, versions] of [
  [393, 700, 1],
  [393, 700, 20],
  [320, 568, 1],
  [768, 1024, 20],
]) {
  test(`phone Messages gives reading priority ${width}x${height}, ${versions} versions`, async ({
    browser,
  }) => {
    const context = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: 1.5,
      isMobile: true,
      hasTouch: true,
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    await page.addInitScript(() => {
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
      localStorage.setItem('givelife-theme', 'dark');
    });
    await page.route('**/donor-messages', async (route) => {
      if (route.request().method() !== 'GET') return route.continue();
      const response = await route.fetch();
      const data = await response.json();
      data.items = data.items.slice(0, versions).map((item) => ({ ...item, text: message }));
      data.generation = null;
      await route.fulfill({ response, json: data });
    });
    try {
      await page.goto('/new#/donors/messages');
      const preview = page.locator('.bank-preview');
      await expect(preview).toContainText('Only 2 hours');
      await page.evaluate(() => document.fonts.ready);
      const reader = page.locator('.bank-detail');
      const reading = await reader.boundingBox();
      const tools = await page.locator('.bank-actions').boundingBox();
      await page.screenshot({ path: `test-results/messages-priority-${width}-${versions}.png` });
      // Six oversized toolbar rows used to leave only 207px for reading at 393x700.
      expect(reading.height, 'message must use at least half the viewport').toBeGreaterThanOrEqual(
        height / 2,
      );
      expect(tools.height, 'controls must not consume the reading area').toBeLessThanOrEqual(160);
      expect(
        tools.y + tools.height,
        'all actions fit without scrolling the workspace',
      ).toBeLessThanOrEqual(height);
      for (const button of await page.locator('.bank-actions button:visible').all()) {
        const box = await button.boundingBox();
        expect(box.height).toBeGreaterThanOrEqual(43.99);
        expect(box.height).toBeLessThanOrEqual(52);
        expect(box.width).toBeGreaterThanOrEqual(43.99);
      }
      await preview.hover();
      await page.mouse.wheel(0, 500);
      await expect.poll(() => reader.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
      expect(await page.locator('.bank-workspace').evaluate((el) => el.scrollTop)).toBe(0);
      await expect(page.locator('.bank-picker')).toBeHidden();
      const navigation = page.locator('.ui2-bank-nav');
      const next = navigation.getByRole('button', { name: 'Next ›', exact: true });
      if (versions === 1) {
        await expect(next).toBeHidden();
        await page.locator('#ui2BankMore summary').click();
        await expect(
          page.getByRole('button', { name: 'Generate 20 versions', exact: true }),
        ).toBeVisible();
        await page.locator('#ui2BankMore summary').click();
      } else {
        await next.click();
        await expect(page.locator('.bank-current')).toHaveText('Message 2 of 20');
        await navigation.getByRole('button', { name: '‹ Previous', exact: true }).click();
        await expect(page.locator('.bank-current')).toHaveText('Message 1 of 20');
      }
      await page.locator('[data-bank-save-id]').click();
      await expect(page.locator('.bank-detail textarea')).toHaveValue(message);
      expect(
        (await page.locator('.bank-detail textarea').boundingBox()).height,
      ).toBeGreaterThanOrEqual(reading.height - 30);
      await page.locator('.bank-back-bottom').click();
      await expect(page.locator('#donorTable')).toBeVisible();
    } finally {
      await context.close();
    }
  });
}
