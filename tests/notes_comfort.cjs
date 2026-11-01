const {chromium}=require('@playwright/test');
const path=require('node:path');const ROOT=path.resolve(__dirname,'..');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{for(const width of [1440,1024,768,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}});
  let saved={html:'<div>Connect with existing donors today.</div><h2>Today’s Task</h2><ol><li>Plan volunteer outreach</li></ol>',revision:1};
  await page.route('http://notes.test/**',async route=>{
   if(route.request().url().endsWith('/notes')){
    const data=route.request().postDataJSON();if(data?.action==='save')saved={html:data.html,revision:saved.revision+1};
    return route.fulfill({json:{locked:false,...saved}});
   }
   return route.fulfill({contentType:'text/html',body:'<style>*{box-sizing:border-box}body{margin:0;font-family:Arial}button,select,input{font:inherit}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}</style><section id="donorsPage"><header class="donor-head"><button id="donorBulk">Bulk</button></header></section>'});
  });
  await page.goto('http://notes.test/');
  await page.addStyleTag({path:ROOT+'/studio.css'});await page.addStyleTag({path:ROOT+'/notes.css'});await page.addScriptTag({path:ROOT+'/notes.js'});
  await page.locator('#donorNotesShortcut').click();await page.locator('#notesEditor').waitFor();
  const metrics=await page.evaluate(()=>{
   const paper=document.querySelector('.notes-paper'),editor=document.querySelector('.notes-editor');
   const p=paper.getBoundingClientRect(),e=editor.getBoundingClientRect();
   return {border:getComputedStyle(paper).borderTopWidth,top:e.top+parseFloat(getComputedStyle(editor).paddingTop),left:e.left+parseFloat(getComputedStyle(editor).paddingLeft),width:p.width,bottom:p.bottom,outer:getComputedStyle(document.querySelector('dialog')).borderTopWidth,overflow:document.documentElement.scrollWidth>innerWidth};
  });
  assert.equal(metrics.border,'1px',`writing border at ${width}`);assert.equal(metrics.outer,'0px');assert.equal(metrics.overflow,false);
  assert(metrics.top<(width>720&&width<1100?155:115),`text starts higher at ${width}: ${metrics.top}`);
  assert(metrics.bottom>=870,`paper uses available height at ${width}`);
  if(width>=1100){
   await page.mouse.move(100,18);
   const aligned=await page.evaluate(()=>{const a=document.querySelector('.notes-headline').getBoundingClientRect(),b=document.querySelector('.notes-toolbar').getBoundingClientRect();return Math.abs(a.top+a.height/2-b.top-b.height/2)<3});
   assert(aligned,'toolbar shares title row');assert(metrics.left>=width/2-400,'centered reading column');
  }else if(width<=720){
   await page.locator('#foundationNotes').dispatchEvent('pointerdown',{pointerType:'touch',clientX:10,clientY:12});
   await page.locator('.notes-toolbar').waitFor({state:'visible'});
   await page.locator('#foundationNotes').dispatchEvent('pointerdown',{pointerType:'touch',clientX:10,clientY:12});
  }
  await page.locator('#notesEditor').fill('Synthetic note updated');
  await page.locator('#notesEditor').press('ControlOrMeta+A');
  await page.mouse.move(100,18);
  await page.locator('.notes-toolbar').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Bold',exact:true}).click();
  await page.waitForTimeout(1100);assert(saved.html.includes('Synthetic note updated'));assert(/<(b|strong)>/.test(saved.html),'formatting saves');
  if(process.env.NOTES_SCREENSHOTS)await page.screenshot({path:path.join(process.env.NOTES_SCREENSHOTS,`notes-${width}.png`)});
  await page.close();console.log(`PASS ${width}px: border, layout, controls, autosave`);
 }}finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});




