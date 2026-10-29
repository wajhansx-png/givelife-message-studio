const {test,expect}=require('@playwright/test');
const auth={Authorization:'Bearer manual-fix-preview-key'};
const LONG=Array.from({length:7},(_,i)=>`Part ${i+1}: this is what is actually in place right now. Schedules: #f2c3c664 pending at 10:00 AM PKT to resume GiveLife main. Groups: GiveLife Foundation every 45 minutes. Balance: Rs. 15,000 left.`).join('\n\n');
async function open(page,request,width,height,reply){
 await page.setViewportSize({width,height});
 await page.addInitScript(()=>{localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');localStorage.setItem('givelife-theme','dark')});
 await request.post('/__test/seed',{headers:auth,data:{reply:reply||'Ready.'}});
 await page.goto('/');await expect(page.locator('#leftChip')).toContainText('25,000');
}
test('a refresh stays on the same Donors tab, and on Messages',async({page,request})=>{
 await open(page,request,1280,800);
 await page.locator('#openDonors').click();await page.locator('.donor-tabs [data-tab=important]').click();
 await page.reload();await expect(page.locator('#donorsPage')).toBeVisible();await expect(page.locator('.donor-tabs [data-tab=important]')).toHaveAttribute('aria-selected','true');
 expect(page.url()).toContain('#/donors/important');
 await page.locator('[data-tab=messages]').click();await page.getByRole('button',{name:'Message 3',exact:true}).click();
 await page.reload();await expect(page.locator('#donorMessages')).toBeVisible();await expect(page.locator('.bank-detail header')).toContainText('Message 3');
});
test('Back and Forward move between screens smoothly and never leave the app',async({page,request})=>{
 await open(page,request,390,844);
 await page.locator('#openDonors').click();await expect(page.locator('#donorsPage')).toBeVisible();
 await page.locator('.donor-tabs [data-tab=donated]').click();
 await page.goBack();await expect(page.locator('#donorsPage')).not.toBeVisible();expect(page.url()).not.toContain('donors');
 await page.goForward();await expect(page.locator('#donorsPage')).toBeVisible();
 await page.locator('#donorMainBottom').click();await expect(page.locator('#donorsPage')).not.toBeVisible();
 await page.locator('#chatOpen').click();await expect(page.locator('#hist')).toBeVisible();await page.reload();await expect(page.locator('#hist')).toBeVisible();
 await page.locator('#histMain').click();await expect(page.locator('#hist')).not.toBeVisible();
 await page.locator('#gear').click();await expect(page.locator('#set')).toBeVisible();await page.reload();await expect(page.locator('#set')).toBeVisible();
 await page.locator('#setCloseBottom').click();await expect(page.locator('#set')).not.toBeVisible();
 await page.locator('#showMsg').click();await page.reload();await expect(page.locator('#card')).toBeVisible();
 await page.locator('#previewBackBottom').click();await expect(page.locator('#card')).not.toBeVisible();
});
test('phone: a small Chat button and a wide Donors button share the thumb row',async({page,request})=>{
 await open(page,request,390,844);
 const chat=await page.locator('#chatOpen').boundingBox(),donors=await page.locator('#openDonors').boundingBox();
 expect(Math.abs(chat.y-donors.y)).toBeLessThan(4);expect(chat.x).toBeLessThan(donors.x);expect(chat.width).toBeLessThan(donors.width);
 expect(donors.y+donors.height).toBeGreaterThan(844*0.6);
});
test('phone: every full screen has a Back button in the lower half',async({page,request})=>{
 await open(page,request,390,844);
 await page.locator('#openDonors').click();expect((await page.locator('#donorMainBottom').boundingBox()).y).toBeGreaterThan(422);
 await page.locator('[data-tab=messages]').click();expect((await page.locator('.bank-back-bottom').boundingBox()).y).toBeGreaterThan(422);
 await page.locator('.bank-back-bottom').click();await page.locator('#donorMainBottom').click();
 await page.locator('#gear').click();expect((await page.locator('#setCloseBottom').boundingBox()).y).toBeGreaterThan(422);await page.locator('#setCloseBottom').click();
 await page.locator('#chatOpen').click();expect((await page.locator('#histMain').boundingBox()).y).toBeGreaterThan(422);
});
test('a long assistant reply fits one screen with no scrolling inside it',async({page,request})=>{
 for(const [w,h] of [[390,844],[412,915],[1280,720],[1440,900]]){
  await open(page,request,w,h,LONG);
  if(w<900)await page.locator('#chatOpen').click();
  const log=page.locator(w<900?'#histLog':'#log');await expect(log.locator('.e.bot').last()).toContainText('Part 7');
  const fit=await log.evaluate(el=>{const r=[...el.querySelectorAll('.e.bot')].at(-1),a=el.getBoundingClientRect(),b=r.getBoundingClientRect();return {inside:b.top>=a.top-1&&b.bottom<=a.bottom+1,own:r.scrollHeight<=r.clientHeight+1,size:parseFloat(r.style.fontSize)}});
  expect(fit.inside,`${w}x${h} reply fully visible`).toBe(true);expect(fit.own).toBe(true);expect(fit.size).toBeGreaterThanOrEqual(10);
 }
});
test('DM sent stays marked, the donor stays in Important, and sending again works',async({page,request})=>{
 await open(page,request,1280,800);await page.locator('#openDonors').click();await page.locator('.donor-tabs [data-tab=important]').click();
 const rows=page.locator('.donor-row');const before=await rows.count();expect(before).toBeGreaterThan(0);
 const first=rows.first();await first.locator('.donor-dm').click();
 await expect(rows.first().locator('.donor-dm')).toContainText('DM sent');
 expect(await rows.count()).toBe(before);await expect(page.locator('.donor-tabs [data-tab=important]')).toHaveAttribute('aria-selected','true');
 await rows.first().locator('.donor-dm').click();await expect(rows.first().locator('.donor-dm')).toContainText('×2');
 await page.reload();await expect(page.locator('.donor-row').first().locator('.donor-dm')).toContainText('DM sent');
});
test('bulk paste shows when every number will be sent before anything starts',async({page,request})=>{
 await open(page,request,390,844);await page.locator('[data-view-button=dm]').click();await page.locator('#sendMoreDonors').click();
 await page.locator('#pastePeople').fill('Ali 03001234567\n03011234567\n1. Sara - 0302 1234567');
 await expect(page.locator('#pastePlan li')).toHaveCount(4);
 await expect(page.locator('#pastePlan li').first()).toContainText('Ali');await expect(page.locator('#pastePlan li').first()).toContainText('Now');
 await expect(page.locator('#pastePlan li').nth(1)).toContainText('Donor 2');await expect(page.locator('#pastePlan li').nth(2)).toContainText('Sara');
 await expect(page.locator('#pastePlan .plan-total')).toContainText('All 3 done by about');
 const textOnScreen=await page.locator('#pastePlan').innerText();expect(textOnScreen).not.toMatch(/0300|1234567/);
 const gap2=await page.locator('#pastePlan li').nth(1).locator('.plan-when').innerText();
 await page.locator('#pasteGap').selectOption('8');await expect.poll(()=>page.locator('#pastePlan li').nth(1).locator('.plan-when').innerText()).not.toBe(gap2);
 await expect(page.locator('#pasteStart')).toBeEnabled();
});
