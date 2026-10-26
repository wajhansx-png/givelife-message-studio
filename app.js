const $=id=>document.getElementById(id);
let editing=false,left=null,timer,saveChain=Promise.resolve(),allT=null,autoOn=false,seenAuto=0;
const view=()=>document.body.dataset.view,fmt=n=>Number(n).toLocaleString('en-US');
const post=(url,body)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
function status(t,bad){const s=$('status');s.textContent=t;s.classList.toggle('err',!!bad)}

/* ---- conversation log (kept on this device) ---- */
let history=[];try{history=JSON.parse(localStorage.getItem('givelife-chat')||'[]')}catch(e){}
let thinking=false;
let rev=null;
function drawLog(anim){const items=history.slice(-40);
 for(const id of ['log','histLog']){const el=$(id),prev=el.scrollTop;el.textContent='';
  items.forEach((h,i)=>{const d=document.createElement('div');d.className='e '+(h.who==='auto'?'sys':h.who==='app'?'bot':h.who)+(h.err?' err':'')+(anim&&i===items.length-1?' in':'');d.dataset.t=h.t;
   d.textContent=rev&&rev.t===h.t?rev.words.slice(0,rev.n).join(''):h.text;el.append(d)});
  if(thinking){const d=document.createElement('div');d.className='e bot dots in';d.innerHTML='<span class="spark">✻</span><em>Thinking…</em>';el.append(d)}
  if(anim){el.scrollTop=prev;el.scrollTo({top:el.scrollHeight,behavior:'smooth'})}else el.scrollTop=el.scrollHeight}}
/* a reply appears word by word, like Claude, then stays */
function prepareReveal(h){clearInterval(rev&&rev.timer);rev=null;
 if(h.who!=='app'||h.err||h.text.length<24||matchMedia('(prefers-reduced-motion:reduce)').matches)return;
 const words=h.text.split(/(\s+)/);rev={t:h.t,words,n:0,timer:0}}
function runReveal(){const r=rev;if(!r)return;const step=Math.max(2,Math.ceil(r.words.length/28));
 r.timer=setInterval(()=>{r.n=Math.min(r.words.length,r.n+step);const txt=r.words.slice(0,r.n).join('');
  document.querySelectorAll('[data-t="'+r.t+'"]').forEach(d=>{d.textContent=txt;const l=d.parentElement;l.scrollTop=l.scrollHeight});
  if(r.n>=r.words.length){clearInterval(r.timer);if(rev===r)rev=null}},32)}
function think(on){thinking=on;drawLog(false)}let logChain=Promise.resolve();
function say(who,text,err){const item={who,text,err:!!err,t:Date.now()};history.push(item);prepareReveal(item);history=history.slice(-80);if(who!=='auto')logChain=logChain.then(()=>post('/chat-log',{who,text,err:!!err})).catch(()=>{});try{localStorage.setItem('givelife-chat',JSON.stringify(history))}catch(e){}drawLog(true);runReveal()}
const GREETING='Hi. Tell me what changed or what to do: "34k left", "came 2000", "Ali 0300 1234567", "send all", or anything else. I remember everything we say here.';
async function syncChat(){try{await logChain;const d=await (await fetch('/chat')).json();
 if(d.items&&d.items.length){history=d.items.slice(-80).map(x=>({who:x.who,text:x.text,err:!!x.err,t:x.t}));try{localStorage.setItem('givelife-chat',JSON.stringify(history))}catch(e){}}
 else if(!history.length)say('app',GREETING);
 else for(const h of history.slice(-40))if(h.who!=='auto')logChain=logChain.then(()=>post('/chat-log',{who:h.who,text:h.text,err:h.err}));
 drawLog(false)}catch(e){if(!history.length)say('app',GREETING)}}
drawLog();syncChat();
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!thinking)syncChat()});
const toEnd=()=>{const l=$('histLog');setTimeout(()=>{l.scrollTop=l.scrollHeight},250)};
$('histCmd').addEventListener('focus',toEnd);if(window.visualViewport)visualViewport.addEventListener('resize',()=>{if($('hist').open)toEnd()});
function openChat(){if($('hist').open)return;syncChat();$('hist').showModal();drawLog();const l=$('histLog');l.scrollTop=l.scrollHeight;$('histCmd').focus()}
const cf=on=>document.body.classList.toggle('cf',!!on&&!isPhone());
$('log').onclick=()=>{if(isPhone())openChat();else{cf(true);$('cmd').focus()}};
/* the chat is big only while you are in it; it shrinks after the click outside has landed, so buttons never move under the finger */
document.addEventListener('pointerdown',e=>{if(!document.body.classList.contains('cf')||e.target.closest('.talk,dialog'))return;
 addEventListener('click',()=>setTimeout(()=>{if(!document.querySelector('.talk').contains(document.activeElement))cf(false)},0),{once:true,capture:false})});
