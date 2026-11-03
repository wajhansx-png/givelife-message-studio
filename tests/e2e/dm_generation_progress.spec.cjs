const {test,expect}=require('@playwright/test');
for(const width of [1440,390])test(`DM generation saves progress and survives refresh ${width}`,async({page})=>{
 await page.setViewportSize({width,height:900});
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 const source='Brother, please help this family.\n\nTheir child needs treatment.\n\nRs. 25,000 LEFT.\n\n03097458815 Easypaisa / JazzCash (Wajdan Khan)';
 const entries=n=>Array.from({length:n},(_,i)=>({id:`wording-${String(i+1).padStart(2,'0')}`,text:i?source.replace('please help',`supporter ${i}, please help`):source,enabled:true}));
 let started=false,polls=0;
 await page.route('**/donor-messages',async route=>{
  const post=route.request().method()==='POST';if(post){expect(route.request().postDataJSON().action).toBe('regenerate');started=true}
  if(started&&!post)polls++;
  const ready=!started?20:polls>1?20:polls?6:1;
  await route.fulfill({json:{items:entries(ready),...(started?{generation:{id:'fake-generation',state:ready===20?'Ready':'Generating',ready,target:20,error:''}}:{})}});
 });
 await page.goto('/#/donors/messages');
 await expect(page.locator('.bank-regenerate')).toBeVisible();await page.locator('.bank-regenerate').click();
 await expect(page.locator('.bank-generation-state')).toContainText('Generating DMs');
 await expect(page.locator('.bank-regenerate')).toBeDisabled();
 await expect(page.locator('.bank-generation-state')).toHaveText('20 DM messages ready',{timeout:10000});
 await expect(page.locator('.bank-generation-state')).toBeVisible();
 await expect(page.locator('.bank-regenerate')).toBeEnabled();
 await page.reload();await expect(page.locator('.bank-generation-state')).toHaveText('20 DM messages ready');
 await expect(page.locator('.bank-preview')).toContainText('Brother');
 await page.screenshot({path:`test-results/dm-generation-${width}.png`});
});
