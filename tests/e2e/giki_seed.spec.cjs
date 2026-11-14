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

for (const [width, height] of [
  [320, 640],
  [412, 890],
  [768, 900],
  [1280, 800],
]) {
  test(`a long list scrolls in its own box and the share message row stays under it at ${width}px`, async ({
    page,
  }) => {
    const lines = Array.from(
      { length: 40 },
      (_, i) => `Person ${i + 1} | +1 555 125 ${String(1000 + i)}`,
    );
    await api(port, '/giki/volunteers', {
      action: 'import',
      text: lines.map((l) => '| ' + l + ' | x |').join('\n'),
    });
    await page.setViewportSize({ width, height });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/giki');
    await expect(page.locator('.vol-row').first()).toBeVisible();
    const total = (await api(port, '/giki/volunteers')).items.length;
    await expect(page.locator('.vol-list-label')).toHaveText('People · ' + total);
    const box = () =>
      page.evaluate(() => {
        const l = document.querySelector('.vol-list').getBoundingClientRect(),
          m = document.querySelector('.vol-msg').getBoundingClientRect(),
          list = document.querySelector('.vol-list');
        return {
          listBottom: Math.round(l.bottom),
          msgTop: Math.round(m.top),
          msgBottom: Math.round(m.bottom),
          msgWidth: Math.round(m.width),
          scrollable: list.scrollHeight > list.clientHeight,
          page: document.documentElement.scrollHeight - innerHeight,
        };
      });
    let b = await box();
    expect(b.scrollable).toBe(true);
    expect(b.msgTop).toBeGreaterThanOrEqual(b.listBottom - 1); // the row never covers a name
    expect(b.msgBottom).toBeLessThanOrEqual(height);
    expect(b.page).toBe(0);
    await page.locator('.vol-list').evaluate((l) => (l.scrollTop = l.scrollHeight));
    await expect(page.locator('.vol-row').last()).toBeInViewport(); // the last name can be reached
    expect(await page.locator('.vol-name').last().textContent()).toContain(String(total) + '.');
    b = await box();
    await expect(page.locator('.giki-share')).toBeInViewport(); // and the message row is still there
    expect(b.msgTop).toBeGreaterThanOrEqual(b.listBottom - 1);
  });
}

for (const width of [320, 360, 390, 412, 768, 1280]) {
  test(`every name is shown in full on one line and the buttons line up at ${width}px`, async ({
    page,
  }) => {
    const long = [
      'warfansameekhan Giki 500 Donor',
      'Mubashar Giki Donor Younas',
      'Aymen Fatima Volunteer Giki',
      'Farhan Ali Giki Best Volunt',
      'Ba-cha 😎 Giki Volunteer',
    ];
    await api(port, '/giki/volunteers', {
      action: 'import',
      text: long.map((n, i) => `| ${i + 1} | ${n} | +1 555 127 ${1000 + i} | x |`).join('\n'),
    });
    await page.setViewportSize({ width, height: 800 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/giki');
    await expect(page.locator('.vol-row').first()).toBeVisible();
    const r = await page.evaluate(() => {
      const rows = [...document.querySelectorAll('.vol-row')];
      const listRight = document.querySelector('.vol-list').getBoundingClientRect().right;
      const cut = rows
        .map((row) => row.querySelector('.vol-name'))
        .filter(
          (n) =>
            n.scrollWidth > n.clientWidth + 1 || n.getBoundingClientRect().right > listRight + 1,
        )
        .map((n) => n.textContent);
      const x = (sel) =>
        new Set(rows.map((row) => Math.round(row.querySelector(sel).getBoundingClientRect().left)))
          .size;
      let overlap = 0;
      rows.forEach((row, i) => {
        const b = row.getBoundingClientRect();
        for (const el of row.querySelectorAll('.vol-name, .vol-case, .vol-share, .vol-manage')) {
          const e = el.getBoundingClientRect();
          if (e.top < b.top - 1 || e.bottom > b.bottom + 1) overlap++;
        }
        if (i && rows[i - 1].getBoundingClientRect().bottom > b.top + 1) overlap++;
      });
      const oneLine = rows.every(
        (row) => row.querySelector('.vol-name').getBoundingClientRect().height < 30,
      );
      const share = document.querySelectorAll('.vol-share').length;
      return { cut, cols: [x('.vol-case'), x('.vol-manage')], overlap, oneLine, share };
    });
    expect(r.cut).toEqual([]); // no name is cut
    expect(r.cols).toEqual([1, 1]); // the buttons sit in the same columns on every row
    expect(r.share).toBe(0); // no DM Share button: DM Case sends the share message too
    expect(r.overlap).toBe(0); // nothing overlaps the next row
    expect(r.oneLine).toBe(true);
  });
}