document.querySelector('.talk').addEventListener('focusout',e=>{if(e.relatedTarget&&!e.relatedTarget.closest('.talk'))setTimeout(()=>{if(!document.querySelector('.talk').contains(document.activeElement))cf(false)},0)});
addEventListener('resize',()=>{if(isPhone())cf(false)});
$('histClose').onclick=()=>$('hist').close();
const isPhone=()=>matchMedia('(max-width:899px)').matches;

/* ---- message preview ---- */
function paint(k){$(k+'Preview').innerHTML=waFormat($(k).value).split('\n').map(l=>'<div class="wa-line'+(l?'':' blank')+'">'+(l||'<br>')+'</div>').join('')}
function render(){paint('group');paint('dm');requestAnimationFrame(fit)}
function fit(){if(editing)return;const chat=$('chat'),m=$(view()+'Preview');
 for(let s=isPhone()?16:22;s>=11;s-=.5){m.style.fontSize=s+'px';if(m.scrollHeight<=chat.clientHeight-30)break}
 chat.style.overflowY=m.scrollHeight>chat.clientHeight-30?'auto':'hidden'}
new ResizeObserver(()=>requestAnimationFrame(fit)).observe($('chat'));
function save(){const data={group:$('group').value,dm:$('dm').value};
 saveChain=saveChain.catch(()=>{}).then(async()=>{const r=await post('/drafts',data);if(!r.ok)throw Error('Save failed');status('✓ Saved')});return saveChain}
function saveSoon(){status('Saving…');clearTimeout(timer);timer=setTimeout(()=>save().catch(()=>status('Save failed',1)),300)}

/* ---- edit in place ---- */
function ser(n){if(n.nodeType===3)return n.nodeValue;if(n.nodeName==='BR')return '\n';
 const inner=[...n.childNodes].map(ser).join(''),t=n.nodeName;
 if(t==='STRONG'||t==='B')return inner.trim()?'*'+inner+'*':inner;if(t==='EM'||t==='I')return inner.trim()?'_'+inner+'_':inner;
 if(t==='S')return inner.trim()?'~'+inner+'~':inner;if(t==='CODE')return '`'+inner+'`';
 if(n.classList&&n.classList.contains('wa-list'))return '* '+inner.replace(/^•\s+/,'');
 if(t==='DIV'&&!(n.classList&&n.classList.contains('wa-line')))return '\n'+inner;return inner}
function readPreview(k){return [...$(k+'Preview').children].map(d=>d.classList.contains('blank')&&!d.textContent.trim()?'':ser(d).replace(/\n$/,'')).join('\n').replace(/ /g,' ')}
function setEditing(on,x,y){const k=view(),m=$(k+'Preview');if(on===editing)return;editing=on;
 document.body.classList.toggle('editing',on);$('edit').textContent=on?'Done':'Edit';$('edit').classList.toggle('on',on);
 if(on){m.contentEditable='true';const r=x!=null&&document.caretRangeFromPoint?document.caretRangeFromPoint(x,y):null;m.focus();if(r){const s=getSelection();s.removeAllRanges();s.addRange(r)}status('Editing · Enter = done · Shift+Enter = new line')}
 else{m.contentEditable='false';$(k).value=readPreview(k);render();save().catch(()=>status('Save failed',1))}}
$('edit').onclick=()=>setEditing(!editing);
$('chat').addEventListener('click',e=>{if(!editing)setEditing(true,e.clientX,e.clientY)});
for(const k of ['group','dm'])$(k+'Preview').addEventListener('paste',e=>{e.preventDefault();document.execCommand('insertText',false,(e.clipboardData.getData('text/plain')||'').replace(/\r/g,''))});

