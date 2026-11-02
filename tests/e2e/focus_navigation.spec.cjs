const {test,expect}=require('@playwright/test');
for(const width of [1440,390])test(`navbar preview opens focused editor without refresh ${width}`,async({page})=>{
 await page.setViewportSize({width,height:900});await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));await page.goto('/');
 await page.locator('#mainNavMore summary').click();await page.locator('#desktopPreview').click();
 await expect(page.locator('#messageFocus')).toBeVisible();await expect(page.locator('#focusFormatted')).not.toHaveText('');await expect(page.locator('.brandbar')).not.toBeVisible();
 await page.locator('#focusBack').click();await expect(page.locator('#messageFocus')).toBeHidden();
 await page.locator('#mainNavMore summary').click();await page.locator('#desktopPreview').click();await expect(page.locator('#messageFocus')).toBeVisible();
 await page.goBack();await expect(page.locator('#messageFocus')).toBeHidden();await page.goForward();await expect(page.locator('#messageFocus')).toBeVisible();
});
