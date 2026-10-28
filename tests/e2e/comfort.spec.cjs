const {test,expect}=require('@playwright/test');
const path=require('node:path');
const auth={Authorization:'Bearer manual-fix-preview-key'};
async function open(page,request,width=1440,height=900,theme='dark'){
 await page.setViewportSize({width,height});
 await page.addInitScript(t=>{localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');localStorage.setItem('givelife-theme',t)},theme);
 await request.post('/__test/seed',{headers:auth,data:{reply:"I've updated the message. The saved caption is ready to review.\n\n*Rs. 25,000 left.* Your existing settings are unchanged."}});
 await page.goto('/');await expect(page.locator('#leftChip')).toContainText('25,000');await page.evaluate(()=>document.fonts.ready);
}
async function shot(page,name){if(process.env.COMFORT_SHOTS)await page.screenshot({path:path.join(process.env.COMFORT_SHOTS,name+'.png'),fullPage:false})}
async function inside(page,locator){const b=await locator.boundingBox();expect(b).not.toBeNull();expect(b.x).toBeGreaterThanOrEqual(-1);expect(b.y).toBeGreaterThanOrEqual(-1);expect(b.x+b.width).toBeLessThanOrEqual(page.viewportSize().width+1);expect(b.y+b.height).toBeLessThanOrEqual(page.viewportSize().height+1)}
test('desktop reading column centers the reply and composer',async({page,request})=>{
 await open(page,request,1600,900);await expect(page.locator('#log .bot').last()).toContainText('ready to review');
 await shot(page,'desktop-chat');
 const box=await page.locator('#log .bot').last().boundingBox(),pane=await page.locator('.talk').boundingBox(),input=await page.locator('#cmdForm').boundingBox();
 expect(Math.abs(box.x+box.width/2-(pane.x+pane.width/2))).toBeLessThan(3);
 expect(Math.abs(input.x+input.width/2-(box.x+box.width/2))).toBeLessThan(3);
 expect(box.width).toBeLessThanOrEqual(780);expect(box.width).toBeGreaterThan(200);
 expect(await page.locator('#log .bot').last().evaluate(el=>getComputedStyle(el).textAlign)).toBe('center');
 const gear=await page.locator('#gear').boundingBox(),dot=await page.locator('#whatsappConnection').boundingBox(),donors=await page.locator('#openDonors').boundingBox();
 expect(gear.y).toBeGreaterThan(840);expect(dot.x).toBeLessThan(donors.x);
});
for(const [width,height,theme] of [[1440,900,'light'],[1024,768,'dark'],[768,1024,'light'],[390,844,'dark'],[320,640,'light']]){
 test(`all workspaces remain usable ${width} ${theme}`,async({page,request})=>{
  await open(page,request,width,height,theme);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await shot(page,`${width}-${theme}-main`);
  await page.locator('#gear').click();await inside(page,page.locator('#set'));await shot(page,`${width}-${theme}-settings`);
  await page.locator('#setClose').click();await page.locator('#openDonors').click();await expect(page.locator('.donor-row').first()).toBeVisible();
  await inside(page,page.locator('#donorsPage'));await shot(page,`${width}-${theme}-donors`);
  await page.locator('[data-tab=messages]').click();await expect(page.locator('#donorMessages')).toBeVisible();await shot(page,`${width}-${theme}-messages`);
  if(width>=390)await expect.poll(()=>page.locator('.bank-preview').evaluate(el=>el.scrollHeight<=el.clientHeight+2)).toBe(true);
  await page.locator('#donorMain').click();await page.getByRole('button',{name:'DM',exact:true}).click();await page.locator('#sendMoreDonors').click();
  await inside(page,page.getByRole('dialog',{name:'Send to more donors',exact:true}));
 });
}
test('mobile chat keeps draft, closes keyboard after send and has a reachable return row',async({page,request})=>{
 await open(page,request,390,844);
 await page.route('**/assistant',r=>r.fulfill({json:{reply:'Your request is ready.'}}));
 await page.locator('#chatOpen').click();await page.locator('#histCmd').fill('check a synthetic request');
 await page.locator('#histMain').click();await page.locator('#chatOpen').click();await expect(page.locator('#histCmd')).toHaveValue('check a synthetic request');
 await page.locator('#histForm .go').click();await expect(page.locator('#histCmd')).not.toBeFocused();
 const send=await page.locator('#histForm .go').boundingBox();expect(send.width).toBeGreaterThanOrEqual(48);expect(send.height).toBeGreaterThanOrEqual(48);
 await inside(page,page.locator('#histMain'));await shot(page,'mobile-chat');
 await page.setViewportSize({width:390,height:450});await inside(page,page.locator('#histForm .go'));await inside(page,page.locator('#histMain'));
});
test('mobile library selection beyond first ten survives reload',async({page,request})=>{
 await open(page,request,390,844);await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();
 const picker=page.getByLabel('Choose saved DM message',{exact:true});await picker.selectOption({label:'Message 20'});
 await expect(page.locator('.bank-detail header')).toContainText('Message 20');await page.reload();await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();
 await expect(page.getByLabel('Choose saved DM message',{exact:true})).toHaveJSProperty('selectedIndex',19);
});
test('donor tabs support arrow keys without retaining stale search',async({page,request})=>{
 await open(page,request);await page.locator('#openDonors').click();await page.locator('#donorSearch').fill('not-a-donor');
 const all=page.locator('[data-tab=all]');await all.click();await expect(page.locator('#donorSearch')).toHaveValue('');
 await all.press('ArrowRight');await expect(page.locator('[data-tab=important]')).toBeFocused();await expect(page.locator('[data-tab=important]')).toHaveAttribute('aria-selected','true');
});
test('message library switches previews and preserves unsaved edits',async({page,request})=>{
 await open(page,request);await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();
 await page.getByRole('button',{name:'Message 2',exact:true}).click();await expect(page.locator('.bank-detail header')).toContainText('Message 2');
 await page.locator('.bank-detail').getByRole('button',{name:'Edit',exact:true}).click();await page.getByLabel('Edit message 2',{exact:true}).fill('Synthetic edited caption.');
 await page.getByRole('button',{name:'Message 1',exact:true}).click();await page.getByRole('button',{name:'Message 2',exact:true}).click();
 await expect(page.getByLabel('Edit message 2',{exact:true})).toHaveValue('Synthetic edited caption.');
 await page.reload();await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();
 await expect(page.getByLabel('Edit message 2',{exact:true})).toHaveValue('Synthetic edited caption.');
});
test('failed chat requests keep the typed draft without retrying',async({page,request})=>{
 await open(page,request);let calls=0;await page.route('**/assistant',r=>{calls++;return r.abort()});
 await page.locator('#cmd').fill('Please explain this synthetic campaign carefully.');await page.locator('#cmdForm .go').click();
 await expect(page.locator('#cmd')).toHaveValue('Please explain this synthetic campaign carefully.');expect(calls).toBe(1);
});
test('first use defaults to dark; light and device themes persist and update',async({page})=>{
 await page.emulateMedia({colorScheme:'light'});await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));await page.goto('/');
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');await page.locator('#gear').click();await page.locator('#theme [data-t=light]').click();
 await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme','light');await page.locator('#gear').click();await page.locator('#theme [data-t=system]').click();
 expect(await page.locator('html').evaluate(el=>getComputedStyle(el).colorScheme)).toBe('light');await page.emulateMedia({colorScheme:'dark'});
 await expect.poll(()=>page.locator('html').evaluate(el=>getComputedStyle(el).colorScheme)).toBe('dark');
});
test('typing during a slow save keeps newer text as an unsaved draft',async({page,request})=>{
 await open(page,request);await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();
 let release,submitted;await page.route('**/donor-messages',async route=>{if(route.request().method()==='POST'&&route.request().postDataJSON().id){submitted=route.request().postDataJSON();await new Promise(resolve=>release=resolve)}await route.continue()});
 await page.locator('.bank-detail').getByRole('button',{name:'Edit',exact:true}).click();const editor=page.getByLabel('Edit message 1',{exact:true}),sentText=(await editor.inputValue())+'\n\nSynthetic submitted A',newerText=sentText+'\nNewer draft B';await editor.fill(sentText);
 await page.locator('.bank-detail').getByRole('button',{name:'Save',exact:true}).click();await expect.poll(()=>!!submitted).toBe(true);
 await editor.fill(newerText);release();
 await expect(page.locator('#donorNotice')).toContainText('newer edits are still unsaved');
 await expect(editor).toHaveValue(newerText);
 const stored=await (await request.get('/donor-messages',{headers:auth})).json();expect(stored.items.find(item=>item.id===submitted.id).text).toBe(sentText);
 await page.reload();await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();await expect(page.getByLabel('Edit message 1',{exact:true})).toHaveValue(newerText);
});
test('regeneration cannot be duplicated by switching message previews',async({page,request})=>{
 await open(page,request);await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();
 let release,calls=0;await page.route('**/donor-messages',async route=>{if(route.request().method()==='POST'&&route.request().postDataJSON().action==='regenerate'){calls++;await new Promise(resolve=>release=resolve)}await route.continue()});
 await page.getByRole('button',{name:'Regenerate',exact:true}).click();await expect.poll(()=>calls).toBe(1);await page.getByRole('button',{name:'Message 2',exact:true}).click();
 await expect(page.getByRole('button',{name:'Regenerate',exact:true})).toBeDisabled();release();await expect(page.getByRole('button',{name:'Regenerate',exact:true})).toBeEnabled();expect(calls).toBe(1);
});
for(const width of [1440,390])test(`secondary screens retain accessible exits at ${width}`,async({page,request})=>{
 await open(page,request,width,844);await page.locator('#gear').click();await page.getByRole('button',{name:'Change poster',exact:true}).click();
 await inside(page,page.locator('#posterDialog'));await shot(page,`${width}-poster`);await page.locator('#posterClose').click();
 await page.locator('#openMemory').click();await inside(page,page.locator('#memoryDialog'));await page.locator('#memoryClose').click();await page.locator('#setClose').click();
 await page.locator('#whatsappConnection').click();const wa=page.getByRole('dialog',{name:'WhatsApp connection',exact:true});await inside(page,wa);await shot(page,`${width}-whatsapp`);await page.locator('#waCloudClose').click();
 await page.locator('#openDonors').click();await page.locator('#donorAdd').click();await inside(page,page.locator('#donorAddDialog'));await shot(page,`${width}-add-donor`);await page.locator('#donorAddCancel').click();await page.locator('#donorMain').click();
 if(width>=900)await page.locator('#chatExpand').click();else await page.locator('#chatOpen').click();await inside(page,page.locator('#hist'));await shot(page,`${width}-history`);
});
test('an empty message library explains how to recover',async({page,request})=>{
 await open(page,request);await page.route('**/donor-messages',r=>r.fulfill({json:{items:[]}}));await page.locator('#openDonors').click();await page.locator('[data-tab=messages]').click();
 await expect(page.locator('#donorMessages')).toContainText('No saved messages yet');await expect(page.getByRole('button',{name:'Regenerate',exact:true})).toBeEnabled();
});
