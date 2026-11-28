/* Desktop Message home (owner's final minimal pick): the menu down the left, one quiet column in the middle: the
   whole message (mini read 14px, no scroll inside it) with Rewrite and ‹ › inside it, then one line under it:
   Timer & groups · Test group · Send to GiveLife (the blue one, right end). Fake WhatsApp only: nothing is sent. */
const { test, expect } = require('@playwright/test');

const LONG =
  "<div><b>A mother has folded her hands for her little girl's life. Mirha's lungs are close to failing.</b></div>" +
  '<div><i>Mirha is just 2. Her lungs are badly affected, and one serious chest infection after another keeps hitting her. Every single breath is hard for her, and her life is at risk.</i></div>' +
  '<div><b>She needs 2 oxygen cylinders, and she needs them right away.</b></div>' +
  '<div>Rs. 18,000 LEFT</div><div><b><i>Only 9 people giving Rs. 2,000, or 1000 rs from 26 people, and her life can be helped</i></b></div>' +
  '<div><b>Easypaisa ONLY</b><br>03097458815<br><b>Wajdan Khan (GiveLife Foundation account)</b></div>';

async function open(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/new');
  await expect(page.locator('#groupPreview')).toBeVisible();
}

for (const [width, height] of [
  [900, 600],
  [1024, 600],
  [1280, 720],
  [1366, 768],
  [1920, 1080],
  [980, 2000],
])
  test(`desktop home ${width}x${height}: menu left, full message, the send line right under it`, async ({
    page,
  }) => {
    await open(page, width, height);
    await page.evaluate((m) => (document.getElementById('groupPreview').innerHTML = m), LONG);
    await page.waitForTimeout(200);
    const tabs = await page.locator('#ui2Tabs').boundingBox();
    const card = await page.locator('#card').boundingBox();
    const send = await page.locator('#btnGivelife').boundingBox();
    expect(tabs.x).toBeLessThan(20); // the menu is on the left edge
    expect(tabs.x + tabs.width).toBeLessThanOrEqual(card.x);
    expect(send.y).toBeGreaterThanOrEqual(card.y + card.height); // the send line is under the message
    expect(send.y - (card.y + card.height)).toBeLessThan(40); // right under it: a short mouse trip
    expect(Math.abs(send.x + send.width - (card.x + card.width))).toBeLessThan(3); // Send ends where the message ends
    expect(send.y + send.height).toBeLessThanOrEqual(height); // the whole message and Send are on the screen
    const r = await page.evaluate(() => {
      const chat = document.getElementById('chat');
      return {
        inner: chat.scrollHeight - chat.clientHeight,
        page: document.documentElement.scrollHeight - innerHeight,
        size: parseFloat(getComputedStyle(document.getElementById('groupPreview')).fontSize),
      };
    });
    expect(r.inner).toBeLessThanOrEqual(1); // no scroll inside the message
    expect(r.page).toBeLessThanOrEqual(1);
    expect(r.size).toBeGreaterThanOrEqual(11); // mini read: 14px, a short screen steps down, never under 11px
    expect(r.size).toBeLessThanOrEqual(16);
    // only Send to GiveLife and Test group stand out; the other groups and the Timer open under "Timer & groups"
    await expect(page.locator('#btnGivelife')).toBeVisible();
    await expect(page.locator('.group-send .test-row')).toBeVisible();
    await expect(page.locator('#btnFree')).toBeHidden();
    await page.locator('#ui2GroupPicker').click();
    await expect(page.locator('#btnFree')).toBeVisible();
    await expect(page.locator('#sendAll')).toBeVisible();
    for (const sel of ['#btnFree', '#sendAll']) {
      const b = await page.locator(sel).boundingBox();
      expect(b.height, sel).toBeGreaterThanOrEqual(40);
    }
    // the send line: one height (Apple: style, not size, marks Send), 12px apart
    const line = await Promise.all(
      ['#ui2GroupPicker', '.group-send .test-row', '#btnGivelife'].map((q) =>
        page.locator(q).boundingBox(),
      ),
    );
    expect(new Set(line.map((b) => Math.round(b.height))).size).toBe(1);
    expect(line[1].x - (line[0].x + line[0].width)).toBeGreaterThanOrEqual(11.5);
  });

