/* GiveLife private notebook: formatting controls, permanent cloud autosave, device trust. */
(()=>{
 const donors=document.getElementById('donorsPage');
 if(!donors)return;
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e};
 const trigger=make('button','donor-notes-trigger','✎ Notes');trigger.type='button';trigger.id='donorNotesTab';
 trigger.setAttribute('aria-label','Open private foundation Notes');
 donors.querySelector('#donorMessagesTab')?.after(trigger);
 const modal=make('dialog','foundation-notes');
 modal.id='foundationNotes';modal.setAttribute('aria-label','Foundation notes');
 modal.innerHTML='<div class="fn-shell">'+
  '<header class="fn-head"><div class="fn-heading"><button class="fn-back" type="button" id="fnClose" aria-label="Back to donors">← Back</button><div><h1>Foundation notes</h1><span>Private ideas, plans & checklists</span></div></div><div class="fn-head-right"><span id="fnStatus" role="status" aria-live="polite"></span><button type="button" id="fnSave" class="fn-save" hidden>Save</button><button type="button" id="fnLock" class="fn-lock" hidden title="Forget this desktop">Lock</button></div></header>'+
  '<div class="fn-lockscreen" id="fnLockscreen"><div class="fn-lock-card"><div class="fn-lock-symbol">✎</div><h2>Your private notebook</h2><p>Foundation ideas and tasks, saved in your cloud. Unlock on this computer once to keep access here.</p><form id="fnUnlockForm"><label for="fnPassword">Notes password</label><input id="fnPassword" type="password" autocomplete="off" required placeholder="Enter your Notes password"><button type="submit" class="fn-primary" id="fnUnlock">Unlock notes</button></form><p id="fnLockError" role="alert"></p><small>Only unlock on your own computer. Use Lock to forget this device.</small></div></div>'+
  '<main class="fn-work" id="fnWork" hidden><div class="fn-editor-wrap"><div class="fn-toolbar" id="fnToolbar" role="toolbar" aria-label="Formatting">'+
  '<label class="fn-label">Text <select id="fnBlock" aria-label="Text style"><option value="p">Normal</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option><option value="h3">Heading 3</option></select></label>'+
  '<span class="fn-sep" aria-hidden="true"></span><button type="button" data-cmd="bold" aria-label="Bold" title="Bold (Ctrl+B)"><b>B</b></button><button type="button" data-cmd="italic" aria-label="Italic" title="Italic (Ctrl+I)"><em>I</em></button>'+
  '<span class="fn-sep" aria-hidden="true"></span><button type="button" data-cmd="insertUnorderedList" aria-label="Bulleted list" title="Bulleted list">☷</button><button type="button" data-cmd="insertOrderedList" aria-label="Numbered list" title="Numbered list">1.</button><button type="button" id="fnChecklist" aria-label="Checklist" title="Checklist">☑</button>'+
  '<span class="fn-sep" aria-hidden="true"></span><div class="fn-colors" aria-label="Text color"><span>Color</span><button type="button" data-color="#2c8f74" style="--swatch:#2c8f74" aria-label="Green text"></button><button type="button" data-color="#3b82f6" style="--swatch:#3b82f6" aria-label="Blue text"></button><button type="button" data-color="#e76f51" style="--swatch:#e76f51" aria-label="Coral text"></button><button type="button" data-color="#a855f7" style="--swatch:#a855f7" aria-label="Purple text"></button><button type="button" data-color="#d97706" style="--swatch:#d97706" aria-label="Amber text"></button></div>'+
  '</div><div class="fn-page"><div class="fn-editor" id="fnEditor" contenteditable="true" role="textbox" aria-label="Write foundation notes" aria-multiline="true" data-placeholder="Write an idea, a plan, or a to-do list…"></div></div><div class="fn-tips">Select text to format · Click a checkbox to complete it · Ctrl+S to save</div></div></main>'+
  '</div>';
 document.body.append(modal);
 const $=id=>modal.querySelector('#'+id),editor=$('fnEditor'),status=$('fnStatus');
 let version=0,dirty=false,saving=false,timer=null,savedRange=null,lastSubmitted='',openEpoch=0,blocked=false;
 const request=async(body)=>{const r=await fetch('/foundation-notes',body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Notes request failed.');return d};
 function state(message,mode='ok'){status.textContent=message;status.dataset.state=mode}
 function renderLocked(){clearTimeout(timer);$('fnLockscreen').hidden=false;$('fnWork').hidden=true;$('fnLock').hidden=true;$('fnSave').hidden=true;state('Locked','quiet')}
 function renderEditor(d){$('fnLockscreen').hidden=true;$('fnWork').hidden=false;$('fnLock').hidden=false;$('fnSave').hidden=false;editor.innerHTML=d.html||'';version=d.version||0;dirty=false;blocked=false;state('All changes saved');}
 async function load(){const epoch=++openEpoch;state('Opening…','quiet');try{const result=await request();if(epoch!==openEpoch)return;if(result.locked){renderLocked()}else{renderEditor(result);$('fnPassword').value=''}}catch(e){state(e.message,'error');renderLocked();$('fnLockError').textContent=e.message}}
 function changed(){dirty=true;state('Unsaved changes','saving');clearTimeout(timer);timer=setTimeout(save,650)}
 async function save(){if(!dirty||saving||blocked||$('fnWork').hidden)return;clearTimeout(timer);saving=true;let html=editor.innerHTML,atVersion=version;lastSubmitted=html;state('Saving…','saving');
  try{const result=await request({action:'save',html,version:atVersion});version=result.version;if(editor.innerHTML===html){dirty=false;state('Saved ✓')}else{dirty=true;state('Saving newer edits…','saving')}}
  catch(e){dirty=true;if(/changed in another tab/i.test(e.message))blocked=true;state(e.message,'error')}
  finally{saving=false;if(dirty&&!blocked)timer=setTimeout(save,1200)}
 }
 function selection(){const s=window.getSelection();if(!s||!s.rangeCount||!editor.contains(s.anchorNode))return null;return s.getRangeAt(0)}
 document.addEventListener('selectionchange',()=>{const r=selection();if(r)savedRange=r.cloneRange()});
 function refocus(){editor.focus({preventScroll:true});if(savedRange){const s=window.getSelection();s.removeAllRanges();try{s.addRange(savedRange)}catch(e){}}}
 function command(cmd,value){refocus();document.execCommand('styleWithCSS',false,true);document.execCommand(cmd,false,value||null);changed()}
 for(const button of modal.querySelectorAll('[data-cmd]')){button.addEventListener('mousedown',e=>e.preventDefault());button.onclick=()=>command(button.dataset.cmd)}
 const block=$('fnBlock');block.onchange=()=>{command('formatBlock',block.value);block.value='p'};
 function selectedList(){const s=window.getSelection();let n=s?.anchorNode;while(n&&n!==editor){if(n.nodeType===1&&n.tagName==='UL')return n;n=n.parentNode}return null}
 const checkButton=$('fnChecklist');checkButton.onmousedown=e=>e.preventDefault();checkButton.onclick=()=>{
  refocus();let ul=selectedList();if(!ul){document.execCommand('insertUnorderedList');ul=selectedList()}
  if(!ul)return;
  const checked=ul.getAttribute('data-list')==='check';if(checked){ul.removeAttribute('data-list');for(const li of ul.querySelectorAll('li'))li.removeAttribute('data-checked')}
  else{ul.setAttribute('data-list','check');for(const li of ul.querySelectorAll('li'))li.setAttribute('data-checked','false')}
  changed();
 };
 function colorize(hex){refocus();document.execCommand('styleWithCSS',false,true);document.execCommand('foreColor',false,hex);changed()}
 for(const button of modal.querySelectorAll('[data-color]')){button.onmousedown=e=>e.preventDefault();button.onclick=()=>colorize(button.dataset.color)}
 editor.addEventListener('input',changed);
 editor.addEventListener('paste',e=>{e.preventDefault();const text=e.clipboardData?.getData('text/plain')||'';document.execCommand('insertText',false,text)});
 editor.addEventListener('click',e=>{const li=e.target.closest('li');if(!li||li.parentElement?.getAttribute('data-list')!=='check')return;const rect=li.getBoundingClientRect();if(e.clientX-rect.left>38)return;li.setAttribute('data-checked',li.getAttribute('data-checked')==='true'?'false':'true');changed()});
 editor.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();save()}if(e.altKey&&e.key==='Enter'){const li=window.getSelection()?.anchorNode?.parentElement?.closest('li');if(li&&li.parentElement?.getAttribute('data-list')==='check'){e.preventDefault();li.setAttribute('data-checked',li.getAttribute('data-checked')==='true'?'false':'true');changed()}}});
 $('fnUnlockForm').onsubmit=async e=>{e.preventDefault();const btn=$('fnUnlock'),input=$('fnPassword');btn.disabled=true;$('fnLockError').textContent='';try{await request({action:'unlock',password:input.value});input.value='';await load()}catch(err){$('fnLockError').textContent=err.message;input.select()}finally{btn.disabled=false}};
 $('fnSave').onclick=save;
 $('fnLock').onclick=async()=>{if(dirty){await save();if(dirty){state('Save your changes before locking.','error');return}}try{await request({action:'forget'});editor.textContent='';renderLocked();$('fnPassword').value=''}catch(e){state(e.message,'error')}};
 function close(){if(dirty)save();modal.close();}
 $('fnClose').onclick=close;modal.addEventListener('cancel',e=>{e.preventDefault();close()});
 modal.addEventListener('close',()=>{openEpoch++;clearTimeout(timer);if(dirty&&!saving)save()});
 trigger.onclick=()=>{if(!modal.open)modal.showModal();load()};
 window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
})();