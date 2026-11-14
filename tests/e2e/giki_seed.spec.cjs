/* /giki: the list you gave is already there the first time the page opens (no tapping), and removing someone sticks. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 532;
let server;
const seed = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'giki-seed-')), 'list.md');
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => {
  fs.writeFileSync(
    seed,
    [
      '| # | Name | Number | Found on |',
      '|--:|---|---|---|',
      '| 1 | . Giki Donor 4 | +1 555 124 0001 | x |',
      '| 2 | Ali Donor Giki | +1 555 124 0002 | x |',
      '| 3 | Sara Giki | +1 555 124 0003 | x |',
    ].join('\n'),
  );
  process.env.GIKI_SEED_FILE = seed;
  server = await startOwnServer(port);
});
test.afterAll(() => {
  server?.kill();
  delete process.env.GIKI_SEED_FILE;
});

test('the people from the file are in the list when the page opens, and a removed person stays removed', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/giki');
  await expect(page.locator('.vol-row')).toHaveCount(3);
  await expect(page.locator('.vol-name')).toContainText([
    'Ali Donor Giki',
    'Giki Donor 4',
    'Sara Giki',
  ]);
  await expect(page.locator('.vol-foot .send-donors')).toHaveText('DM all (3)');
  const first = (await api(port, '/giki/volunteers')).items[0];
  await api(port, '/giki/volunteers', { action: 'delete', id: first.id });
  await page.reload();
  await expect(page.locator('.vol-row')).toHaveCount(2); // not brought back
  expect((await api(port, '/volunteers')).items).toHaveLength(0); // the main volunteers are untouched
});
