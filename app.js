const $=id=>document.getElementById(id);
let draftSaved=null,draftsReady=false,draftsLoad=null;
let editing=false,left=null,timer,saveChain=Promise.resolve(),allT=null,autoOn=false,seenAuto=0;
const view=()=>document.body.dataset.view,fmt=n=>Number(n).toLocaleString('en-US');
const post=(url,body)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
function status(t,bad){const s=$('status');s.textContent=t;s.classList.toggle('err',!!bad);if(bad)setLiveNotice(t,true)}

/* ---- conversation log (kept on this device) ---- */
let history=[];try{const saved=JSON.parse(localStorage.getItem('givelife-chat')||'[]');if(Array.isArray(saved))history=saved.filter(h=>h&&typeof h.text==='string').slice(-80)}catch(e){}
let thinking=false,pendingChats=0;
const scrollState={log:{top:0,follow:true},histLog:{top:0,follow:true}};
const unreadReplies={log:false,histLog:false};
function paintUnread(){for(const [id,button] of [['log','chatLatest'],['histLog','histLatest']])$(button).hidden=!unreadReplies[id]}
function showLatest(id){scrollState[id].follow=true;unreadReplies[id]=false;followChat($(id),true);paintUnread()}
try{const saved=JSON.parse(sessionStorage.getItem('givelife-chat-scroll')||'{}');for(const id of Object.keys(scrollState))if(saved[id]&&Number.isFinite(saved[id].top))scrollState[id]={top:saved[id].top,follow:saved[id].follow!==false}}catch(e){}
function rememberScroll(){try{sessionStorage.setItem('givelife-chat-scroll',JSON.stringify(scrollState))}catch(e){}}
function followChat(el,reply=false){if(!el.clientHeight)return;const last=el.querySelector('.e:last-of-type');
 const top=reply&&last&&last.classList.contains('bot')&&last.offsetHeight>el.clientHeight-32?el.scrollTop+last.getBoundingClientRect().top-el.getBoundingClientRect().top-16:el.scrollHeight;
 el.scrollTop=Math.max(0,top);scrollState[el.id].top=el.scrollTop;
}
function drawLog(){const items=history.slice(-40);
 for(const id of ['log','histLog']){const el=$(id),state=scrollState[id],prev=state.top;el.textContent='';
  items.forEach(h=>{const d=document.createElement('div');d.className='e '+(h.who==='auto'?'sys':h.who==='app'?'bot':h.who)+(h.err?' err':'');d.dataset.t=h.t;
   d.textContent=h.text;el.append(d);if(h.who==='app'&&h.id){const f=document.createElement('button');f.className='reply-feedback';f.type='button';f.textContent='Correct this';f.setAttribute('aria-label','Correct this response');f.onclick=e=>{e.stopPropagation();openFeedback(h.id)};el.append(f)}});
  if(thinking){const d=document.createElement('div');d.className='e bot dots';d.textContent='Thinking…';el.append(d)}
  if(el.clientHeight){if(state.follow)followChat(el,items.at(-1)?.who==='app'&&!thinking);else el.scrollTop=prev}
 }}
for(const id of Object.keys(scrollState))$(id).addEventListener('scroll',()=>{const el=$(id);if(!el.clientHeight)return;scrollState[id]={top:el.scrollTop,follow:el.scrollHeight-el.clientHeight-el.scrollTop<64};if(scrollState[id].follow){unreadReplies[id]=false;paintUnread()}rememberScroll()},{passive:true});
function followReplies(){for(const id of Object.keys(scrollState)){scrollState[id].follow=true;unreadReplies[id]=false}paintUnread()}
function think(on){pendingChats=Math.max(0,pendingChats+(on?1:-1));thinking=pendingChats>0;drawLog()}let logChain=Promise.resolve();
function say(who,text,err,turnId){if(typeof text!=='string'||!text.trim())return;const item={id:turnId||(crypto.randomUUID?crypto.randomUUID():String(Date.now())+Math.random()),who,text,err:!!err,t:Date.now()};history.push(item);history=history.slice(-80);if(who==='you')followReplies();if(who==='app'){for(const id of Object.keys(scrollState))if(!scrollState[id].follow)unreadReplies[id]=true;paintUnread();$($('hist').open?'histAnnouncement':'chatAnnouncement').textContent=text}if(who!=='auto')logChain=logChain.then(()=>post('/chat-log',{who,text,err:!!err,turn_id:item.id})).catch(()=>{});try{localStorage.setItem('givelife-chat',JSON.stringify(history))}catch(e){}drawLog();if(err)setLiveNotice(text,true)}
const GREETING='Hi. Tell me what changed or what to do: "34k left", "came 2000", "Ali 0300 1234567", "send all", or anything else. I can use saved preferences and recent context.';
async function syncChat(){try{await logChain;const d=await (await fetch('/chat')).json();
 if(d.items&&d.items.length){history=d.items.slice(-80).map(x=>({id:x.turn_id||x.id,who:x.who,text:x.text,err:!!x.err,t:x.t}));try{localStorage.setItem('givelife-chat',JSON.stringify(history))}catch(e){}}
 else if(!history.length)say('app',GREETING);
 else for(const h of history.slice(-40))if(h.who!=='auto')logChain=logChain.then(()=>post('/chat-log',{who:h.who,text:h.text,err:h.err}));
 drawLog(false)}catch(e){if(!history.length)say('app',GREETING)}}
drawLog();syncChat();
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!thinking)syncChat()});
function isPhone(){return matchMedia('(max-width:899px)').matches}
function openChat(){if($('hist').open)return;if(editing)setEditing(false);rememberScroll();$('hist').showModal();
 // A navigation control receives focus. Opening chat never opens a soft keyboard.
 (isPhone()?$('histMain'):$('histClose')).focus({preventScroll:true});syncChat();requestAnimationFrame(drawLog)}
