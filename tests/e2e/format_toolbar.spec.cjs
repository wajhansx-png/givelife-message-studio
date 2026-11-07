const { test, expect } = require('@playwright/test');
const { showPreview, showDm } = require('./helpers.cjs');

/* Selecting text in the Group or DM editor opens a tiny Bold / Italic toolbar right under the selection.
   Fake WhatsApp only: nothing is ever sent. */
const KEY = { Authorization: 'Bearer manual-fix-preview-key' };
async function openEditor(page, kind) {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/');
  if (kind === 'dm') await showDm(page);
  await showPreview(page);
  await page.locator('#focusEdit').click();
  await expect(page.locator('#focusText')).toBeVisible();
}
const rectOfSelection = (page) =>
  page.evaluate(() => {
    const t = document.getElementById('focusText'),
      probe = document.createElement('div'),
      cs = getComputedStyle(t);
    for (const p of ['font', 'padding', 'border', 'width', 'lineHeight', 'letterSpacing'])
      probe.style[p] = cs[p];
    probe.style.cssText +=
      ';position:fixed;visibility:hidden;white-space:pre-wrap;overflow-wrap:break-word';
    probe.textContent = t.value.slice(0, t.selectionEnd);
    const span = document.createElement('span');
    span.textContent = '.';
    probe.append(span);
    document.body.append(probe);
    const box = t.getBoundingClientRect(),
      m = probe.getBoundingClientRect(),
      s = span.getBoundingClientRect(),
      out = { bottom: box.top + (s.bottom - m.top) - t.scrollTop };
    probe.remove();
    return out;
  });

for (const kind of ['group', 'dm'])
  for (const width of [1440, 390])
    test(`${kind} editor: selecting text shows Bold/Italic under it ${width}`, async ({
      page,
      request,
    }) => {
      await page.setViewportSize({ width, height: 800 });
      await openEditor(page, kind);
      const text = 'Please help this family today.\n\nRs. 50,000 needed urgently';
      await page.locator('#focusText').fill(text);
      const bar = page.locator('#waMarkBar');
      await expect(bar).toBeHidden();

      // Select the word "family" by double-click, like a real user.
      await page.locator('#focusText').evaluate((t) => {
        const i = t.value.indexOf('family');
        t.focus();
        t.setSelectionRange(i, i + 6);
      });
      await expect(bar).toBeVisible();
      const box = await bar.boundingBox();
      const sel = await rectOfSelection(page);
      expect(box.y).toBeGreaterThanOrEqual(sel.bottom - 2); // under the selection, never over the text
      expect(box.y - sel.bottom).toBeLessThan(40); // and close to it
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      for (const b of await bar.locator('button').all()) {
        const r = await b.boundingBox();
        expect(r.height).toBeGreaterThanOrEqual(34);
        expect(r.width).toBeGreaterThanOrEqual(40);
      }

      // Bold, then the same button again removes it.
      await bar.getByRole('button', { name: 'Bold selected text' }).click();
      await expect(page.locator('#focusText')).toHaveValue(text.replace('family', '*family*'));
      await expect(bar).toBeVisible(); // selection kept, so a second style can follow
      await bar.getByRole('button', { name: 'Italic selected text' }).click();
      await expect(page.locator('#focusText')).toHaveValue(text.replace('family', '_*family*_'));
      await bar.getByRole('button', { name: 'Italic selected text' }).click();
      await bar.getByRole('button', { name: 'Bold selected text' }).click();
      await expect(page.locator('#focusText')).toHaveValue(text);

      // Undo restores the text (the browser's own history is kept).
      await bar.getByRole('button', { name: 'Bold selected text' }).click();
      await page.locator('#focusText').press('Control+z');
      await expect(page.locator('#focusText')).toHaveValue(text);

      // Collapsing the selection hides it.
      await page.locator('#focusText').evaluate((t) => t.setSelectionRange(3, 3));
      await expect(bar).toBeHidden();

      // The styled text is what gets saved and shown.
      await page.locator('#focusText').evaluate((t) => {
        const i = t.value.indexOf('urgently');
        t.setSelectionRange(i, i + 8);
      });
      await bar.getByRole('button', { name: 'Bold selected text' }).click();
      await page.locator('#focusEdit').click();
      await expect(page.locator('#focusState')).toContainText('Saved');
      await expect(page.locator('#focusFormatted strong')).toHaveText('urgently');
      const saved = await (await request.get('/drafts', { headers: KEY })).json();
      expect(saved[kind]).toContain('*urgently*');
      // Escape hides an open toolbar.
      await page.locator('#focusEdit').click();
      await page.locator('#focusText').evaluate((t) => {
        t.focus();
        t.setSelectionRange(0, 6);
      });
      await expect(bar).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(bar).toBeHidden();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBe(true);
    });

test('toolbar stays on screen at the bottom edge and with the phone keyboard area', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 520 });
  await openEditor(page, 'group');
  await page
    .locator('#focusText')
    .fill(Array.from({ length: 30 }, (_, i) => 'Line ' + i + ' word').join('\n'));
  await page.locator('#focusText').evaluate((t) => {
    t.scrollTop = t.scrollHeight;
    const i = t.value.lastIndexOf('word');
    t.focus();
    t.setSelectionRange(i, i + 4);
  });
  const bar = page.locator('#waMarkBar');
  await expect(bar).toBeVisible();
  const box = await bar.boundingBox();
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(520);
});

test('Ctrl+B and Ctrl+I style the selection while the toolbar is open', async ({ page }) => {
  await openEditor(page, 'group');
  await page.locator('#focusText').fill('Help Yousuf now');
  await page.locator('#focusText').evaluate((t) => t.setSelectionRange(5, 11));
  await expect(page.locator('#waMarkBar')).toBeVisible();
  await page.keyboard.press('Control+b');
  await expect(page.locator('#focusText')).toHaveValue('Help *Yousuf* now');
});

test('the toolbar never opens outside the message editors', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.goto('/');
  await page.locator('#cmd').fill('some words in the chat box');
  await page.locator('#cmd').evaluate((t) => t.setSelectionRange(0, 4));
  await page.waitForTimeout(200);
  await expect(page.locator('#waMarkBar')).toBeHidden();
});

for (const width of [1440, 390])
  test(`modal base-message dialog: the toolbar is clickable inside it ${width}`, async ({
    page,
  }) => {
    const { openDonorMessages } = require('./helpers.cjs');
    await page.setViewportSize({ width, height: 800 });
    await page.addInitScript(() =>
      localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
    );
    await page.goto('/#/donors/all');
    await openDonorMessages(page);
    await page.getByRole('button', { name: 'Base message', exact: true }).click();
    const area = page.locator('#baseMessageText');
    await expect(area).toBeVisible();
    await area.fill('Brother, please help this family today.');
    await area.evaluate((t) => {
      const i = t.value.indexOf('help');
      t.focus();
      t.setSelectionRange(i, i + 4);
    });
    const bar = page.locator('#waMarkBar');
    await expect(bar).toBeVisible();
    await bar.getByRole('button', { name: 'Italic selected text' }).click();
    await expect(area).toHaveValue('Brother, please _help_ this family today.');
    // The older button row in the dialog uses the same logic.
    await page.locator('#baseMessageDialog [data-mark="*"]').click();
    await expect(area).toHaveValue('Brother, please *_help_* this family today.');
  });
