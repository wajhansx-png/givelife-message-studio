const {test,expect}=require('@playwright/test');
const {reveal,openSettings,openPreview,openMessages}=require('./helpers.cjs');
test.use({actionTimeout:8000});
const path=require('node:path');
const auth={Authorization:'Bearer manual-fix-preview-key'};
const reply='Here is the current update.\n\n*What is ready*\nThe saved caption and poster are ready to review. No messages were sent during this check.\n\n*Next steps*\n'+Array.from({length:7},(_,i)=>`${i+1}. *Review step ${i+1}.* Keep the existing task, message and recipient unchanged. Open the relevant screen when you need it.`).join('\n\n');
async function open(page,request,width=1440,height=900,stableChat=true){
 if(stableChat)await page.route('**/chat',r=>r.fulfill({json:{items:[{who:'app',text:reply,t:Date.now(),turn_id:'smooth-review'}]}}));
 await page.setViewportSize({width,height});await page.addInitScript(()=>{localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');localStorage.setItem('givelife-theme','dark')});
 await request.post('/__test/seed',{headers:auth,data:{reply}});await page.goto('/');await expect(page.locator('#leftChip')).toContainText('25,000');await page.evaluate(()=>document.fonts.ready);
}
test('desktop actions sit below the reply and the narrower group rail gives text more width',async({page,request})=>{
 await page.route('**/chat-next-actions',r=>r.fulfill({json:{items:['View message','Send test','Send to GiveLife main'].map((label,i)=>({id:String(i+1).repeat(32),label}))}}));
 await open(page,request);await expect(page.locator('#chatNextActions button')).toHaveCount(3);
 const actions=await page.locator('#chatNextActions').boundingBox(),log=await page.locator('#log').boundingBox(),rail=await page.locator('.action-rail').boundingBox(),talk=await page.locator('.talk').boundingBox();
 expect(actions.y).toBeGreaterThanOrEqual(log.y+log.height-2);expect(rail.width).toBeLessThanOrEqual(288);expect(log.width).toBeGreaterThan(talk.width-4);
 const padding=await page.locator('#log').evaluate(el=>parseFloat(getComputedStyle(el).paddingRight));expect(padding).toBeLessThanOrEqual(26);
 for(const b of await page.locator('.action-rail button[data-target]').all()){const box=await b.boundingBox();expect(box.height).toBeGreaterThanOrEqual(40)}
 if(process.env.COMFORT_SHOTS)await page.screenshot({path:path.join(process.env.COMFORT_SHOTS,'smooth-desktop.png')});
});
test('sending while reading old chat always reveals the new answer, even after another scroll while waiting',async({page,request})=>{
 const items=Array.from({length:30},(_,i)=>({who:i%2?'app':'you',text:'Earlier conversation '+i+' '+('readable history '.repeat(18)),t:Date.now()-60000+i,turn_id:'old-'+i}));
 await page.route('**/chat',r=>r.fulfill({json:{items}}));await page.route('**/command',r=>r.fulfill({json:{handled:false}}));
 let release;const wait=new Promise(resolve=>release=resolve);await page.route('**/assistant',async r=>{await wait;await r.fulfill({json:{reply:'LATEST ANSWER: the requested screen is ready.',actions:[]}})});
 await open(page,request,390,700,false);await page.locator('#chatOpen').click();const log=page.locator('#histLog');await log.evaluate(el=>el.scrollTop=0);
 await page.locator('#histCmd').fill('Please explain this screen');await page.locator('#histForm .go').click();await expect(log).toContainText('Thinking');await log.evaluate(el=>el.scrollTop=0);release();
 const answer=log.locator('.bot').last();await expect(answer).toContainText('LATEST ANSWER');await expect.poll(()=>answer.evaluate(el=>{const box=el.getBoundingClientRect(),pane=el.parentElement.getBoundingClientRect();return box.top>=pane.top-2&&box.bottom<=pane.bottom+2})).toBe(true);
 await expect(page.locator('#histCmd')).not.toBeFocused();
});
test('refresh waits for unlock before restoring the requested tab',async({page,request})=>{
 await page.setViewportSize({width:390,height:700});await page.goto('/#/donors/messages');await expect(page.locator('#cloudLogin')).toBeVisible();
 await page.locator('#cloudKey').fill('manual-fix-preview-key');await page.locator('#cloudUnlock').click();await expect(page.locator('#donorsPage')).toBeVisible();await expect(page.locator('[data-tab=messages]')).toHaveAttribute('aria-selected','true');
 await page.reload();await expect(page.locator('[data-tab=messages]')).toHaveAttribute('aria-selected','true');
});
test('WhatsApp connection screen survives refresh and Back without reconnecting or sending',async({page,request})=>{
 await open(page,request,390,700);await page.locator('#whatsappConnection').click();await expect(page).toHaveURL(/#\/whatsapp$/);await page.reload();await expect(page.getByRole('dialog',{name:'WhatsApp connection',exact:true})).toBeVisible();
 await page.locator('#waCloudClose').click();await expect(page.getByRole('dialog',{name:'WhatsApp connection',exact:true})).not.toBeVisible();
});
test('reduced motion keeps navigation immediate without decorative animations',async({page,request})=>{
 await page.emulateMedia({reducedMotion:'reduce'});await open(page,request,390,700);await page.locator('#chatOpen').click();await expect(page.locator('#hist')).toBeVisible();
 expect(await page.locator('#hist').evaluate(el=>el.getAnimations().filter(x=>x.playState==='running').length)).toBe(0);await page.locator('#histMain').click();await page.locator('#openDonors').click();await page.reload();await expect(page.locator('#donorsPage')).toBeVisible();
});
for(const [width,height] of [[1280,720],[1024,600],[390,700],[320,568]])test(`screen and tab restoration with fast navigation ${width}x${height}`,async({page,request})=>{
 test.setTimeout(90000);
 // Keep this navigation check independent of shared fake-server record mutations.
 const items=Array.from({length:3},(_,i)=>({id:String(i+1).repeat(32),name:'Synthetic donor '+(i+1),important:i===0,donated:false,amount:0,delivery:'Not contacted'}));
 await page.route('**/donors?tab=all',r=>r.fulfill({json:{items,counts:{all:3,important:1,donated:0,not_donated:3,not_contacted:3,donated_amount:0}}}));
 await page.route('**/donor-delivery',r=>r.fulfill({json:{state:'Idle',sent:0,total:0,receipts:[]}}));
 await page.route('**/donor-messages',r=>r.fulfill({json:{items:[{id:'a'.repeat(32),text:'Brother, this is the complete synthetic caption.\n\nPlease review the current appeal.\n\nNo real message is sent during this test.'}]}}));
 await open(page,request,width,height);
 for(const tab of ['all','important','donated','not_contacted','messages']){
  await page.locator('#openDonors').click();if(tab==='messages')await openMessages(page);else await page.locator(`[data-tab=${tab}]`).click();await page.reload();await expect(page.locator(`[data-tab=${tab}]`)).toHaveAttribute('aria-selected','true');
  if(tab==='messages')await page.locator('.bank-back').click();await page.locator('#donorMainBottom').click();await page.locator(width<900?'#chatOpen':'#chatExpand').click();await expect(page.locator('#hist')).toBeVisible();await page.locator('#histClose').isVisible().then(visible=>page.locator(visible?'#histClose':'#histMain').click());
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 if(width<900&&process.env.COMFORT_SHOTS){await page.locator('#chatOpen').click();await page.screenshot({path:path.join(process.env.COMFORT_SHOTS,`smooth-mobile-${width}.png`)})}
});
test('browser Back and Forward restore the visible screen after immediate Close navigation',async({page,request})=>{
 await open(page,request,1280,720);await page.locator('#openDonors').click();await expect(page.locator('#donorsPage')).toBeVisible();
 await page.goBack();await expect(page.locator('#donorsPage')).not.toBeVisible();await page.goForward();await expect(page.locator('#donorsPage')).toBeVisible();await page.locator('#donorMainBottom').click();
 await openSettings(page);await page.goBack();await expect(page.locator('#set')).not.toBeVisible();await page.goForward();await expect(page.locator('#set')).toBeVisible();await page.locator('#setClose').click();
 await openPreview(page);await page.goBack();await expect(page.locator('#messageFocus')).not.toBeVisible();await page.goForward();await expect(page.locator('#messageFocus')).toBeVisible();
});
