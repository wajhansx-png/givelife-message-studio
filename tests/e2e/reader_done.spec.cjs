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

test('each button works on its own: a language button is plain, Trigger strengthens the message on screen in ITS language, only when pressed', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await open(page);
  const styles = [];
  await page.route('**/message-style', async (r) => {
    const body = JSON.parse(r.request().postData());
    styles.push(body);
    const urdu = body.style.startsWith('ur');
    await r.fulfill({ json: { text: (urdu ? '*اردو ہک*' : '*English hook*') + '\n\n_Written by the scripted writer._\n\nRs. 5,000 LEFT' } });
  });
  const trigger = page.locator('.focus-styles [data-trigger]');
  const lang = (l) => page.locator(`.focus-styles [data-lang="${l}"]`);
  await lang('en').click();
  await expect.poll(() => styles.length).toBe(1);
  expect(styles[0].style).toBe('en'); // plain
  await trigger.click(); // the English on screen, stronger
  await expect.poll(() => styles.length).toBe(2);
  expect(styles[1].style).toBe('en_more');
  expect(styles[1].current).toContain('English hook'); // written from the message that was on screen
  await expect(trigger).toHaveAttribute('aria-pressed', 'false'); // not a mode: it does not stay on
  await lang('ur').click(); // Urdu + English afterwards is plain again
  await expect.poll(() => styles.length).toBe(3);
  expect(styles[2].style).toBe('ur_en');
  await trigger.click(); // the Urdu + English on screen, stronger
  await expect.poll(() => styles.length).toBe(4);
  expect(styles[3].style).toBe('ur_en_more');
  await lang('en').click();
  await expect.poll(() => styles.length).toBe(5);
  expect(styles[4].style).toBe('en'); // nothing stayed triggered
  // pasted message + Done, then Trigger: written from the pasted message, in its language (it has an Urdu first line)
  await page.locator('#focusEdit').click();
  await paste(page, PASTED);
  await page.locator('#focusEdit').click();
  await expect(page.locator('#ui2RewriteRow')).toBeVisible();
  await trigger.click();
  await expect.poll(() => styles.length).toBe(6);
  expect(styles[5].style).toBe('ur_en_more');
  expect(styles[5].current).toBe(PASTED);
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

test('Done with the keyboard closing: a long message is not left tiny (it measures again for the full screen)', async ({ page }) => {
  const LONG = Array.from({ length: 9 }, (_, i) => `Line ${i + 1}: Mirha is only 2 years old and her lungs are almost failing. Please help today.`).join('\n\n') + '\n\n*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation';
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: LONG });
  await open(page);
  const size = () => page.locator('#focusFormatted').evaluate((e) => parseFloat(getComputedStyle(e).fontSize));
  const before = await size();
  await page.locator('#focusEdit').click();
  await page.setViewportSize({ width: 390, height: 470 }); // the keyboard opens
  await page.waitForTimeout(300);
  await page.locator('#focusEdit').click(); // Done (the keyboard is still up for a moment)
  await page.setViewportSize({ width: 390, height: 844 }); // and goes away
  await expect.poll(size, { timeout: 4000 }).toBeCloseTo(before, 0); // the same size as before editing, not 9.5px
});

test('a failed write says why on screen, and the button being used says Writing…', async ({ page }) => {
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await open(page);
  let release;
  const gate = new Promise((r) => (release = r));
  await page.route('**/message-style', async (r) => {
    await gate;
    await r.fulfill({ status: 503, json: { error: 'AI is not connected, so nothing was written. Your message is unchanged.' } });
  });
  const ur = page.locator('.focus-styles [data-lang="ur"]');
  await ur.click();
  const after = await ur.evaluate((e) => getComputedStyle(e, '::after').content + '|' + getComputedStyle(e, '::after').position);
  expect(after).toBe('"Writing…"|static'); // a label inside the button, never a blank box
  release();
  const note = page.locator('#ui2Note');
  await expect(note).toBeVisible(); // the status line is hidden on a phone: this note is how the owner knows
  await expect(note).toContainText('AI is not connected');
  await expect(page.locator('#focusFormatted')).toContainText('Base wording'); // the message was left alone
});

