const {test,expect}=require('@playwright/test');
async function open(page,width){
 await page.setViewportSize({width,height:850});
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await page.request.post('/__test/seed',{headers:{Authorization:'Bearer manual-fix-preview-key'},data:{reset_notes:true}});
 await page.goto('/#/donors/all/notes');
 await page.locator('#notesPassword').fill('test-preview-only-pin');await page.locator('#notesUnlockButton').click();
 await page.locator('#notesEditor').fill('Plan volunteer outreach');
}
for(const width of [1440,390,320])test(`Notes selection formatting and blue caret ${width}`,async({page})=>{
 await open(page,width);const editor=page.locator('#notesEditor'),bar=page.locator('#notesSelectionTools');
 await expect(page.locator('#notesCaret')).toBeVisible();
 expect(await page.locator('#notesCaret').evaluate(e=>getComputedStyle(e).backgroundColor)).toBe('rgb(96, 165, 250)');
 expect((await page.locator('#notesCaret').boundingBox()).width).toBeGreaterThanOrEqual(2);
 await expect(bar).not.toBeVisible();await editor.press('ControlOrMeta+A');await expect(bar).toBeVisible();
 await expect(bar.getByRole('button')).toHaveCount(2);
 await bar.getByRole('button',{name:'More formatting'}).click();await bar.getByRole('button',{name:'Bold',exact:true}).click();await expect(editor.locator('strong,b')).toContainText('Plan volunteer outreach');
 await bar.getByLabel('Selected text style').selectOption('h2');await expect(editor.locator('h2')).toContainText('Plan volunteer outreach');
 await bar.getByRole('button',{name:'More formatting'}).click();await bar.getByLabel('Selected text color').selectOption('#85b7f6');
 await expect(editor.locator('[style*=color],font')).toHaveCount(1);
 const bounds=await bar.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
 if(process.env.NOTES_SELECTION_SHOTS)await page.screenshot({path:`${process.env.NOTES_SELECTION_SHOTS}/selection-${width}.png`});
 await editor.press('ArrowRight');await expect(bar).not.toBeVisible();
 await expect(page.locator('#notesSync')).toHaveText('Saved',{timeout:10000});
 expect(await editor.innerHTML()).not.toContain('notes-caret');
});
test('selection lists, More options and outside selections are scoped to Notes',async({page})=>{
 await open(page,1440);const editor=page.locator('#notesEditor'),bar=page.locator('#notesSelectionTools');
 await editor.press('ControlOrMeta+A');await bar.getByRole('button',{name:'More formatting'}).click();await bar.getByRole('button',{name:'Bulleted list',exact:true}).click();await expect(editor.locator('ul li')).toContainText('Plan volunteer outreach');
 await bar.getByRole('button',{name:'Numbered list',exact:true}).click();await expect(editor.locator('ol li')).toContainText('Plan volunteer outreach');
 await bar.getByRole('button',{name:'More formatting'}).click();await bar.getByRole('button',{name:'Italic',exact:true}).click();await expect(editor.locator('i,em')).toContainText('Plan volunteer outreach');
 await page.evaluate(()=>{const r=document.createRange();r.selectNodeContents(document.querySelector('.notes-headline'));const s=getSelection();s.removeAllRanges();s.addRange(r)});
 await expect(bar).not.toBeVisible();
});
