/* Private foundation notebook. The password stays on the server, not in localStorage. */
(()=>{
 const donor=document.getElementById('donorsPage');
 if(!donor)return;
 const make=(tag,klass,text)=>{const e=document.createElement(tag);if(klass)e.className=klass;if(text!==undefined)e.textContent=text;return e};
 const button=make('button','donor-notes-shortcut','Notes');
 button.type='button';button.id='donorNotesShortcut';button.setAttribute('aria-label','Open private foundation notes');
 const header=donor.querySelector('.donor-head');
 header?.insertBefore(button,header.querySelector('#donorBulk'));

 const page=make('dialog','foundation-notes');
 page.id='foundationNotes';page.setAttribute('aria-label','Private foundation notes');
 page.innerHTML=String.raw`
   <section class="notes-shell">
    <header class="notes-head">
     <button class="notes-back" type="button" id="notesBack" aria-label="Back to Donors">← Back</button>
     <div class="notes-headline"><span class="notes-kicker">GIVELIFE FOUNDATION</span><h1>My Notes</h1></div>
     <span class="notes-sync" id="notesSync" role="status" aria-live="polite"></span>
     <button type="button" class="notes-lock" id="notesLock" hidden>Lock</button>
     <button type="button" class="notes-fullscreen" id="notesFullscreen" aria-pressed="false" title="Hide browser chrome while writing">Full screen</button>
    </header>
    <div class="notes-center" id="notesLocked" hidden>
      <div class="notes-unlock">
       <div class="notes-lock-icon" aria-hidden="true">✦</div>
       <h2>Private ideas, all in one place.</h2>
       <p>Only you can read or edit this notebook. Unlock it once on your desktop and it will remember this browser.</p>
       <form id="notesUnlockForm" autocomplete="off">
        <label for="notesPassword">Notes password</label>
        <div class="notes-password-row"><input id="notesPassword" type="password" name="notes_password" autocomplete="current-password" required placeholder="Enter password" aria-label="Notes password"><button class="notes-primary" type="submit" id="notesUnlockButton">Unlock notes</button></div>
        <p class="notes-error" id="notesError" role="alert"></p>
       </form>
       <small>Access is remembered on this browser. You can lock it manually at any time.</small>
      </div>
    </div>
    <section class="notes-workspace" id="notesWorkspace" hidden>
      <div class="notes-toolbar" role="toolbar" aria-label="Format your notes">
        <label class="notes-select-label"><span class="sr-only">Text style</span><select id="notesStyle" aria-label="Text style"><option value="p">Normal text</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option><option value="h3">Heading 3</option></select></label>
        <span class="notes-separator" aria-hidden="true"></span>
        <button type="button" data-command="bold" aria-label="Bold" title="Bold (Ctrl+B)"><b>B</b></button>
        <button type="button" data-command="italic" aria-label="Italic" title="Italic (Ctrl+I)"><i>I</i></button>
        <span class="notes-separator" aria-hidden="true"></span>
        <button type="button" data-command="insertUnorderedList" aria-label="Bulleted list" title="Bulleted list">☷</button>
        <button type="button" data-command="insertOrderedList" aria-label="Numbered list" title="Numbered list">1.</button>
        <button type="button" id="notesChecklist" aria-label="Checklist" title="Checklist">☑</button>
        <span class="notes-separator" aria-hidden="true"></span>
        <label class="notes-color-wrap" title="Text color"><span class="sr-only">Text color</span><select id="notesColor" aria-label="Text color">
         <option value="">Color</option><option value="#d5d9e0">Slate</option><option value="#85b7f6">Blue</option>
         <option value="#8ddfba">Green</option><option value="#efc389">Amber</option><option value="#f4a4ad">Red</option>
         <option value="#c7aff6">Purple</option>
        </select></label>
      </div>
      <div class="notes-paper-scroll">
       <main class="notes-paper">
        <div id="notesEditor" class="notes-editor" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Your foundation notes" data-placeholder="" spellcheck="true"></div>
       </main>
      </div>
      <footer class="notes-foot"><span id="notesHint">Your ideas are private · Saved to GiveLife</span><button type="button" id="notesRetry" hidden>Retry save</button></footer>
    </section>
   </section>`;
 document.body.append(page);
 const el=id=>document.getElementById(id);
 const editor=el('notesEditor'),sync=el('notesSync'),retry=el('notesRetry');
 let revision=0,loaded=false,dirty=false,saving=false,saveTimer=null,retryDelay=0;
 // Writing mode is fully quiet. Hover the top 125px (desktop), tap the top
 // edge (touch), or press Alt+T (keyboard) to reveal actions. Editor focus
 // alone must NOT reveal the toolbar: typing should never feel distracting.
 const notesHead=page.querySelector('.notes-head'),notesToolbar=page.querySelector('.notes-toolbar');
 const fullscreenButton=el('notesFullscreen');
 // Wide screens share one controls row; touch layouts retain their separate
 // horizontally scrollable toolbar. Moving the same nodes keeps selections
 // and formatting handlers intact.
 const wideNotes=matchMedia('(min-width:1100px)');
 function placeToolbar(){
  if(wideNotes.matches&&page.dataset.mode==='writing')notesHead.insertBefore(notesToolbar,sync);
  else el('notesWorkspace').prepend(notesToolbar);
 }
 placeToolbar();wideNotes.addEventListener('change',placeToolbar);
 page.dataset.mode='loading';
 page.dataset.controls='closed';
 function revealControls(){if(page.dataset.mode==='writing')page.dataset.controls='open'}
 function concealControls(force=false){
  if(page.dataset.mode!=='writing')return;
  if(!force&&(notesHead.contains(document.activeElement)||notesToolbar.contains(document.activeElement)))return;
  page.dataset.controls='closed';
 }
 page.addEventListener('pointermove',event=>{
  if(page.dataset.mode!=='writing'||event.pointerType==='touch')return;
  const top=event.clientY-page.getBoundingClientRect().top;
  if(top<=125)revealControls();
  else if(top>160&&!notesHead.contains(event.target)&&!notesToolbar.contains(event.target))concealControls(true);
 });
 page.addEventListener('pointerleave',()=>concealControls());
 page.addEventListener('pointerdown',event=>{
  if(event.pointerType!=='touch'||page.dataset.mode!=='writing')return;
  const top=event.clientY-page.getBoundingClientRect().top;
  if(top<=38&&!notesHead.contains(event.target)&&!notesToolbar.contains(event.target)){
   event.preventDefault();
   page.dataset.controls=page.dataset.controls==='open'?'closed':'open';
  }
 });
 page.addEventListener('focusin',event=>{
  if(notesHead.contains(event.target)||notesToolbar.contains(event.target))revealControls();
 });
 let shortcutFocusPending=false,shortcutFocusRevision=0;
 page.addEventListener('pointerdown',()=>{shortcutFocusRevision++},true);
 document.addEventListener('keyup',event=>{
  if(event.key!=='Alt'||!shortcutFocusPending)return;
  shortcutFocusPending=false;
  requestAnimationFrame(()=>{
   if(page.open&&page.dataset.mode==='writing'&&page.dataset.controls==='open')
    el('notesStyle').focus({preventScroll:true});
  });
 });
 document.addEventListener('keydown',event=>{
  if(!page.open||page.dataset.mode!=='writing')return;
  if(event.altKey&&!event.ctrlKey&&!event.metaKey&&event.key.toLowerCase()==='t'){
   event.preventDefault();
   page.dataset.controls=page.dataset.controls==='open'?'closed':'open';
   // Alt keyup is the reliable moment: Chromium may restore the editor's
   // focus when the modifier is released, undoing focus set on keydown.
   shortcutFocusPending=page.dataset.controls==='open';
   if(shortcutFocusPending){
    const revision=++shortcutFocusRevision;
    // Some browsers restore the contenteditable focus after Alt keyup.
    // One guarded post-keyboard retry prevents that without stealing focus
    // from any subsequent pointer interaction.
    setTimeout(()=>{
     if(page.open&&revision===shortcutFocusRevision&&page.dataset.controls==='open')
      el('notesStyle').focus({preventScroll:true});
    },140);
   }
  }
  if(event.key==='Escape'&&page.dataset.controls==='open'&&!document.fullscreenElement){
   event.preventDefault();event.stopPropagation();concealControls(true);editor.focus({preventScroll:true});
  }
 });
 async function toggleFullscreen(){
  try{
   if(document.fullscreenElement){await document.exitFullscreen();return}
   // Native fullscreen rejects modal <dialog> in some browsers. Fullscreen the
   // document instead; its open Notes dialog remains the topmost visible layer.
   const target=document.documentElement;
   if(typeof target.requestFullscreen!=='function'){
    setStatus('Full screen is unavailable on this browser.',true);return;
   }
   await target.requestFullscreen({navigationUI:'hide'});
  }catch(_){setStatus('Browser did not allow full screen.',true)}
 }
 fullscreenButton.addEventListener('click',toggleFullscreen);
 let notesWasFullscreen=false;
 document.addEventListener('fullscreenchange',()=>{
  const active=!!document.fullscreenElement;
  fullscreenButton.textContent=active?'Exit full screen':'Full screen';
  fullscreenButton.setAttribute('aria-pressed',String(active));
  if(active&&page.open){notesWasFullscreen=true;return}
  if(!active&&notesWasFullscreen&&page.open){
   notesWasFullscreen=false;
   // Chromium sometimes leaves the modal inert after a document-level
   // fullscreen transition. Reopen the same dialog to restore its top layer
   // without reloading Notes or touching the unsaved editor content.
   const scroll=paperScroll.scrollTop;
   page.close();page.showModal();
   paperScroll.scrollTop=scroll;
   scheduleSize();
   concealControls(true);
   if(!mobileNotes.matches)requestAnimationFrame(()=>{
    if(page.open){editor.focus({preventScroll:true});concealControls(true)}
   });
  }
 });
 // A stable paper height prevents the editor itself from collapsing when a
 // mobile keyboard opens; only its scrollable viewport becomes shorter.
 const mobileNotes=matchMedia('(max-width:720px)');
 const paperScroll=page.querySelector('.notes-paper-scroll');
 let expandedHeight=0,lastMobileWidth=0,caretFrame=0,layoutFrame=0;
 function revealCaret(){
  if(!page.open||document.activeElement!==editor||!paperScroll)return;
  const selection=window.getSelection();
  if(!selection||!selection.rangeCount)return;
  const range=selection.getRangeAt(0).cloneRange();
  range.collapse(false);
  const caret=range.getBoundingClientRect(),viewport=paperScroll.getBoundingClientRect();
  if(!caret.height&&!caret.width)return;
  const padding=28;
  if(caret.bottom>viewport.bottom-padding)paperScroll.scrollTop+=caret.bottom-(viewport.bottom-padding);
  else if(caret.top<viewport.top+padding)paperScroll.scrollTop-=viewport.top+padding-caret.top;
 }
 function scheduleCaret(){
  cancelAnimationFrame(caretFrame);
  caretFrame=requestAnimationFrame(()=>requestAnimationFrame(revealCaret));
 }
 function sizeForKeyboard(){
  if(!page.open)return;
  if(!mobileNotes.matches){
   page.dataset.keyboard='closed';
   for(const key of ('--notes-visible-height','--notes-visible-top','--notes-paper-min-height'))page.style.removeProperty(key);
   expandedHeight=0;lastMobileWidth=0;return;
  }
  const visual=window.visualViewport;
  const visibleHeight=Math.min(window.innerHeight,visual?.height||window.innerHeight);
  if(lastMobileWidth!==window.innerWidth){
   lastMobileWidth=window.innerWidth;
   expandedHeight=Math.max(window.innerHeight,visibleHeight);
  }
  if(!expandedHeight)expandedHeight=Math.max(window.innerHeight,visibleHeight);
  const focused=document.activeElement===editor||document.activeElement===el('notesPassword');
  const keyboard=(focused||page.dataset.keyboard==='open')&&expandedHeight-visibleHeight>120;
  if(!keyboard&&!focused)expandedHeight=Math.max(expandedHeight,visibleHeight);
  page.dataset.keyboard=keyboard?'open':'closed';
  page.style.setProperty('--notes-paper-min-height',Math.round(Math.max(380,expandedHeight-80))+'px');
  if(keyboard){
   page.style.setProperty('--notes-visible-height',Math.round(visibleHeight)+'px');
   page.style.setProperty('--notes-visible-top',Math.round(visual?.offsetTop||0)+'px');
   scheduleCaret();
  }else{
   page.style.removeProperty('--notes-visible-height');
   page.style.removeProperty('--notes-visible-top');
  }
 }
 function scheduleSize(){
  cancelAnimationFrame(layoutFrame);
  layoutFrame=requestAnimationFrame(sizeForKeyboard);
 }
 window.addEventListener('resize',scheduleSize);
 window.addEventListener('orientationchange',()=>{expandedHeight=0;lastMobileWidth=0;scheduleSize()});
 if(window.visualViewport){
  window.visualViewport.addEventListener('resize',scheduleSize);
  window.visualViewport.addEventListener('scroll',scheduleSize);
 }
 page.addEventListener('focusin',scheduleSize);
 page.addEventListener('focusout',()=>setTimeout(scheduleSize,180));
 editor.addEventListener('input',scheduleCaret);
 editor.addEventListener('keyup',scheduleCaret);

 const setStatus=(s,error=false)=>{sync.textContent=s;sync.dataset.error=String(error)};
 async function request(body){
  const r=await fetch('/notes',body===undefined?{credentials:'same-origin'}:{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let response;try{response=await r.json()}catch(e){throw Error('Notes server did not respond correctly.')}
  if(!r.ok)throw Error(response.error||'Unable to save notes.');
  return response;
 }
 function screen(locked){
  el('notesLocked').hidden=!locked;
  el('notesWorkspace').hidden=locked;
  el('notesLock').hidden=locked;
  page.dataset.mode=locked?'locked':'writing';
  placeToolbar();
  page.dataset.controls='closed';
 }
 async function load(){
  setStatus('Loading…');
  try{
   const r=await request();
   if(r.locked){loaded=false;screen(true);setStatus('Locked');return}
   if(!dirty||!loaded){
    editor.innerHTML=r.html||'';
    revision=r.revision||0;
    dirty=false;loaded=true;
   }
   screen(false);setStatus(dirty?'Unsaved changes':'Saved');
  }catch(e){setStatus(e.message,true);retry.hidden=false}
 }
 let notesRoute='donors/all/notes',notesParentState=null;
 async function open(){
  const restoring=Nav.path().endsWith('/notes');
  notesParentState=restoring?window.history.state?.notesParent||null:window.history.state;
  notesRoute=Nav.path().replace(/\/notes$/,'')+'/notes';
  Nav.go(notesRoute);
  if(!restoring)window.history.replaceState({...window.history.state,notesParent:notesParentState},'',location.href);
  if(!page.open)page.showModal();
  scheduleSize();
  await load();
  if(!page.open)return;
  scheduleSize();
  if(el('notesWorkspace').hidden)el('notesPassword').focus({preventScroll:true});
  else if(!mobileNotes.matches)editor.focus({preventScroll:true});
 }
 const rememberDirty=()=>{
  dirty=true;retry.hidden=true;setStatus('Saving…');
  clearTimeout(saveTimer);saveTimer=setTimeout(save,800);
 };
 async function save(){
  clearTimeout(saveTimer);
  if(saving||!dirty||!loaded)return;
  saving=true;const html=editor.innerHTML,base=revision;
  try{
   const r=await request({action:'save',html,revision:base});
   revision=r.revision;dirty=editor.innerHTML!==html;
   retry.hidden=true;setStatus(dirty?'Saving…':'Saved');
  }catch(e){
   dirty=true;setStatus(e.message,true);retry.hidden=false;
  }finally{
   saving=false;
   if(dirty&&retry.hidden)saveTimer=setTimeout(save,350);
  }
 }
 el('notesUnlockForm').addEventListener('submit',async e=>{
  e.preventDefault();
  const pin=el('notesPassword').value,submit=el('notesUnlockButton');
  submit.disabled=true;el('notesError').textContent='';
  try{
   const r=await request({action:'unlock',password:pin});
   el('notesPassword').value='';
   revision=r.revision||0;editor.innerHTML=r.html||'';dirty=false;loaded=true;
   screen(false);setStatus('Saved');scheduleSize();if(!mobileNotes.matches)editor.focus({preventScroll:true});
  }catch(err){el('notesError').textContent=err.message}
  finally{submit.disabled=false}
 });
 editor.addEventListener('input',rememberDirty);
 // Paste text safely rather than allowing clipboard HTML to execute in the editor.
 editor.addEventListener('paste',e=>{e.preventDefault();document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));rememberDirty()});
 let savedRange=null;
 document.addEventListener('selectionchange',()=>{
  if(!page.open||!loaded)return;
  const selection=window.getSelection();
  if(selection?.rangeCount&&editor.contains(selection.anchorNode))savedRange=selection.getRangeAt(0).cloneRange();
 });
 const restoreSelection=()=>{
  editor.focus();
  if(savedRange&&editor.contains(savedRange.commonAncestorContainer)){
   const selection=window.getSelection();selection.removeAllRanges();selection.addRange(savedRange);
  }
 };
 // Keep the selected text while clicking toolbar buttons.
 page.querySelectorAll('.notes-toolbar button').forEach(b=>b.addEventListener('mousedown',e=>e.preventDefault()));
 page.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>{
  restoreSelection();document.execCommand(b.dataset.command,false,null);rememberDirty();
 }));
 const applyBlock=tag=>{
  restoreSelection();document.execCommand('formatBlock',false,tag);rememberDirty();
 };
 el('notesStyle').addEventListener('change',e=>{applyBlock(e.target.value);e.target.value='p'});
 el('notesColor').addEventListener('change',e=>{
  if(!e.target.value)return;
  restoreSelection();document.execCommand('foreColor',false,e.target.value);
  e.target.value='';rememberDirty();
 });
 const findList=()=>{
  let node=window.getSelection()?.anchorNode;
  if(node?.nodeType===3)node=node.parentElement;
  return node?.closest?.('ul,ol')||null;
 };
 el('notesChecklist').addEventListener('click',()=>{
  restoreSelection();
  const old=findList();
  if(old&&old.tagName==='UL'){
   old.classList.toggle('notes-checklist');
  }else{
   document.execCommand('insertUnorderedList',false,null);
   const created=findList();
   if(created?.tagName==='UL')created.classList.add('notes-checklist');
  }
  rememberDirty();
 });
 editor.addEventListener('click',e=>{
  const li=e.target.closest('ul.notes-checklist > li');
  if(!li)return;
  const rect=li.getBoundingClientRect();
  if(e.clientX>rect.left+16)return; // only the checkbox gutter toggles
  li.dataset.checked=li.dataset.checked==='true'?'false':'true';
  rememberDirty();
 });
 // Selection tools are outside the editable document: they never enter saved HTML.
 (()=>{
  const bar=make('div','notes-selection-tools');bar.id='notesSelectionTools';bar.hidden=true;
  bar.setAttribute('role','toolbar');bar.setAttribute('aria-label','Format selected text');
  const style=make('select');style.setAttribute('aria-label','Selected text style');
  for(const [value,label] of [['h2','Heading 2'],['h1','Heading 1'],['h3','Heading 3'],['p','Normal text']]){const option=make('option','',label);option.value=value;style.append(option)}
  bar.append(style);
  const toggleButtons=new Map();
  const command=(label,text,cmd,parent=bar)=>{
   const b=make('button','',text);b.type='button';b.setAttribute('aria-label',label);b.title=label;
   b.addEventListener('pointerdown',e=>e.preventDefault());
   b.onclick=()=>{if(!validRange(savedRange))return;restoreSelection();document.execCommand(cmd,false,null);rememberDirty();if(parent!==bar){extra.hidden=true;more.setAttribute('aria-expanded','false')}queue()};
   if(cmd!=='removeFormat'){toggleButtons.set(cmd,b);b.setAttribute('aria-pressed','false')}
   parent.append(b);return b;
  };
  command('Numbered list','1. List','insertOrderedList');
  const more=make('button','','More');more.type='button';more.setAttribute('aria-label','More formatting');more.setAttribute('aria-expanded','false');
  const extra=make('div','notes-selection-more');extra.hidden=true;extra.id='notesSelectionMore';more.setAttribute('aria-controls',extra.id);bar.append(more,extra);
  more.addEventListener('pointerdown',e=>e.preventDefault());more.onclick=()=>{extra.hidden=!extra.hidden;more.setAttribute('aria-expanded',String(!extra.hidden));positionBar()};
  command('Bold','B','bold',extra);command('Italic','Italic','italic',extra);command('Bulleted list','• List','insertUnorderedList',extra);
  const color=make('select');color.setAttribute('aria-label','Selected text color');
  for(const [value,label] of [['','Color'],['#ededed','Default'],['#85b7f6','Blue'],['#8ddfba','Green'],['#efc389','Amber'],['#f4a4ad','Red'],['#c7aff6','Purple']]){const o=make('option','',label);o.value=value;color.append(o)}
  extra.append(color);
  style.onchange=()=>{if(validRange(savedRange))applyBlock(style.value);queue()};
  color.onchange=()=>{if(color.value&&validRange(savedRange)){restoreSelection();document.execCommand('foreColor',false,color.value);rememberDirty()}color.value='';extra.hidden=true;more.setAttribute('aria-expanded','false');queue()};
  page.append(bar);
  const caret=make('span','notes-caret');caret.id='notesCaret';caret.hidden=true;caret.setAttribute('aria-hidden','true');page.append(caret);
  let frame=0,composing=false,dismissed=false;
  function validRange(range){return range&&editor.contains(range.startContainer)&&editor.contains(range.endContainer)}
  function hideCaret(){caret.hidden=true;editor.classList.remove('notes-custom-caret')}
  function hideBar(){bar.hidden=true;extra.hidden=true;more.setAttribute('aria-expanded','false')}
  function positionBar(){
   if(bar.hidden||!validRange(savedRange))return;
   const viewport=window.visualViewport,top=viewport?.offsetTop||0,left=viewport?.offsetLeft||0;
   const width=viewport?.width||innerWidth,bottom=top+(viewport?.height||innerHeight);
   const pane=paperScroll.getBoundingClientRect();
   const rects=[...savedRange.getClientRects()].filter(r=>r.bottom>Math.max(pane.top,top)&&r.top<Math.min(pane.bottom,bottom));
   if(!rects.length){hideBar();return}
   const anchor=rects[0],box=bar.getBoundingClientRect();
   bar.style.left=Math.max(left+8,Math.min(anchor.left+anchor.width/2-box.width/2,left+width-box.width-8))+'px';
   const above=anchor.top-box.height-10,below=rects.at(-1).bottom+10;
   bar.style.top=(mobileNotes.matches?Math.max(top+8,bottom-box.height-12):Math.max(top+136,Math.min(above>=top+136?above:below,bottom-box.height-8)))+'px';
  }
  function update(){
   if(!page.open||!loaded||el('notesWorkspace').hidden||composing){hideBar();hideCaret();return}
   const selection=getSelection(),range=selection?.rangeCount?selection.getRangeAt(0):null;
   if(!validRange(range)){hideBar();hideCaret();return}
   if(!range.collapsed&&selection.toString().trim()){
    hideCaret();savedRange=range.cloneRange();
    if(dismissed||page.dataset.controls==='open'){hideBar();return}
    for(const [cmd,b] of toggleButtons)b.setAttribute('aria-pressed',String(document.queryCommandState(cmd)));
    bar.hidden=false;positionBar();return;
   }
   hideBar();dismissed=false;
   if(document.activeElement!==editor){hideCaret();return}
   const rect=range.getBoundingClientRect(),pane=paperScroll.getBoundingClientRect();
   if(!rect.height||rect.top<pane.top||rect.bottom>pane.bottom){hideCaret();return}
   const node=range.startContainer.nodeType===3?range.startContainer.parentElement:range.startContainer;
   const height=Math.max(rect.height,parseFloat(getComputedStyle(node).fontSize)*1.2);
   caret.style.cssText=`left:${rect.left}px;top:${Math.max(pane.top,rect.top-(height-rect.height)/2)}px;height:${height}px`;
   caret.hidden=false;editor.classList.add('notes-custom-caret');
  }
  function queue(){cancelAnimationFrame(frame);frame=requestAnimationFrame(update)}
  document.addEventListener('selectionchange',queue);
  new MutationObserver(queue).observe(page,{attributes:true,attributeFilter:['data-controls']});
  editor.addEventListener('input',()=>{dismissed=false;queue()});
  editor.addEventListener('pointerdown',()=>{dismissed=false});
  editor.addEventListener('keyup',queue);editor.addEventListener('focus',queue);editor.addEventListener('blur',queue);
  editor.addEventListener('compositionstart',()=>{composing=true;hideCaret()});editor.addEventListener('compositionend',()=>{composing=false;queue()});
  page.addEventListener('scroll',queue,true);window.addEventListener('resize',queue);
  window.visualViewport?.addEventListener('resize',queue);window.visualViewport?.addEventListener('scroll',queue);
  page.addEventListener('close',()=>{hideBar();hideCaret()});
  window.addEventListener('blur',()=>{hideBar();hideCaret()});window.addEventListener('focus',queue);
  bar.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();dismissed=true;hideBar();editor.focus({preventScroll:true})}});
 })();

 retry.onclick=()=>{retry.hidden=true;save()};
 async function back(allowed=()=>true){
  if(dirty){clearTimeout(saveTimer);await save();if(!allowed())return false;if(dirty){setStatus('Save failed. Use Retry save before leaving.',true);retry.hidden=false;return}}
  if(!allowed())return false;
  if(document.fullscreenElement)await document.exitFullscreen().catch(()=>{});
  if(!allowed())return false;
  page.close();page.dataset.keyboard='closed';page.dataset.controls='closed';return true;
 }
 el('notesBack').onclick=async()=>{if(await back()){
  Nav.go(notesRoute.replace(/\/notes$/,''),{replace:true});
  if(notesParentState)window.history.replaceState(notesParentState,'',location.href);
  renderNav();
 }};
 el('notesLock').onclick=async()=>{
  if(dirty){await save();if(dirty){setStatus('Save changes before locking.',true);return}}
  try{await request({action:'lock'});loaded=false;screen(true);setStatus('Locked')}catch(e){setStatus(e.message,true)}
 };
 page.addEventListener('cancel',e=>{e.preventDefault();el('notesBack').click()});
 window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
 window.FoundationNotes={show:open,hide:back,isOpen:()=>page.open,route:()=>notesRoute};
 button.onclick=open;
})();



