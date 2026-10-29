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
 await page.locator('#showMsg').click();await expect(page).toHaveURL(/#\/preview/);await page.reload();await expect(page.locator('#card')).toBeVisible();
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
test('a long assistant reply stays readable: big text, starts at its first line, scrolls instead of shrinking',async({page,request})=>{
 for(const [w,h] of [[390,844],[412,915],[1280,720],[1440,900]]){
  await open(page,request,w,h,LONG);
  if(w<900)await page.locator('#chatOpen').click();
  const log=page.locator(w<900?'#histLog':'#log');await expect(log.locator('.e.bot').last()).toContainText('Part 7');
  const measure=()=>log.evaluate(el=>{const r=[...el.querySelectorAll('.e.bot')].at(-1),a=el.getBoundingClientRect(),b=r.getBoundingClientRect();return {top:b.top>=a.top-1&&b.top<a.bottom,size:parseFloat(r.style.fontSize)}});
  await expect.poll(async()=>(await measure()).top,{timeout:5000}).toBe(true);
  expect((await measure()).size,`${w}x${h} font`).toBeGreaterThanOrEqual(12.5);
 }
});
test('DM sent stays marked, the donor stays in Important, and sending again works',async({page,request})=>{
 await open(page,request,1280,800);await page.locator('#openDonors').click();await page.locator('.donor-tabs [data-tab=important]').click();
 const rows=page.locator('.donor-row');const before=await rows.count();expect(before).toBeGreaterThan(0);
 const first=rows.first();await first.locator('.donor-dm').click();
 await expect(rows.first().locator('.donor-dm')).toContainText('DM sent');
 expect(await rows.count()).toBe(before);await expect(page.locator('.donor-tabs [data-tab=important]')).toHaveAttribute('aria-selected','true');
 await rows.first().locator('.donor-dm').click();await expect(rows.first().locator('.donor-dm')).toContainText(/×\d/);
 await page.reload();await expect(page.locator('.donor-row').first().locator('.donor-dm')).toContainText('DM sent');
});
test('bulk paste shows when every number will be sent before anything starts',async({page,request})=>{
 await open(page,request,390,844);await page.locator('[data-view-button=dm]').click();await page.locator('#sendMoreDonors').click();
 await page.locator('#pastePeople').fill('Ali 03001234567\n03011234567\n1. Sara - 0302 1234567');
 await expect(page.locator('#pastePlan li')).toHaveCount(4);
 await expect(page.locator('#pasteNext')).toHaveText('DM all 3');await expect(page.locator('#pastePlan li').nth(1)).toContainText('Donor 2');
 await page.locator('#pasteNext').click();await expect(page.locator('#pastePeople')).toBeHidden();
 await expect(page.locator('#pastePlan li').first()).toContainText('Ali');await expect(page.locator('#pastePlan li').first()).toContainText('Now');
 await expect(page.locator('#pastePlan li').nth(1)).toContainText('Donor 2');await expect(page.locator('#pastePlan li').nth(2)).toContainText('Sara');
 await expect(page.locator('#pastePlan .plan-total')).toContainText('All 3 done by about');
 const textOnScreen=await page.locator('#pastePlan').innerText();expect(textOnScreen).not.toMatch(/0300|1234567/);
 const gap2=await page.locator('#pastePlan li').nth(1).locator('.plan-when').innerText();
 await page.locator('#pasteGap').selectOption('8');await expect.poll(()=>page.locator('#pastePlan li').nth(1).locator('.plan-when').innerText()).not.toBe(gap2);
 await expect(page.locator('#pasteStart')).toBeEnabled();
 await page.locator('#pasteBack').click();await expect(page.locator('#pastePeople')).toBeVisible();
});
test('DM in bulk button sits in the Donors header and opens the bulk modal',async({page,request})=>{
 await open(page,request,1280,800);await page.locator('#openDonors').click();
 await page.locator('#donorBulk').click();await expect(page.locator('.paste-dialog')).toBeVisible();
 await page.locator('#pastePeople').fill('03001234567 03011234567 03021234567');
 await expect(page.locator('#pasteNext')).toHaveText('DM all 3');
 await expect(page.locator('#pastePlan li').nth(2)).toContainText('Donor 3');
});

test('the batch dialog explains that later rounds start by themselves',async({page,request})=>{
 await open(page,request,1280,800);await page.locator('#openDonors').click();await page.locator('#donorSendAll').click();
 await page.locator('#batchLimit').fill('1');
 const text=await page.locator('#batchAudience').innerText();
 expect(text).toMatch(/start by themselves|recipients in this batch/);
 if(/start by themselves/.test(text))await expect(page.locator('#batchRest')).toBeVisible();else await expect(page.locator('#batchRestRow')).toBeHidden();
});

test('a stopped batch offers Continue and the dialog says already-sent people are skipped',async({page,request})=>{
 await open(page,request,390,844);
 const stopped={state:'Stopped',scope:'important',sent:2,skipped:0,failed:0,total:5,resumable:3,gap_seconds:240,poster:true,error:'WhatsApp is disconnected.',receipts:[{id:'a',name:'Ali',state:'Sent',time:1700000000},{id:'b',name:'Bilal',state:'Uncertain'}],waiting:['Sara','Omar','Zain']};
 let posted=null;
 await page.route('**/donor-delivery',async r=>{if(r.request().method()==='POST'){posted=r.request().postDataJSON();return r.fulfill({json:{reply:'Continuing your stopped batch: 2 already handled are skipped, 3 left.',job:stopped}})}return r.fulfill({json:stopped})});
 await page.locator('#openDonors').click();
 await expect(page.locator('#donorContinue')).toBeVisible();await expect(page.locator('#donorContinue')).toContainText('3 left');
 await page.locator('#donorBatchSummary').click();
 await expect(page.locator('#batchSent li').first()).toContainText('Ali');await expect(page.locator('#batchNext li')).toHaveText(['Sara','Omar','Zain']);await expect(page.locator('#batchOther')).toContainText('Bilal');
 await page.locator('#donorContinue').click();await expect.poll(()=>posted).not.toBeNull();
 expect(posted.scope).toBe('important');expect(posted.fresh).toBeUndefined();expect(posted.ids).toBeUndefined();
 await page.locator('#donorSendImportant:visible, #donorMain:visible').first().isVisible();
 await page.locator('#donorSendImportant').click();
 await expect(page.locator('#batchResume')).toBeVisible();await expect(page.locator('#batchResumeText')).toContainText('already sent will be skipped');
 await expect(page.locator('#batchStart')).toHaveText('Continue DMs');
 await page.locator('#batchFresh').check();posted=null;await page.locator('#batchStart').click();
 await expect.poll(()=>posted).not.toBeNull();expect(posted.fresh).toBe(true);
});
