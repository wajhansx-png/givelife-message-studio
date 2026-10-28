const {test,expect}=require('@playwright/test');
const auth={Authorization:'Bearer manual-fix-preview-key'};
test('pasted DM modal validates, deduplicates and starts the first personalized DM',async({page,request})=>{
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await page.goto('/');await page.getByRole('button',{name:'DM',exact:true}).click();
 await page.getByRole('button',{name:'Send to more donors',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Send to more donors',exact:true});await expect(modal).toBeVisible();
 await page.getByLabel('Numbers and names',{exact:true}).fill('03001112222, Ali\nAyesha, 03012223333\n+923001112222, Ali duplicate');
 await expect(page.locator('#pasteResult')).toContainText('2 recipients');
 await expect(page.locator('#pasteResult')).not.toContainText('1112222');
 await expect(page.getByRole('button',{name:'Add & start DMs',exact:true})).toBeEnabled();
 await page.getByLabel('Gap between DMs',{exact:true}).selectOption('3');
 await page.getByRole('button',{name:'Add & start DMs',exact:true}).dblclick();
 await expect(page.locator('#donorsPage')).toBeVisible();
 await expect.poll(async()=>{const r=await request.get('/donor-delivery',{headers:auth});return (await r.json()).sent}).toBe(1);
 const status=await (await request.get('/donor-delivery',{headers:auth})).json();expect(status.total).toBe(2);expect(status.gap_seconds).toBe(180);
 const events=await (await request.get('/__test/events',{headers:auth})).json();
 expect(events.events.filter(e=>e.fields.phone==='923001112222').length).toBe(1);
 expect(events.events.find(e=>e.fields.phone==='923001112222').fields.caption).toMatch(/^Ali Brother/);
 await request.post('/donor-delivery',{headers:auth,data:{stop:true}});
});
test('private APIs reject missing authentication and invalid origins',async({request})=>{
 expect((await request.get('/donors')).status()).toBe(401);
 expect((await request.post('/donor-paste',{data:{action:'preview',text:'03001234567, Ali'}})).status()).toBe(401);
 expect((await request.post('/donor-paste',{headers:{...auth,Origin:'https://untrusted.invalid'},data:{action:'preview',text:'03001234567, Ali'}})).status()).toBe(403);
});

