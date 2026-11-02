const {test,expect}=require('@playwright/test');
for(const width of [1440,390])test(`preview actions visible and connected ${width}`,async({page})=>{
 await page.setViewportSize({width,height:900});await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await page.goto('/#/preview');
 for(const id of ['previewChangePoster','edit','fresh','copy'])await expect(page.locator('#'+id)).toBeVisible();
 await page.locator('#previewChangePoster').click();await expect(page.locator('#posterDialog')).toBeVisible();await page.locator('#posterClose').click();
 await page.locator('#edit').click();await expect(page.locator('#groupPreview')).toHaveAttribute('contenteditable','true');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

