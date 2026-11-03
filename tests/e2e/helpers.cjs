/* Shared by the e2e specs. Secondary actions live in compact "More" menus, so each helper opens the menu
   only when the control it needs is not already on screen. */
async function openSettings(page){
 const gear=page.locator('#gear');
 if(!(await gear.isVisible())){await page.locator('#mainNavMore > summary').click()}
 await gear.click();
}
async function showPreview(page){
 const preview=page.locator('#desktopPreview');
 if(!(await preview.isVisible())){await page.locator('#mainNavMore > summary').click()}
 await preview.click();
}
async function openDonorMessages(page){
 const tab=page.locator('#donorMessagesTab');
 if(!(await tab.isVisible())){await page.locator('#donorNavMore > summary').click()}
 await tab.click();
}
module.exports={openSettings,showPreview,openDonorMessages};
