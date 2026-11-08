const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const { auditElements } = require('./element-audit.cjs');
const { showPreview } = require('./helpers.cjs');
const AUTH = { Authorization: 'Bearer manual-fix-preview-key' };
const click = (selector) => (page) => page.locator(selector).first().click();
const screens = [
  { name: 'main', route: '', root: '.app' },
  {
    name: 'main-menu',
    route: '',
    root: '#mainNavMore .compact-nav-panel',
    prepare: click('#mainNavMore > summary'),
  },
  { name: 'chat', route: 'chat', root: '#hist' },
  { name: 'settings', route: 'settings', root: '#set' },
  { name: 'memory', route: 'settings/memory', root: '#memoryDialog' },
  { name: 'poster', route: 'settings/poster', root: '#posterDialog' },
  { name: 'connection', route: 'whatsapp', root: '#whatsappDialog' },
  { name: 'shortcuts', route: 'keyboard', root: '#keyboardDialog' },
  { name: 'donors', route: 'donors/all', root: '#donorsPage' },
  {
    name: 'donor-menu',
    route: 'donors/all',
    root: '.donor-more[open] > div',
    prepare: click('.donor-more > summary'),
  },
  {
    name: 'donor-options',
    route: 'donors/all',
    root: '#donorNavMore .compact-nav-panel',
    prepare: click('#donorNavMore > summary'),
  },
  { name: 'donor-add', route: 'donors/all/add', root: '#donorAddDialog' },
  { name: 'donor-bulk', route: 'donors/all/bulk', root: '#donorPasteDialog' },
  { name: 'donor-batch', route: 'donors/all/pace', root: '#donorBatchPicker' },
  {
    name: 'donor-resume',
    route: 'donors/all',
    root: '#donorResumeDialog',
    prepare: async (p) => {
      const toggle = p.locator('#donorToggle');
      if (await toggle.isVisible()) await toggle.click();
      else await p.locator('#donorResumeAtInline').click();
    },
  },
  {
    name: 'donor-clock',
    route: 'donors/all',
    root: '#donorResumeDialog',
    prepare: click('#donorResumeAtInline'),
  },
  { name: 'donor-messages', route: 'donors/messages', root: '#donorsPage' },
  {
    name: 'donor-message-edit',
    route: 'donors/messages',
    root: '#donorsPage',
    prepare: async (p) =>
      p.locator('.bank-actions').getByRole('button', { name: 'Edit', exact: true }).click(),
  },
  { name: 'volunteers', route: 'donors/volunteers', root: '#donorsPage' },
  { name: 'group-preview', route: 'preview', root: '#messageFocus' },
  { name: 'group-edit', route: 'preview', root: '#messageFocus', prepare: click('#focusEdit') },
  {
    name: 'dm-preview',
    route: '',
    root: '#messageFocus',
    prepare: async (p) => {
      await p.evaluate(() => setView('dm'));
      await showPreview(p);
    },
  },
  { name: 'notes-locked', route: 'notes', root: '#foundationNotes' },
  {
    name: 'notes-editor',
    route: 'notes',
    root: '#foundationNotes',
    prepare: async (p) => {
      await p.locator('#notesPassword').fill('test-preview-only-pin');
      await p.locator('#notesUnlockButton').click();
      await expect(p.locator('#notesEditor')).toBeVisible();
    },
  },
  { name: 'research', url: '/group-finder', root: 'body' },
  {
    name: 'research-universities',
    url: '/group-finder',
    root: '#targets',
    prepare: click('#targetsOpen'),
  },
  {
    name: 'research-import',
    url: '/group-finder',
    root: '#importDialog',
    prepare: click('#importOpen'),
  },
];
const sizes =
  process.env.ELEMENT_AUDIT_SMOKE === '1'
    ? [[390, 844, 'dark']]
    : [
        [320, 568, 'light'],
        [390, 844, 'dark'],
        [768, 1024, 'light'],
        [1280, 800, 'dark'],
        [1920, 1080, 'light'],
        [740, 360, 'dark'],
        [640, 400, 'light'],
        [320, 256, 'dark'],
      ];
for (const [width, height, theme] of sizes) {
  test(`element audit ${width}x${height} ${theme}`, async ({ browser, request }, testInfo) => {
    test.setTimeout(240000);
    await request.post('/donor-delivery', { headers: AUTH, data: { stop: true } });
    const results = [];
    const context = await browser.newContext({
      viewport: { width, height },
      reducedMotion: 'reduce',
    });
    await context.addInitScript(
      ({ theme }) => {
        localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
        localStorage.setItem('givelife-theme', theme);
      },
      { theme },
    );
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    page.setDefaultNavigationTimeout(20000);
    fs.mkdirSync('test-results/element-audit', { recursive: true });
    for (const screen of screens) {
      try {
        // A fresh document closes native modal top layers from the previous state.
        await page.goto('about:blank');
        await page.goto(screen.url || (process.env.AUDIT_PATH || '') + '/#/' + screen.route, {
          waitUntil: 'domcontentloaded',
        });
        // Navigation and data loading settle before measuring a surface.
        if (screen.prepare) await screen.prepare(page);
        await expect(page.locator(screen.root)).toBeVisible({ timeout: 5000 });
        if (screen.name === 'donors')
          await expect(page.locator('.donor-row').first()).toBeVisible();
        if (screen.name === 'donor-messages')
          await expect(page.locator('.bank-preview').first()).toBeVisible();
        if (screen.name === 'volunteers') await expect(page.locator('#volName')).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        const result = await auditElements(page, screen.root);
        results.push({ screen: screen.name, ...result });
      } catch (error) {
        results.push({
          screen: screen.name,
          controls: 0,
          failures: [{ issues: ['screen-open-failed'], name: String(error.message).slice(0, 180) }],
        });
      }
      fs.writeFileSync(
        `test-results/element-audit/progress-${width}-${height}.json`,
        JSON.stringify(results),
      );
    }
    await context.close();
    fs.mkdirSync('test-results/element-audit', { recursive: true });
    const report = {
      size: { width, height, theme },
      screens: results.length,
      controls: results.reduce((n, r) => n + r.controls, 0),
      layoutElements: results.reduce((n, r) => n + (r.layoutElements || 0), 0),
      results,
    };
    const filename = `test-results/element-audit/${width}-${height}-${theme}.json`;
    fs.writeFileSync(filename, JSON.stringify(report, null, 2));
    await testInfo.attach('element-audit', { path: filename, contentType: 'application/json' });
    const failures = results.flatMap((r) =>
      (r.failures || []).map((f) => ({ screen: r.screen, ...f })),
    );
    console.log(
      JSON.stringify({
        width,
        height,
        screens: results.length,
        controls: report.controls,
        failures: failures.length,
        examples: failures.slice(0, 10),
      }),
    );
    expect(failures).toEqual([]);
  });
}
