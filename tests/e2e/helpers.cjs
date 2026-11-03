/* Shared navigation helpers. Settings and Preview live inside the "More" menu and the DM composer has no
   navbar tab any more (it is reached with the D key or the "dm" chat command). */
async function reveal(page,selector){
 const control=page.locator(selector);
 if(!await control.isVisible())await page.locator('#mainNavMore > summary').click();
 return control;
}
async function openSettings(page){await (await reveal(page,'#gear')).click()}
async function openPreview(page){await (await reveal(page,'#desktopPreview')).click()}
async function openMessages(page){
 const tab=page.locator('#donorMessagesTab');
 if(!await tab.isVisible())await page.locator('#donorNavMore > summary').click();
 await tab.click();
}
async function showDm(page){await page.evaluate(()=>setView('dm'))}
module.exports={reveal,openSettings,openPreview,openMessages,showDm};
