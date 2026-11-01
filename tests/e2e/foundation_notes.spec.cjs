const {test,expect}=require('@playwright/test');
const auth={Authorization:'Bearer manual-fix-preview-key'};
async function open(page,request,width=1280,height=800){
 await page.setViewportSize({width,height});
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await request.post('/__test/seed',{headers:auth,data:{reply:'Ready.',reset_notes:true}});
 await page.goto('/');
 await page.locator('#openDonors').click();
 await page.locator('#donorNotesShortcut').click();
 await expect(page.locator('#foundationNotes')).toBeVisible();
}
test('private notes: password, autosave, reload, desktop remembrance and lock',async({page,request})=>{
 await open(page,request);
 await expect(page.locator('#notesLocked')).toBeVisible();
 await page.locator('#notesPassword').fill('wrong');
 await page.locator('#notesUnlockButton').click();
 await expect(page.locator('#notesError')).toContainText('Incorrect');
 await page.locator('#notesPassword').fill('test-preview-only-pin');
 await page.locator('#notesUnlockButton').click();
 const editor=page.locator('#notesEditor');
 await expect(editor).toBeVisible();
 await editor.fill('Plan student volunteer outreach');
 await expect(page.locator('#notesSync')).toHaveText('Saved',{timeout:10000});
 await page.mouse.move(100,18); // reveal hidden navigation as a user would
 await page.locator('#notesBack').click();
 await page.locator('#donorNotesShortcut').click();
 await expect(editor).toContainText('Plan student volunteer outreach');
 await expect(page.locator('#notesLocked')).toBeHidden();
 await page.reload();
 if(!(await page.locator('#donorsPage').isVisible()))await page.locator('#openDonors').click();
 await page.locator('#donorNotesShortcut').click();
 await expect(page.locator('#notesLocked')).toBeHidden();
 await expect(editor).toContainText('Plan student volunteer outreach');
 await page.mouse.move(100,18);
 await page.locator('#notesLock').click();
 await expect(page.locator('#notesLocked')).toBeVisible();
 await page.mouse.move(100,18); // reveal hidden navigation as a user would
 await page.mouse.move(100,18);
 await page.locator('#notesBack').click();
 await page.locator('#donorNotesShortcut').click();
 await expect(page.locator('#notesLocked')).toBeVisible();
 expect(await page.evaluate(()=>localStorage.getItem('givelife-notes-password'))).toBeNull();
});
test('phone notes: readable editing surface, toolbar and no sideways scrolling',async({page,request})=>{
 await open(page,request,390,844);
 await page.locator('#notesPassword').fill('test-preview-only-pin');
 await page.locator('#notesUnlockButton').click();
 const editor=page.locator('#notesEditor');
 await expect(editor).toBeVisible();
 await editor.fill('Find university representatives');
 await editor.press('ControlOrMeta+A');
 // Formatting controls are hidden until the pointer reaches the top.
 await page.mouse.move(130,18);
 await expect(page.locator('.notes-toolbar')).toBeVisible();
 await page.getByRole('button',{name:'Bold',exact:true}).click();
 await expect(editor.locator('b,strong')).toContainText('Find university representatives');
 await page.locator('#notesStyle').selectOption('h2');
 await expect(editor.locator('h2')).toHaveCount(1);
 await expect(page.locator('#notesSync')).toHaveText('Saved',{timeout:10000});
 const wide=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
 expect(wide).toBe(false);
 const bar=await page.locator('.notes-toolbar').boundingBox();
 expect(bar.x+bar.width).toBeLessThanOrEqual(391);
});

