const {test,expect}=require('@playwright/test');
const auth={Authorization:'Bearer manual-fix-preview-key'};

test('Foundation Notes: unlocked editor formats and autosaves from Donors',async({page,request})=>{
 await page.setViewportSize({width:390,height:844});
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await request.post('/__test/seed',{headers:auth,data:{reply:'Ready.'}});
 let unlocked=false,body='',version=0,saves=0;
 await page.route('**/foundation-notes',async route=>{
  const req=route.request(),action=req.method()==='POST'?JSON.parse(req.postData()||'{}'):{};
  let data;
  if(req.method()==='GET')data=unlocked?{locked:false,html:body,version,updated_at:123}:{locked:true};
  else if(action.action==='unlock'){unlocked=true;data={locked:false}}
  else if(action.action==='save'){
   if(!unlocked)return route.fulfill({status:403,json:{error:'Locked'}});
   body=action.html;version++;saves++;data={html:body,version,updated_at:123}
  }else if(action.action==='forget'){unlocked=false;data={locked:true}}
  else data={error:'Unknown'};
  await route.fulfill({status:200,json:data});
 });
 await page.goto('/');
 await page.locator('#openDonors').click();
 await expect(page.locator('#donorNotesTab')).toBeVisible();
 await expect(page.locator('#donorNotesTab')).toBeInViewport();
 await page.locator('#donorNotesTab').click();
 await expect(page.locator('#fnLockscreen')).toBeVisible();
 await page.locator('#fnPassword').fill('test-only-password');
 await page.locator('#fnUnlock').click();
 const editor=page.locator('#fnEditor');
 await expect(editor).toBeVisible();
 await editor.fill('Foundation donor ideas');
 await page.locator('#fnToolbar [data-cmd=bold]').click();
 await expect.poll(()=>saves,{timeout:6000}).toBeGreaterThan(0);
 await expect.poll(()=>body).toContain('Foundation donor ideas');
 await page.locator('#fnClose').click();
 await page.locator('#donorNotesTab').click();
 await expect(editor).toContainText('Foundation donor ideas');
 await expect(page.locator('#fnLockscreen')).toBeHidden();
 await page.locator('#fnLock').click();
 await expect(page.locator('#fnLockscreen')).toBeVisible();
});

test('Foundation Notes desktop: main editing tools fit, with no horizontal overflow',async({page,request})=>{
 await page.setViewportSize({width:1440,height:900});
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await request.post('/__test/seed',{headers:auth,data:{reply:'Ready.'}});
 await page.route('**/foundation-notes',route=>route.fulfill({status:200,json:{locked:false,html:'<h2>Foundation ideas</h2><p>List outreach leads.</p>',version:4}}));
 await page.goto('/');
 await page.locator('#openDonors').click();
 await page.locator('#donorNotesTab').click();
 await expect(page.locator('#fnEditor')).toContainText('Foundation ideas');
 for(const selector of ['#fnBlock','#fnToolbar [data-cmd=bold]','#fnToolbar [data-cmd=italic]','#fnChecklist','#fnToolbar [data-cmd=insertOrderedList]','#fnToolbar [data-color="#3b82f6"]'])
  await expect(page.locator(selector)).toBeVisible();
 const overflow=await page.evaluate(()=>document.querySelector('.fn-shell').scrollWidth>innerWidth+1);
 expect(overflow).toBe(false);
});
