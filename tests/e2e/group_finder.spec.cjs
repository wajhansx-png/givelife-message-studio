const {test,expect}=require('@playwright/test');
const auth={Authorization:'Bearer group-finder-preview-only'};
const link='https://chat.whatsapp.com/AbCdEfGhIjKlMnOpQrStUv';
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','group-finder-preview-only'));
});
test('research, evidence review and refresh work without outbound messaging',async({page,request})=>{
 const calls=[];page.on('request',req=>{if(req.method()==='POST')calls.push(req.url())});
 await page.goto('/group-finder');await expect(page.getByRole('heading',{name:'No groups researched yet'})).toBeVisible();
 await page.getByRole('button',{name:'Find groups',exact:true}).click();
 await expect(page.locator('#researchPhase')).toContainText('Research complete',{timeout:15000});
 await expect(page.locator('#groupRows')).toContainText('Demo University welfare');
 await expect(page.locator('#groupRows')).toContainText('Posting: Not checked');
 await page.getByRole('button',{name:'Review Demo University welfare'}).click();
 const dialog=page.getByRole('dialog',{name:'Demo University welfare'});await expect(dialog).toBeVisible();
 await expect(page.locator('#joinedGroup option')).toHaveCount(2);
 await page.locator('#check-invite').selectOption('valid');await page.locator('#check-member').selectOption('yes');await page.locator('#check-posting').selectOption('all_members');await page.locator('#check-charity').selectOption('allowed');
 await page.getByLabel('What did you check?').fill('Synthetic admin confirmed charity and all-member posting.');
 await page.locator('#confirmCheck').check();await page.getByRole('button',{name:'Save verified checks'}).click();await expect(dialog).not.toBeVisible();
 await page.getByRole('button',{name:/^Ready/}).click();await expect(page.locator('#groupRows')).toContainText('Ready');
 await page.reload();await expect(page.getByRole('button',{name:/^Ready/})).toHaveAttribute('aria-pressed','true');
 expect(calls.every(url=>new URL(url).pathname==='/api/group-finder')).toBe(true);
 const response=await request.get('/api/group-finder?tab=ready',{headers:auth});expect((await response.json()).counts.ready).toBe(1);
 expect(await page.evaluate(()=>window.injected)).toBeUndefined();
});
test('changing All clears a search and imported links cannot verify permissions',async({page,request})=>{
 const current=await(await request.get('/api/group-finder',{headers:auth})).json();
 await request.post('/api/group-finder',{headers:auth,data:{action:'import',university_id:current.universities[0].id,text:link.replace('Ab','Zb'),title:'<img src=x onerror=alert(1)>',source_url:'https://example.edu/claimed'}});
 await page.goto('/group-finder?tab=needs_verification&q=missing');await expect(page.locator('#groupRows')).toBeEmpty();
 await page.getByRole('button',{name:/^All/}).click();await expect(page.locator('#search')).toHaveValue('');
 await expect(page.locator('#groupRows')).toContainText('<img src=x onerror=alert(1)>');expect(await page.locator('#groupRows img').count()).toBe(0);
});
for(const size of [{width:1440,height:900},{width:768,height:1024},{width:390,height:844},{width:320,height:640}]){
 test(`research screen and review fit ${size.width}px`,async({page})=>{
  await page.setViewportSize(size);await page.goto('/group-finder');await expect(page.locator('#findGroups')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'Universities',exact:true}).click();await expect(page.getByRole('dialog',{name:'Research universities'})).toBeVisible();
  const bounds=await page.locator('#targets').boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(size.width+1);
  await page.getByRole('button',{name:'Close universities',exact:true}).click();
  await page.screenshot({path:`test-results/group-finder/main-${size.width}.png`,fullPage:true});
 });
}
test('private APIs reject missing keys and foreign origins',async({request})=>{
 expect((await request.get('/api/group-finder')).status()).toBe(401);
 expect((await request.post('/api/group-finder',{headers:{...auth,Origin:'https://attacker.invalid'},data:{action:'search'}})).status()).toBe(403);
});