test('Test group: the flask and the words sit together in the middle of the button, level with Send', async ({
  page,
}) => {
  for (const [width, height] of [
    [1280, 720],
    [1920, 1080],
  ]) {
    await open(page, width, height);
    const m = await page.evaluate(() => {
      const row = document.querySelector('.group-send .test-row');
      const word = row.querySelector('.gb-name');
      const b = row.getBoundingClientRect();
      const w = word.getBoundingClientRect();
      const send = document.getElementById('btnGivelife').getBoundingClientRect();
      const flask = parseFloat(getComputedStyle(row, '::before').width) || 16;
      return {
        left: b.x,
        right: b.x + b.width,
        wordLeft: w.x,
        wordRight: w.x + w.width,
        flask,
        sendX: send.x,
        sendW: send.width,
        boxW: b.width,
      };
    });
    // the flask (16px + 7px gap) sits right before the words, and the pair is centred in the button
    const pairLeft = m.wordLeft - 7 - m.flask;
    const pairCentre = (pairLeft + m.wordRight) / 2;
    expect(Math.abs(pairCentre - (m.left + m.right) / 2)).toBeLessThan(6);
    expect(pairLeft - m.left).toBeGreaterThan(12); // not stuck to the left edge
    expect(m.left).toBeLessThan(m.sendX); // on the same line, before Send
  }
});

test('a message line stays short enough to read fast on a wide screen', async ({ page }) => {
  await open(page, 1920, 1080);
  const card = await page.locator('#card').boundingBox();
  expect(card.width).toBeLessThanOrEqual(700);
});

for (const width of [390, 768])
  test(`phone keeps the bottom menu, tablet has it at the top (iPad) at ${width}px`, async ({
    page,
  }) => {
    await open(page, width, 844);
    const tabs = await page.locator('#ui2Tabs').boundingBox();
    if (width < 600) expect(tabs.y).toBeGreaterThan(600);
    else expect(tabs.y).toBeLessThan(150);
    // the Hide button belongs to the computer's side menu only; every tab label stays on one line
    await expect(page.locator('#ui2RailHide')).toBeHidden();
    const rows = await page.evaluate(() =>
      [...document.querySelectorAll('#ui2Tabs .ui2-tab')]
        .filter((t) => t.offsetParent)
        .map((t) => Math.round(t.getBoundingClientRect().top)),
    );
    expect(new Set(rows).size).toBe(1); // all tabs on one row
    expect(rows.length).toBeGreaterThanOrEqual(5);
  });

for (const width of [900, 980, 1280])
  test(`"Reconnect WhatsApp" does not touch Auto at ${width}px, even in a crowded bar`, async ({
    page,
  }) => {
    await open(page, width, 900);
    const r = await page.evaluate(() => {
      const wa = document.getElementById('whatsappConnection'),
        live = document.getElementById('live');
      wa.dataset.state = 'offline';
      wa.parentElement.style.maxWidth = '560px';
      const a = wa.getBoundingClientRect(),
        l = live.getBoundingClientRect();
      return { right: a.right, left: l.left, scroll: wa.scrollWidth, client: wa.clientWidth };
    });
    expect(r.right).toBeLessThanOrEqual(r.left + 1);
    expect(r.scroll).toBeLessThanOrEqual(r.client + 1);
  });

test('computer: the versions row shows each saved version (click or ← →) and comes back to the base; Send follows the version on screen', async ({
  page,
}) => {
  await open(page, 1280, 800);
  await page.evaluate(async () => {
    const post = (b) =>
      fetch('/focus-bank', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: 'group', ...b }),
      });
    const d = await (await fetch('/focus-bank?kind=group')).json();
    if (!d.revision)
      await post({ action: 'save', text: d.source || document.getElementById('group').value });
    await post({
      action: 'manual',
      messages: ['First version. Rs. 25,000 needed.', 'Second version. Rs. 25,000 needed.'],
    });
  });
  await page.reload();
  const msg = page.locator('#groupPreview');
  const row = page.locator('#ui2VerRow');
  await expect(row.locator('.ui2-vr-chip')).toHaveCount(3); // Base · 1 · 2
  await expect(page.locator('#ui2VerNav')).toBeHidden(); // no ‹ › on a computer: the row does it
  const base = await msg.textContent();
  await row.locator('.ui2-vr-chip[data-i="1"]').click();
  await expect(msg).toContainText('First version');
  await expect(row.locator('.ui2-vr-chip.is-on')).toHaveAttribute('data-i', '1');
  expect(await page.evaluate(() => window.focusShownVersion)).toContain('First version');
  await page.keyboard.press('ArrowRight');
  await expect(msg).toContainText('Second version');
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => msg.textContent()).toBe(base);
  expect(await page.evaluate(() => window.focusShownVersion)).toBe('');
  await page.keyboard.press('ArrowLeft'); // back from the base goes to the last version
  await expect(msg).toContainText('Second version');
  // the row sits right above the message
  const r = await row.boundingBox(),
    card = await page.locator('#card').boundingBox();
  expect(r.y + r.height).toBeLessThanOrEqual(card.y + 1);
});

