const {test,expect}=require('@playwright/test');
const AxeBuilder=require('@axe-core/playwright').default;
const fs=require('node:fs');
test.use({actionTimeout:7000});
async function setup(page){
 await page.addInitScript(()=>{localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');localStorage.setItem('givelife-theme','dark')});
}
for(const width of [1440,768,390,320]){
 test(`Notes refresh and Back preserve screen ${width}`,async({page})=>{
  await setup(page);await page.setViewportSize({width,height:850});
  await page.goto('/#/donors/important');await page.locator('#donorNotesShortcut').click();
  await expect(page).toHaveURL(/#\/donors\/important\/notes$/);
  await page.reload();await expect(page.locator('#foundationNotes')).toBeVisible();
  await expect(page.locator('#notesPassword')).toBeVisible();
  await page.locator('#notesBack').click();await expect(page.locator('#donorsPage')).toBeVisible();
  await expect(page).toHaveURL(/#\/donors\/important$/);
 });
 test(`screens fit and accessibility ${width}`,async({page},info)=>{
  await setup(page);await page.setViewportSize({width,height:850});
  test.setTimeout(180000);const problems=[];
  for(const route of ['', 'chat','preview','donors/all','donors/messages','donors/volunteers','settings','whatsapp','team']){
   await page.goto('/#/'+route);await page.waitForTimeout(350);
   const errors=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
   for(const v of errors.violations)problems.push({route,id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
   if(process.env.UI_SHOTS)await page.screenshot({path:`${process.env.UI_SHOTS}/${width}-${route.replaceAll('/','-')||'main'}.png`});
  }
  await info.attach('accessibility.json',{body:JSON.stringify(problems,null,2),contentType:'application/json'});
  expect(problems.filter(v=>['critical','serious'].includes(v.impact))).toEqual([]);
 });
}
test('refresh never paints Main before the requested screen, even with slow scripts',async({page})=>{
 await setup(page);
 await page.route('**/donors.js',async route=>{await new Promise(r=>setTimeout(r,600));await route.continue()});
 await page.addInitScript(()=>{
  window.wrongScreenFrames=0;
  function inspect(){const main=document.querySelector('.app'),donors=document.getElementById('donorsPage');
   if(main&&!donors?.open&&getComputedStyle(main).visibility==='visible'&&getComputedStyle(main).display!=='none')window.wrongScreenFrames++;
   if(!donors?.open)requestAnimationFrame(inspect);
  }requestAnimationFrame(inspect);
 });
 await page.goto('/#/donors/messages');await expect(page.locator('#donorsPage')).toBeVisible();
 expect(await page.evaluate(()=>wrongScreenFrames)).toBe(0);
});
test('Team and memory restore without redoing actions',async({page})=>{
 await setup(page);await page.goto('/#/team');await expect(page.locator('#teamPage')).toBeVisible();
 await page.reload();await expect(page.locator('#teamPage')).toBeVisible();
 await page.goto('/#/settings/memory');await expect(page.locator('#memoryDialog')).toBeVisible();
 await page.reload();await expect(page.locator('#memoryDialog')).toBeVisible();
 await page.locator('#memoryClose').click();await expect(page).toHaveURL(/#\/settings$/);
});
test('secondary forms restore and close without sending',async({page})=>{
 await setup(page);
 for(const [route,id,close] of [['donors/all/add','donorAddDialog','donorAddCancel'],['donors/all/bulk','donorPasteDialog','pasteCancel'],['donors/all/pace','donorBatchPicker','batchCancel'],['settings/poster','posterDialog','posterClose']]){
  await page.goto('/#/'+route);await expect(page.locator('#'+id)).toBeVisible();
  await page.reload();await expect(page.locator('#'+id)).toBeVisible();
  await page.locator('#'+close).click();await expect(page.locator('#'+id)).not.toBeVisible();
 }
});
test('Notes keeps its parent navigation after refresh',async({page})=>{
 await setup(page);await page.goto('/#/preview');await page.locator('#openDonors').click();
 await page.locator('#donorNotesShortcut').click();await page.reload();
 await page.locator('#notesBack').click();await page.locator('#donorMainBottom').click();
 await expect(page).toHaveURL(/#\/preview$/);await expect(page.locator('#card')).toBeVisible();
});
test('closing Memory while its response is delayed never reopens it',async({page})=>{
 await setup(page);let release;const ready=new Promise(r=>release=r);
 await page.route('**/knowledge',async route=>{await ready;await route.fulfill({json:{entries:[],feedback_count:0,archived_turns:0}})});
 await page.goto('/#/settings/memory');await expect(page.locator('#memoryDialog')).toBeVisible();
 await page.locator('#memoryClose').click();release();await page.waitForTimeout(100);
 await expect(page.locator('#memoryDialog')).not.toBeVisible();await expect(page).toHaveURL(/#\/settings$/);
});
for(const width of [1440,390])test(`light theme and donor forms accessibility ${width}`,async({page})=>{
 test.setTimeout(180000);await setup(page);await page.setViewportSize({width,height:850});
 await page.addInitScript(()=>localStorage.setItem('givelife-theme','light'));
 for(const route of ['', 'donors/all','donors/all/add','donors/all/bulk','donors/all/pace','settings/poster','donors/all/notes']){
  await page.goto('/#/'+route);await page.waitForTimeout(300);
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(result.violations.filter(v=>['critical','serious'].includes(v.impact)).map(v=>({route,id:v.id,nodes:v.nodes.map(n=>n.target)}))).toEqual([]);
 }
});
