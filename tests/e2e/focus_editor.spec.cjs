const {test,expect}=require('@playwright/test');
for(const width of [1440,390])test(`focused message surface preserves text and size ${width}`,async({page,request})=>{
 await page.setViewportSize({width,height:900});await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await page.goto('/#/preview');await expect(page.locator('#messageFocus')).toBeVisible();await expect(page.locator('#focusFormatted')).not.toHaveText('');
 await expect(page.locator('.brandbar')).not.toBeVisible();await expect(page.locator('#focusBack')).toBeVisible();
 const before=await page.locator('.focus-paper').boundingBox();await page.locator('#focusEdit').click();await expect(page.locator('#focusText')).toBeVisible();
 const text='*Please help this family today.*\n\nRs. 50,000 needed\n\n03097458815 Easypaisa / JazzCash Wajdan Khan';await page.locator('#focusText').fill(text);
 await page.locator('#focusText').evaluate(t=>{t.setSelectionRange(1,7)});await page.getByRole('button',{name:'I Italic',exact:true}).click();await expect(page.locator('#focusText')).toHaveValue(text.replace('Please','_Please_'));
 const after=await page.locator('.focus-paper').boundingBox();expect(after.width).toBe(before.width);expect(after.height).toBe(before.height);
 await page.locator('#focusEdit').click();await expect(page.locator('#focusState')).toContainText('Saved');await page.reload();await expect(page.locator('#focusFormatted')).toContainText('Please help');
 const saved=await (await request.get('/drafts',{headers:{Authorization:'Bearer manual-fix-preview-key'}})).json();expect(saved.group).toContain('_Please_');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await page.screenshot({path:`test-results/focus-${width}.png`});
 await page.locator('#focusBack').click();await expect(page.locator('#messageFocus')).toBeHidden();
});