test('mobile virtual keyboard keeps Notes paper tall while the caret stays visible',async({page,request})=>{
 await open(page,request,390,844);
 await page.locator('#notesPassword').fill('test-preview-only-pin');
 await page.locator('#notesUnlockButton').click();
 const editor=page.locator('#notesEditor');
 await expect(editor).toBeVisible();
 // Opening Notes must not force the mobile keyboard until the user taps the page.
 expect(await page.evaluate(()=>document.activeElement?.id)).not.toBe('notesEditor');
 const initial=await page.evaluate(()=>({
  paper:document.querySelector('.notes-paper').getBoundingClientRect().height,
  scroller:document.querySelector('.notes-paper-scroll').getBoundingClientRect().height
 }));
 await editor.fill(Array.from({length:36},(_,i)=>'Foundation idea '+(i+1)).join('\\n'));
 await editor.focus();
 // Mobile Chromium has no native keyboard, so resize the visual viewport as an
 // Android keyboard does with interactive-widget=resizes-content.
 await page.setViewportSize({width:390,height:460});
 await expect(page.locator('#foundationNotes')).toHaveAttribute('data-keyboard','open');
 const smaller=await page.evaluate(()=>{
  const paper=document.querySelector('.notes-paper'),scroller=document.querySelector('.notes-paper-scroll');
  const bar=document.querySelector('.notes-toolbar');
  const bounds=scroller.getBoundingClientRect();
  return {paper:paper.getBoundingClientRect().height,scroller:bounds.height,
   toolbar:bar.getBoundingClientRect().height,
   xOverflow:document.documentElement.scrollWidth>innerWidth+1,
   scrollable:scroller.scrollHeight>scroller.clientHeight+20,
   keyboardOverlay:bounds.bottom>innerHeight+1};
 });
 expect(smaller.paper).toBeGreaterThanOrEqual(initial.paper-8);
 expect(smaller.scroller).toBeGreaterThan(150);
 expect(smaller.toolbar).toBeLessThanOrEqual(50);
 expect(smaller.scrollable).toBe(true);
 expect(smaller.xOverflow).toBe(false);
 expect(smaller.keyboardOverlay).toBe(false);
 await editor.press('End');
 await editor.type(' Extra mobile update');
 await expect(editor).toContainText('Extra mobile update');
 await page.setViewportSize({width:390,height:844});
 await expect(page.locator('#foundationNotes')).toHaveAttribute('data-keyboard','closed');
 expect((await page.locator('.notes-paper-scroll').boundingBox()).height).toBeGreaterThan(smaller.scroller);
});