test('a message a button wrote never replaces the saved base by itself: Back, a swipe and Test keep the base; Save base keeps the new one', async ({ page }) => {
  const MINE = '*My own message for Mirha.*\n\n_She is 2 and her lungs are failing. Please help her today._\n\n🔴 Rs. 11,000 LEFT\n\n*JAZZCASH ONLY*\n03097458815\n*Wajdan Khan (GiveLife Foundation account)*';
  const WROTE = '*Your kindness is already helping Mirha breathe.*\n\n_Written by the scripted writer._\n\nRs. 11,000 LEFT';
  await page.route('**/message-style', (r) => r.fulfill({ json: { text: WROTE } }));
  for (const leave of ['back', 'swipe', 'test']) {
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: MINE });
    await open(page);
    await page.locator('.focus-styles [data-lang="en"]').click();
    await expect(page.locator('#focusFormatted')).toContainText('Your kindness');
    if (leave === 'back') await page.locator('#focusBack').click();
    if (leave === 'swipe') await page.locator('#ui2Swipe .ui2-swipe-next').click();
    if (leave === 'test') {
      await page.locator('#focusTest').click();
      await expect(page.locator('#ui2Note')).toContainText('not saved yet');
    }
    await page.waitForTimeout(800);
    expect(await saved(), leave).toBe(MINE); // the owner's own message is still the base
  }
  // the owner chooses to keep it: Save base
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: MINE });
  await open(page);
  await page.locator('.focus-styles [data-lang="en"]').click();
  await expect(page.locator('#focusFormatted')).toContainText('Your kindness');
  await page.locator('#ui2MsgTools .ui2-base-btn').click();
  await page.locator('#focusBaseSave').click();
  await expect.poll(saved).toBe(WROTE);
});

for (const [width, height] of [
  [320, 568],
  [1024, 600],
  [1280, 720],
])
  test(`a very long message at ${width}x${height}: readable (11px or more), and Generate / Test / Back stay on screen`, async ({ page }) => {
    const LONG = Array.from({ length: 12 }, (_, i) => `Line ${i + 1}: Mirha is only 2 years old and takes fewer than 20 breaths every minute. Her lungs are almost failing.`).join('\n\n') + '\n\n*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation';
    await api(port, '/focus-bank', { kind: 'group', action: 'save', text: LONG });
    await open(page, width, height);
    await page.waitForTimeout(500);
    for (const editing of [false, true]) {
      if (editing) await page.locator('#focusEdit').click();
      const m = await page.evaluate(() => ({
        fs: parseFloat(getComputedStyle(document.getElementById('focusFormatted')).fontSize),
        bottoms: ['.ui2-gen-btn', '#focusTest', '#focusBack'].map((s) => document.querySelector(s).getBoundingClientRect().bottom),
        h: innerHeight,
      }));
      if (!editing) expect(m.fs).toBeGreaterThanOrEqual(11);
      for (const b of m.bottoms) expect(b, editing ? 'editing' : 'reading').toBeLessThanOrEqual(m.h + 1);
    }
  });

test('a late answer never replaces a message the owner changed meanwhile; a new text says "New · not saved" and ‹ › goes back to the saved one', async ({ page }) => {
  const MINE = '*My own message for Mirha.*\n\n_She is 2 and her lungs are failing. Please help her today._\n\n🔴 Rs. 11,000 LEFT\n\n*JAZZCASH ONLY*\n03097458815\n*Wajdan Khan (GiveLife Foundation account)*';
  await api(port, '/focus-bank', { kind: 'group', action: 'save', text: BASE });
  await open(page);
  let release;
  const gate = new Promise((r) => (release = r));
  await page.route('**/message-style', async (r) => {
    await gate; // the AI is slow
    await r.fulfill({ json: { text: '*Mirha cannot wait.*\n\n_Written by the scripted writer._\n\nRs. 11,000 LEFT' } });
  });
  await page.locator('.focus-styles [data-lang="en"]').click();
  // meanwhile the owner pastes and saves his own message
  await page.locator('#focusEdit').click();
  await paste(page, MINE);
  await page.locator('#focusEdit').click();
  await expect.poll(saved).toBe(MINE);
  release(); // the old answer arrives late
  await expect(page.locator('#ui2Note')).toContainText('not used');
  await page.waitForTimeout(500);
  expect(await page.locator('#focusText').inputValue()).toBe(MINE); // still his message on screen
  expect(await saved()).toBe(MINE);
  // a new text that IS shown says so, and ‹ goes back to the saved message
  await page.unroute('**/message-style');
  await page.route('**/message-style', (r) => r.fulfill({ json: { text: '*New wording.*\n\n_Written by the scripted writer._\n\nRs. 11,000 LEFT' } }));
  await page.locator('.focus-styles [data-lang="en"]').click();
  await expect(page.locator('#focusFormatted')).toContainText('New wording');
  await expect(page.locator('#ui2Swipe .ui2-ver')).toHaveText('New · not saved');
  await page.locator('#ui2Swipe .ui2-swipe-prev').click();
  await expect(page.locator('#focusFormatted')).toContainText('My own message');
  expect(await saved()).toBe(MINE);
});
