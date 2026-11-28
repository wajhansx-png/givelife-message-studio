/* Pasting into the reader's editor keeps the text exactly as pasted: it never turns bold (or italic) because the
   caret sat in an old bold line. Fake WhatsApp only. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 653;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

const START = '*Bold first line*\n\n_Italic second line_\n\nPlain third line';
const PASTE = 'Pasted first line\n\nPasted *real bold* and plain\nlast line';

async function paste(page, text) {
  await page.evaluate((t) => {
    const ed = document.getElementById('ui2Live');
    const data = new DataTransfer();
    data.setData('text/plain', t);
    ed.dispatchEvent(
      new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }),
    );
  }, text);
}

for (const width of [390, 1280])
  test(`paste after select all + delete stays exactly as pasted at ${width}px`, async ({
    page,
  }) => {
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: START });
    await page.setViewportSize({ width, height: width < 900 ? 800 : 900 });
    await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
    await page.goto('/new#/preview');
    await page.locator('#focusEdit').click();
    const ed = page.locator('#ui2Live');
    await expect(ed).toBeVisible();
    await ed.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.press('Delete');
    await paste(page, PASTE);
    await expect.poll(() => page.locator('#focusText').inputValue()).toBe(PASTE);
  });

test('paste in the middle of a bold word does not inherit the bold, and replaces a selection', async ({
  page,
}) => {
  await api(port, '/focus-bank', {
    kind: 'group',
    action: 'save',
    text: '*Bold line here*\nplain',
  });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await page.locator('#focusEdit').click();
  const ed = page.locator('#ui2Live');
  await expect(ed).toBeVisible();
  // caret inside the bold word "line"
  await page.evaluate(() => {
    const b = document.querySelector('#ui2Live b');
    const t = b.firstChild;
    const r = document.createRange();
    r.setStart(t, 4);
    r.collapse(true);
    const s = getSelection();
    s.removeAllRanges();
    s.addRange(r);
  });
  await paste(page, 'XX');
  await expect
    .poll(() => page.locator('#focusText').inputValue())
    .toBe('*Bold*XX *line here*\nplain');
});
