/* Shared by the e2e specs. Secondary actions live in compact "More" menus, so each helper opens the menu
   only when the control it needs is not already on screen. */
async function reveal(page, selector) {
  const control = page.locator(selector);
  if (!(await control.isVisible())) await page.locator('#mainNavMore > summary').click();
  return control;
}
async function openSettings(page) {
  await (await reveal(page, '#gear')).click();
}
async function showPreview(page) {
  await (await reveal(page, '#desktopPreview')).click();
}
async function openDonorMessages(page) {
  const tab = page.locator('#donorMessagesTab');
  if (!(await tab.isVisible())) await page.locator('#donorNavMore > summary').click();
  await tab.click();
}
/* The DM composer has no navbar tab; it is reached with the D key or the "dm" chat command. */
async function showDm(page) {
  await page.evaluate(() => setView('dm'));
}
module.exports = { reveal, openSettings, showPreview, openDonorMessages, showDm };
