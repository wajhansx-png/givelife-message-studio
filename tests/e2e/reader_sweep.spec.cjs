/* The Message reader, end to end: every button, the More menu, swipe, edit, paste, Save base, new versions,
   group and DM view, phone and computer. Any page error or console error fails it. Fake WhatsApp only. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 667;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

const BASE = '*Bold opening line*\n\n_Italic second line_\n\nRs. 5,000 needed. Please help today.';

for (const [width, kind] of [[320, 'group'], [390, 'group'], [390, 'dm'], [768, 'group'], [1280, 'group'], [1280, 'dm']])
  test(`reader works with no errors: ${kind} at ${width}px`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => {
      if (m.type() === 'error' && !/Failed to load resource|net::ERR|favicon|fonts\.g/i.test(m.text())) errors.push('console: ' + m.text());
    });
    page.on('dialog', (d) => d.dismiss());
    await api(port, '/focus-bank', { kind, action: 'save', text: (kind === 'dm' ? 'Brother, ' : '') + BASE });
    await api(port, '/focus-bank', { kind, action: 'manual', messages: ['*Version one* Please help today. Rs. 5,000 needed.', '*Version two* Please help today. Rs. 5,000 needed.'] });
    await page.setViewportSize({ width, height: width < 900 ? 800 : 900 });
    await page.addInitScript(([k, v]) => {
      localStorage.setItem('givelife-cloud-key', k);
      localStorage.setItem('givelife-view', v); // the group or the DM message opens in the reader
    }, [KEY, kind]);
    await page.goto('/new#/preview');
    const focus = page.locator('#messageFocus');
    await expect(focus).toBeVisible();
    await expect(focus).toHaveAttribute('data-kind', kind);
    await expect(page.locator('#focusFormatted')).not.toHaveText('');
    // versions: next, next, previous
    await page.locator('#ui2Swipe .ui2-swipe-next').click();
    await page.locator('#ui2Swipe .ui2-swipe-next').click();
    await page.locator('#ui2Swipe .ui2-swipe-prev').click();
    await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText(/of|\/|Original|Base/);
    // More opens and closes
    const more = page.locator('#messageFocus .focus-rail-more > summary');
    await more.click();
    await expect(page.locator('#messageFocus .focus-rail-more > div')).toBeVisible();
    await page.mouse.click(4, 4); // a tap outside closes it (on a phone the sheet can cover ⋯)
    await expect(page.locator('#messageFocus .focus-rail-more > div')).toBeHidden();
    // edit: type, bold, italic, heart, then Done
    await page.locator('#focusEdit').click();
    const ed = page.locator('#ui2Live');
    await expect(ed).toBeVisible();
    await ed.click();
    await page.keyboard.press('End');
    await page.keyboard.type(' typed');
    for (const name of ['Bold', 'Italic', 'Heart']) await page.locator('#ui2Float').getByRole('button', { name, exact: true }).click();
    await page.evaluate(() => {
      const d = new DataTransfer();
      d.setData('text/plain', 'pasted line');
      document.getElementById('ui2Live').dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true, cancelable: true }));
    });
    await expect.poll(() => page.locator('#focusText').inputValue()).toContain('pasted line');
    await page.locator('#focusEdit').click(); // Done
    await expect(ed).toBeHidden();
    // Save base (dialog), then the sparkle (new versions)
    await page.locator('#ui2MsgTools .ui2-base-btn').click();
    await expect(page.locator('#focusBaseDialog')).toBeVisible();
    await page.locator('#focusBaseSave').click();
    await expect(page.locator('#focusBaseDialog')).toBeHidden();
    await page.locator('#messageFocus .ui2-gen-btn').click();
    // Copy
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {});
    if (await page.locator('#focusCopy').isVisible()) await page.locator('#focusCopy').click();
    // Files button opens More at the files
    if (await page.locator('#ui2Swipe .ui2-files-btn').isVisible()) {
      await page.locator('#ui2Swipe .ui2-files-btn').click();
      await more.click();
    }
    // no sideways scroll
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });
