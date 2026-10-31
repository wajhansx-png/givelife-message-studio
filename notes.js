/* GiveLife Notes: one private, autosaved, distraction-free document. */
(()=>{
 const root=document.getElementById('donorNotes');
 if(!root)return;
 const DEVICE_KEY='givelife-notes-device';
 let token='',revision=0,loaded=false,loading=false,dirty=false,saving=false,saveTimer=0,selection=null,saveError='';
 try{token=localStorage.getItem(DEVICE_KEY)||''}catch(_){}
 const el=id=>document.getElementById(id);
 const status=(text,bad=false)=>{const node=el('notesStatus');if(node){node.textContent=text;node.dataset.error=String(bad)}};
 const request=async(body)=>{
  const headers={'X-Notes-Token':token};
  if(body!==undefined)headers['Content-Type']='application/json';
  const res=await fetch('/notes',body===undefined?{headers}:{method:'POST',headers,body:JSON.stringify(body)});
  let data;
  try{data=await res.json()}catch(_){throw Error('Notes could not connect to the cloud. Your text is still on this screen.')}
  if(!res.ok){const error=Error(data.error||'Notes request failed.');error.locked=!!data.locked;throw error}
  return data;
 };
 root.innerHTML=`<div class="notes-wrap">
  <div class="notes-gate" id="notesGate">
    <div class="notes-lock-symbol" aria-hidden="true">✦</div>
    <h2>Foundation Notes</h2>
    <p>Your private space for ideas, plans and to-do lists.</p>
    <form id="notesUnlockForm" autocomplete="off">
      <label for="notesPassword">Notes password</label>
      <input type="password" id="notesPassword" name="notes_password" inputmode="numeric" autocomplete="off" required placeholder="Enter password">
      <button type="submit" class="notes-primary" id="notesUnlockButton">Unlock notes</button>
      <small>This browser stays unlocked, even after you close it. You can lock it manually anytime.</small>
      <span class="notes-auth-error" id="notesAuthError" role="alert"></span>
    </form>
  </div>
  <div class="notes-workspace" id="notesWorkspace" hidden>
    <header class="notes-header">
      <div><h2>Foundation Notes</h2><p>Ideas, plans & things to remember</p></div>
      <div class="notes-header-right">
        <span id="notesStatus" role="status" aria-live="polite">Saved</span>
        <button type="button" id="notesSave" class="notes-quiet">Save now</button>
        <button type="button" id="notesLock" class="notes-quiet">Lock</button>
      </div>
    </header>
    <div class="notes-toolbar" role="toolbar" aria-label="Formatting">
      <select id="notesHeading" aria-label="Paragraph style" title="Heading style">
        <option value="p">Normal text</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option><option value="h3">Heading 3</option>
      </select>
      <span class="notes-separator" aria-hidden="true"></span>
      <button type="button" data-cmd="bold" title="Bold (Ctrl+B)" aria-label="Bold"><b>B</b></button>
      <button type="button" data-cmd="italic" title="Italic (Ctrl+I)" aria-label="Italic"><i>I</i></button>
      <span class="notes-separator" aria-hidden="true"></span>
      <button type="button" data-cmd="insertUnorderedList" title="Bullet list" aria-label="Bullet list">☷</button>
      <button type="button" data-cmd="insertOrderedList" title="Numbered list" aria-label="Numbered list">1.</button>
      <button type="button" id="notesChecklist" title="Checklist" aria-label="Checklist">☑</button>
      <span class="notes-separator" aria-hidden="true"></span>
      <label class="notes-color" title="Text color"><span>A</span><input id="notesColor" type="color" value="#176d60" aria-label="Text color"></label>
      <button type="button" data-cmd="removeFormat" title="Clear formatting" aria-label="Clear formatting">Tx</button>
    </div>
    <div class="notes-sheet">
      <div id="notesEditor" role="textbox" aria-label="Your foundation notes" aria-multiline="true" contenteditable="true" spellcheck="true" data-placeholder="Write your first idea…"></div>
    </div>
    <footer class="notes-footer"><span>Auto-saves as you type · Ctrl+S to save</span><span>Only you can open these notes</span></footer>
  </div>
 </div>`;
 const editor=el('notesEditor');
 const gate=el('notesGate'),workspace=el('notesWorkspace');
 const showGate=(error='')=>{
  gate.hidden=false;workspace.hidden=true;loaded=false;el('notesAuthError').textContent=error;
 };
 const showWorkspace=()=>{gate.hidden=true;workspace.hidden=false;};
 const load=async()=>{
  if(loading)return;
  loading=true;
  try{
   const result=await request();
   // Never replace unsaved text with remote content.
   if(!dirty){revision=result.revision;editor.innerHTML=result.html||'';loaded=true;saveError='';showWorkspace();status('All changes saved')}
  }catch(error){
   if(error.locked){token='';try{localStorage.removeItem(DEVICE_KEY)}catch(_){}showGate('Unlock Notes to continue.')}
   else if(dirty){status(error.message,true)}
   else showGate(error.message);
  }finally{loading=false}
 };
 const schedule=()=>{dirty=true;saveError='';status('Saving…');clearTimeout(saveTimer);saveTimer=setTimeout(save,850)};
 const save=async()=>{
  clearTimeout(saveTimer);
  if(!loaded||!dirty||saving)return;
  saving=true;
  const html=editor.innerHTML;
  const initialRevision=revision;
  status('Saving…');
  try{
   const result=await request({action:'save',html,revision:initialRevision});
   revision=result.revision;
   if(editor.innerHTML===html){dirty=false;status('All changes saved')}
   else{status('Saving newer changes…');saveTimer=setTimeout(save,500)}
   saveError='';
  }catch(error){
   saveError=error.message;
   status(error.message+' Your draft is still here.',true);
   if(error.locked){status('Device unlock expired. Copy your edits before locking the page.',true)}
  }finally{saving=false}
 };
 const keepSelection=()=>{
  const current=window.getSelection();
  if(current&&current.rangeCount&&editor.contains(current.anchorNode)){selection=current.getRangeAt(0).cloneRange()}
 };
 const focusSelection=()=>{
  editor.focus({preventScroll:true});
  if(selection){try{const s=window.getSelection();s.removeAllRanges();s.addRange(selection)}catch(_){}}
 };
 const exec=(cmd,value)=>{
  focusSelection();
  document.execCommand(cmd,false,value);
  keepSelection();schedule();
 };
 const toolbar=root.querySelector('.notes-toolbar');
 toolbar.addEventListener('mousedown',event=>{
  if(event.target.closest('button')){keepSelection();event.preventDefault()}
 });
 toolbar.addEventListener('click',event=>{
  const b=event.target.closest('[data-cmd]');if(b)exec(b.dataset.cmd);
 });
 el('notesHeading').addEventListener('pointerdown',keepSelection);
 el('notesHeading').addEventListener('change',event=>{exec('formatBlock',event.target.value);event.target.value='p'});
 el('notesColor').addEventListener('pointerdown',keepSelection);
 el('notesColor').addEventListener('input',event=>exec('foreColor',event.target.value));
 el('notesChecklist').addEventListener('click',()=>{
  focusSelection();
  let node=window.getSelection()?.anchorNode;
  if(node?.nodeType===3)node=node.parentElement;
  const existing=node?.closest?.('ul[data-checklist="true"]');
  if(existing){existing.removeAttribute('data-checklist');existing.querySelectorAll('li').forEach(li=>li.removeAttribute('data-checked'))}
  else{
   document.execCommand('insertUnorderedList',false,null);
   node=window.getSelection()?.anchorNode;
   if(node?.nodeType===3)node=node.parentElement;
   let ul=node?.closest?.('ul');
   if(!ul)ul=node?.closest?.('li')?.parentElement;
   if(ul&&ul.tagName==='UL'){ul.dataset.checklist='true';ul.querySelectorAll('li').forEach(li=>li.dataset.checked='false')}
  }
  schedule();
 });
 editor.addEventListener('click',event=>{
  const li=event.target.closest('ul[data-checklist="true"] > li');
  if(!li)return;
  const rect=li.getBoundingClientRect();
  // Checkbox occupies the first 26 pixels; text remains freely editable.
  if(event.clientX-rect.left<26){li.dataset.checked=li.dataset.checked==='true'?'false':'true';event.preventDefault();schedule()}
 });
 editor.addEventListener('beforeinput',()=>keepSelection());
 editor.addEventListener('keyup',keepSelection);
 editor.addEventListener('mouseup',keepSelection);
 editor.addEventListener('input',schedule);
 editor.addEventListener('paste',event=>{
  // Untrusted rich clipboard HTML must never execute in this page.
  event.preventDefault();
  exec('insertText',(event.clipboardData?.getData('text/plain')||'').slice(0,100000));
 });
 editor.addEventListener('drop',event=>event.preventDefault());
 root.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){
   event.preventDefault();save();
  }
 });
 el('notesSave').onclick=()=>save();
 el('notesLock').onclick=async()=>{
  if(dirty){await save();if(dirty){status('Could not save. Copy your notes before locking.',true);return}}
  try{await request({action:'lock'})}catch(_){}
  token='';try{localStorage.removeItem(DEVICE_KEY)}catch(_){}
  showGate();el('notesPassword').focus();
 };
 el('notesUnlockForm').onsubmit=async event=>{
  event.preventDefault();
  const button=el('notesUnlockButton');
  const pin=el('notesPassword').value;
  button.disabled=true;button.textContent='Unlocking…';el('notesAuthError').textContent='';
  try{
   // The password is only transmitted over the same HTTPS studio connection.
   const result=await request({action:'unlock',password:pin});
   token=result.token;try{localStorage.setItem(DEVICE_KEY,token)}catch(_){}
   el('notesPassword').value='';
   await load();
  }catch(error){el('notesAuthError').textContent=error.message}
  finally{button.disabled=false;button.textContent='Unlock notes'}
 };
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&dirty)save()});
 window.addEventListener('online',()=>{if(dirty)save()});
 window.GiveLifeNotes={
  async show(){if(loaded){showWorkspace();return}if(token){await load()}else showGate()},
  save
 };
})();
