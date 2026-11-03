const {test,expect}=require('@playwright/test');
const {openSettings,openDonorMessages}=require('./helpers.cjs');
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
 await openDonorMessages(page);await page.getByRole('button',{name:'Message 3',exact:true}).click();
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
 await openSettings(page);await expect(page.locator('#set')).toBeVisible();await page.reload();await expect(page.locator('#set')).toBeVisible();
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
 await openDonorMessages(page);expect((await page.locator('.bank-back-bottom').boundingBox()).y).toBeGreaterThan(422);
 await page.locator('.bank-back-bottom').click();await page.locator('#donorMainBottom').click();
 await openSettings(page);expect((await page.locator('#setCloseBottom').boundingBox()).y).toBeGreaterThan(422);await page.locator('#setCloseBottom').click();
 await page.locator('#chatOpen').click();expect((await page.locator('#histMain').boundingBox()).y).toBeGreaterThan(422);
});
test('a long assistant reply stays readable: big text, starts at its first line, scrolls instead of shrinking',async({page,request})=>{
 for(const [w,h] of [[390,844],[412,915],[1280,720],[1440,900]]){
  /* each size starts like a first visit: scroll positions remembered from the previous size would not apply */
  await page.evaluate(()=>{try{sessionStorage.clear()}catch(e){}}).catch(()=>{});
  await open(page,request,w,h,LONG);
  if(w<900)await page.locator('#chatOpen').click();
  const log=page.locator(w<900?'#histLog':'#log');await expect(log.locator('.e.bot').last()).toContainText('Part 7');
  const measure=()=>log.evaluate(el=>{const r=[...el.querySelectorAll('.e.bot')].at(-1),a=el.getBoundingClientRect(),b=r.getBoundingClientRect();return {top:b.top>=a.top-1&&b.top<a.bottom,size:parseFloat(r.style.fontSize)}});
  await expect.poll(async()=>(await measure()).top,{timeout:5000,message:`${w}x${h} first line of the reply must be visible`}).toBe(true);
  expect((await measure()).size,`${w}x${h} font`).toBeGreaterThanOrEqual(12.5);
 }
});
test('a contacted donor is hidden from Important, can be shown, and still shows DM sent at the bottom',async({page,request})=>{
 await open(page,request,1280,800);await page.locator('#openDonors').click();await page.locator('.donor-tabs [data-tab=important]').click();
 const rows=page.locator('.donor-row');const before=await rows.count();expect(before).toBeGreaterThan(1);
 const firstId=await rows.first().getAttribute('data-donor-id');const secondId=await rows.nth(1).getAttribute('data-donor-id');
 await expect(page.locator('#donorHideRow')).toBeHidden();
 await rows.first().locator('.donor-dm').click();
 await expect(rows).toHaveCount(before-1);await expect(rows.first()).toHaveAttribute('data-donor-id',secondId);
 await expect(page.locator('#donorHideSent')).toContainText('1 contacted hidden');
 await page.locator('#donorHideSent').click();await expect(rows).toHaveCount(before);
 const sent=page.locator(`.donor-row[data-donor-id="${firstId}"]`);await expect(sent.locator('.donor-dm')).toContainText('DM sent');await expect(rows.last()).toHaveAttribute('data-donor-id',firstId);
 await expect(page.locator('.donor-tabs [data-tab=important]')).toHaveAttribute('aria-selected','true');
 await sent.locator('.donor-dm').click();await expect(sent.locator('.donor-dm')).toContainText(/×\d/);
 await page.reload();await expect(page.locator('#donorHideSent')).toContainText('Showing contacted');
 await page.locator('#donorHideSent').click();await expect(page.locator(`.donor-row[data-donor-id="${firstId}"]`)).toHaveCount(0);
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

test('the batch dialog plans batches of 20, pauses, per-batch pauses and random gaps',async({page,request})=>{
 await open(page,request,390,844);await page.locator('#openDonors').click();await page.locator('#donorSendAll').click();
 await expect(page.locator('#batchCount')).toHaveValue(/\d+/);await page.locator('#batchCount').fill('100');
 await expect(page.locator('#batchPlan')).toContainText('100 people · 5 batches of up to 20');
 await page.locator('#batchPause').selectOption('custom');await expect(page.locator('#batchPauseCustom')).toBeVisible();await page.locator('#batchPauseCustom').fill('45');
 await expect(page.locator('#batchPlan')).toContainText('5 batches');
 await page.locator('.batch-more summary').click();await page.locator('#batchEach').fill('20, 30, 60');
 await expect(page.locator('#batchRandomRow')).toBeHidden();await page.locator('#batchRandom').check();await expect(page.locator('#batchJMin')).toBeVisible();
 await page.locator('#batchEach').fill('0');await expect(page.locator('#batchPlan')).toContainText('Check the pause');
 const box=await page.locator('.batch-dialog').boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(391);
});
test('starting sends one confirmed request with batches, pauses and random gap',async({page,request})=>{
 await open(page,request,390,844);let posted=null;
 await page.route('**/donor-delivery',async r=>{if(r.request().method()==='POST'){posted=r.request().postDataJSON();return r.fulfill({json:{reply:'Started.',job:{state:'Starting'}}})}return r.fulfill({json:{state:'Idle',sent:0,skipped:0,failed:0,total:0}})});
 await page.locator('#openDonors').click();await page.locator('#donorSendAll').click();
 await page.locator('#batchCount').fill('45');await page.locator('#batchGap').fill('3');await page.locator('#batchPause').selectOption('30');
 await page.locator('.batch-more summary').click();await page.locator('#batchEach').fill('20, 40');await page.locator('#batchRandom').check();await page.locator('#batchJMin').fill('5');await page.locator('#batchJMax').fill('12');
 await page.locator('#batchStart').click();await expect.poll(()=>posted).not.toBeNull();
 expect(posted).toMatchObject({scope:'all',chunk:20,limit:45,gap_seconds:180,rests:[1200,2400],jitter:{min:-5,max:12},skip_contacted:true});
 expect(typeof posted.request_id).toBe('string');expect(posted.ids).toBeUndefined();
});

test('a stopped batch offers Continue and the dialog says already-sent people are skipped',async({page,request})=>{
 await open(page,request,390,844);
 const stopped={state:'Stopped',scope:'important',sent:2,skipped:0,failed:0,total:5,resumable:3,gap_seconds:240,poster:true,error:'WhatsApp is disconnected.',receipts:[{id:'a',name:'Ali',state:'Sent',time:1700000000},{id:'b',name:'Bilal',state:'Uncertain'}],waiting:['Sara','Omar','Zain']};
 let posted=null;
 await page.route('**/donor-delivery',async r=>{if(r.request().method()==='POST'){posted=r.request().postDataJSON();return r.fulfill({json:{reply:'Continuing your stopped batch: 2 already handled are skipped, 3 left.',job:stopped}})}return r.fulfill({json:stopped})});
 await page.locator('#openDonors').click();
 await expect(page.locator('#donorContinue')).toBeVisible();await expect(page.locator('#donorContinue')).toContainText('3 left');
 await page.locator('#donorProgress span').click();
 await expect(page.locator('#batchSent li').first()).toContainText('Ali');await expect(page.locator('#batchNext li')).toHaveText(['Sara','Omar','Zain']);await expect(page.locator('#batchOther')).toContainText('Bilal');
 await page.locator('#donorContinue').click();await expect.poll(()=>posted).not.toBeNull();
 expect(posted.scope).toBe('important');expect(posted.fresh).toBeUndefined();expect(posted.ids).toBeUndefined();
 await page.locator('#donorSendImportant:visible, #donorMain:visible').first().isVisible();
 await page.locator('#donorSendImportant').click();
 await expect(page.locator('#batchResume')).toBeVisible();await expect(page.locator('#batchResumeText')).toContainText('already sent will be skipped');
 await expect(page.locator('#batchStart')).toHaveText('Continue');
 await page.locator('#batchFresh').check();posted=null;await page.locator('#batchStart').click();
 await expect.poll(()=>posted).not.toBeNull();expect(posted.fresh).toBe(true);
});

test('the three dots menu has a usual-donation field that saves and shows under the name',async({page,request})=>{
 await open(page,request,1280,800);await page.locator('#openDonors').click();
 const row=page.locator('.donor-row').first();const id=await row.getAttribute('data-donor-id');
 await expect(row.locator('input.donor-normal')).toBeHidden();
 await row.locator('.donor-more summary').click();
 const field=row.locator('.donor-normal-box input');await expect(field).toBeVisible();await field.fill('500');await row.locator('.donor-normal-save').click();
 await expect(page.locator(`.donor-row[data-donor-id="${id}"] .donor-normal-tag`)).toContainText('Rs. 500');
 await expect.poll(async()=>{const r=await request.get('/donors?tab=all',{headers:auth});return (await r.json()).items.find(d=>d.id===id).normal_amount}).toBe(500);
 await page.locator(`.donor-row[data-donor-id="${id}"] .donor-more summary`).click();
 await page.locator(`.donor-row[data-donor-id="${id}"] .donor-normal-box input`).fill('');await page.locator(`.donor-row[data-donor-id="${id}"] .donor-normal-save`).click();
 await expect(page.locator(`.donor-row[data-donor-id="${id}"] .donor-normal-tag`)).toHaveCount(0);
});
test('on desktop the Back button sits in the middle of the screen, and the groups box is close to the chat',async({page,request})=>{
 await open(page,request,1440,900);
 const rail=await page.locator('.action-rail').boundingBox();const app=await page.locator('.app').boundingBox();
 expect(rail.x+rail.width).toBeLessThanOrEqual(1440-60);expect(rail.x).toBeGreaterThan(1440/2);
 await page.locator('#openDonors').click();
 const back=await page.locator('#donorMainBottom').boundingBox();expect(Math.abs(back.x+back.width/2-720)).toBeLessThan(260);
 const dm=await page.locator('.donor-row .donor-dm').first().boundingBox();expect(Math.abs(dm.x+dm.width/2-720)).toBeLessThan(160);
 await page.locator('#donorMainBottom').click();await expect(page.locator('#donorsPage')).toBeHidden();
 await page.locator('.gear').first().click();const dock=await page.locator('#setCloseBottom').boundingBox();expect(Math.abs(dock.x+dock.width/2-720)).toBeLessThan(40);
});

test('desktop preview: message centred with left-aligned text, actions at the bottom, shortcuts in the groups box',async({page,request})=>{
 await open(page,request,1440,900);
 await page.locator('#railPreview').click();await expect(page.locator('#card')).toBeVisible();
 const card=await page.locator('#card').boundingBox();const msg=await page.locator('#groupPreview').boundingBox();
 expect(Math.abs((msg.x+msg.width/2)-(card.x+card.width/2))).toBeLessThan(30);
 expect(await page.locator('#groupPreview').evaluate(el=>getComputedStyle(el).textAlign)).toMatch(/left|start/);
 const tools=await page.locator('#card .tools').boundingBox();expect(tools.y).toBeGreaterThan(msg.y+msg.height-1);
 const edit=await page.locator('#edit').boundingBox();expect(Math.abs((edit.x+edit.width/2)-(card.x+card.width/2))).toBeLessThan(160);
 await page.locator('#railDonors').click();await expect(page.locator('#donorsPage')).toBeVisible();
});

test('donor list is numbered, progress is one slim line, and tabs have a visible fill',async({page,request})=>{
 await open(page,request,1440,800);
 await page.route('**/donor-delivery',r=>r.request().method()==='POST'?r.continue():r.fulfill({json:{state:'Waiting',scope:'important',sent:1,skipped:0,failed:0,total:10,pending:9,gap_seconds:240,receipts:[],waiting:[],next_at:Date.now()/1000+60}}));
 await page.locator('#openDonors').click();
 const names=await page.locator('.donor-row .donor-name').evaluateAll(els=>els.slice(0,3).map(e=>getComputedStyle(e,'::before').content));
 expect(names.every(c=>c.includes('counter(donor)'))).toBe(true);
 await expect(page.locator('#donorProgress span')).toContainText('1 sent · 9 pending · 0 failed');
 await expect(page.locator('#donorBatchList')).toBeHidden();
 const h=(await page.locator('#donorProgress').boundingBox()).height;expect(h).toBeLessThan(50);
 const bg=await page.locator('.donor-tabs button[aria-selected=false]').first().evaluate(e=>getComputedStyle(e).backgroundColor);expect(bg).not.toBe('rgba(0, 0, 0, 0)');
 await expect(page.locator('#donorMain')).toBeHidden();
});

test('the poster dialog and the chat clip accept an MP4 video as well as a picture',async({page,request})=>{
 await open(page,request,1280,800);
 expect(await page.locator('#file').getAttribute('accept')).toContain('video/mp4');
 await page.locator('#openDonors').click();await page.locator('#donorMain, #donorMainBottom').first().isVisible().catch(()=>{});
 await page.evaluate(()=>document.getElementById('posterDialog')?.querySelector('input[type=file]')?.getAttribute('accept'));
 expect(await page.evaluate(()=>document.getElementById('posterFile').accept)).toContain('video/mp4');
});

test('on a very wide screen the groups box stays close to the centre of the screen',async({page,request})=>{
 await open(page,request,1920,1000);
 const rail=await page.locator('.action-rail').boundingBox();
 expect(rail.x).toBeLessThan(960+300);expect(rail.x+rail.width).toBeLessThan(960+620);
});

test('tapping a donor name stars it, every screen has one "Back" and it is the last button next to the main action',async({page,request})=>{
 await open(page,request,1440,800);await page.locator('#openDonors').click();
 const row=page.locator('.donor-row').nth(5),star=row.locator('.donor-star');const before=await star.getAttribute('aria-pressed');
 await row.locator('.donor-name').click();await expect(star).not.toHaveAttribute('aria-pressed',before);
 await expect(page.locator('#donorMainBottom')).toHaveText('← Back');
 const last=await page.locator('.donor-bottom').evaluate(el=>[...el.children].filter(n=>n.offsetParent).sort((a,b)=>a.getBoundingClientRect().x-b.getBoundingClientRect().x).at(-1).id);expect(last).toBe('donorMainBottom');
 await openDonorMessages(page);await expect(page.locator('.bank-back-bottom')).toHaveText('← Back');await expect(page.locator('.donor-sub')).toHaveCount(0);
});

test('Volunteers tab: all five tabs fit on one line, add by name and number, save the message and DM one volunteer',async({page,request})=>{
 for(const [w,h] of [[1440,800],[390,844],[320,568]]){
  await open(page,request,w,h);await page.locator('#openDonors').click();
  const tops=await page.locator('.donor-tabs button').evaluateAll(els=>[...new Set(els.map(e=>Math.round(e.getBoundingClientRect().top)))]);expect(tops.length,`${w}px: tabs on one line`).toBe(1);
  await page.locator('[data-tab=volunteers]').click();await expect(page.locator('#donorVolunteers')).toBeVisible();
  await expect(page.locator('.donor-bottom')).toBeHidden();
  await page.locator('#volName').fill('Test Volunteer '+w);await page.locator('#volPhone').fill('0300'+String(1000000+w).slice(0,7));await page.locator('#donorVolunteers .vol-add .primary').click();
  await expect(page.locator('.vol-row',{hasText:'Test Volunteer '+w})).toHaveCount(1);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);expect(overflow,`${w}px: no sideways scroll`).toBe(false);
  page.once('dialog',d=>d.accept());
  const row=page.locator('.vol-row',{hasText:'Test Volunteer '+w});
  await row.locator('.donor-more summary').click();await row.getByRole('button',{name:'Remove'}).click();
 }
});

test('team over WhatsApp: tasks in the screen, a natural first message, his reply shows up to check, verified',async({page,request})=>{
 const auth={Authorization:'Bearer manual-fix-preview-key'};
 const post=(data)=>request.post('/__test/seed',{headers:auth,data});
 const events=async()=>(await (await request.get('/__test/events',{headers:auth})).json()).events.filter(e=>e.path==='/send/message');
 await open(page,request,1440,800);
 await page.locator('#openTeam').click();await expect(page.locator('.team-setup')).toBeVisible();
 await page.locator('.team-setup input[name=team_name]').fill('Bilal Ahmed');await page.locator('.team-setup input[name=team_phone]').fill('03001234567');await page.locator('.team-setup .primary').click();
 await expect(page.locator('.team-big')).toContainText('No tasks yet');
 await page.getByRole('button',{name:'+ Add tasks'}).click();
 await page.locator('#teamText').fill("1) Post in the 3 groups\n2) Update the sheet\nDeadline in 4 hours");await page.getByRole('button',{name:'Plan the tasks'}).click();
 await expect(page.locator('.team-page').getByText('Nothing is sent until you press Start')).toBeVisible();
 await page.getByRole('button',{name:'Start tasks'}).click();await expect(page.locator('.team-big')).toContainText('0 of 2 done');
 const before=(await events()).length;await page.waitForTimeout(1500);await post({team_tick:true});await post({team_tick:true});
 const sent=(await events()).slice(before);expect(sent.length,'the first message goes once, even after two ticks').toBe(1);
 expect(sent[0].fields.phone).toBe('923001234567');expect(sent[0].fields.message).toContain('Post in the 3 groups');expect(sent[0].fields.message).not.toMatch(/Task #|Reply "|bot/i);expect(sent[0].fields.message).toMatch(/^Assalam o alaikum Bilal,/);
 await post({incoming:'posted in the groups, done https://example.com/p',team_tick:true});
 await expect(page.locator('.team-review')).toContainText('Post in the 3 groups',{timeout:12000});await expect(page.locator('.team-review')).toContainText('Proof');
 await page.locator('.team-review').getByRole('button',{name:/Verified/}).click();await expect(page.locator('.team-big')).toContainText('1 of 2 done');
 const cmd=async text=>(await request.post('/command',{headers:auth,data:{text}})).json();
 expect((await cmd('team status')).reply).toContain('1 of 2 done');expect((await cmd('hello how are you')).reply||'').not.toContain('of 2 done');
});

test('team screen is one screen with no scrolling at every size, even with a lot of data',async({page,request})=>{
 const auth={Authorization:'Bearer manual-fix-preview-key'};
 const sizes=[[1920,900],[1440,800],[1280,720],[1024,600],[768,1024],[412,915],[390,844],[360,640],[320,568]];
 for(const demo of [[[0,'Waiting']],[[1,'Reported'],[2,'Asked'],[1,'Done']],[[8,'Reported'],[14,'Asked'],[3,'Late'],[5,'Done']]]){
  for(const [w,h] of sizes){
   await open(page,request,w,h);await request.post('/__test/seed',{headers:auth,data:{team_demo:demo}});
   await page.locator('#openTeam').click();await expect(page.locator('.team-page')).toBeVisible();await page.waitForTimeout(350);
   const m=await page.evaluate(()=>{const b=document.querySelector('.team-body'),s=document.querySelector('.team-shell'),f=document.querySelector('.team-foot');const r=f.getBoundingClientRect();
    const bad=[...document.querySelectorAll('.team-page button')].filter(x=>x.offsetParent&&(x.getBoundingClientRect().height<43||x.getBoundingClientRect().right>innerWidth+1||x.getBoundingClientRect().left<-1)).map(x=>x.textContent.trim()+':'+Math.round(x.getBoundingClientRect().height));
    return {fit:b.scrollHeight<=b.clientHeight+1,x:document.documentElement.scrollWidth>innerWidth+1||s.scrollWidth>s.clientWidth+1,footIn:r.bottom<=innerHeight+1&&r.top>=0,bad,add:!!document.querySelector('.team-add')||!!document.querySelector('#teamText')}});
   expect(m.fit,`${w}x${h} ${JSON.stringify(demo)}: nothing to scroll`).toBe(true);expect(m.x,`${w}x${h}: no sideways scroll`).toBe(false);expect(m.footIn,`${w}x${h}: Back is on screen`).toBe(true);expect(m.bad,`${w}x${h}: every button is 44px tall and inside`).toEqual([]);expect(m.add,`${w}x${h}: the add button stays`).toBe(true);
   await page.locator('.team-back').click();
  }
 }
 await open(page,request,390,700);await request.post('/__test/seed',{headers:auth,data:{team_demo:[[2,'Asked']]}});await page.locator('#openTeam').click();await page.getByRole('button',{name:'+ Add tasks'}).click();
 await page.locator('#teamText').fill(Array.from({length:20},(_,i)=>'Task number '+(i+1)+' with some words').join('\n')+'\ndeadline tomorrow 9pm');await page.getByRole('button',{name:'Plan the tasks'}).click();await expect(page.getByRole('button',{name:'Start tasks'})).toBeVisible();
 const fit=await page.evaluate(()=>{const b=document.querySelector('.team-body');return b.scrollHeight<=b.clientHeight+1});expect(fit,'a 20-task plan preview also fits one screen').toBe(true);
});

test('team screen keeps the focused field (and the phone keyboard) when the window resizes or refreshes',async({page,request})=>{
 await open(page,request,390,700);await request.post('/__test/seed',{headers:auth,data:{team_demo:[[1,'Asked']]}});
 await page.locator('#openTeam').click();await page.getByRole('button',{name:'+ Add tasks'}).click();
 const box=page.locator('#teamText');await box.click();await box.fill('Post in groups');
 await page.setViewportSize({width:390,height:380});await page.waitForTimeout(400);   // what the keyboard does
 await page.evaluate(()=>window.dispatchEvent(new Event('resize')));await page.waitForTimeout(400);
 expect(await page.evaluate(()=>document.activeElement?.id)).toBe('teamText');expect(await box.inputValue()).toBe('Post in groups');
 await page.waitForTimeout(9500);   // past one automatic refresh
 expect(await page.evaluate(()=>document.activeElement?.id)).toBe('teamText');expect(await box.inputValue()).toBe('Post in groups');
});

test('team: a planning error is visible inside the Team screen, and quiet hours are an optional switch in Settings',async({page,request})=>{
 await page.route('**/team',route=>route.request().method()==='POST'&&route.request().postDataJSON()?.action==='plan'
  ?route.fulfill({status:400,json:{error:'The deadline must be in the future.'}}):route.continue());
 await open(page,request,390,700);await request.post('/__test/seed',{headers:auth,data:{team_demo:[[1,'Asked']]}});
 await page.locator('#openTeam').click();await page.getByRole('button',{name:'+ Add tasks'}).click();
 await page.locator('#teamText').fill('Do the thing');await page.getByRole('button',{name:'Plan the tasks'}).click();
 const err=page.locator('.team-page .team-error');await expect(err).toBeVisible();await expect(err).toContainText('deadline');
 const box=await err.boundingBox();expect(box.y).toBeGreaterThan(0);expect(box.y+box.height).toBeLessThan(700);
 await page.locator('.team-back').click();await openSettings(page);const sw=page.locator('#teamQuietOn');await expect(sw).not.toBeChecked();
 await sw.check();await expect.poll(async()=>(await (await request.get('/team',{headers:auth})).json()).quiet).toEqual([23,7]);
 await sw.uncheck();await expect.poll(async()=>(await (await request.get('/team',{headers:auth})).json()).quiet).toBeNull();
});