function closeChat(){saveChatDraft($('histCmd').value);document.activeElement?.blur();rememberScroll();$('hist').close();if(isPhone())$('chatOpen').focus({preventScroll:true})}
$('chatOpen').onclick=openChat;$('chatExpand').onclick=openChat;
$('chatLatest').onclick=()=>showLatest('log');$('histLatest').onclick=()=>showLatest('histLog');
$('histClose').onclick=closeChat;$('histMain').onclick=closeChat;
$('hist').addEventListener('cancel',e=>{e.preventDefault();closeChat()});
/* ---- message preview ---- */
let previewView=null,previewScroll={};try{previewScroll=JSON.parse(sessionStorage.getItem('givelife-preview-scroll')||'{}')||{}}catch(e){}
$('chat').addEventListener('scroll',()=>{if(!previewView)return;previewScroll[previewView]=$('chat').scrollTop;try{sessionStorage.setItem('givelife-preview-scroll',JSON.stringify(previewScroll))}catch(e){}},{passive:true});
function paint(k){$(k+'Preview').innerHTML=waFormat($(k).value).split('\n').map(l=>'<div class="wa-line'+(l?'':' blank')+'">'+(l||'<br>')+'</div>').join('')}
function render(){paint('group');paint('dm');requestAnimationFrame(()=>{fit();if(!editing)$('chat').scrollTop=previewScroll[view()]||0})}
function fit(){if(editing)return;const chat=$('chat'),m=$(view()+'Preview');m.style.fontSize=isPhone()?'16px':'17px';chat.style.overflowY='auto'}
new ResizeObserver(()=>requestAnimationFrame(fit)).observe($('chat'));
function save(){if(!draftsReady)return Promise.resolve();const data={group:$('group').value,dm:$('dm').value},payload=JSON.stringify(data);
 saveChain=saveChain.catch(()=>{}).then(async()=>{if(payload===draftSaved)return;const r=await post('/drafts',data);if(!r.ok)throw Error('Save failed');draftSaved=payload;status('✓ Saved')});return saveChain}
async function ensureDrafts(){if(draftsReady)return;if(!draftsLoad)draftsLoad=fetch('/drafts').then(async r=>{if(!r.ok)throw Error('Could not load captions');const d=await r.json();if(typeof d.group!=='string'||typeof d.dm!=='string')throw Error('Saved captions are invalid');cached('drafts',d);applyDrafts(d)}).finally(()=>draftsLoad=null);return draftsLoad}
async function ensureCaption(kind){await ensureDrafts();if(!$(kind)||!$(kind).value.trim())throw Error('The caption is empty. Use New or Edit to add it before sending.')}
function saveSoon(){status('Saving…');clearTimeout(timer);timer=setTimeout(()=>save().catch(()=>status('Save failed',1)),300)}

/* ---- edit in place ---- */
function ser(n){if(n.nodeType===3)return n.nodeValue;if(n.nodeName==='BR')return '\n';
 const inner=[...n.childNodes].map(ser).join(''),t=n.nodeName;
 if(t==='STRONG'||t==='B')return inner.trim()?'*'+inner+'*':inner;if(t==='EM'||t==='I')return inner.trim()?'_'+inner+'_':inner;
 if(t==='S')return inner.trim()?'~'+inner+'~':inner;if(t==='CODE')return '`'+inner+'`';
 if(n.classList&&n.classList.contains('wa-list'))return '* '+inner.replace(/^•\s+/,'');
 if(t==='DIV'&&!(n.classList&&n.classList.contains('wa-line')))return '\n'+inner;return inner}
function readPreview(k){return [...$(k+'Preview').children].map(d=>d.classList.contains('blank')&&!d.textContent.trim()?'':ser(d).replace(/\n$/,'')).join('\n').replace(/ /g,' ')}
function setEditing(on,x,y){if(on&&!draftsReady){status('Loading the saved captions…');return}const k=view(),m=$(k+'Preview');if(on===editing)return;editing=on;
 document.body.classList.toggle('editing',on);$('edit').textContent=on?'Done':'Edit';$('edit').classList.toggle('on',on);
 if(on){m.contentEditable='true';const r=x!=null&&document.caretRangeFromPoint?document.caretRangeFromPoint(x,y):null;m.focus();if(r){const s=getSelection();s.removeAllRanges();s.addRange(r)}status('Editing · Enter = done · Shift+Enter = new line')}
 else{m.contentEditable='false';$(k).value=readPreview(k);render();save().catch(()=>status('Save failed',1))}}
$('edit').onclick=()=>setEditing(!editing);

for(const k of ['group','dm'])$(k+'Preview').addEventListener('paste',e=>{e.preventDefault();document.execCommand('insertText',false,(e.clipboardData.getData('text/plain')||'').replace(/\r/g,''))});

