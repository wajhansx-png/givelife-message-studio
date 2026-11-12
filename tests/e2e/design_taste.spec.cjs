const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
/* Design taste from the owner's PDF: words not icons, no shadow under buttons, taps about 40px+, 15px message text,
   Tools/More as a bottom sheet. Fake WhatsApp only. */
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 437;
let server;
test.use({ baseURL: 'http://127.0.0.1:' + port, reducedMotion: 'no-preference' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
const audit = (page, scope) =>
  page.evaluate((scope) => {
    const out = [];
    const vis = (e) => {
      const r = e.getBoundingClientRect();
      const c = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && c.visibility !== 'hidden' && c.display !== 'none';
    };
    for (const b of document.querySelectorAll(scope + ' button, ' + scope + ' summary')) {
      if (!vis(b)) continue;
      const r = b.getBoundingClientRect(),
        c = getComputedStyle(b),
        t = b.textContent.trim();
      const id = (b.id ? '#' + b.id : '') + '"' + t.slice(0, 22) + '"';
      // owner-approved exceptions: the small settings icon on each row and the − / + steppers
      if (b.matches('.cr-gear, .cr-step')) {
        if (!b.getAttribute('aria-label')) out.push('NO-LABEL ' + id);
        if (r.height < 38.5 || r.width < 38.5) out.push('SHORT ' + id);
        continue;
      }
      if (!/[A-Za-z]{2}/.test(t)) out.push('ICON ' + id);
      if (c.boxShadow !== 'none' && !/^rgba\([^)]*\) 0px 0px 0px 1px inset$/.test(c.boxShadow))
        out.push('SHADOW ' + id + ' ' + c.boxShadow.slice(0, 40));
      if (r.height < 38.5) out.push('SHORT ' + id + ' h=' + (r.height | 0));
      if (r.height > 56 && b.closest('.cr-bar, .cr-row-actions, #csFoot'))
        out.push('TWO-LINE ' + id + ' h=' + (r.height | 0));
      if (/[✎⋯×▾⌕☰→]/.test(t)) out.push('SYMBOL ' + id);
    }
    for (const e of document.querySelectorAll(
      scope + ' .cr-quote, ' + scope + ' textarea, ' + scope + ' .cr-draft',
    ))
      if (vis(e) && parseFloat(getComputedStyle(e).fontSize) < 15)
        out.push('SMALL-MSG ' + e.className + ' ' + getComputedStyle(e).fontSize);
    return out;
  }, scope);
for (const [w, h] of [
  [320, 568],
  [390, 844],
  [1280, 800],
])
  test(
    'design taste holds on the Case page, its sheets and the main screen at ' + w + 'px',
    async ({ page }) => {
      await page.setViewportSize({ width: w, height: h });
      await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
      await page.goto('/new#/case');
      await expect(page.locator('.cr-row')).toHaveCount(5);
      expect(await audit(page, '#casePage')).toEqual([]);
      await page.locator('#crTools').click();
      await page.waitForTimeout(300);
      const box = await page
        .locator('#caseSheet')
        .boundingBox()
        .catch(() => null);
      expect(await audit(page, '#caseSheet')).toEqual([]);
      if (w < 900) expect(box.y + box.height).toBeGreaterThan(h - 2); // a bottom sheet, not a menu dropping from the top
      await page.evaluate(() => document.getElementById('caseSheet').close());
      for (const [name, open] of [
        ['start', '#crStart'],
        ['prepare', '#crPrepare'],
        ['row', '.cr-row[data-key="top"] .cr-name b'],
      ]) {
        await page.locator(open).click();
        await page.waitForTimeout(500);
        expect(await audit(page, '#caseSheet'), name).toEqual([]);
        await page.evaluate(() => document.getElementById('caseSheet').close());
      }
      await page.goto('/new#/');
      await page.waitForTimeout(1500);
      expect(await audit(page, 'body')).toEqual([]);
    },
  );