test('the home message shows only Rewrite and ‹ ›; Rewrite opens the page with Copy, Edit and ⋯', async ({
  page,
}) => {
  await open(page, 1280, 800);
  await expect(page.locator('#copy')).toBeHidden(); // fewer buttons: the tools are one click away
  await expect(page.locator('#edit')).toBeHidden();
  await expect(page.locator('#ui2GnavMain .ui2-rewrite')).toBeVisible();
  await page.locator('#ui2GnavMain .ui2-rewrite').click();
  await expect(page.locator('#messageFocus')).toBeVisible();
  for (const sel of ['#focusCopy', '#focusEdit', '#messageFocus .focus-rail-more > summary'])
    await expect(page.locator(sel)).toBeVisible();
});

test('the menu folds with Hide and opens with Show (remembered)', async ({ page }) => {
  await open(page, 1280, 800);
  const wide = (await page.locator('#ui2Tabs').boundingBox()).width;
  await page.locator('#ui2RailHide').click();
  const narrow = (await page.locator('#ui2Tabs').boundingBox()).width;
  expect(narrow).toBeLessThan(70);
  expect(wide).toBeGreaterThan(150);
  await page.reload();
  await expect(page.locator('#ui2RailHide')).toHaveAttribute('aria-label', 'Show the menu');
  await page.locator('#ui2RailHide').click();
  expect((await page.locator('#ui2Tabs').boundingBox()).width).toBeGreaterThan(150);
});

test('Send on the home page never changes the message (the reader was never opened)', async ({
  page,
}) => {
  const posts = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && /\/(next-message|drafts)$/.test(r.url())) posts.push(r.url());
  });
  await page.route('**/send-group', (r) => r.fulfill({ json: { job_id: 'fake-job' } }));
  await open(page, 1280, 800);
  const before = await page.locator('#group').inputValue();
  await page.locator('#btnGivelife').click();
  await page.waitForTimeout(1000);
  expect(await page.locator('#group').inputValue()).toBe(before);
  expect(posts.filter((u) => u.endsWith('/next-message'))).toEqual([]);
});

test('Copy copies the version on screen; the arrows never replace text being edited', async ({
  browser,
}) => {
  const ctx = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  await open(page, 1280, 800);
  await page.evaluate(async () => {
    const post = (b) =>
      fetch('/focus-bank', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: 'group', ...b }),
      });
    const d = await (await fetch('/focus-bank?kind=group')).json();
    if (!d.revision)
      await post({ action: 'save', text: d.source || document.getElementById('group').value });
    await post({ action: 'manual', messages: ['Copy me version. Rs. 25,000 needed.'] });
  });
  await page.reload();
  await page.locator('#ui2VerRow .ui2-vr-chip[data-i="1"]').click();
  await expect(page.locator('#groupPreview')).toContainText('Copy me version');
  // Copy and Edit are off the home screen now; their keys/old links still press them, so the rules still hold
  await page.evaluate(() => document.getElementById('copy').click());
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('Copy me version');
  await page.evaluate(() => document.getElementById('edit').click()); // edits the base, not the version
  await expect(page.locator('#groupPreview')).not.toContainText('Copy me version');
  const editing = await page.locator('#groupPreview').textContent();
  await page.evaluate(() => document.getElementById('homeNext').click()); // the arrow (or key) while editing
  await page.keyboard.press('ArrowRight');
  expect(await page.locator('#groupPreview').textContent()).toBe(editing);
  await page.evaluate(() => document.getElementById('edit').click());
  await ctx.close();
});

test('phones show the same Rewrite and ‹ › inside the message', async ({ page }) => {
  await open(page, 390, 844);
  await expect(page.locator('#ui2GnavMain #ui2VerNav')).toBeVisible();
  await expect(page.locator('#ui2GnavMain .ui2-rewrite')).toBeVisible();
});
