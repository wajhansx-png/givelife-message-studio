const {test,expect}=require('@playwright/test');
test.use({trace:'off'});

const original='*Ready to review*\n\nThe original has _emphasis_, `code`, an & sign, and <literal text>.\n\n'+Array.from({length:8},(_,i)=>`${i+1}. *Review step ${i+1}.* Keep the exact saved message and recipient. This synthetic reply checks fitting without sending any message.`).join('\n\n')+'\n\nWould you like to review it?';
const userText='Please review the *entire* original message.\nKeep its line breaks.';
async function open(page,width=1280,height=720){
 await page.setViewportSize({width,height});
 await page.addInitScript(()=>{localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');localStorage.setItem('givelife-theme','dark')});
 await page.route('**/chat',route=>route.fulfill({json:{items:[{who:'you',text:userText,t:1,turn_id:'render-user'},{who:'app',text:original,t:2,turn_id:'render-reply'}]}}));
 await page.goto('/');await expect(page.locator('#leftChip')).toContainText('25,000');await expect(page.locator('#log .bot')).toContainText('Ready to review');await page.evaluate(()=>document.fonts.ready);
}

test('refresh and thinking preserve the same boxed reply and its fitted layout',async({page})=>{
 await open(page);
 const result=await page.evaluate(async()=>{
  const reply=document.querySelector('#log .e.bot:not(.dots)'),samples=[];
  // Observe painted frames, including the extra ResizeObserver frames after fitting.
  const sample=()=>{const el=document.querySelector('#log .e.bot:not(.dots)'),cs=getComputedStyle(el),r=el.getBoundingClientRect();samples.push({same:el===reply,cols:cs.columnCount,long:el.closest('.talk').classList.contains('long-reply'),box:cs.backgroundColor,border:cs.borderTopWidth,x:r.x,y:r.y,w:r.width,h:r.height})};
  await syncChat();think(true);think(false);
  for(let i=0;i<20;i++){await new Promise(requestAnimationFrame);sample()}
  return samples;
 });
 expect(result.every(x=>x.same),'An unchanged reply must keep its DOM node when chat refreshes or thinking changes').toBe(true);
 expect(result.every(x=>x.box!=='rgba(0, 0, 0, 0)'&&parseFloat(x.border)>0)).toBe(true);
 expect(new Set(result.slice(2).map(x=>JSON.stringify([x.cols,x.long,x.x,x.y,x.w,x.h]))).size,'The fitted reply must settle without a ResizeObserver feedback loop').toBe(1);
});

test('a new assistant answer is boxed and fitted from its first painted frame',async({page})=>{
 await open(page);const reply='NEW BOXED ANSWER\n\n'+original;
 await page.route('**/command',route=>route.fulfill({json:{handled:false}}));
 await page.route('**/assistant',route=>route.fulfill({json:{reply,actions:[]}}));
 await page.evaluate(()=>{window.answerFrames=[];window.captureAnswer=true;function capture(){const el=[...document.querySelectorAll('#log .e.bot:not(.dots)')].at(-1);if(el?.textContent.includes('NEW BOXED ANSWER')){const cs=getComputedStyle(el),r=el.getBoundingClientRect();window.answerFrames.push({box:cs.backgroundColor,border:cs.borderTopWidth,opacity:cs.opacity,cols:cs.columnCount,w:r.width,h:r.height})}if(window.captureAnswer)requestAnimationFrame(capture)}requestAnimationFrame(capture)});
 await page.locator('#cmd').fill('Please explain the synthetic review');await page.locator('#cmdForm .go').click();await expect(page.locator('#log .bot').last()).toContainText('NEW BOXED ANSWER');
 await expect.poll(()=>page.evaluate(()=>window.answerFrames.length)).toBeGreaterThanOrEqual(10);
 const frames=await page.evaluate(()=>{window.captureAnswer=false;return window.answerFrames});
 expect(frames.every(x=>x.opacity==='1'&&x.box!=='rgba(0, 0, 0, 0)'&&parseFloat(x.border)>0)).toBe(true);
 expect(new Set(frames.map(x=>JSON.stringify([x.cols,x.w,x.h]))).size).toBe(1);
});

for(const [width,height] of [[1280,720],[1024,600],[390,700],[320,568]])test(`copy full original chat messages at ${width}x${height}`,async({page,context})=>{
 await context.grantPermissions(['clipboard-read','clipboard-write']);await open(page,width,height);
 await page.evaluate(()=>{const write=navigator.clipboard.writeText.bind(navigator.clipboard);navigator.clipboard.writeText=text=>{window.lastCopiedSource=text;return write(text)}});
 if(width<900)await page.locator('#chatOpen').click();else await page.locator('#chatExpand').click();
 const log=page.locator('#histLog');
 for(const [role,text] of [['you',userText],['bot',original]]){
  const message=log.locator('.e.'+role).last(),copy=message.getByRole('button',{name:role==='you'?'Copy your message':'Copy assistant message',exact:true});
  await expect(copy).toBeVisible();await copy.scrollIntoViewIfNeeded();await copy.focus();await page.keyboard.press('Enter');
  await expect.poll(()=>page.evaluate(()=>window.lastCopiedSource)).toBe(text);
  // The Windows system clipboard exposes CRLF even when writeText receives LF.
  await expect.poll(()=>page.evaluate(async()=>(await navigator.clipboard.readText()).replace(/\r\n/g,'\n'))).toBe(text);
  await expect(copy).toHaveText('Copied');
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
