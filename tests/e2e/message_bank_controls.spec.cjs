const { test, expect } = require('@playwright/test');
const KEY = 'manual-fix-preview-key';
const text =
  'Brother, please help this family.\n\nRs. 25,000 LEFT.\n\n03097458815 Easypaisa only, Wajdan Khan.';
const regenerateControl = (page, base, width) =>
  page.locator(
    base === '/'
      ? '.bank-gen-icon'
      : width < 900
        ? '.ui2-bank-nav [data-ui2-proxy="#donorMessages .bank-gen-icon"]'
        : '.ui2-desktop-regenerate',
  );
const nextControl = (page, base, width) =>
  page.locator(
    base === '/'
      ? '.bank-next-arrow'
      : width < 900
        ? '.ui2-bank-nav [data-ui2-proxy="#donorMessages .bank-next-arrow"]'
        : '.ui2-desktop-next',
  );
const items = [1, 2].map((number) => ({
  id: 'version-' + number,
  text: text + '\nVersion ' + number,
  enabled: true,
}));

for (const base of ['/', '/new/']) {
  for (const width of [390, 1440]) {
    test(`regeneration control remains disabled after changing versions ${base} ${width}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
      let release;
      let calls = 0;
      await page.route('**/donor-messages', async (route) => {
        if (route.request().method() === 'POST') {
          expect(route.request().postDataJSON().action).toBe('regenerate');
          calls++;
          await new Promise((resolve) => (release = resolve));
        }
        await route.fulfill({ json: { items } });
      });
      await page.goto(base + '#/donors/messages');
      const regenerate = regenerateControl(page, base, width);
      await regenerate.click();
      try {
        await expect.poll(() => calls).toBe(1);
        await expect(regenerate).toBeDisabled();
        await nextControl(page, base, width).click();
        await expect(page.locator('.bank-current')).toHaveText('Message 2 of 2');
        await expect(nextControl(page, base, width)).toBeDisabled();
        await expect(regenerate).toBeDisabled();
        expect(calls).toBe(1);
      } finally {
        release?.();
      }
      await expect(regenerate).toBeEnabled();
      expect(calls).toBe(1);
    });

    test(`empty message bank can save a base and generate versions ${base} ${width}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((key) => localStorage.setItem('givelife-cloud-key', key), KEY);
      let saved = [];
      const actions = [];
      await page.route('**/donor-messages', async (route) => {
        if (route.request().method() === 'POST') {
          const body = route.request().postDataJSON();
          actions.push(body.action);
          if (body.action === 'base') {
            expect(body.text).toBe(text);
            saved = [{ id: 'version-1', text: body.text, enabled: true }];
          } else {
            expect(body.action).toBe('regenerate');
            saved = items;
          }
        }
        await route.fulfill({ json: { items: saved } });
      });
      await page.goto(base + '#/donors/messages');
      await expect(page.locator('#donorMessages')).toContainText('No saved messages yet');
      await page.getByRole('button', { name: 'Add base message', exact: true }).click();
      await page.getByRole('textbox', { name: 'Base message', exact: true }).fill(text);
      await page.getByRole('button', { name: 'Save base message', exact: true }).click();
      await expect(page.locator('#baseMessageDialog')).toBeHidden();
      await expect(page.locator('.bank-preview')).toContainText('Brother');
      await regenerateControl(page, base, width).click();
      await expect(page.locator('.bank-current')).toHaveText('Message 1 of 2');
      expect(actions).toEqual(['base', 'regenerate']);
    });
  }
}
