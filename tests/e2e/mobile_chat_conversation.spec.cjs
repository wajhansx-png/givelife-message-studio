const {test,expect}=require('@playwright/test');

// Synthetic conversation only. No WhatsApp requests or donor mutations.
const turns=[
 {who:'you',text:'Hi',t:1,turn_id:'mobile-user-hi'},
 {who:'app',text:'Hi!',t:2,turn_id:'mobile-bot-hi'},
 {who:'you',text:'Can you check this message?',t:3,turn_id:'mobile-user-question'},
 {who:'app',text:'✓ Sent to the test group.',t:4,turn_id:'mobile-bot-result'},
 {who:'app',text:'Summary:\n\nThe case is complete. No messages should go to donors until a new case starts.\n\n1. Review the latest receipts.\n2. Keep the previous history.\n3. Verify every confirmation before reporting success.',t:5,turn_id:'mobile-bot-long'}
];

async function showChat(page,width,height){
 await page.setViewportSize({width,height});
 await page.addInitScript(()=>{
   localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');
   localStorage.setItem('givelife-theme','dark');
 });
 await page.route('**/chat',route=>route.fulfill({json:{items:turns}}));
 await page.goto('/');
 await expect(page.locator('#leftChip')).toContainText('25,000');
 await page.locator('#chatOpen').click();
 await expect(page.locator('#histLog .e.bot')).toHaveCount(3);
 await page.evaluate(()=>document.fonts.ready);
}

for(const [w,h] of [[320,568],[360,640],[390,844],[412,915],[768,900]]){
 test('mobile chat is readable with unobstructed Copy at '+w+'x'+h,async({page})=>{
  await showChat(page,w,h);
  const audit=await page.evaluate(()=>{
    const log=document.querySelector('#histLog');
    const bots=[...log.querySelectorAll(':scope > .e.bot:not(.dots)')];
    const users=[...log.querySelectorAll(':scope > .e.you')];
    const getRect=n=>n.getBoundingClientRect();
    const copyBelow=b=>{
      const c=b.querySelector(':scope > .message-copy');
      const contents=[...b.children].filter(n=>n!==c);
      return c&&contents.length&&getRect(c).top>=Math.max(...contents.map(n=>getRect(n).bottom))-1;
    };
    const assistant=bots[0], user=users[0], shortLine=assistant.querySelector('.reply-line');
    const replyStyle=getComputedStyle(assistant),userBubble=user.querySelector('.message-text');
    return {
      botWidth:getRect(assistant).width,
      logWidth:getRect(log).width,
      botTransparent:replyStyle.backgroundColor==='rgba(0, 0, 0, 0)'&&replyStyle.backgroundImage==='none',
      botReadable:getRect(shortLine).width>=90&&getRect(shortLine).height<45,
      botCopyBelow:bots.every(copyBelow),
      userCopyBelow:users.every(copyBelow),
      userBubbleWidth:getRect(userBubble).width,
      userBubbleRight:getRect(userBubble).right,
      logRight:getRect(log).right,
      horizontalOverflow:document.documentElement.scrollWidth>innerWidth+1,
      buttonWidth:getRect(assistant.querySelector('.message-copy')).width,
      userContent:userBubble.textContent
    };
  });
  expect(audit.botTransparent,'AI text must not be trapped in oversized cards').toBe(true);
  expect(audit.botReadable,'Hi! should be a single readable line, not stacked vertically').toBe(true);
  expect(audit.botWidth).toBeGreaterThan(audit.logWidth*.65);
  expect(audit.botCopyBelow,'Copy must be below the assistant text').toBe(true);
  expect(audit.userCopyBelow,'Copy must be below the user bubble').toBe(true);
  expect(audit.userBubbleWidth,'Hi should remain a compact bubble').toBeLessThan(130);
  expect(audit.userBubbleRight).toBeLessThanOrEqual(audit.logRight+1);
  expect(audit.horizontalOverflow).toBe(false);
  expect(audit.buttonWidth,'Copy must remain easily tappable').toBeGreaterThanOrEqual(44);
  expect(audit.userContent).toBe('Hi');

  // Scroll and keyboard focus must not cause horizontal overflow.
  await page.locator('#histCmd').focus();
  await page.locator('#histCmd').fill('Follow-up message');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 });
}

for(const [width,height] of [[320,568],[390,844],[768,900]]){
 for(const theme of ['dark','light']){
  test('mobile chat canvas keeps the same color '+theme+' '+width+'x'+height,async({page})=>{
   await page.setViewportSize({width,height});
   await page.addInitScript(theme=>{
    localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');
    localStorage.setItem('givelife-theme',theme);
   },theme);
   await page.route('**/chat',route=>route.fulfill({json:{items:turns}}));
   await page.goto('/');
   await expect(page.locator('#chatOpen')).toBeVisible();
   await page.locator('#chatOpen').click();
   const colors=await page.evaluate(()=>{
    const selectors=['#hist','#hist > header','#histLog','#hist .chat-return','#histNextActions'];
    return selectors.map(selector=>{
     const element=document.querySelector(selector),style=getComputedStyle(element);
     return {selector,color:style.backgroundColor,image:style.backgroundImage};
    });
   });
   expect(new Set(colors.map(item=>item.color)).size,'Each chat section must be one color').toBe(1);
   expect(colors.every(item=>item.image==='none'),'No separate gradient should interrupt the chat').toBe(true);
  });
 }
}
