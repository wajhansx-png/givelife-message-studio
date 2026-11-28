const { test, expect } = require('@playwright/test');

async function unlock(page, width, height = 850) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.request.post('/__test/seed', {
    headers: { Authorization: 'Bearer manual-fix-preview-key' },
    data: { reset_notes: true },
  });
  await page.goto('/new#/donors/all/notes');
  await page.locator('#notesPassword').fill('test-preview-only-pin');
  await page.locator('#notesUnlockButton').click();
  await expect(page.locator('#notesEditor')).toBeVisible();
}

test('Enter starts the next paragraph in the default colour; earlier colour is kept', async ({
  page,
}) => {
  await unlock(page, 1280, 800);
  const editor = page.locator('#notesEditor');
  await editor.evaluate((e) => {
    e.innerHTML = '<p><font color="#f4a4ad">Red line</font></p>';
    const r = document.createRange();
    r.selectNodeContents(e.querySelector('font'));
    r.collapse(false);
    const s = getSelection();
    s.removeAllRanges();
    s.addRange(r);
    e.focus();
  });
  await page.keyboard.press('Enter');
  await page.keyboard.type('plain');
  const html = await editor.innerHTML();
  expect(html).toContain('<font color="#f4a4ad">Red line</font>');
  expect(html).toMatch(/<p>plain<\/p>/);
  expect(html).not.toMatch(/<font[^>]*>plain/);
});
