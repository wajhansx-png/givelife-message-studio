const {test,expect}=require('@playwright/test');
const {showPreview}=require('./helpers.cjs');
const auth={Authorization:'Bearer manual-fix-preview-key'};
async function open(page,request){
 await request.post('/__test/seed',{headers:auth,data:{reply:'GROUP message saved (poster + caption).\n\n'+caption}});
 await page.goto('/');
 if(await page.getByLabel('Private access key',{exact:true}).isVisible()){
  await page.getByLabel('Private access key',{exact:true}).fill('manual-fix-preview-key');await page.getByRole('button',{name:'Unlock studio',exact:true}).click();
 }
 await expect(page.locator('#leftChip')).toContainText('25,000');
}
const caption='*Yousuf is 2 years old. His treatment is still possible, and Rs. 25,000 is what stands between him and it.*\n\nFluid in his brain *can damage his eyesight and paralyse his body.* Both kidneys are badly swollen, and he has a hernia too. 💔\n\n*_Rs. 25,000 LEFT_*\n\n*_13 people donating Rs. 2,000_*\n*_OR 25 people donating Rs. 1,000_* 🤲\n\nPlease help with his treatment today.\n\n*03097458815*\nEasypaisa / JazzCash (GiveLife Foundation account)\n\nReply *Done* after donating.\n- GiveLife Foundation';
for(const [width,height] of [[1440,900],[1280,720],[1024,768],[390,844],[320,640]]){
 test(`full saved caption fits ${width}x${height}`,async({page,request})=>{
  await page.setViewportSize({width,height});await open(page,request);
  await request.post('/__test/seed',{headers:auth,data:{group:caption}});
  await page.reload();
  if(width>=900)await showPreview(page);else await page.locator('#showMsg').click();
  await expect(page.locator('#groupPreview')).toContainText('GiveLife Foundation');
  await expect.poll(()=>page.locator('#chat').evaluate(el=>el.scrollHeight<=el.clientHeight+2)).toBe(true);
  const bounds=await page.locator('.app').evaluate(el=>({bottom:el.getBoundingClientRect().bottom,h:innerHeight,width:document.documentElement.scrollWidth,w:innerWidth}));
  expect(bounds.bottom).toBeLessThanOrEqual(bounds.h+2);expect(bounds.width).toBeLessThanOrEqual(bounds.w+1);
 });
}
test('latest desktop reply is fully visible above composer',async({page,request})=>{
 await page.setViewportSize({width:1280,height:720});await open(page,request);
 await expect(page.locator('#log .bot').last()).toContainText('GiveLife Foundation');
 const measure=()=>page.locator('#log .bot').last().evaluate(el=>({top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom,composer:document.querySelector('#cmdForm').getBoundingClientRect().top,height:innerHeight}));
 /* the answer finishes fitting a moment after it appears */
 await expect.poll(async()=>{const m=await measure();return m.bottom<=m.composer},{timeout:5000}).toBe(true);const b=await measure();
 expect(b.bottom).toBeLessThanOrEqual(b.composer);expect(b.bottom).toBeLessThanOrEqual(b.height);
});

