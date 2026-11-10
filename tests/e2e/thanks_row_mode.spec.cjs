const { test, expect } = require('@playwright/test');
const { startOwnServer, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 251;
const headers = { Authorization: 'Bearer ' + KEY };
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());
for (const width of [1440, 390, 320]) {
  test(`Thanks donor checkbox routes only the clicked donor at ${width}px`, async ({
    page,
    request,
  }) => {
    const ids = [];
    for (let i = 0; i < 2; i++) {
      const data = await (
        await request.post('/donors', {
          headers,
          data: {
            action: 'add',
            name: `Row ${width} ${i}`,
            phone: '15551' + String(width).padStart(4, '0') + String(i).padStart(2, '0'),
          },
        })
      ).json();
      ids.push(data.donor.id);
      await request.post('/donors', {
        headers,
        data: { action: 'update', id: data.donor.id, donated: true },
      });
    }
    await request.post('/left', { headers, data: { left: 0 } });
    let saved = await (await request.get('/donor-thanks', { headers })).json();
    const upload = await (
      await request.post('/upload-image', {
        headers,
        data: {
          use: 'bulk',
          data:
            'data:application/pdf;base64,' + Buffer.from('%PDF-1.4 completion').toString('base64'),
        },
      })
    ).json();
    await request.post('/donor-thanks', {
      headers,
      data: {
        action: 'save',
        case_id: saved.case_id,
        revision: saved.revision,
        attachment: upload.id,
        filename: 'Proof.pdf',
        caption: 'Alhamdulillah, complete.',
        message: 'JazakAllah khair, {name}.',
      },
    });
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/donors/donated');
    const check = page.getByRole('checkbox', { name: /Thanks donor/ });
    await expect(check).not.toBeChecked();
    await check.check();
    await expect(page.locator('#donorsPage')).toHaveAttribute('data-thanks-mode', '');
    const before = (await (await request.get('/__test/events', { headers })).json()).events.length;
    const row = page.locator(`.donor-row[data-donor-id="${ids[1]}"]`);
    await row.locator('.donor-dm').click();
    await expect
      .poll(
        async () => (await (await request.get('/__test/events', { headers })).json()).events.length,
      )
      .toBe(before + 2);
    const events = (await (await request.get('/__test/events', { headers })).json()).events.slice(
      before,
    );
    expect(events[0].fields.caption).toBe('Alhamdulillah, complete.');
    expect(events[1].fields.message).toBe('JazakAllah khair, Bhai.');
    expect(events[0].fields.phone).toBe('15551' + String(width).padStart(4, '0') + '01');
    await row.locator('.donor-dm').click();
    await expect(page.locator('#thanksRowStatus')).toContainText('already sent');
    expect((await (await request.get('/__test/events', { headers })).json()).events.length).toBe(
      before + 2,
    );
    await check.uncheck();
    let normal = 0;
    await page.route('**/donor-send', async (route) => {
      normal++;
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Normal DM path verified.' }),
      });
    });
    await row.locator('.donor-dm').click();
    await expect.poll(() => normal).toBe(1);
    await expect(page.locator('#donorNotice')).toContainText('Normal DM path verified.');
    await page.getByRole('button', { name: 'Dismiss notification', exact: true }).click();
    await check.check();
    await page.locator('.donor-tabs [data-tab="all"]').click();
    await page.locator('.donor-tabs [data-tab="donated"]').click();
    await expect(check).not.toBeChecked();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    const bounds = await page.locator('.thanks-row-mode').boundingBox();
    if (width < 900) {
      const ys = await page
        .locator('.donor-bottom > :is(.donor-thanks,.ui2-msgs-bottom,#donorMainBottom)')
        .evaluateAll((es) => es.map((e) => Math.round(e.getBoundingClientRect().y)));
      expect(new Set(ys).size).toBe(1);
    }
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1);
  });
}

test('Thanks donor mode cannot turn on for an unfinished case', async ({ page, request }) => {
  await request.post('/left', { headers, data: { left: 1000 } });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/donors/donated');
  const check = page.getByRole('checkbox', { name: /Thanks donor/ });
  await check.click();
  await expect(page.locator('#thanksRowStatus')).toContainText('Finish this case');
  await expect(check).not.toBeChecked();
  await expect(page.locator('#donorsPage')).not.toHaveAttribute('data-thanks-mode');
});