test('quiet Notes keeps only writing visible; top-edge reveals controls and fullscreen',async({page,request})=>{
 await open(page,request,1280,800);
 await page.locator('#notesPassword').fill('test-preview-only-pin');
 await page.locator('#notesUnlockButton').click();
 await expect(page.locator('#notesEditor')).toBeVisible();
 const head=page.locator('.notes-head'),toolbar=page.locator('.notes-toolbar');
 // Pointer starts away from the top after entry so editing is distraction-free.
 await page.mouse.move(920,600);
 await expect(head).toBeHidden();
 await expect(toolbar).toBeHidden();
 const colors=await page.evaluate(()=>{
  const page=document.getElementById('foundationNotes');
  const paper=document.querySelector('.notes-paper');
  const editor=document.getElementById('notesEditor');
  return {
   page:getComputedStyle(page).backgroundColor,
   paper:getComputedStyle(paper).backgroundColor,
   editor:getComputedStyle(editor).backgroundColor,
   border:getComputedStyle(paper).borderTopWidth,
   outline:getComputedStyle(editor).outlineStyle,
   shadow:getComputedStyle(paper).boxShadow
  };
 });
 expect(colors.page).toBe('rgb(36, 36, 36)');
 expect(colors.paper).toBe('rgba(0, 0, 0, 0)');
 expect(colors.editor).toBe('rgba(0, 0, 0, 0)');
 expect(colors.border).toBe('0px');
 expect(colors.outline).toBe('none');
 expect(colors.shadow).toBe('none');
 await page.locator('#notesEditor').fill('A focused foundation idea');
 await expect(toolbar).toBeHidden();
 await page.mouse.move(100,18);
 await expect(head).toBeVisible();
 await expect(toolbar).toBeVisible();
 await expect(page.getByRole('button',{name:'Full screen',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Full screen',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(true);
 await page.evaluate(()=>document.exitFullscreen());
 await page.mouse.move(920,600);
 await expect(toolbar).toBeHidden();
 await page.keyboard.press('Alt+t');
 await expect(toolbar).toBeVisible();
 await expect(page.locator('#notesStyle')).toBeFocused();
 await page.keyboard.press('Escape');
 await expect(toolbar).toBeHidden();
});
test('mobile Notes opens a hidden toolbar by tapping top edge without shrinking editor',async({page,request})=>{
 await open(page,request,390,844);
 await page.locator('#notesPassword').fill('test-preview-only-pin');
 await page.locator('#notesUnlockButton').click();
 await expect(page.locator('#notesEditor')).toBeVisible();
 await expect(page.locator('.notes-toolbar')).toBeHidden();
 const height=(await page.locator('.notes-paper').boundingBox()).height;
 await page.locator('#foundationNotes').dispatchEvent('pointerdown',{pointerType:'touch',clientX:12,clientY:16});
 await expect(page.locator('.notes-toolbar')).toBeVisible();
 await page.locator('#notesStyle').selectOption('h2');
 await page.locator('#notesEditor').fill('Volunteer outreach');
 expect((await page.locator('.notes-paper').boundingBox()).height).toBeGreaterThanOrEqual(height-2);
 await page.locator('#foundationNotes').dispatchEvent('pointerdown',{pointerType:'touch',clientX:12,clientY:16});
 await expect(page.locator('.notes-toolbar')).toBeHidden();
});

test('desktop note-taking: type, select, style, save, reopen and keep writing focus',async({page,request})=>{
 await open(page,request,1440,900);
 await page.locator('#notesPassword').fill('test-preview-only-pin');
 await page.locator('#notesUnlockButton').click();
 const editor=page.locator('#notesEditor');
 await editor.fill('Meet university donors and plan outreach');
 await expect(page.locator('#notesSync')).toHaveText('Saved',{timeout:10000});
 await page.mouse.move(850,620);
 await expect(page.locator('.notes-toolbar')).toBeHidden();
 await editor.focus();await editor.press('ControlOrMeta+A');
 await page.mouse.move(160,18);
 await page.getByRole('button',{name:'Bold',exact:true}).click();
 const selectedHtml=await editor.innerHTML();
 expect(selectedHtml,'Bold must apply visibly to the selected note text').toMatch(/<(?:b|strong)\b|font-weight\s*:\s*(?:bold|700)/i);
 await expect(page.locator('#notesSync')).toHaveText('Saved',{timeout:10000});
 await page.mouse.move(900,610);
 await expect(page.locator('.notes-toolbar')).toBeHidden();
 const editorHeight=(await editor.boundingBox()).height;
 await editor.focus();
 await editor.press('End');
 await editor.press('Enter');
 await editor.type('New volunteer recruitment ideas');
 await expect(editor).toContainText('New volunteer recruitment ideas');
 await expect(page.locator('#notesSync')).toHaveText('Saved',{timeout:10000});
 expect((await editor.boundingBox()).height).toBeGreaterThanOrEqual(editorHeight-2);
 await page.mouse.move(110,18);
 await page.locator('#notesBack').click();
 await page.locator('#donorNotesShortcut').click();
 await expect(editor).toContainText('Meet university donors');
 await expect(editor).toContainText('New volunteer recruitment ideas');
});
test('narrow phone: controls fit, text stays legible, touch reveals and hides tools',async({page,request})=>{
 await open(page,request,320,680);
 await page.locator('#notesPassword').fill('test-preview-only-pin');
 await page.locator('#notesUnlockButton').click();
 const editor=page.locator('#notesEditor');
 await expect(editor).toBeVisible();
 await expect(page.locator('.notes-toolbar')).toBeHidden();
 await editor.fill('Contact committed donors today.');
 await expect(page.locator('#notesSync')).toHaveText('Saved',{timeout:10000});
 await page.locator('#foundationNotes').dispatchEvent('pointerdown',{pointerType:'touch',clientX:10,clientY:12});
 await expect(page.locator('.notes-toolbar')).toBeVisible();
 const bounds=await page.evaluate(()=>{
  const screen=document.getElementById('foundationNotes').getBoundingClientRect();
  const back=document.getElementById('notesBack').getBoundingClientRect();
  const lock=document.getElementById('notesLock').getBoundingClientRect();
  const full=document.getElementById('notesFullscreen').getBoundingClientRect();
  const bar=document.querySelector('.notes-toolbar').getBoundingClientRect();
  return {screen:[screen.left,screen.right],back:[back.left,back.right],lock:[lock.left,lock.right],
   full:[full.left,full.right],toolbar:[bar.left,bar.right],overflow:document.documentElement.scrollWidth>innerWidth+1};
 });
 expect(bounds.back[0]).toBeGreaterThanOrEqual(0);
 expect(bounds.full[1]).toBeLessThanOrEqual(321);
 expect(bounds.lock[1]).toBeLessThanOrEqual(321);
 expect(bounds.back[1]).toBeLessThan(bounds.lock[0]);
 expect(bounds.lock[1]).toBeLessThan(bounds.full[0]);
 expect(bounds.toolbar[1]).toBeLessThanOrEqual(321);
 expect(bounds.overflow).toBe(false);
 await page.locator('#foundationNotes').dispatchEvent('pointerdown',{pointerType:'touch',clientX:10,clientY:12});
 await expect(page.locator('.notes-toolbar')).toBeHidden();
 await page.setViewportSize({width:320,height:400});
 await editor.focus();
 await expect(page.locator('#foundationNotes')).toHaveAttribute('data-keyboard','open');
 expect((await page.locator('.notes-paper').boundingBox()).height).toBeGreaterThan(400);
});