/* ---- views, amount, DM greeting ---- */
function setView(v){if(editing)setEditing(false);if(previewView)previewScroll[previewView]=$('chat').scrollTop;document.body.dataset.view=v;previewView=v;document.querySelectorAll('[data-view-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.viewButton===v)));
 $('ctx').textContent=v==='group'?'Group message · poster attached':'DM · poster attached';localStorage.setItem('givelife-view',v);requestAnimationFrame(()=>{fit();$('chat').scrollTop=previewScroll[v]||0});flip()}
document.querySelectorAll('[data-view-button]').forEach(b=>b.onclick=()=>setView(b.dataset.viewButton));
function showLeft(){const c=$('leftChip');c.textContent=left==null?'Rs. …':'Rs. '+fmt(left);const w=document.createElement('span');w.className='lw';w.textContent=' left';c.append(w)}
function applyDrafts(d){if(typeof d.group==='string'&&typeof d.dm==='string')draftsReady=true;if(d.dm_identity){$('dmName').value=d.dm_identity.name||'';$('dmPhone').value=d.dm_identity.phone||'';gender=d.dm_identity.gender==='Sister'?'Sister':'Brother';document.querySelectorAll('#gender button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.g===gender)))}if(d.group!=null||d.dm!=null)draftSaved=JSON.stringify({group:d.group??$('group').value,dm:d.dm??$('dm').value});if(d.group!=null)$('group').value=d.group;if(d.dm!=null)$('dm').value=d.dm;if(d.left!=null){left=d.left;showLeft()}applyGreeting(false);render()}
async function setLeft(n){if(editing)setEditing(false);const r=await post('/left',{left:n}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not update amount');applyDrafts(d);await save()}
$('leftChip').onclick=()=>{openChat();$('histCmd').placeholder='Amount left, e.g. 25000 or 25k';$('histCmd').focus({preventScroll:true})};
let gender='Brother';
function logicalName(value){if(/acc+ount|\d|@|https?:\/\/|[_/\\]|\b(jr|junior|sr|senior|accounts?|accts?|admin|team|group|member|donors?|business|company|shop|store|services?|official|office|unknown|unnamed|name|contact|number|test|user|brother|sister|friend|wife|wifey|boss|customer|client|support|sales|marketing|web|developer|designer|agency|digital|seo|upwork|fiverr|foundation|givelife)\b/i.test(value))return '';const words=value.replace(/[^A-Za-z\s'-]/g,'').trim().split(/\s+/),n=words[0];return words.length<=4&&words.every(w=>w.length>=2)&&/^[A-Za-z][A-Za-z'-]{1,19}$/.test(n)&&/[aeiouy]/i.test(n)?n[0].toUpperCase()+n.slice(1).toLowerCase():''}
function greet(){const n=logicalName($('dmName').value.trim());return n?n+' '+gender:'Brother'}
const GREET=/^(\*?_?)(?:(?:[A-Za-z][A-Za-z .'-]{0,45})\s+)?(?:Brother|Sister)\b([_*]?)[,.:!]?[ \t\r\n]*/i;
function applyGreeting(doSave=true){const t=$('dm').value;if(!t)return;const g=greet(),nt=GREET.test(t)?t.replace(GREET,(_,open,close)=>open+g+close+', '):g+', '+t;
 if(nt!==t){$('dm').value=nt;paint('dm');requestAnimationFrame(fit);if(doSave)saveSoon()}}
function setGender(g){gender=g;document.querySelectorAll('#gender button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.g===g)));applyGreeting()}
document.querySelectorAll('#gender button').forEach(b=>b.onclick=()=>setGender(b.dataset.g));
$('dmName').addEventListener('input',()=>applyGreeting());

/* ---- tools ---- */
async function freshWording(){await ensureDrafts();if(editing)setEditing(false);const k=view();clearTimeout(timer);await save();const r=await post(k==='group'?'/next-message':'/next-dm'),d=await r.json();$(k).value=d.message;if(k==='dm')applyGreeting(false);render();flip();await save()}
$('fresh').onclick=async()=>{$('fresh').disabled=true;try{await freshWording();status('✓ New wording ready')}catch(e){status('Could not make new wording',1)}finally{$('fresh').disabled=false}};
$('copy').onclick=async()=>{if(editing)setEditing(false);try{await navigator.clipboard.writeText($(view()).value);status('✓ Copied')}catch(e){status('Copy failed',1)}};

/* ---- sending ---- */
let operationCount=0;
function busy(on){operationCount=Math.max(0,operationCount+(on?1:-1));document.body.classList.toggle('sending',operationCount>0);paintStatusLine()}
const watchingJobs=new Set(),sendLocks=new Set(),jobLocks=new Map();let displayJob=null;
function lockSend(key,on){if(on&&sendLocks.has(key))return false;if(on)sendLocks.add(key);else sendLocks.delete(key);
 const buttons=key==='all'?[$('sendAll')]:key==='dm'?[$('sendDm')]:[...document.querySelectorAll(key.startsWith('test:')?'[data-test="'+key.slice(5)+'"]':'[data-group="'+key+'"]')];
 for(const b of buttons){b.disabled=on;b.setAttribute('aria-busy',String(on))}return true}
function releaseJob(id){for(const key of jobLocks.get(id)||[])lockSend(key,false);jobLocks.delete(id)}

const requestId=()=>typeof crypto.randomUUID==='function'?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
async function watchGroupJob(id,caption){
 if(watchingJobs.has(id))return;watchingJobs.add(id);displayJob=id;busy(true);
 try{let done=false,failures=0;const until=Date.now()+12*60*1000;
  while(!done&&Date.now()<until){let job;
   try{const r=await fetch('/send-status/'+id);job=await r.json();if(!r.ok)throw Error(job.error||'Could not read the send result');failures=0}
   catch(e){if(++failures>=3)throw Error('Could not confirm delivery. Check WhatsApp. No send was retried.');await new Promise(res=>setTimeout(res,2000));continue}
   if(displayJob===id){if($('groupStatus').textContent!==job.message)$('groupStatus').textContent=job.message;$('groupStatus').title=(job.results||[]).map(x=>x.group+': '+(x.code==='SUCCESS'?'Confirmed sent':x.message)).join('\n')}setLiveNotice(job.message,false);
   done=job.done;
   if(done){const bad=(job.results||[]).some(x=>x.code!=='SUCCESS');say('app',job.message+((job.results||[]).length?' '+job.results.map(x=>x.group+': '+(x.code==='SUCCESS'?'✓ Sent':x.message||'Not confirmed')).join(', '):''),bad);
    if(job.next_caption&&$('group').value===caption&&!editing){$('group').value=job.next_caption;render()}}
   if(!done)await new Promise(res=>setTimeout(res,1200));
  }
  if(!done)throw Error('This send is still unconfirmed. Check WhatsApp before sending again.');
 }catch(e){say('app',e.message,1)}finally{watchingJobs.delete(id);releaseJob(id);busy(false);requestAnimationFrame(fit)}
}
async function sendGroup(key){if(!lockSend(key,true))return;let tracked=false;if(editing)setEditing(false);if(!$('chips').hidden)$('moreG').click();setLiveNotice('Sending to '+(GN[key]||key)+'…');busy(true);
 try{await ensureCaption('group');clearTimeout(timer);await save();const caption=$('group').value;$('groupStatus').textContent='Sending now…';
  const r=await post('/send-group',{group:key,message:caption,request_id:requestId()}),start=await r.json();if(!r.ok)throw Error(start.error||'Could not start');
  if(!start.job_id)throw Error('No send receipt was returned. Check WhatsApp before trying again.');const keys=jobLocks.get(start.job_id)||new Set();keys.add(key);jobLocks.set(start.job_id,keys);tracked=true;watchGroupJob(start.job_id,caption);
 }catch(e){$('groupStatus').textContent='✗ '+e.message;say('app',e.message,1)}finally{if(!tracked)lockSend(key,false);busy(false)}}
document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>sendGroup(b.dataset.group));
function armAll(){return sendGroup('all')}
$('sendAll').onclick=armAll;
async function sendTest(kind){const key='test:'+kind;if(!lockSend(key,true))return;setLiveNotice('Sending to test group…');busy(true);try{await ensureCaption(kind);clearTimeout(timer);await save();const r=await post('/test',{message:$(kind).value}),d=await r.json();const result=d.code==='SUCCESS'?'✓ Sent to the test group.':'Test failed: '+(d.message||d.error||'');say('app',result,d.code!=='SUCCESS');setLiveNotice(result,d.code!=='SUCCESS')}
 catch(e){say('app',e.message||'Could not send',1)}finally{lockSend(key,false);busy(false)}}
document.querySelectorAll('[data-test]').forEach(b=>b.onclick=()=>{if(editing)setEditing(false);sendTest(b.dataset.test)});
function cleanPhone(p){p=p.replace(/[\s()+-]/g,'');if(p.startsWith('00'))p=p.slice(2);if(/^03\d{9}$/.test(p))p='92'+p.slice(1);return /^[1-9]\d{7,14}$/.test(p)?p:''}
$('sendDm').onclick=async()=>{if(editing)setEditing(false);const phone=cleanPhone($('dmPhone').value);
 if(!phone){say('app','Enter a phone number first, e.g. 0300 1234567.',1);$('dmPhone').focus();return}
 if(!lockSend('dm',true))return;busy(true);try{await ensureCaption('dm');applyGreeting(false);clearTimeout(timer);await save();
  const r=await post('/send-custom',{target:'phone',phone,message:$('dm').value,poster:true,kind:'dm_appeal',name:$('dmName').value,gender}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not send');
  if(d.code==='SUCCESS'){const result='✓ DM sent to '+greet()+'.';say('app',result+' New wording is ready for the next person.');setLiveNotice(result);$('dmPhone').value='';$('dmName').value='';setGender('Brother');await freshWording()}
  else say('app','Not confirmed: '+(d.message||'')+' Check WhatsApp before retrying.',1)}
 catch(e){say('app',e.message,1)}finally{lockSend('dm',false);busy(false)}};

/* ---- send a plain message to a contact, group or number: works without the AI ---- */
async function sendTo(who,text){
 let to=who;const g=GKEY(who);
 if(g)to=g;else if(who&&!/^\+?\d[\d\s-]{6,}$/.test(who)){
  const r=await post('/find',{query:who}),d=await r.json();
  if(!d.items.length)return `I checked your chats and contacts (${d.checked}) and found nobody called "${who}". Send me the number and I will message it.`;
  if(d.items.length>1&&!d.items.some(x=>x.name.toLowerCase()===who.toLowerCase()))return 'Which one?\n'+d.items.slice(0,5).map((x,i)=>`${i+1}. ${x.name}`).join('\n')+'\nSay: send '+text+' to <full name>.';
  const hit=d.items.find(x=>x.name.toLowerCase()===who.toLowerCase())||d.items[0];to=hit.id;who=hit.name}
 const r=await post('/send-now',{to,text,with_picture:false,literal:true}),d=await r.json();
 if(!r.ok)throw Error(d.error||'Could not send');return `Sent "${text.slice(0,60)}" to ${who||d.to||'the last person'}.`}
const GKEY=w=>({main:'main',givelife:'main',community:'community','upwork community':'community',fiverr:'fiverr','fiverr course':'fiverr',upwork:'upwork','upwork course':'upwork',uet:'uet','fiverr uet':'uet',toprated:'toprated','top rated':'toprated',test:'test','test group':'test'})[String(w).toLowerCase().trim()];

/* ---- pictures in the chat ---- */
let attached=null;
function clearAttachment(){attached=null;$('att').hidden=true}
$('attX').onclick=clearAttachment;
document.querySelectorAll('[data-clip]').forEach(b=>b.onclick=()=>$('file').click());
$('file').onchange=async()=>{const f=$('file').files[0];$('file').value='';if(!f)return;
 const img=await createImageBitmap(f),k=Math.min(1,1600/Math.max(img.width,img.height)),c=document.createElement('canvas');c.width=Math.round(img.width*k);c.height=Math.round(img.height*k);c.getContext('2d').drawImage(img,0,0,c.width,c.height);
 const data=c.toDataURL('image/jpeg',.85);try{const r=await post('/upload-image',{data,use:'attachment'}),d=await r.json();if(!r.ok)throw Error(d.error);
  attached={id:d.id,data,url:data};$('attImg').src=data;$('att').hidden=false;say('app','Picture attached. Paste numbers to send it, or say "make it the poster".')}catch(e){say('app','Could not attach: '+e.message,1)}};

/* ---- lists of people: "send these with 2 min gap", numbers with names, one per line or separated ---- */
const FEMALE=new Set('ayesha aisha fatima zainab maryam mariam laiba sana hira iqra amna sawaira yusra areeba mahnoor noor kiran sadia saba rabia hina nida mehwish sidra anam anum bushra khadija asma uzma sara sarah zoya alina hajra dania rimsha mehak esha ifra aleena maham momina tehreem eman iman aiman kinza fiza javeria sobia shazia nadia farah rida ramsha warda wajeeha hafsa sumaira tayyaba uswa zara zahra nimra minahil bisma'.split(' '));
const NOTNAME=/\b(web|developer|development|graphics?|entrepreneur|official|store|shop|studio|agency|design(er)?|marketing|services?|tech|digital|freelancer|admin|group|team|pakistan|seo|business|mw|brother|sister|send|bhejo|gap|min|mint|minute|minutes|sec|seconds|hours?|after|start|with|and|the|these|people|numbers?|message|msg|dm|each|change|wording|same|picture|image|poster)\b/i;
function nameFrom(s){
 const words=s.replace(/^\W+/u,'').split(/\s+/).filter(Boolean).filter(x=>!NOTNAME.test(x));
 if(words.some(x=>/\d|…|\.\.\.|[\p{Extended_Pictographic}]/u.test(x))||/\b(develop|graphic|entrepreneur|design|market|official)/i.test(s))return '';
 s=words.join(' ').replace(/[^\p{L}\s.'-]/gu,' ').replace(/\s+/g,' ').trim();if(!s)return '';const w=s.split(' ');
 if(!w.length||w.length>3)return '';const n=w.slice(0,2).join(' ');return /^[A-Za-z][A-Za-z.'-]{1,19}(?: [A-Za-z][A-Za-z.'-]{1,19})?$/.test(n)?n.replace(/\b\w/g,c=>c.toUpperCase()):''}
function parseList(t){const people=[],re=/(?:\+?92|0092|0)[\s-]?3\d{2}[\s-]?\d{7}/g,lines=t.split(/\n|;/);
 for(const line of lines){let m;const found=[...line.matchAll(re)];for(let i=0;i<found.length;i++){m=found[i];
  const before=line.slice(i?found[i-1].index+found[i-1][0].length:0,m.index),after=found.length===1?line.slice(m.index+m[0].length):'';
  const raw=(before+' '+after).replace(/[~|•,:]/g,' ');const name=nameFrom(raw);
  const sister=/\b(sister|sis|behen|baji|madam|miss|mrs)\b/i.test(raw)||(name&&FEMALE.has(name.split(' ')[0].toLowerCase()));
  people.push({phone:m[0].replace(/[\s-]/g,''),name,gender:sister?'Sister':'Brother'})}}
 const g=t.match(/(\d+(?:\.\d+)?)\s*(m(?:in(?:ute)?s?|ints?)?|s(?:ec(?:ond)?s?)?|h(?:ours?)?)\b\s*(?:ka\s*)?gap|gap\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(m(?:in(?:ute)?s?|ints?)?|s(?:ec(?:ond)?s?)?)?/i);
 let gap=90;if(g){const v=parseFloat(g[1]||g[3]),u=(g[2]||g[4]||'m').toLowerCase();gap=u.startsWith('s')?v:u.startsWith('h')?v*3600:v*60}
 const st=t.match(/start\s*(?:after|in)\s*(\d+(?:\.\d+)?)\s*(m|min|mint|minutes?|h|hours?)?/i);const start=st?parseFloat(st[1])*(/^h/i.test(st[2]||'')?3600:60):0;
 const vary=!/\bsame (message|wording|text)\b/i.test(t);
 const seen=new Set();return {people:people.filter(p=>!seen.has(p.phone)&&seen.add(p.phone)),gap:Math.max(45,gap),start,vary}}
let listT=null;
function startList(l){if(listT){clearTimeout(listT);listT=null}
 const names=l.people.slice(0,4).map(p=>(p.name?p.name+' ':'')+p.gender).join(', ')+(l.people.length>4?` +${l.people.length-4} more`:'');
 say('app',`Sending to ${l.people.length} ${l.people.length===1?'person':'people'}: ${names}. Gap about ${Math.round(l.gap/6)/10} min, ${l.vary?'new wording for each person':'same message'}, ${attached?'your picture':'the poster'}${l.start?`, starting in ${Math.round(l.start/6)/10} min`:''}. Starting in 5 seconds — tap Stop to cancel.`);
 showCamp('Starting in 5 seconds…');
 listT=setTimeout(async()=>{listT=null;try{const r=await post('/campaign',{people:l.people,gap_seconds:l.gap,vary:l.vary,start_after_seconds:l.start,image:attached?attached.id:'poster',rest_every:10,rest_minutes:10}),d=await r.json();
  if(!r.ok)throw Error(d.error);say('app',d.reply);pollCamp()}catch(e){say('app',e.message,1);$('camp').hidden=true}},5000)}
function showCamp(t){$('campText').textContent=t;$('camp').hidden=false}
let campTimer=null,campPolling=false,lastCampLog=localStorage.getItem('givelife-camp-last')||'';
async function pollCamp(){if(campPolling)return;campPolling=true;clearTimeout(campTimer);campTimer=null;try{const r=await fetch('/campaign');if(!r.ok)throw Error('Could not check DMs');const c=await r.json();
 if(c.running){const w=c.wait?` · next in ${Math.floor(c.wait/60)}:${String(c.wait%60).padStart(2,'0')}`:'';showCamp(`DMs ${c.sent}/${c.total} sent${c.skipped?`, ${c.skipped} skipped`:''}${w}${c.current&&c.current!=='Waiting'?' · '+c.current:''}`);setLiveNotice($('campText').textContent);campTimer=setTimeout(pollCamp,3000)}
 else if(!listT){$('camp').hidden=true;const last=(c.log||[]).slice(-1)[0];if(c.total&&last&&last!==lastCampLog){lastCampLog=last;try{localStorage.setItem('givelife-camp-last',last)}catch(e){}say('app',`DM list done: ${c.sent} sent, ${c.skipped} skipped, ${c.failed} failed.`)}}}catch(e){if(!$('camp').hidden)setLiveNotice('Cannot refresh DM progress. Check your connection.',true)}finally{campPolling=false;if(!campTimer)campTimer=setTimeout(pollCamp,10000)}}
$('campStop').onclick=async()=>{if(listT){clearTimeout(listT);listT=null;$('camp').hidden=true;say('app','Cancelled. Nothing was sent.');return}
 const b=$('campStop');b.disabled=true;try{const r=await post('/campaign',{stop:true}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not stop DMs');say('app',d.reply);setLiveNotice(d.reply);pollCamp()}catch(e){say('app',e.message,1)}finally{b.disabled=false}};

/* ---- the assistant: quick commands work instantly; anything else goes to the AI ---- */
const num=(s,k)=>Math.round(parseFloat(s.replace(/,/g,''))*(k?1000:1));
async function quick(t){const low=t.toLowerCase().trim();
 if(/^(hi+|hello|hey|salam)\W*$/i.test(t))return 'Hi!';
 if(/^(ok|okay|thanks|thank you|theek|done thanks)\W*$/i.test(t))return /thank/i.test(t)?'You’re welcome.':'Okay.';
 if(editing)setEditing(false);clearTimeout(timer);await ensureDrafts();await save();
 const response=await post('/command',{text:t,request_id:requestId()}),direct=await response.json();
 if(!response.ok)throw Error(direct.error||'Command failed. Nothing was retried.');
 if(direct.handled){applyDrafts(direct);if(direct.job_id)watchGroupJob(direct.job_id,direct.caption||$('group').value);return direct.reply}
 if(/^(dm|group)$/.test(low)){setView(low);return 'Switched to '+low.toUpperCase()+'.'}
 if(/^(new|regenerate|next|naya)$/.test(low)){await freshWording();return 'New wording ready.'}
 if(low==='copy'){$('copy').click();return 'Copied.'}
 if(/^auto(pilot)?\s+(on|off)$/.test(low)){await toggleAuto(/on$/.test(low));return null}
 if(/^(rules?|my rules|show rules|list rules)$/.test(low)){const d=await(await fetch('/rules')).json();return d.items.length?d.items.map(x=>x.text).join('\n'):'No scheduling rules saved.'}
 if(/^(?:\+?92|0)?3\d{9}$/.test(t.replace(/[ ()-]/g,''))){setView('dm');$('dmPhone').value=t;$('dmName').value='';setGender('Brother');return 'Full DM prepared for that number. Nothing was sent.'}
 if(attached&&/\b(papers?|reports?|documents?)\b/i.test(t)&&/\b(this|these|save|use|add)\b/i.test(t)){const r=await post('/upload-image',{data:attached.data,use:'papers'}),d=await r.json();if(!r.ok)throw Error(d.error);clearAttachment();return 'Medical papers saved.'}
 return undefined}

async function act(text){const t=text.trim();if(!t)return;say('you',t);
 const q=await quick(t);if(q!==undefined){if(q)say('app',q);return}
 think(true);let r,d;
 try{await logChain;r=await post('/assistant',{text:t,request_id:requestId(),image:attached?attached.id:null,history:history.slice(-13,-1),screen:{view:view(),dm:{name:$('dmName').value,phone:$('dmPhone').value,gender}}});d=await r.json().catch(()=>({}));if(r.ok&&d.task_id){let finished=false;const until=Date.now()+4*60*1000;while(!finished&&Date.now()<until){await new Promise(res=>setTimeout(res,500));const check=await fetch('/assistant-status/'+d.task_id),task=await check.json();if(!check.ok)throw Error(task.error||'Request no longer tracked. Nothing was retried.');if(task.done){if(task.error)throw Error(task.error);d=task.result;finished=true}}if(!finished)throw Error('The assistant result is not confirmed. Check recent activity; I will not repeat the send.')}}finally{think(false)}
 if(r.status===503){say('app','I did not understand that, and the AI assistant is not connected, so only direct commands work. Try: "34k left", "came 2000", "send hi to Ali", "send main", "fiverr every 30 min", "rules".',1);return}
 if(!r.ok)throw Error(d.error||'The assistant could not answer.');
 if(!d.superseded){applyDrafts(d);if(d.autopilot!=null)paintAuto(d.autopilot)}say('app',d.reply,false,d.turn_id);if(d.job_id)watchGroupJob(d.job_id,d.caption||$('group').value);for(const j of d.jobs||[])watchGroupJob(j.job_id,j.caption||$('group').value);
 for(const a of d.actions||[]){
  if(a.type==='prepare_dm'){setView('dm');$('dmPhone').value=a.phone||'';$('dmName').value=a.name||'';setGender(a.gender==='Sister'?'Sister':'Brother')}
  }}
/* A draft is independent of the message caption, and shared between both chat views. */
function saveChatDraft(value){for(const id of ['cmd','histCmd'])if($(id).value!==value)$(id).value=value;try{localStorage.setItem('givelife-chat-draft',value)}catch(e){}resizeComposer()}
function resizeComposer(){for(const id of ['cmd','histCmd']){const input=$(id);input.style.height='44px';input.style.height=Math.min(120,Math.max(44,input.scrollHeight))+'px'}}
try{saveChatDraft(localStorage.getItem('givelife-chat-draft')||'')}catch(e){}
for(const id of ['cmd','histCmd'])$(id).addEventListener('input',()=>saveChatDraft($(id).value));
function hideKeys(){if(isPhone()){document.activeElement?.blur();$('cmd').blur();$('histCmd').blur()}}
async function submitChat(e,id){e.preventDefault();const value=$(id).value;if(!value.trim())return;
 saveChatDraft('');hideKeys();followReplies();requestAnimationFrame(updateChatViewport);
 try{await act(value)}catch(err){say('app',err.message,1)}
}
$('cmdForm').onsubmit=e=>submitChat(e,'cmd');$('histForm').onsubmit=e=>submitChat(e,'histCmd');
for(const id of ['cmd','histCmd'])$(id).addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();$(id).form.requestSubmit()}});
let viewportFrame=0;
function updateChatViewport(){cancelAnimationFrame(viewportFrame);viewportFrame=requestAnimationFrame(()=>{const v=window.visualViewport;document.documentElement.style.setProperty('--chat-height',Math.round(v?v.height:innerHeight)+'px');document.documentElement.style.setProperty('--chat-top',Math.round(v?v.offsetTop:0)+'px');if($('hist').open){const el=$('histLog');if(scrollState.histLog.follow)followChat(el,history.at(-1)?.who==='app');else el.scrollTop=scrollState.histLog.top}})}
if(window.visualViewport){visualViewport.addEventListener('resize',updateChatViewport);visualViewport.addEventListener('scroll',updateChatViewport)}addEventListener('resize',updateChatViewport);updateChatViewport();
let correctionTurn=null;
function openFeedback(id){correctionTurn=id;$('feedbackText').value='';$('feedbackRemember').checked=false;$('feedbackStatus').textContent='';$('feedbackDialog').showModal();$('feedbackText').focus()}
$('feedbackClose').onclick=()=>$('feedbackDialog').close();
$('feedbackForm').onsubmit=async e=>{e.preventDefault();await logChain;const r=await post('/feedback',{turn_id:correctionTurn,correction:$('feedbackText').value,remember:$('feedbackRemember').checked}),d=await r.json();if(!r.ok){$('feedbackStatus').textContent=d.error;return}$('feedbackDialog').close();status(d.warning||('Correction saved'+($('feedbackRemember').checked?' to memory.':'.')),!!d.warning)};
async function showMemory(){const r=await fetch('/knowledge'),d=await r.json(),box=$('memoryContent');box.textContent='';const stats=document.createElement('p');stats.textContent=d.feedback_count+' confirmed corrections · '+d.archived_turns+' archived turns. Patterns: '+(Object.entries(d.patterns||{}).map(([k,v])=>k+' '+v).join(', ')||'none yet');box.append(stats);for(const item of d.entries||[]){const row=document.createElement('div');row.className='memory-item';const label=document.createElement('p');label.textContent=item.text;const remove=document.createElement('button');remove.type='button';remove.textContent='Forget';remove.onclick=async()=>{await post('/knowledge',{forget:item.id});showMemory()};row.append(label,remove);box.append(row)}if(!$('memoryDialog').open)$('memoryDialog').showModal()}
if($('openMemory'))$('openMemory').onclick=()=>showMemory().catch(e=>status(e.message,1));$('memoryClose').onclick=()=>$('memoryDialog').close();
if($('runChatEval'))$('runChatEval').onclick=async()=>{const b=$('runChatEval'),label=$('chatEvalStatus');b.disabled=true;try{const r=await post('/assistant-evaluate',{}),start=await r.json();if(!r.ok)throw Error(start.error);for(let i=0;i<600;i++){const response=await fetch('/assistant-evaluate/'+start.eval_id),task=await response.json();if(!response.ok)throw Error(task.error||'Could not read evaluation.');label.textContent=(task.results||[]).map(x=>x.case+': '+(x.passed?'passed':'FAILED — '+(x.error||((x.calls||[]).join(', ')+' | '+(x.reply||''))))).join('\n')+'\n'+(task.results||[]).length+'/'+task.total+' complete';if(task.done)break;await new Promise(resolve=>setTimeout(resolve,1000))}}catch(e){label.textContent=e.message}finally{b.disabled=false}};


/* ---- autopilot ---- */
let aiAvailable=false;
function paintAuto(on){autoOn=!!on;$('auto').setAttribute('aria-pressed',String(autoOn));$('auto').setAttribute('aria-checked',String(autoOn));$('auto').querySelector('.lbl').textContent=autoOn?'ON':'OFF';$('live').dataset.on=autoOn?'1':'0';paintStatusLine()}
async function toggleAuto(on){const r=await post('/autopilot',{on}),d=await r.json();paintAuto(d.on);say(d.on||!on?'auto':'app',d.reply,!d.on&&on);if(d.on)pollAuto()}
$('auto').onclick=()=>toggleAuto(!autoOn).catch(e=>say('app',e.message,1));
let liveSnapshot=null,checkedAt=0,pollError='',liveNotice=null,lastAnnouncedError='';
function setLiveNotice(text,error=false){liveNotice={text:String(text||''),error,at:Date.now()};paintStatusLine()}
function paintStatusLine(){const box=$('live');if(!box)return;const offline=!navigator.onLine,wa=$('whatsappConnection')?.dataset.state;
 const error=offline?'No internet':pollError||((wa==='offline'||wa==='error')?'WhatsApp disconnected. Tap its status to reconnect.':'')||(liveNotice?.error&&Date.now()-liveNotice.at<120000?liveNotice.text:'');
 const age=checkedAt?Math.max(0,Math.floor((Date.now()-checkedAt)/1000)):null;
 const recent=liveNotice&&Date.now()-liveNotice.at<90000;
 const serverActive=/^(Sending|Posting|Waiting|On hold|Paused:|Goal complete)/i.test(liveSnapshot?.now||'');
 const activity=error||((watchingJobs.size||operationCount>0)?liveNotice?.text||'Sending…':serverActive?liveSnapshot.now:recent?liveNotice.text:autoOn?(liveSnapshot?.now||'Loading activity…'):'Automatic actions off');
 const text=activity+(age===null?'':` · Checked ${age<60?age+'s':Math.floor(age/60)+'m'} ago`);
 if(error!==lastAnnouncedError){lastAnnouncedError=error;$('liveAnnouncement').textContent=error}
 box.dataset.error=error?'1':'0';$('liveNow').textContent='Auto '+(autoOn?'ON':'OFF');$('liveMeta').textContent=text;$('liveBar').title='Auto '+(autoOn?'ON':'OFF')+' · '+text;$('liveBar').setAttribute('aria-label',$('liveBar').title+' · View details');
}
let autoPolling=false;
async function pollAuto(){if(autoPolling)return;autoPolling=true;try{const r=await fetch('/autopilot');if(!r.ok)throw Error('Status unavailable. Tap for details.');const d=await r.json();checkedAt=Date.now();pollError='';aiAvailable=!!d.ai;liveSnapshot=d.status||null;paintAuto(d.on);paintLive(d.status);for(const x of d.log||[]){if(x.time*1000>seenAuto){seenAuto=x.time*1000;if(!x.q&&x.time*1000>Date.now()-15*60000)say('auto',x.text)}}}catch(e){pollError='Cannot reach cloud. Status may be old.';paintStatusLine()}finally{autoPolling=false}}
setInterval(paintStatusLine,1000);
const waObserver=new MutationObserver(paintStatusLine);if($('whatsappConnection'))waObserver.observe($('whatsappConnection'),{attributes:true,attributeFilter:['data-state']});

/* ---- live box: what Auto is doing right now ---- */
const GN={main:'GiveLife',community:'Upwork Community',fiverr:'Fiverr',upwork:'Upwork',uet:'Fiverr UET',toprated:'Top Rated'};
const PACE={L1:'Normal pace: donations are coming.',L2:'Donations slowed: posting faster.',L3:'Donations very slow: working at full effort.',L4:'Long quiet spell: easing off so the groups do not get tired.'};
function paintLive(st){const box=$('live');if(!st){$('liveMore').textContent=$('liveMeta').textContent;return}
 box.dataset.pace=st.pace;paintStatusLine();
 const n=(st.next||[])[0],t=st.today||{};
 const more=$('liveMore');more.textContent='';
 const add=(k,v)=>{const d=document.createElement('div'),a=document.createElement('div');a.className='k';a.textContent=k;d.textContent=v;more.append(a,d)};
 if(box.dataset.error==='1')add('Needs attention',$('liveMeta').textContent);
 add('Pace',PACE[st.pace]||st.pace);
 if(st.why)add('Right now',st.why);
 if((st.next||[]).length)add('Next posts',st.next.map(x=>`${GN[x.group]||x.group} ${x.in?'in '+x.in+' min':'now'}`).join(' · '));
 add('Today',`${t.posts||0} group posts, ${t.dms||0} DMs, ${t.signals||0} people said they donated`);
 if(st.away_hours>=1)add('You',`Away for ${st.away_hours} h. I am running things; I will only message you if something needs you.`);
 for(const l of (st.learned||[]).slice(0,3))add('Learned',l)}
$('liveBar').onclick=()=>{paintLive(liveSnapshot);const m=$('liveMore'),open=m.hidden;m.hidden=!open;$('liveBar').setAttribute('aria-expanded',String(open))};
document.addEventListener('pointerdown',e=>{if(!$('liveMore').hidden&&!$('live').contains(e.target)){$('liveMore').hidden=true;$('liveBar').setAttribute('aria-expanded','false')}});

/* ---- settings: test AI, DM sources, log out WhatsApp ---- */
const setNote=(id,text,cls)=>{const e=$(id);e.textContent=text;e.className=cls||''};
async function loadSet(){try{const s=(await (await fetch('/autopilot')).json()).summary||{};$('swDm').checked=!!s.dm_enabled;$('swNew').checked=s.dm_new!==false;$('swNew').disabled=!s.dm_enabled;$('set').dataset.daily=s.dm_daily||30}catch(e){}}
async function checkWa(){setNote('waRes','Checking the groups…');try{const d=await (await fetch('/wa-check')).json();
 if(!d.whatsapp)setNote('waRes','Not connected. Use the WhatsApp button at the top.','err');
 else if(d.missing&&d.missing.length)setNote('waRes','Connected, but this number is not in: '+d.missing.join(', ')+'. Link the number that is in the groups.','err');
 else setNote('waRes','Connected and in all 6 groups'+(d.fixed&&d.fixed.length?' (updated '+d.fixed.length+' group link'+(d.fixed.length>1?'s':'')+')':'')+'.','ok')}catch(e){setNote('waRes','Could not check.','err')}}
$('gear').onclick=()=>{$('set').showModal();loadSet();checkWa()};
$('setClose').onclick=()=>$('set').close();
async function saveDms(){const on=$('swDm').checked;$('swNew').disabled=!on;
 try{const r=await post('/autopilot-settings',{action:'dms',enabled:on,daily:+($('set').dataset.daily||30),new_people:$('swNew').checked}),d=await r.json();if(!r.ok)throw Error(d.error);status('✓ '+d.reply)}catch(e){status(e.message||'Could not save',1);loadSet()}}
$('swDm').onchange=saveDms;$('swNew').onchange=saveDms;
$('aiTest').onclick=async()=>{const b=$('aiTest');b.disabled=true;setNote('aiRes','Asking the assistant…');
 try{const d=await (await fetch('/ai-test')).json();d.ok?setNote('aiRes',`Working. Answered in ${(d.ms/1000).toFixed(1)} s.`,'ok'):setNote('aiRes',d.error||'Not working.','err')}
 catch(e){setNote('aiRes','Could not reach the server.','err')}finally{b.disabled=false}};
let outT=null;
$('waOut').onclick=async()=>{const b=$('waOut');
 if(!b.classList.contains('arm')){b.classList.add('arm');b.textContent='Tap again to confirm';clearTimeout(outT);outT=setTimeout(()=>{b.classList.remove('arm');b.textContent='Log out'},4000);return}
 clearTimeout(outT);b.classList.remove('arm');b.textContent='Log out';b.disabled=true;
 try{const r=await post('/wa-logout',{confirm:true}),d=await r.json();if(!r.ok)throw Error(d.error);setNote('waRes','Logged out. Use the WhatsApp dot at the top to link again.','ok');say('app','WhatsApp was logged out. Link it again from the WhatsApp dot at the top.')}
 catch(e){setNote('waRes',e.message,'err')}finally{b.disabled=false}};

$('moreG').onclick=()=>{const c=$('chips'),open=c.hidden;c.hidden=!open;document.body.classList.toggle('more-open',open);$('moreG').setAttribute('aria-expanded',String(open));requestAnimationFrame(fit)};
document.addEventListener('pointerdown',e=>{if(!$('chips').hidden&&!e.target.closest('.group-send,#moreG'))$('moreG').click();const menu=document.querySelector('.overflow-tools');if(menu?.open&&!menu.contains(e.target))menu.open=false});

/* ---- no internet: the page still opens, shows the last message, and says Auto keeps running on the server ---- */
function netBanner(){const off=!navigator.onLine;$('offline').hidden=!off;document.body.classList.toggle('isoffline',off);paintStatusLine()}
addEventListener('online',()=>{netBanner();pollAuto();syncChat()});addEventListener('offline',netBanner);netBanner();
const cached=(k,v)=>{try{if(v===undefined)return JSON.parse(localStorage.getItem('givelife-c-'+k)||'null');localStorage.setItem('givelife-c-'+k,JSON.stringify(v))}catch(e){return null}};

/* ---- hide the message to work only with the buttons and chat ---- */
function setNoMsg(on){if(editing)setEditing(false);document.body.classList.toggle('nomsg',on);$('showMsg').hidden=!on;try{localStorage.setItem('givelife-nomsg',on?'1':'')}catch(e){}if(!on){requestAnimationFrame(fit);flip()}}
$('hideMsg').onclick=e=>{e.stopPropagation();setNoMsg(true)};$('showMsg').onclick=()=>setNoMsg(false);
try{if(localStorage.getItem('givelife-nomsg'))setNoMsg(true)}catch(e){}

/* ---- theme: Auto follows the phone/PC setting; Light or Dark is remembered on this device ---- */
function themeNow(){try{return localStorage.getItem('givelife-theme')||'system'}catch(e){return 'system'}}
function isDark(){const t=document.documentElement.dataset.theme;return t?t==='dark':matchMedia('(prefers-color-scheme:dark)').matches}
function applyTheme(t){const r=document.documentElement;if(t==='light'||t==='dark')r.dataset.theme=t;else delete r.dataset.theme;
 try{localStorage.setItem('givelife-theme',t)}catch(e){}
 document.querySelectorAll('#theme button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.t===t)));
 const m=document.querySelector('meta[name=theme-color]');if(m)m.content=isDark()?'#1a1a18':'#f5f4ef'}
document.querySelectorAll('#theme button').forEach(b=>b.onclick=()=>applyTheme(b.dataset.t));

matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{if(themeNow()==='system')applyTheme('system')});
applyTheme(themeNow());

function flip(){const m=$(view()+'Preview');m.classList.remove('flip');void m.offsetWidth;m.classList.add('flip')}

/* Desktop shortcuts do not move controls or steal focus from dialogs. */
document.addEventListener('keydown',e=>{
 if(typeof e.key!=='string')return;
 if(e.key==='Escape'&&!$('chips').hidden){e.preventDefault();$('moreG').click();$('moreG').focus({preventScroll:true});return}
 if(editing){if(e.key==='Escape'||(e.key==='Enter'&&!e.shiftKey&&!e.isComposing)){e.preventDefault();setEditing(false)}return}
 if(document.querySelector('dialog[open]'))return;
 const inField=['INPUT','TEXTAREA'].includes(document.activeElement.tagName);
 if(e.key==='Escape'&&inField){document.activeElement.blur();return}
 if(inField||e.ctrlKey||e.metaKey||e.altKey||isPhone())return;
 const a={'/':()=>$('cmd').focus(),g:()=>setView('group'),d:()=>setView('dm'),e:()=>setEditing(true),n:()=>$('fresh').click(),c:()=>$('copy').click(),h:()=>setNoMsg(!document.body.classList.contains('nomsg'))}[e.key.toLowerCase()];
 if(a){e.preventDefault();a()}});

/* ---- start ---- */
setView(localStorage.getItem('givelife-view')==='dm'?'dm':'group');
seenAuto=Number(localStorage.getItem('givelife-seen-auto')||0);addEventListener('beforeunload',()=>localStorage.setItem('givelife-seen-auto',String(seenAuto)));
ensureDrafts().then(()=>status('✓ Ready')).catch(()=>{const d=cached('drafts');if(d){applyDrafts(d);status('Offline · showing the last saved message',1)}else status('Could not load',1)});
fetch('/left').then(r=>r.json()).then(d=>{left=d.left;cached('left',d.left);showLeft()}).catch(()=>{const l=cached('left');if(l!=null){left=l;showLeft()}});
fetch('/poster').then(r=>r.ok?r.blob():null).then(b=>{if(b){$('poster').src=URL.createObjectURL(b);$('poster').hidden=false}}).catch(()=>{});
pollAuto();setInterval(pollAuto,10000);pollCamp();


