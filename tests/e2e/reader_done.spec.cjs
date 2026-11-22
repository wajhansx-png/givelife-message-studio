/* Message page, editing: a clear Done button; Done keeps the text exactly as pasted; after Done the language /
   Trigger buttons start fresh and work as normal; Generate makes the message on the screen the base first.
   Private fake server, scripted writer, no real AI or WhatsApp. */
const { test, expect } = require('@playwright/test');
const { startOwnServer, api, KEY } = require('./own_server.cjs');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011) + 761;
let server;
test.use({ baseURL: `http://127.0.0.1:${port}` });
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => (server = await startOwnServer(port)));
test.afterAll(() => server?.kill());

const PASTED =
  '*میرہ کی سانسیں اب بھی خطرے میں ہیں*\n\n_Mirha is only 2 years old. Her lungs are almost failing._\n\n\nنبی کریم ﷺ نے فرمایا: "جو شخص"\n(2699 صحیح مسلم)\n\n🔴 Rs. 11,000 LEFT\n  \n*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation';
const BASE = '*Base wording* of the case. Please help today. Rs. 5,000 needed.';

async function open(page, width = 390, height = 844) {
  await page.setViewportSize({ width, height });
  await page.addInitScript((k) => localStorage.setItem('givelife-cloud-key', k), KEY);
  await page.goto('/new#/preview');
  await expect(page.locator('#focusFormatted')).toContainText(/\S/);
}
const paste = (page, text, html) =>
  page.evaluate(
    ([t, h]) => {
      const ed = document.getElementById('ui2Live');
      ed.focus();
      const r = document.createRange();
      r.selectNodeContents(ed);
      const s = getSelection();
      s.removeAllRanges();
      s.addRange(r);
      const dt = new DataTransfer();
      if (t) dt.setData('text/plain', t);
      if (h) dt.setData('text/html', h);
      ed.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    },
    [text, html],
  );
const saved = async () => (await api(port, '/focus-bank?kind=group')).source;

for (const [width, height] of [
  [320, 640],
  [390, 844],
  [820, 1180],
  [1280, 720],
])
  test(`editing at ${width}px: one clear Done button with its word, big, not covered`, async ({ page }) => {
    await open(page, width, height);
    await page.locator('#focusEdit').click();
    const done = page.locator('#focusEdit');
    await expect(done).toHaveText('Done');
    const m = await done.evaluate((e) => {
      const r = e.getBoundingClientRect(),
        c = getComputedStyle(e);
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return { w: r.width, h: r.height, fs: parseFloat(c.fontSize), right: r.right, bottom: r.bottom, hit: e === hit || e.contains(hit) };
    });
    expect(m.fs).toBeGreaterThanOrEqual(15); // the word shows (it is not an icon only)
    expect(m.h).toBeGreaterThanOrEqual(42);
    expect(m.w).toBeGreaterThanOrEqual(100);
    expect(m.right).toBeLessThanOrEqual(width + 0.5);
    expect(m.bottom).toBeLessThanOrEqual(height);
    expect(m.hit).toBe(true);
    await expect(page.locator('#ui2Float [data-done]')).toHaveCount(0); // one Done, not two
    await done.click();
    await expect(done).toHaveText('Edit');
  });

test('Done keeps the text exactly as pasted (blank lines, stars, Urdu, emoji) and saves it as the base', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await open(page);
  await page.locator('#focusEdit').click();
  await paste(page, PASTED);
  expect(await page.locator('#focusText').inputValue()).toBe(PASTED);
  await page.locator('#focusEdit').click();
  await expect.poll(saved).toBe(PASTED);
  expect(await page.locator('#focusText').inputValue()).toBe(PASTED);
  // and after a reload the same text is what the page shows
  await page.reload();
  await expect(page.locator('#focusFormatted')).toContainText('Mirha is only 2 years old');
  expect(await page.locator('#focusText').inputValue()).toBe(PASTED);
});

test('a paste that only has HTML still goes in, one line per block', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await open(page);
  await page.locator('#focusEdit').click();
  await paste(page, '', '<p>First line</p><p>Second line<br>third line</p>');
  const v = await page.locator('#focusText').inputValue();
  expect(v.replace(/\n+/g, '|')).toBe('First line|Second line|third line');
  await page.locator('#focusEdit').click();
});

test('after Done the Trigger button works as normal on the pasted message (it does not turn itself off)', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await open(page);
  const styles = [];
  await page.route('**/message-style', async (r) => {
    styles.push(JSON.parse(r.request().postData()));
    await r.fulfill({ json: { text: '*Stronger hook*\n\n_Written by the scripted writer._\n\nRs. 5,000 LEFT' } });
  });
  const trigger = page.locator('.focus-styles [data-trigger]');
  await trigger.click(); // Trigger is now ON
  await expect(trigger).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#focusEdit').click();
  await paste(page, PASTED); // the owner pastes his own message
  await page.locator('#focusEdit').click(); // Done
  await expect(trigger).toHaveAttribute('aria-pressed', 'false'); // fresh: nothing left over from before
  await expect(page.locator('#ui2RewriteRow')).toBeVisible();
  await trigger.click();
  await expect.poll(() => styles.length).toBe(2);
  expect(styles[1].style).toBe('ur_en_more'); // a real Trigger (the pasted text has Urdu), not the plain one
  expect(styles[1].current).toBe(PASTED); // written from the pasted message
  await expect(trigger).toHaveAttribute('aria-pressed', 'true');
});

test('Generate makes the message on the screen the base first: pasted, or a version showing', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await api(port, '/focus-bank', {
    kind: 'group',
    action: 'manual',
    messages: ['*Second wording* of the case. Please help today. Rs. 5,000 needed.', '*Third wording* of the case. Please help today. Rs. 5,000 needed.'],
  });
  await open(page);
  const calls = [];
  await page.route('**/focus-bank', async (r) => {
    if (r.request().method() === 'POST') calls.push(JSON.parse(r.request().postData()));
    await r.continue();
  });
  // 1) a version is showing (‹ ›): Generate makes it the base, then writes from it
  await page.locator('#ui2Swipe .ui2-swipe-next').click();
  await expect(page.locator('#focusFormatted')).toContainText('Second wording');
  await page.locator('.ui2-gen-btn').click();
  await expect.poll(() => calls.map((c) => c.action).join()).toContain('save,regenerate');
  const save1 = calls.find((c) => c.action === 'save');
  expect(save1.text).toContain('Second wording');
  await expect.poll(saved).toContain('Second wording');
  // 2) the owner pastes a message, presses Done, then Generate: the pasted message is the base
  calls.length = 0;
  await expect(page.locator('.ui2-gen-btn')).toBeEnabled({ timeout: 30000 });
  await page.locator('#focusEdit').click();
  await paste(page, PASTED);
  await page.locator('#focusEdit').click();
  await expect.poll(saved).toBe(PASTED);
  await page.locator('.ui2-gen-btn').click();
  await expect.poll(() => calls.filter((c) => c.action === 'regenerate').length).toBe(1);
  expect(await saved()).toBe(PASTED); // still the base: the new versions came from it
});