/* ---- views, amount, DM greeting ---- */
function setView(v){if(editing)setEditing(false);document.body.dataset.view=v;document.querySelectorAll('[data-view-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.viewButton===v)));
 $('ctx').textContent=v==='group'?'Group message · poster attached':'DM · poster attached';localStorage.setItem('givelife-view',v);requestAnimationFrame(fit);flip()}
document.querySelectorAll('[data-view-button]').forEach(b=>b.onclick=()=>setView(b.dataset.viewButton));
function showLeft(){const c=$('leftChip');c.textContent=left==null?'Rs. …':'Rs. '+fmt(left);const w=document.createElement('span');w.className='lw';w.textContent=' left';c.append(w)}
function applyDrafts(d){if(d.group!=null)$('group').value=d.group;if(d.dm!=null)$('dm').value=d.dm;if(d.left!=null){left=d.left;showLeft()}applyGreeting(false);render()}
async function setLeft(n){if(editing)setEditing(false);const r=await post('/left',{left:n}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not update amount');applyDrafts(d);await save()}
$('leftChip').onclick=()=>{const c=$('cmd');c.value='';c.placeholder='New amount left, e.g. 34000 or 34k';c.focus()};
let gender='Brother';
function greet(){const n=$('dmName').value.trim();return (n?n+' ':'')+gender}
const GREET=/^(?:[^\n,]{0,40}\s)?(?:Brother|Sister),\s/;
function applyGreeting(doSave=true){const t=$('dm').value;if(!t)return;const g=greet()+', ',nt=GREET.test(t)?t.replace(GREET,g):g+t;
 if(nt!==t){$('dm').value=nt;paint('dm');requestAnimationFrame(fit);if(doSave)saveSoon()}}
function setGender(g){gender=g;document.querySelectorAll('#gender button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.g===g)));applyGreeting()}
document.querySelectorAll('#gender button').forEach(b=>b.onclick=()=>setGender(b.dataset.g));
$('dmName').addEventListener('input',()=>applyGreeting());

/* ---- tools ---- */
async function freshWording(){if(editing)setEditing(false);const k=view();clearTimeout(timer);await save();const r=await post(k==='group'?'/next-message':'/next-dm'),d=await r.json();$(k).value=d.message;if(k==='dm')applyGreeting(false);render();flip();await save()}
$('fresh').onclick=async()=>{$('fresh').disabled=true;try{await freshWording();status('✓ New wording ready')}catch(e){status('Could not make new wording',1)}finally{$('fresh').disabled=false}};
$('copy').onclick=async()=>{if(editing)setEditing(false);try{await navigator.clipboard.writeText($(view()).value);status('✓ Copied')}catch(e){status('Copy failed',1)}};

/* ---- sending ---- */
function busy(on){document.body.classList.toggle('sending',on);document.querySelectorAll('[data-group],#sendAll,[data-test],#sendDm,#fresh').forEach(b=>b.disabled=on)}
async function sendGroup(key){if(editing)setEditing(false);if(!$('chips').hidden)$('moreG').click();busy(true);
 try{clearTimeout(timer);await save();$('groupStatus').textContent='Starting…';
  const r=await post('/send-group',{group:key,message:$('group').value}),start=await r.json();if(!r.ok)throw Error(start.error||'Could not start');
  let done=false;while(!done){const j=await (await fetch('/send-status/'+start.job_id)).json();
   $('groupStatus').textContent=j.message+'\n'+j.results.map(x=>x.group+': '+(x.code==='SUCCESS'?'✓ Sent':x.message)).join('\n');done=j.done;
   if(done){say('app',j.message+(j.results.length?' '+j.results.map(x=>x.group+(x.code==='SUCCESS'?' ✓':' ✗')).join(', '):''));if(j.next_caption){$('group').value=j.next_caption;render()}}
   if(!done)await new Promise(res=>setTimeout(res,1500))}}
 catch(e){$('groupStatus').textContent='✗ '+e.message;say('app',e.message,1)}finally{busy(false);requestAnimationFrame(fit)}}
document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>sendGroup(b.dataset.group));
function armAll(){const b=$('sendAll'),txt='Send to ALL 6 groups';
 if(allT){clearInterval(allT);allT=null;b.classList.remove('arm');b.textContent=txt;say('app','Cancelled. Nothing was sent.');return}
 let n=3;b.classList.add('arm');b.textContent=`Sending in ${n}… tap to cancel`;
 allT=setInterval(()=>{n--;if(n>0){b.textContent=`Sending in ${n}… tap to cancel`;return}clearInterval(allT);allT=null;b.classList.remove('arm');b.textContent=txt;sendGroup('all')},1000)}
$('sendAll').onclick=armAll;
async function sendTest(kind){busy(true);try{clearTimeout(timer);await save();const r=await post('/test',{message:$(kind).value}),d=await r.json();say('app',d.code==='SUCCESS'?'✓ Sent to the test group.':'Test failed: '+(d.message||d.error||''),d.code!=='SUCCESS')}
 catch(e){say('app',e.message||'Could not send',1)}finally{busy(false)}}
document.querySelectorAll('[data-test]').forEach(b=>b.onclick=()=>{if(editing)setEditing(false);sendTest(b.dataset.test)});
function cleanPhone(p){p=p.replace(/[\s()+-]/g,'');if(p.startsWith('00'))p=p.slice(2);if(/^03\d{9}$/.test(p))p='92'+p.slice(1);return /^[1-9]\d{7,14}$/.test(p)?p:''}
$('sendDm').onclick=async()=>{if(editing)setEditing(false);const phone=cleanPhone($('dmPhone').value);
 if(!phone){say('app','Enter a phone number first, e.g. 0300 1234567.',1);$('dmPhone').focus();return}
 busy(true);try{applyGreeting(false);clearTimeout(timer);await save();
  const r=await post('/send-custom',{target:'phone',phone,message:$('dm').value,poster:true}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not send');
  if(d.code==='SUCCESS'){say('app','✓ DM sent to '+greet()+'. New wording is ready for the next person.');$('dmPhone').value='';$('dmName').value='';setGender('Brother');await freshWording()}
  else say('app','Not confirmed: '+(d.message||'')+' Check WhatsApp before retrying.',1)}
 catch(e){say('app',e.message,1)}finally{busy(false)}};

/* ---- send a plain message to a contact, group or number: works without the AI ---- */
async function sendTo(who,text){
 let to=who;const g=GKEY(who);
 if(g)to=g;else if(who&&!/^\+?\d[\d\s-]{6,}$/.test(who)){
  const r=await post('/find',{query:who}),d=await r.json();
  if(!d.items.length)return `I checked your chats and contacts (${d.checked}) and found nobody called "${who}". Send me the number and I will message it.`;
  if(d.items.length>1&&!d.items.some(x=>x.name.toLowerCase()===who.toLowerCase()))return 'Which one?\n'+d.items.slice(0,5).map((x,i)=>`${i+1}. ${x.name}`).join('\n')+'\nSay: send '+text+' to <full name>.';
  const hit=d.items.find(x=>x.name.toLowerCase()===who.toLowerCase())||d.items[0];to=hit.id;who=hit.name}
 const r=await post('/send-now',{to,text,with_picture:false}),d=await r.json();
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
let campTimer=null,lastCampLog=localStorage.getItem('givelife-camp-last')||'';
async function pollCamp(){clearTimeout(campTimer);try{const c=await (await fetch('/campaign')).json();
 if(c.running){const w=c.wait?` · next in ${Math.floor(c.wait/60)}:${String(c.wait%60).padStart(2,'0')}`:'';showCamp(`DMs ${c.sent}/${c.total} sent${c.skipped?`, ${c.skipped} skipped`:''}${w}${c.current&&c.current!=='Waiting'?' · '+c.current:''}`);campTimer=setTimeout(pollCamp,3000)}
 else if(!listT){$('camp').hidden=true;const last=(c.log||[]).slice(-1)[0];if(c.total&&last&&last!==lastCampLog){lastCampLog=last;try{localStorage.setItem('givelife-camp-last',last)}catch(e){}say('app',`DM list done: ${c.sent} sent, ${c.skipped} skipped, ${c.failed} failed.`)}}}catch(e){}}
$('campStop').onclick=async()=>{if(listT){clearTimeout(listT);listT=null;$('camp').hidden=true;say('app','Cancelled. Nothing was sent.');return}
 const r=await post('/campaign',{stop:true}),d=await r.json();say('app',d.reply)};

/* ---- the assistant: quick commands work instantly; anything else goes to the AI ---- */
const num=(s,k)=>Math.round(parseFloat(s.replace(/,/g,''))*(k?1000:1));
async function quick(t){const low=t.toLowerCase();let m;
 if(m=low.match(/^(?:came|got|received|recieved|aya|aaya|aye|aaye|\+)\s*(?:rs\.?\s*)?([\d,.]+)\s*(k)?\s*(?:came|aya|aaya)?$/)){
  if(left==null)throw Error('Amount left is not loaded yet.');const n=num(m[1],m[2]),nl=Math.max(0,left-n);await setLeft(nl);return `Rs. ${fmt(n)} came. Rs. ${fmt(nl)} left now; both messages updated.`}
 if(!/3\d{2}[\s-]?\d{7}/.test(t)&&(m=low.match(/^(?:left|remain(?:ing)?|baqi|need(?:ed)?)?\s*(?:rs\.?\s*)?([\d,.]+)\s*(k)?\s*(?:left|remain(?:ing)?|remains|baqi|reh gaye|needed)?$/))){
  const n=num(m[1],m[2]);if(!(n>=0&&n<=10000000))throw Error('That amount looks wrong.');await setLeft(n);return `Rs. ${fmt(n)} left. Both messages updated.`}
 if(/\bpapers?\b|\breports?\b|\bdocuments?\b/i.test(t)&&attached&&/\b(these|this|is|are|save|use|add)\b/i.test(t)){const r=await post('/upload-image',{data:attached.data,use:'papers'}),d=await r.json();if(!r.ok)throw Error(d.error);
  clearAttachment();return `Saved as medical papers (${String(d.id).replace('papers-','')} page${d.id==='papers-1'?'':'s'} so far). I will send them privately to anyone who asks. Attach more pages the same way.`}
 if(m=low.match(/^(?:pace|speed)\s+(\d+)\s*(?:\/|and|,|\s)\s*(\d+)$/)){const r=await post('/autopilot-settings',{action:'pace',main:+m[1],freelance:+m[2]}),d=await r.json();return d.reply||d.error}
 if(/^(normal|default) (pace|speed)$/.test(low)){const r=await post('/autopilot-settings',{action:'pace',main:0,freelance:0}),d=await r.json();return d.reply}
 if(/\b(make|use|set)\b.*\bposter\b|^poster$/i.test(t)&&attached){const r=await post('/upload-image',{data:attached.data,use:'poster'}),d=await r.json();if(!r.ok)throw Error(d.error);
  $('poster').src=attached.url;$('poster').hidden=false;clearAttachment();return 'Done. This picture is now the poster for group posts and DMs.'}
 if(/^(hi+|hello|hey|salam|assalam[\w\s-]*|ok|okay|thanks|thank you|shukriya|jazakallah)\W*$/i.test(t))return /^(thanks|thank you|shukriya|jazakallah)/i.test(t)?'Anytime.':'Hi. What should I do?';
 const BATCH=async b=>{const r=await post('/dm-batch',b),d=await r.json();if(!r.ok)throw Error(d.error||'Could not start');return d.reply};
 if(m=t.match(/^(?:send\s+)?(?:(\d+)\s+)?(?:dms?|messages?)\s+(?:to\s+)?(?:(\d+)\s+)?(?:my\s+|our\s+|the\s+|past\s+|old\s+|existing\s+)*donors?$/i))return await BATCH({kind:'donors',count:+(m[1]||m[2]||10)});
 if(m=t.match(/^(?:send\s+)?(?:(\d+)\s+)?(?:dms?|messages?)\s+(?:to\s+)?(?:(\d+)\s+)?(?:members?\s+|people\s+|persons\s+)?(?:of|from|in)\s+(?:the\s+)?(.+?)(?:\s+group)?$/i)){const g=GKEY(m[3]);if(g&&g!=='test')return await BATCH({kind:'group',group:g,count:+(m[1]||m[2]||10)})}
 const TIMED=/\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\bat\s+\d{1,2}\b|\b(daily|every day|every \d+)\b/i;
 if((m=t.match(/^(?:send|bhejo|message|msg|text)\s+(.+?)\s+(?:to|ko)\s+(.+)$/i))&&!/^(all|main|free|test|these|them|this|it|the (?:appeal|poster|message))\b/i.test(m[1])&&!TIMED.test(t)){
  return await sendTo(m[2].trim(),m[1].replace(/^["“'](.*)["”']$/,'$1'))}
 if((m=t.match(/^(?:send|bhejo)\s+(?!(?:all|main|free|test|to|the|a|my|these|them|this)\b)(.{1,300})$/i))&&!/\b(groups?|poster|picture|image)\b/i.test(m[1])&&!TIMED.test(t)&&!/3\d{2}[\s-]?\d{7}/.test(m[1])){
  return await sendTo('',m[1].replace(/^["“'](.*)["”']$/,'$1'))}
 const list=parseList(t);
 if(list.people.length>=2||(list.people.length===1&&/\b(send|bhejo|message|msg|dm)\b/i.test(t))){startList(list);return null}
 if(m=t.match(/(?:\+?92|0092|0)?[\s-]?3\d{2}[\s-]?\d{7}/)){
  const phone=m[0].trim();let rest=(t.slice(0,m.index)+' '+t.slice(m.index+m[0].length)).trim();
  const sister=/\b(sister|sis|behen|behan|baji|madam|miss|mrs)\b/i.test(rest);
  rest=rest.replace(/\b(sister|sis|behen|behan|baji|madam|miss|mrs|brother|bro|bhai|mr|dm|send|to)\b/gi,'').replace(/[^\p{L}\s.'-]/gu,'').replace(/\s+/g,' ').trim();
  const name=rest&&/^\p{L}/u.test(rest)&&rest.length<=30?rest.replace(/\b\p{L}/gu,c=>c.toUpperCase()):'';
  setView('dm');$('dmPhone').value=phone;$('dmName').value=name;setGender(sister?'Sister':'Brother');
  return `Ready: DM to ${greet()} (${phone}). Tap "Send DM with poster".`}
 if(m=low.match(/^(?:rules?|my rules|show rules|list rules)$/)){const d=await (await fetch('/rules')).json();return d.items.length?'Auto mode follows:\n'+d.items.map((x,i)=>`${i+1}. ${x.text}`).join('\n')+'\nSay "forget 2" to remove one.':'No rules yet. With Auto on, just tell me things like "post in fiverr every 30 min" or "no posting 2am to 7am".'}
 if(m=low.match(/^(?:forget|delete|remove)\s+(?:rule\s*)?#?(\d+)$/)){const d=await (await fetch('/rules')).json(),it=d.items[+m[1]-1];if(!it)return 'There is no rule '+m[1]+'.';await post('/rules',{delete:it.id});return 'Removed: '+it.text}
 if(/^(send )?(to )?all( groups)?$/.test(low)){setView('group');armAll();return 'Sending to all 6 groups in 3 seconds. Tap the orange button to cancel.'}
 if(/^(new|regenerate|next|naya)$/.test(low)){await freshWording();return 'New wording ready.'}
 if(/^copy$/.test(low)){$('copy').click();return 'Copied.'}
 if(/^(dm|group)$/.test(low)){setView(low);return 'Switched to '+low.toUpperCase()+'.'}
 if(m=t.match(/^(?:remember|yaad rakho|note)[:\s]+(.{3,})$/i)){const r=await post('/memory',{rule:m[1]}),d=await r.json();return d.reply}
 if(/^auto(pilot)?\s+(on|off)$/.test(low)){await toggleAuto(/on$/.test(low));return null}
 const G={main:'main',givelife:'main',community:'community','upwork community':'community',fiverr:'fiverr','fiverr course':'fiverr',upwork:'upwork','upwork course':'upwork',uet:'uet','fiverr uet':'uet',toprated:'toprated','top rated':'toprated'};
 const setting=async b=>{const r=await post('/autopilot-settings',b),d=await r.json();if(!r.ok)throw Error(d.error);return d.reply};
 if(m=low.match(/^(pause|stop posting in|stop)\s+([a-z ]+?)(?:\s+for\s+(\d+)\s*(h|hours?|d|days?))?$/)){const k=G[m[2].trim()];if(k)return setting({action:'pause',key:k,hours:m[3]?(+m[3])*(/^d/.test(m[4])?24:1):24})}
 if(m=low.match(/^(resume|start posting in|start)\s+([a-z ]+)$/)){const k=G[m[2].trim()];if(k)return setting({action:'resume',key:k})}
 if(m=low.match(/^(?:send|post|share|bhejo|daalo|dalo)(?:\s+(?:it|this|message|msg|post))?(?:\s+(?:in|to|on|mein|me|main))?\s+([a-z ]+?)(?:\s+(?:group|groups|mein|me))?$/)){
  const w=m[1].trim(),k=G[w]||({freelance:'free','all freelance':'free','5 freelance':'free',test:'test','test group':'test',all:'all','all groups':'all'})[w];
  if(k){setView('group');if(k==='all'){armAll();return 'Sending to all 6 groups in 3 seconds. Tap the orange button to cancel.'}
   if(k==='test'){sendTest('group');return 'Sending to the test group.'}sendGroup(k);return 'Sending to '+({main:'GiveLife main',free:'all 5 freelance groups',community:'Upwork Community',fiverr:'Fiverr Course',upwork:'Upwork Course',uet:'Fiverr UET',toprated:'Top Rated'}[k]||k)+' now.'}}
 if(m=low.match(/^quiet\s+(\d{1,2})\s*(?:-|to)?\s*(\d{1,2})$/))return setting({action:'quiet',start:+m[1],end:+m[2]});
 if(/^quiet off$/.test(low))return setting({action:'quiet',start:0,end:0});
 if(m=low.match(/^(?:auto )?dms?\s+(on|off)(?:\s+(\d+))?$/))return setting({action:'dms',enabled:m[1]==='on',daily:m[2]?+m[2]:30});
 if(/^(status|report|kya haal|halat)$/.test(low)){const d=await (await fetch('/autopilot')).json(),s=d.summary||{};
  return `Autopilot ${d.on?'ON':'OFF'} · pace ${s.pace} (main every ${s.main_every} min, freelance every ${s.freelance_every} min) · ${s.minutes_since_money} min since money · today ${s.posts_today} posts, ${s.dms_today}/${s.dm_daily} DMs, ${s.possible_donations_today} possible donations`+(Object.keys(s.paused||{}).length?` · paused: ${Object.keys(s.paused).join(', ')}`:'')+(s.quiet?` · quiet ${s.quiet[0]}–${s.quiet[1]}h`:'')}
 if(t.length>=60&&t.includes('\n')){const k=view();$(k).value=t;if(k==='dm')applyGreeting(false);render();await save();return 'Your text is now the '+k.toUpperCase()+' message.'}
 return undefined}
async function act(text){const t=text.trim();if(!t)return;say('you',t);
 const q=await quick(t);if(q!==undefined){if(q)say('app',q);return}
 const rr=await post('/rule-text',{text:t}),rd=await rr.json().catch(()=>({}));
 if(rd.rule){if(rd.saved){say('app','Rule saved: '+rd.summary+' Auto mode will follow it. Say "rules" to see them all.');return}
  if(!aiAvailable){say('app',rd.summary+' Auto mode is off, so I did not save it as a rule. Say "auto on" and tell me again.');return}}
 think(true);let r,d;
 try{await logChain;r=await post('/assistant',{text:t,image:attached?attached.id:null,history:history.slice(-13,-1),screen:{view:view(),dm:{name:$('dmName').value,phone:$('dmPhone').value,gender}}});d=await r.json().catch(()=>({}))}finally{think(false)}
 if(r.status===503){say('app','I did not understand that, and the AI assistant is not connected, so only direct commands work. Try: "34k left", "came 2000", "send hi to Ali", "send main", "fiverr every 30 min", "rules".',1);return}
 if(!r.ok)throw Error(d.error||'The assistant could not answer.');
 applyDrafts(d);if(d.autopilot!=null)paintAuto(d.autopilot);say('app',d.reply);
 for(const a of d.actions||[]){
  if(a.type==='prepare_dm'){setView('dm');$('dmPhone').value=a.phone||'';$('dmName').value=a.name||'';setGender(a.gender==='Sister'?'Sister':'Brother')}
  }}
const hideKeys=()=>{if(matchMedia('(pointer:coarse)').matches&&document.activeElement&&document.activeElement.blur)document.activeElement.blur()};
$('cmdForm').onsubmit=async e=>{e.preventDefault();const c=$('cmd'),v=c.value;c.value='';hideKeys();
 try{await act(v)}catch(err){say('app',err.message,1)}paintAuto(autoOn)};
$('histForm').onsubmit=async e=>{e.preventDefault();const c=$('histCmd'),v=c.value;c.value='';hideKeys();try{await act(v)}catch(err){say('app',err.message,1)}};
$('cmd').addEventListener('focus',()=>{if(isPhone()){$('cmd').blur();openChat()}else cf(true)});

/* ---- autopilot ---- */
let aiAvailable=false;
function paintAuto(on){autoOn=!!on;$('auto').setAttribute('aria-pressed',String(autoOn));$('auto').querySelector('.lbl').textContent=autoOn?'ON':'OFF';$('live').dataset.on=autoOn?'1':'0';
 if(!autoOn){$('liveNow').textContent='Auto is off';$('liveMeta').textContent='Switch on: runs 24 hours';$('liveMore').hidden=true;$('liveBar').setAttribute('aria-expanded','false')}
 const ph=autoOn?'Auto is on · tell me rules…':'Message GiveLife…';$('cmd').placeholder=ph;$('histCmd').placeholder=autoOn?'Auto is on · tell me rules…':'Reply to GiveLife…'}
async function toggleAuto(on){const r=await post('/autopilot',{on}),d=await r.json();paintAuto(d.on);say(d.on||!on?'auto':'app',d.reply,!d.on&&on);if(d.on)pollAuto()}
$('auto').onclick=()=>toggleAuto(!autoOn).catch(e=>say('app',e.message,1));
async function pollAuto(){try{const d=await (await fetch('/autopilot')).json();aiAvailable=!!d.ai;paintAuto(d.on);paintLive(d.status);for(const x of d.log||[]){if(x.time*1000>seenAuto){seenAuto=x.time*1000;if(!x.q&&x.time*1000>Date.now()-15*60000)say('auto',x.text)}}}catch(e){}}

/* ---- live box: what Auto is doing right now ---- */
const GN={main:'GiveLife',community:'Upwork Community',fiverr:'Fiverr',upwork:'Upwork',uet:'Fiverr UET',toprated:'Top Rated'};
const PACE={L1:'Normal pace: donations are coming.',L2:'Donations slowed: posting faster.',L3:'Donations very slow: working at full effort.',L4:'Long quiet spell: easing off so the groups do not get tired.'};
function paintLive(st){const box=$('live');if(!autoOn||!st)return;
 box.dataset.pace=st.pace;$('liveNow').textContent=st.now;
 const n=(st.next||[])[0],t=st.today||{};
 $('liveMeta').textContent=(n?`Next: ${GN[n.group]||n.group} ${n.in?'in '+n.in+' min':'now'} · `:'')+`${t.posts||0} posts · ${t.dms||0} DMs`;
 const more=$('liveMore');more.textContent='';
 const add=(k,v)=>{const d=document.createElement('div'),a=document.createElement('div');a.className='k';a.textContent=k;d.textContent=v;more.append(a,d)};
 add('Pace',PACE[st.pace]||st.pace);
 if(st.why)add('Right now',st.why);
 if((st.next||[]).length)add('Next posts',st.next.map(x=>`${GN[x.group]||x.group} ${x.in?'in '+x.in+' min':'now'}`).join(' · '));
 add('Today',`${t.posts||0} group posts, ${t.dms||0} DMs, ${t.signals||0} people said they donated`);
 if(st.away_hours>=1)add('You',`Away for ${st.away_hours} h. I am running things; I will only message you if something needs you.`);
 for(const l of (st.learned||[]).slice(0,3))add('Learned',l)}
$('liveBar').onclick=()=>{const m=$('liveMore'),open=m.hidden;m.hidden=!open;$('liveBar').setAttribute('aria-expanded',String(open))};
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

/* ---- suggestions: what the owner would do next; one tap to do it ---- */
let sug=null;const dismissed=()=>{try{return JSON.parse(localStorage.getItem('givelife-dismissed')||'{}')}catch(e){return{}}};
function paintPace(s){const p=$('pace');if(!p||!s)return;p.dataset.pace=s.pace;p.title=s.pace==='L1'?'Donations normal':`No money for ${s.minutes_since_money} min`}
async function pollSuggestions(){try{const d=await (await fetch('/suggestions')).json();paintPace(d.summary);const dm=dismissed(),now=Date.now();
 sug=(d.items||[]).find(x=>!(dm[x.id]>now)&&!(d.autopilot&&x.action!=='owner'))||null;
 $('sugg').hidden=!sug;if(sug){$('suggText').textContent=isPhone()&&sug.short?sug.short:sug.text;$('suggText').title=sug.text;$('suggDo').textContent=sug.action==='owner'?'OK, noted':'Do it';$('sugg').dataset.level=sug.level}}catch(e){}}
function dismiss(hours){if(!sug)return;const dm=dismissed();dm[sug.id]=Date.now()+hours*3600e3;try{localStorage.setItem('givelife-dismissed',JSON.stringify(dm))}catch(e){}$('sugg').hidden=true}
$('suggNo').onclick=()=>dismiss(1);
$('suggDo').onclick=async()=>{if(!sug)return;const s=sug;dismiss(s.action==='owner'?6:0.5);
 if(s.action==='send_all'){setView('group');await freshWording();armAll();say('app','Fresh message going to all groups. Tap the orange button within 3 seconds to cancel.')}
 else if(s.action==='dm_batch'||s.action==='share'){const r=await post('/suggestion',{action:s.action}),d=await r.json();say('app',d.reply||d.error,!r.ok)}
 else say('app','Noted: '+s.text)};

$('moreG').onclick=()=>{const c=$('chips'),open=c.hidden;c.hidden=!open;document.body.classList.toggle('more-open',open);$('moreG').setAttribute('aria-expanded',String(open));requestAnimationFrame(fit)};

/* ---- theme: Auto follows the phone/PC setting; Light or Dark is remembered on this device ---- */
function themeNow(){try{return localStorage.getItem('givelife-theme')||'system'}catch(e){return 'system'}}
function isDark(){const t=document.documentElement.dataset.theme;return t?t==='dark':matchMedia('(prefers-color-scheme:dark)').matches}
function applyTheme(t){const r=document.documentElement;if(t==='light'||t==='dark')r.dataset.theme=t;else delete r.dataset.theme;
 try{localStorage.setItem('givelife-theme',t)}catch(e){}
 document.querySelectorAll('#theme button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.t===t)));
 const m=document.querySelector('meta[name=theme-color]');if(m)m.content=isDark()?'#1a1a18':'#f5f4ef'}
document.querySelectorAll('#theme button').forEach(b=>b.onclick=()=>applyTheme(b.dataset.t));
$('themeBtn').onclick=()=>applyTheme(isDark()?'light':'dark');
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{if(themeNow()==='system')applyTheme('system')});
applyTheme(themeNow());

/* ---- touch feel: tapping send/attach never opens or closes the keyboard; light haptic on every button ---- */
document.querySelectorAll('.composer .go,.composer .clip').forEach(b=>b.addEventListener('pointerdown',e=>e.preventDefault()));
document.addEventListener('pointerdown',e=>{if(e.target.closest('button')&&navigator.vibrate)try{navigator.vibrate(8)}catch(x){}},{passive:true});
function flip(){const m=$(view()+'Preview');m.classList.remove('flip');void m.offsetWidth;m.classList.add('flip')}

/* ---- keyboard: the cursor lives in the chat box ---- */
document.addEventListener('keydown',e=>{
 if(editing){if(e.key==='Escape'||(e.key==='Enter'&&!e.shiftKey)){e.preventDefault();setEditing(false)}return}
 const inField=['INPUT','TEXTAREA'].includes(document.activeElement.tagName);
 if(e.key==='Escape'&&inField){document.activeElement.blur();return}
 if(inField||e.ctrlKey||e.metaKey||e.altKey)return;
 const a={'/':()=>$('cmd').focus(),g:()=>setView('group'),d:()=>setView('dm'),e:()=>setEditing(true),n:()=>$('fresh').click(),c:()=>$('copy').click()}[e.key.toLowerCase()];
 if(a){e.preventDefault();a()}else if(e.key.length===1){$('cmd').focus()}});

/* ---- start ---- */
setView(localStorage.getItem('givelife-view')==='dm'?'dm':'group');
seenAuto=Number(localStorage.getItem('givelife-seen-auto')||0);addEventListener('beforeunload',()=>localStorage.setItem('givelife-seen-auto',String(seenAuto)));
fetch('/drafts').then(r=>r.json()).then(d=>{applyDrafts(d);status('✓ Ready')}).catch(()=>status('Could not load',1));
fetch('/left').then(r=>r.json()).then(d=>{left=d.left;showLeft()}).catch(()=>{});
fetch('/poster').then(r=>r.ok?r.blob():null).then(b=>{if(b){$('poster').src=URL.createObjectURL(b);$('poster').hidden=false}}).catch(()=>{});
pollAuto();setInterval(pollAuto,10000);pollSuggestions();setInterval(pollSuggestions,60000);pollCamp();

