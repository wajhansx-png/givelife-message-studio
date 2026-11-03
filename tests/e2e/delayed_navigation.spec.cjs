const {test,expect}=require('@playwright/test');
async function setup(page){await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));await page.goto('/')}
test('slow Gap response cannot reopen a closed donor screen',async({page})=>{
 await setup(page);await page.locator('#openDonors').click();let release;const gate=new Promise(r=>release=r);
 await page.route('**/donor-delivery',async r=>{await gate;await r.continue()});
 await page.locator('#donorPace').click();await page.goBack();release();await page.waitForTimeout(300);
 await expect(page.locator('#donorBatchPicker')).not.toBeVisible();
});
test('Back then Forward during a Notes save keeps Notes open',async({page})=>{
 await setup(page);await page.locator('#donorNotesShortcut').click();
 await page.locator('#notesPassword').fill('test-preview-only-pin');await page.locator('#notesUnlockButton').click();
 let release,started=false;const gate=new Promise(r=>release=r);
 await page.route('**/notes',async r=>{if(r.request().postDataJSON()?.action==='save'){started=true;await gate}await r.continue()});
 await page.locator('#notesEditor').fill('Synthetic note while navigating');await page.goBack();
 await expect.poll(()=>started).toBe(true);await page.goForward();release();await page.waitForTimeout(300);
 await expect(page).toHaveURL(/\/notes$/);await expect(page.locator('#foundationNotes')).toBeVisible();
});
