const { test, expect } = require('@playwright/test');
const { auditElements } = require('./element-audit.cjs');
const fs = require('node:fs');
test.use({ reducedMotion: 'reduce' });
test.describe.configure({ mode: 'parallel' });
const routes = [
  ['home', '', '.app'],
  ['preview', 'preview', '#messageFocus'],
  ['chat', 'chat', '#hist'],
  ['notes', 'notes', '#foundationNotes'],
  ['settings', 'settings', '#set'],
  ['memory', 'settings/memory', '#memoryDialog'],
  ['poster', 'settings/poster', '#posterDialog'],
  ['keyboard', 'keyboard', '#keyboardDialog'],
  ['connection', 'whatsapp', '#whatsappDialog'],
  ...['all', 'important', 'top', 'donated', 'not_contacted', 'volunteers', 'messages'].map((t) => [
    t,
    'donors/' + t,
    '#donorsPage',
  ]),
  ...['add', 'bulk', 'pace'].map((t, i) => [
    t,
    'donors/all/' + t,
    ['#donorAddDialog', '#donorPasteDialog', '#donorBatchPicker'][i],
  ]),
];
const states = [
  ...routes,
  ['notes-locked', 'notes', '#foundationNotes'],
  ['group-choice', '', '#dropFree', '.ui2-choose-btn'],
  ['group-timing', '', '#ui2LaterPanel', '#ui2Later'],
  ['speed-advanced', 'donors/all/pace', '#donorBatchPicker', '#ui2SpeedMore > summary'],
  [
    'manual-messages',
    'preview',
    '#manualMessages',
    async (p) => {
      await p.locator('.focus-rail-more > summary').click();
      await p.locator('#focusManual').click();
    },
  ],
  [
    'save-base',
    'preview',
    '#focusBaseDialog',
    async (p) => {
      await p.locator('.focus-rail-more > summary').click();
      await p.locator('#focusSave').click();
    },
  ],
  [
    'resume-groups',
    '',
    '.resume-groups-dialog',
    (p) => p.locator('.resume-open').evaluate((e) => e.click()),
  ],
  ['home-more', '', '#ui2Sheet', (p) => p.locator('#ui2Tabs [data-tab=more]').click()],
  ['message-more', 'preview', '.focus-rail-more[open] > div', '.focus-rail-more > summary'],
  ['editor', 'preview', '#messageFocus', '#focusEdit'],

  ['donor-more', 'donors/all', '#donorNavMore .compact-nav-panel', '#donorNavMore > summary'],
  ['row-more', 'donors/all', '.donor-more[open] > div', '.donor-more > summary'],
  [
    'donor-search',
    'donors/all',
    '.donor-toolbar',
    async (p) => {
      if (await p.locator('#ui2DonorSearch').isVisible())
        await p.locator('#ui2DonorSearch').click();
    },
  ],
  [
    'follow-up',
    'donors/messages',
    '#donorsPage',
    (p) => p.getByRole('tab', { name: 'Follow-up', exact: true }).click(),
  ],
  [
    'message-edit',
    'donors/messages',
    '#donorsPage',
    (p) => p.locator('.bank-actions').getByRole('button', { name: 'Edit', exact: true }).click(),
  ],
  ['message-menu', 'donors/messages', '#ui2BankMore > div', '#ui2BankMore > summary'],
  [
    'writer',
    'donors/messages',
    '#caseWriterDialog',
    (p) => p.getByRole('button', { name: 'Write Case', exact: true }).click(),
  ],
  ['report', '', '.report-dialog', (p) => p.locator('.report-open').evaluate((e) => e.click())],
  [
    'reply',
    '',
    '.replies-dialog',
    async (p) => {
      await p.locator('.reply-open').evaluate((e) => e.click());
      await p.locator('#repList textarea').first().waitFor({ state: 'visible' });
      await expect(p.locator('#repNote')).not.toHaveText('');
    },
  ],
  ['research', '/new/group-finder', 'body'],
  ['research-import', '/new/group-finder', '#importDialog', '#importOpen'],
  ['research-universities', '/new/group-finder', '#targets', '#targetsOpen'],
];

for (const [w, h] of [
  [280, 480],
  [320, 480],
  [390, 844],
  [430, 932],
  [568, 320],
  [667, 375],
  [768, 1024],
  [899, 700],
  [900, 700],
  [1024, 768],
  [1280, 800],
  [1440, 900],
  [1920, 1080],
]) {
  test('all controls ' + w + 'x' + h, async ({ page: p }, info) => {
    test.setTimeout(90000);
    await p.setViewportSize({ width: w, height: h });
    await p.addInitScript(() => {
      if (location.protocol !== 'http:') return;
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key');
      localStorage.setItem('givelife-theme', 'dark');
    });
    p.setDefaultTimeout(5000);
    const results = [];
    for (const [name, route, root, prepare] of states) {
      let errors = [];
      const handler = (e) => errors.push(e.message);
      p.on('pageerror', handler);
      try {
        await p.goto('about:blank');
        await p.goto(route.startsWith('/') ? route : '/new' + (route ? '#/' + route : ''));
        if (route.startsWith('donors/'))
          await p.locator('#donorsPage').waitFor({ state: 'visible' });
        if (name === 'notes') {
          await p.locator('#notesPassword:visible,#notesEditor:visible').first().waitFor();
          if (await p.locator('#notesPassword').isVisible()) {
            await p.locator('#notesPassword').fill('test-preview-only-pin');
            await p.locator('#notesUnlockButton').click();
          }
          await p.locator('#notesEditor').waitFor({ state: 'visible' });
        }
        if (name === 'notes-locked') {
          if (await p.locator('#notesLock').isVisible())
            await p.locator('#notesLock').click();
          await p.locator('#notesPassword').waitFor({ state: 'visible' });
        }
        if (prepare) {
          if (typeof prepare === 'function') await prepare(p);
          else await p.locator(prepare).first().click();
        }
        await p.locator(root).waitFor({ state: 'visible' });
        await p.evaluate(() => document.fonts.ready);
        const r = await auditElements(p, root);
        results.push({ name, errors, ...r });
      } catch (e) {
        results.push({ name, error: e.message });
      }
      p.off('pageerror', handler);
    }
    fs.writeFileSync(info.outputPath('controls.json'), JSON.stringify(results, null, 2));
    await info.attach('controls', {
      path: info.outputPath('controls.json'),
      contentType: 'application/json',
    });
    expect(results.filter((r) => r.error || r.errors?.length || r.failures?.length)).toEqual([]);
  });
}
