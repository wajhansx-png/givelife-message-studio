const $=id=>document.getElementById(id);
let draftSaved=null,draftsReady=false,draftsLoad=null;
let editing=false,left=null,timer,saveChain=Promise.resolve(),allT=null,autoOn=false,autoKnown=false,seenAuto=0;
const view=()=>document.body.dataset.view,fmt=n=>Number(n).toLocaleString('en-US');
const post=(url,body)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
/* Where you are lives in the address (#/donors/important). A refresh stays put and the phone's Back button steps out one screen. */
const Nav={rendering:false,
 path(){try{return decodeURIComponent((location.hash||'').replace(/^#\/?/,''))}catch(e){return ''}},
 top(){return Nav.path().split('/')[0]},
 /* The chat log below owns the name `history`, so the browser's is always reached as window.history. */
 valid(path){return /^(?:chat|settings(?:\/(?:memory|poster))?|keyboard|team|preview|whatsapp|donors\/(?:all|important|donated|not_donated|not_contacted|volunteers|messages)(?:\/(?:notes|add|bulk|pace))?)$/.test(path)},
 go(path,{replace=false}={}){if(Nav.rendering||Nav.path()===path)return;const h=window.history,from=replace?h.state?.from:Nav.path();try{(replace?h.replaceState:h.pushState).call(h,{nav:1,from:Nav.valid(from)?from:''},'',path?'#/'+path:location.pathname+location.search);dispatchEvent(new Event('studio-navigate'))}catch(e){}},
 // Close synchronously. A delayed history.back() can undo the next tap or race a refresh.
 leave(name){if(Nav.rendering||Nav.top()!==name)return;const from=window.history.state?.from;Nav.go(Nav.valid(from)&&from.split('/')[0]!==name?from:'',{replace:true});renderNav()}};
/* Server-issued next steps are tied to the exact saved draft, never AI-authored commands. */
let nextActions=[],nextActionEpoch=0;const nextActionPending=new Set();
function drawNextActions(){renderSendMode();requestAnimationFrame(()=>fitConversation());for(const id of ['chatNextActions','histNextActions']){const row=$(id);if(!row)continue;row.textContent='';row.hidden=!nextActions.length;for(const a of nextActions){const b=document.createElement('button');b.type='button';b.textContent=a.label;b.title=a.detail||'';b.disabled=!!a.disabled||nextActionPending.has(a.id);b.setAttribute('aria-label',a.label+(a.detail?' · '+a.detail:''));b.onclick=()=>runNextAction(a);row.append(b)}}}
function renderSendMode(){const label=$('sendMode');if(!label)return;const mode=nextActions[0]?.detail||'Poster + caption';label.textContent=mode;if($('ctx'))$('ctx').textContent=view()==='group'?(mode==='Text only'?'Group · text only':'Group · poster'):($('dmPoster')?.checked===false?'DM · text only':'DM · poster');if($('poster')?.src)$('poster').hidden=view()==='group'&&mode==='Text only'}
function clearNextActions(){nextActionEpoch++;nextActions=[];drawNextActions()}
async function refreshNextActions(){const epoch=++nextActionEpoch;try{const r=await fetch('/chat-next-actions');if(!r.ok)return;const d=await r.json();if(epoch!==nextActionEpoch)return;nextActions=(Array.isArray(d.items)?d.items:[]).filter(a=>a&&/^[a-f0-9]{32}$/.test(a.id)&&typeof a.label==='string').slice(0,3);drawNextActions()}catch(e){}}
async function runNextAction(a){if(a.disabled||nextActionPending.has(a.id))return;nextActionPending.add(a.id);drawNextActions();try{const r=await post('/chat-action',{action_id:a.id}),d=await r.json();if(!r.ok)throw Error(d.error||'This action is unavailable. Refresh the draft.');if(d.choose_group){closeChat();setView('group')}if(d.reply)say('app',d.reply);if(d.job_id){a.disabled=true;watchGroupJob(d.job_id,d.caption)}}catch(e){say('app',e.message,1)}finally{nextActionPending.delete(a.id);await refreshNextActions();drawNextActions()}}
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
function dashboardConversation(items){
 const lastUser=items.map(x=>x.who).lastIndexOf('you'),after=items.slice(lastUser+1),reply=after.filter(x=>x.who==='app').at(-1),event=after.filter(x=>x.who==='auto').at(-1);
 return [lastUser>=0?items[lastUser]:null,reply,event].filter(Boolean)
}
/* Existing turns retain their nodes; only fresh user messages slide in. */
let shownTurns=null,conversationLayoutReady=false,conversationFrame=0;const turnKey=h=>h.id||h.t+':'+h.text;
/* Reading layout only: the reply text is never changed. Each line gets a role (heading, numbered step,
   bullet, opening line, closing question) so the eye can scan titles first and details second. */
function lineRole(raw,index,lines){const t=raw.trim();if(!t)return 'blank';
 /* A heading is a short bold label ("Where it stands"). Bold caption lines with amounts, numbers, italics or a full stop stay normal text. */
 if(/^#{1,6}\s/.test(t)||/^\*{1,2}[^*_]+\*{1,2}:?$/.test(t)&&t.length<90&&!/\d/.test(t)&&!/[.!?](\*{1,2})$/.test(t))return 'head';
 if(/^\d+[.)]\s/.test(t))return 'num';
 if(/^[•▪◦·*-]\s/.test(t))return 'bullet';
 const firstText=lines.findIndex(x=>x.trim()),lastText=lines.length-1-[...lines].reverse().findIndex(x=>x.trim());
 if(index===lastText&&/\?\s*$/.test(t)&&index!==firstText)return 'ask';
 if(index===firstText&&lines.filter(x=>x.trim()).length>3)return 'lead';
 return 'text'}
function replyHtml(text){
 // Correct malformed AI numbering for display only; Copy still uses original text.
 // No changes to actual message content or chat storage.
 const normalized=String(text).replace(/\r\n/g,'\n')
  .replace(/(^|\n)\s*\*\*([1-9])([A-Z])/g,'$1$2. **$3')
  .replace(/(^|\n)\s*([1-9])\*{3,4}(?=[A-Z])/g,'$1$2. **')
  .replace(/(^|\n)([1-9]\. \*\*[^\n*]+\*\*)(?=[A-Za-z])/g,'$1$2 ');
 const raw=normalized.split('\n'),html=chatFormat(normalized).split('\n');
 return html.map((line,i)=>{const role=lineRole(raw[i]||'',i,raw);let body=line||'<br>';
  if(role==='num'){body=body.replace(/^<span class="wa-list">(\d+)[.)] /,'<span class="wa-list"><b class="rn">$1</b>');
   /* Bold opening = the step's title; the rest is its detail on the next line. */
   const m=body.match(/^(<span class="wa-list"><b class="rn">\d+<\/b>)(<strong>.*?<\/strong>)\s*([\s\S]*)<\/span>$/)||body.match(/^(<span class="wa-list"><b class="rn">\d+<\/b>)()([\s\S]*)<\/span>$/);
   if(m)body=m[1]+(m[2]?'<span class="rt">'+m[2]+'</span>':'')+(m[3]?'<span class="rd">'+m[3]+'</span>':'')+'</span>'}
  if(role==='bullet')body=body.replace(/^<span class="wa-list">•\s+/,'<span class="wa-list">').replace(/^[•▪◦·]\s+/,'');
  body=body.replace(/\bRs\.?\s?\d[\d,]*(?:\.\d+)?/g,'<span class="amt">$&</span>');
  return '<div class="reply-line r-'+role+(line?'':' blank')+'" style="--i:'+Math.min(i,16)+'">'+body+'</div>'}).join('')}
function drawLog(){const allItems=history.slice(-40);
 const fresh=new Set(shownTurns?allItems.map(turnKey).filter(k=>!shownTurns.has(k)):[]);shownTurns=new Set(allItems.map(turnKey));
 for(const id of ['log','histLog']){const items=id==='log'&&!isPhone()?dashboardConversation(allItems):allItems;const el=$(id),state=scrollState[id],prev=state.top,existing=new Map([...el.children].map(n=>[n._turnKey,n])),wanted=[];
  items.forEach(h=>{const key=turnKey(h),signature=JSON.stringify([h.who,h.text,!!h.err]);let d=existing.get(key);
   if(!d){d=document.createElement('div');d._turnKey=key}
   if(d._messageSignature!==signature){d._messageSignature=signature;d._chatText=h.text;d.className='e '+(h.who==='auto'?'sys':h.who==='app'?'bot':h.who)+(h.err?' err':'')+(fresh.has(key)?' enter':'');d.dataset.t=h.t;
    if(h.who==='app'&&typeof chatFormat==='function')d.innerHTML=replyHtml(h.text);else if(h.who==='you'){d.textContent='';const bubble=document.createElement('span');bubble.className='message-text';bubble.textContent=h.text;d.append(bubble)}else d.textContent=h.text;
    const copy=document.createElement('button');copy.type='button';copy.className='message-copy';copy.textContent='Copy';copy.setAttribute('aria-label',h.who==='you'?'Copy your message':h.who==='app'?'Copy assistant message':'Copy activity message');
    copy.onclick=async()=>{try{await navigator.clipboard.writeText(d._chatText);copy.textContent='Copied';$($('hist').open?'histAnnouncement':'chatAnnouncement').textContent='Message copied.'}catch(e){copy.textContent='Retry';$($('hist').open?'histAnnouncement':'chatAnnouncement').textContent='Could not copy. Try again.'}};d.append(copy)}
   wanted.push(d)});
  if(thinking){let d=existing.get('thinking');if(!d){d=document.createElement('div');d._turnKey='thinking';d.className='e bot dots';d.textContent='Thinking…'}wanted.push(d)}
  const keep=new Set(wanted);for(const child of [...el.children])if(!keep.has(child))child.remove();wanted.forEach((child,i)=>{if(el.children[i]!==child)el.insertBefore(child,el.children[i]||null)});
  if(conversationLayoutReady)fitConversation();
  if(el.clientHeight){if(state.follow)followChat(el,items.at(-1)?.who==='app'&&!thinking);else el.scrollTop=prev}
 }
 scheduleConversationFit()
}
for(const id of Object.keys(scrollState))$(id).addEventListener('scroll',()=>{const el=$(id);if(!el.clientHeight)return;scrollState[id]={top:el.scrollTop,follow:el.scrollHeight-el.clientHeight-el.scrollTop<64};if(scrollState[id].follow){unreadReplies[id]=false;paintUnread()}rememberScroll()},{passive:true});
function followReplies(){for(const id of Object.keys(scrollState)){scrollState[id].follow=true;unreadReplies[id]=false}paintUnread()}
function think(on){pendingChats=Math.max(0,pendingChats+(on?1:-1));thinking=pendingChats>0;drawLog()}let logChain=Promise.resolve();
function say(who,text,err,turnId){if(typeof text!=='string'||!text.trim())return;const item={id:turnId||(crypto.randomUUID?crypto.randomUUID():String(Date.now())+Math.random()),who,text,err:!!err,t:Date.now()};history.push(item);history=history.slice(-80);if(who==='you')followReplies();if(who==='app'){for(const id of Object.keys(scrollState))if(!scrollState[id].follow)unreadReplies[id]=true;paintUnread();$($('hist').open?'histAnnouncement':'chatAnnouncement').textContent=text}if(who!=='auto')logChain=logChain.then(()=>post('/chat-log',{who,text,err:!!err,turn_id:item.id})).catch(()=>{});try{localStorage.setItem('givelife-chat',JSON.stringify(history))}catch(e){}drawLog();if(err)setLiveNotice(text,true)}
const GREETING='Hi! Tell me what changed, like "34k left" or "send all" — I remember your preferences.';
async function syncChat(){try{await logChain;const d=await (await fetch('/chat')).json();
 if(d.items&&d.items.length){history=d.items.slice(-80).map(x=>({id:x.turn_id||x.id,who:x.who,text:x.text,err:!!x.err,t:x.t}));try{localStorage.setItem('givelife-chat',JSON.stringify(history))}catch(e){}}
 else if(!history.length)say('app',GREETING);
 else for(const h of history.slice(-40))if(h.who!=='auto')logChain=logChain.then(()=>post('/chat-log',{who:h.who,text:h.text,err:h.err}));
 drawLog(false)}catch(e){if(!history.length)say('app',GREETING)}}
drawLog();syncChat();matchMedia('(max-width:899px)').addEventListener('change',()=>drawLog());
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!thinking)syncChat()});
function isPhone(){return matchMedia('(max-width:899px)').matches}
function openChat(){if($('hist').open)return;if(editing)setEditing(false);rememberScroll();$('hist')._returnFocus=document.activeElement;$('hist').showModal();refreshNextActions();Nav.go('chat');
 // A navigation control receives focus. Opening chat never opens a soft keyboard.
 (isPhone()?$('histMain'):$('histClose')).focus({preventScroll:true});syncChat();requestAnimationFrame(drawLog)}
function closeChat(){if(!$('hist').open)return;saveChatDraft($('histCmd').value);document.activeElement?.blur();rememberScroll();const back=$('hist')._returnFocus;$('hist').close();if(isPhone())$('chatOpen').focus({preventScroll:true});else (back?.isConnected?back:$('chatExpand')).focus({preventScroll:true});Nav.leave('chat')}
$('chatOpen').onclick=openChat;$('chatExpand').onclick=openChat;
$('chatLatest').onclick=()=>showLatest('log');$('histLatest').onclick=()=>showLatest('histLog');
$('histClose').onclick=closeChat;$('histMain').onclick=closeChat;
$('hist').addEventListener('cancel',e=>{e.preventDefault();closeChat()});
/* ---- message preview ---- */
let previewView=null,previewScroll={};try{previewScroll=JSON.parse(sessionStorage.getItem('givelife-preview-scroll')||'{}')||{}}catch(e){}
$('chat').addEventListener('scroll',()=>{if(!previewView)return;previewScroll[previewView]=$('chat').scrollTop;try{sessionStorage.setItem('givelife-preview-scroll',JSON.stringify(previewScroll))}catch(e){}},{passive:true});
function paint(k){$(k+'Preview').innerHTML=waFormat($(k).value).split('\n').map(l=>'<div class="wa-line'+(l?'':' blank')+'">'+(l||'<br>')+'</div>').join('')}
function render(){paint('group');paint('dm');requestAnimationFrame(()=>{fit();if(!editing)$('chat').scrollTop=previewScroll[view()]||0})}
function fit(){if(editing)return;const chat=$('chat'),m=$(view()+'Preview');if(!chat.clientHeight)return;
 const style=getComputedStyle(chat),available=chat.clientHeight-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom);
 chat.style.overflowY='hidden';
 for(let size=isPhone()?14:17;size>=11;size-=.5){m.style.fontSize=size+'px';if(m.scrollHeight<=available)break}
 // Unusually long content stays accessible; ordinary saved captions fit in place.
 if(m.scrollHeight>available)chat.style.overflowY='auto'
}
/* [font px, columns, tightness]. Short answers get a big font. Long ones use the width of a wide screen
   (two columns) before the text is ever made small, and scrolling is the very last resort. */
/* Readable first: the font never goes below 14px. If a long answer still does not fit, it scrolls
   (starting at its first line) instead of shrinking into tiny text. */
const FIT_STEPS=[[16,1,0],[15,1,0],[14.5,1,0]];
/* Wide screens: one column for short answers, then two, then three, choosing the fewest columns that keep the text big. */
const FIT_STEPS_WIDE=[[18,1,0],[17,1,0],[16,1,0],[17,2,0],[16,2,0],[15,2,0],[16,3,0],[15,3,0],[14.5,2,1],[14.5,3,1],[14,2,1],[14,3,1]];
function fitConversation(){
 for(const id of ['log','histLog']){const log=$(id);if(!log.clientHeight)continue;const reply=[...log.querySelectorAll('.e.bot:not(.dots)')].at(-1);if(!reply)continue;
  /* Choose the mode from the normal layout every time. Measuring the already-expanded layout
     used to hide the question, make the answer fit, and switch it back on the next resize. */
  const talk=id==='log'&&matchMedia('(min-width:900px)').matches?log.closest('.talk'):null;
  if(talk)talk.classList.remove('long-reply');
  let fitted=fitReply(log,reply,id);
  if(talk&&(reply.classList.contains('cols2')||!fitted)){talk.classList.add('long-reply');fitReply(log,reply,id)}
 }
}
function fitReply(log,reply,id){
  const style=getComputedStyle(log),padding=parseFloat(style.paddingTop)+parseFloat(style.paddingBottom);
  let reserve=44;
  if(id==='log')reserve=[...log.children].filter(n=>n!==reply).reduce((n,node)=>n+node.offsetHeight+8,8);
  const available=Math.max(80,log.clientHeight-padding-reserve);
  /* A long reply gets smaller and tighter, step by step, until all of it fits on this screen without scrolling. */
  let fitted=false;const cs=getComputedStyle(log),room=log.clientWidth-parseFloat(cs.paddingLeft)-parseFloat(cs.paddingRight),wide=log.clientWidth>=760,biggest=log.clientWidth<500?15:18;
  for(const [size,cols,tight] of (wide?FIT_STEPS_WIDE:FIT_STEPS)){if(size>biggest||cols>2&&room<760)continue;reply.style.fontSize=size+'px';reply.classList.toggle('cols3',cols>2);reply.classList.toggle('cols2',cols>1);reply.classList.toggle('tight',tight>=1);reply.classList.toggle('tighter',tight>=2);if(reply.scrollHeight<=available){fitted=true;break}}
  /* If even the smallest step does not fit, keep the boxes (they scroll a little) rather than one long column. */
  if(!fitted){if(wide){const three=room>=760;reply.style.fontSize='14px';reply.classList.toggle('cols3',three);reply.classList.add('cols2');reply.classList.add('tight');reply.classList.remove('tighter')}else{reply.style.fontSize=(log.clientWidth<500?15:16)+'px';reply.classList.remove('cols2','cols3','tight','tighter')}}
  return fitted
}
function scheduleConversationFit(){if(conversationFrame)return;conversationFrame=requestAnimationFrame(()=>{conversationFrame=0;fitConversation();for(const id of Object.keys(scrollState))if(scrollState[id].follow)followChat($(id),true)})}
conversationLayoutReady=true;
new ResizeObserver(()=>requestAnimationFrame(fit)).observe($('chat'));
for(const id of ['log','histLog'])new ResizeObserver(scheduleConversationFit).observe($(id));
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
function setEditing(on,x,y){if(on&&!draftsReady){status('Loading the saved captions…');return}const k=view(),m=$(k+'Preview');if(on===editing)return;if(on&&document.body.classList.contains('nomsg'))setNoMsg(false);editing=on;
 document.body.classList.toggle('editing',on);$('edit').textContent=on?'Done':'Edit';$('edit').classList.toggle('on',on);
 if(on){m.contentEditable='true';m.style.fontSize=isPhone()?'16px':'17px';$('chat').style.overflowY='auto';const r=x!=null&&document.caretRangeFromPoint?document.caretRangeFromPoint(x,y):null;m.focus();if(r){const s=getSelection();s.removeAllRanges();s.addRange(r)}status('Editing · Enter = done · Shift+Enter = new line')}
 else{m.contentEditable='false';$(k).value=readPreview(k);render();status('Ready');save().catch(()=>status('Save failed',1))}}
$('edit').onclick=()=>setEditing(!editing);

for(const k of ['group','dm'])$(k+'Preview').addEventListener('paste',e=>{e.preventDefault();document.execCommand('insertText',false,(e.clipboardData.getData('text/plain')||'').replace(/\r/g,''))});

/* ---- views, amount, DM greeting ---- */
function setView(v){if(editing)setEditing(false);if(previewView)previewScroll[previewView]=$('chat').scrollTop;document.body.dataset.view=v;previewView=v;document.querySelectorAll('[data-view-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.viewButton===v)));
 $('ctx').textContent=v==='group'?'Group · poster':'DM · poster';renderSendMode();localStorage.setItem('givelife-view',v);requestAnimationFrame(()=>{fit();$('chat').scrollTop=previewScroll[v]||0});flip()}
/* Large screen changes cross-fade where the browser supports view transitions. */
// Update immediately; animation never holds a click or waits for a network request.
const surfaceAnimations=new WeakMap();
function moveSurface(surface){if(!surface||!surface.getClientRects().length||!surface.animate||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 surfaceAnimations.get(surface)?.cancel();const animation=surface.animate([{opacity:.78},{opacity:1}],{duration:150,easing:'cubic-bezier(.2,.8,.2,1)'});surfaceAnimations.set(surface,animation)}
function smooth(change){const result=change();moveSurface($('main-workspace'));return result}
document.querySelectorAll('[data-view-button]').forEach(b=>b.onclick=()=>{if(b.dataset.viewButton!==view())smooth(()=>setView(b.dataset.viewButton))});
let shownLeft=null,leftTween=0;
function paintLeft(value){const c=$('leftChip');c.textContent=value==null?'Rs. …':'Rs. '+fmt(Math.round(value));const w=document.createElement('span');w.className='lw';w.textContent=' left';c.append(w)}
function showLeft(){cancelAnimationFrame(leftTween);const from=shownLeft,to=left;shownLeft=to;
 if(from==null||to==null||from===to||matchMedia('(prefers-reduced-motion: reduce)').matches||document.hidden){paintLeft(to);return}
 const start=performance.now(),span=Math.min(900,300+Math.abs(to-from)/60);
 const tick=now=>{const t=Math.min(1,(now-start)/span),eased=1-Math.pow(1-t,3);paintLeft(from+(to-from)*eased);if(t<1)leftTween=requestAnimationFrame(tick);else{paintLeft(to);$('leftChip').classList.remove('bump')}};
 $('leftChip').classList.add('bump');leftTween=requestAnimationFrame(tick)}
function applyDrafts(d){if(typeof d.group==='string'&&typeof d.dm==='string')draftsReady=true;if(d.dm_identity){$('dmName').value=d.dm_identity.name||'';$('dmPhone').value=d.dm_identity.phone||'';gender=d.dm_identity.gender==='Sister'?'Sister':'Brother';document.querySelectorAll('#gender button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.g===gender)))}if(d.group!=null||d.dm!=null)draftSaved=JSON.stringify({group:d.group??$('group').value,dm:d.dm??$('dm').value});if(d.group!=null)$('group').value=d.group;if(d.dm!=null)$('dm').value=d.dm;if(d.left!=null){left=d.left;showLeft()}applyGreeting(false);render()}
$('leftChip').onclick=()=>{openChat();$('histCmd').placeholder='Amount left, e.g. 25000 or 25k';$('histCmd').focus({preventScroll:true})};
let gender='Brother';
function logicalName(value){if(/acc+ount|\d|@|https?:\/\/|[_/\\]|\b(jr|junior|sr|senior|accounts?|accts?|admin|team|group|member|donors?|business|company|shop|store|services?|official|office|unknown|unnamed|name|contact|number|test|user|brother|bhai|sister|friend|wife|wifey|boss|customer|client|support|sales|marketing|web|developer|designer|agency|digital|seo|upwork|fiverr|foundation|givelife)\b/i.test(value))return '';const words=value.replace(/[^A-Za-z\s'-]/g,'').trim().split(/\s+/),n=words[0];return words.length<=4&&words.every(w=>w.length>=2)&&/^[A-Za-z][A-Za-z'-]{1,19}$/.test(n)&&/[aeiouy]/i.test(n)?n[0].toUpperCase()+n.slice(1).toLowerCase():''}
function greet(){const n=logicalName($('dmName').value.trim());return n?n+' '+(gender==='Sister'?'Sister':'Bhai'):'Bhai'}
const GREET=/^(\*?_?)(?:(?:[A-Za-z][A-Za-z .'-]{0,45})\s+)?(?:Brother|Bhai|Sister)\b([_*]?)[,.:!]?[ \t\r\n]*/i;
function applyGreeting(doSave=true){const t=$('dm').value;if(!t)return;const g=greet(),nt=GREET.test(t)?t.replace(GREET,(_,open,close)=>open+g+close+', '):g+', '+t;
 if(nt!==t){$('dm').value=nt;paint('dm');requestAnimationFrame(fit);if(doSave)saveSoon()}}
function setGender(g){gender=g;document.querySelectorAll('#gender button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.g===g)));applyGreeting()}
document.querySelectorAll('#gender button').forEach(b=>b.onclick=()=>setGender(b.dataset.g));
$('dmPoster').addEventListener('change',()=>{$('sendDm').textContent=$('dmPoster').checked?'Send DM with poster':'Send text-only DM';renderSendMode()});
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
async function sendGroup(key){if(!lockSend(key,true))return;let tracked=false;if(editing)setEditing(false);setLiveNotice('Sending to '+(GN[key]||key)+'…');busy(true);
 try{await ensureCaption('group');clearTimeout(timer);await save();const caption=$('group').value;$('groupStatus').textContent='Sending now…';
  const r=await post('/send-group',{group:key,message:caption,request_id:requestId()}),start=await r.json();if(!r.ok)throw Error(start.error||'Could not start');
  if(!start.job_id)throw Error('No send receipt was returned. Check WhatsApp before trying again.');const keys=jobLocks.get(start.job_id)||new Set();keys.add(key);jobLocks.set(start.job_id,keys);tracked=true;watchGroupJob(start.job_id,caption);
 }catch(e){$('groupStatus').textContent='✗ '+e.message;say('app',e.message,1)}finally{if(!tracked)lockSend(key,false);busy(false)}}
document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>sendGroup(b.dataset.group));
function armAll(){return sendGroup('all')}
$('sendAll').onclick=armAll;
async function fillEmptyCaption(kind){await ensureDrafts();if($(kind)&&!$(kind).value.trim()){const r=await post(kind==='group'?'/next-message':'/next-dm'),d=await r.json();if(r.ok&&typeof d.message==='string'&&d.message.trim()){$(kind).value=d.message;if(kind==='dm')applyGreeting(false);render();await save()}}}
async function sendTest(kind){const key='test:'+kind;if(!lockSend(key,true))return;setLiveNotice('Sending to test group…');busy(true);try{await fillEmptyCaption(kind);await ensureCaption(kind);clearTimeout(timer);await save();const r=await post('/test',{message:$(kind).value}),d=await r.json();const result=d.code==='SUCCESS'?'✓ Sent to the test group.':'Test failed: '+(d.message||d.error||'');say('app',result,d.code!=='SUCCESS');setLiveNotice(result,d.code!=='SUCCESS')}
 catch(e){say('app',e.message||'Could not send',1)}finally{lockSend(key,false);busy(false)}}
document.querySelectorAll('[data-test]').forEach(b=>b.onclick=()=>{if(editing)setEditing(false);sendTest(b.dataset.test)});
function cleanPhone(p){p=p.replace(/[\s()+-]/g,'');if(p.startsWith('00'))p=p.slice(2);if(/^03\d{9}$/.test(p))p='92'+p.slice(1);return /^[1-9]\d{7,14}$/.test(p)?p:''}
$('sendDm').onclick=async()=>{if(editing)setEditing(false);const phone=cleanPhone($('dmPhone').value);
 if(!phone){say('app','Enter a phone number first, e.g. 0300 1234567.',1);$('dmPhone').focus();return}
 if(!lockSend('dm',true))return;busy(true);try{await ensureCaption('dm');applyGreeting(false);clearTimeout(timer);await save();
  const r=await post('/send-custom',{target:'phone',phone,message:$('dm').value,poster:$('dmPoster').checked,kind:'dm_appeal',name:$('dmName').value,gender}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not send');
  if(d.code==='SUCCESS'){const result='✓ DM sent to '+greet()+'.';say('app',result+' New wording is ready for the next person.');setLiveNotice(result);$('dmPhone').value='';$('dmName').value='';setGender('Brother');await freshWording()}
  else say('app','Not confirmed: '+(d.message||'')+' Check WhatsApp before retrying.',1)}
 catch(e){say('app',e.message,1)}finally{lockSend('dm',false);busy(false)}};

/* Confirmed group-send times. Missing records never imply a successful send. */
let groupSentTimes=null;
function sentAge(stamp){const seconds=Math.max(0,Math.floor(Date.now()/1000-stamp));return seconds<60?'just now':seconds<3600?Math.floor(seconds/60)+' min ago':seconds<86400?Math.floor(seconds/3600)+' h ago':Math.floor(seconds/86400)+' d ago'}
function paintGroupTimes(data){if(data&&typeof data==='object'&&!Array.isArray(data))groupSentTimes=data;
 for(const el of document.querySelectorAll('[data-last-group]')){const key=el.dataset.lastGroup,keys=key==='all'?['main','community','fiverr','upwork','uet','toprated']:key==='free'?['community','fiverr','upwork','uet','toprated']:[key];
  const valid=keys.map(k=>groupSentTimes?.[k]).filter(t=>typeof t==='number'&&Number.isFinite(t)&&t>0&&t<=Date.now()/1000+60);
  el.textContent=!groupSentTimes?'Checking…':!valid.length?'Not sent yet':(keys.length>1?'Latest: ':'Sent ')+sentAge(Math.max(...valid));
  el.title=keys.length>1?keys.map(k=>(GN[k]||k)+': '+(typeof groupSentTimes?.[k]==='number'&&groupSentTimes[k]>0&&groupSentTimes[k]<=Date.now()/1000+60?new Date(groupSentTimes[k]*1000).toLocaleString():'Not sent yet')).join('\n'):valid.length?'Confirmed '+new Date(valid[0]*1000).toLocaleString():'No confirmed send recorded';
 }
}
setInterval(paintGroupTimes,30000);

/* ---- send a plain message to a contact, group or number: works without the AI ---- */

/* ---- pictures in the chat ---- */
let attached=null;
function clearAttachment(){attached=null;$('att').hidden=true;$('attImg').hidden=false}
$('attX').onclick=clearAttachment;
document.querySelectorAll('[data-clip]').forEach(b=>b.onclick=()=>$('file').click());
$('file').onchange=async()=>{const f=$('file').files[0];$('file').value='';if(!f)return;
 if(f.type.startsWith('video/')){try{if(f.size>15000000||!/mp4|quicktime/.test(f.type))throw Error('Use an MP4 video under 15 MB.');const data=await new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=()=>no(Error('Could not read the video.'));r.readAsDataURL(f)});const r=await post('/upload-image',{data,use:'attachment'}),d=await r.json();if(!r.ok)throw Error(d.error);attached={id:d.id,data,url:'',video:true};$('attImg').hidden=true;$('att').querySelector('span').textContent='Video attached. It will be sent with the next DMs and group messages instead of the poster.';$('att').hidden=false;say('app','Video attached. Paste numbers to send it, or say "make it the poster".')}catch(e){say('app','Could not attach: '+e.message,1)}return}
 const img=await createImageBitmap(f),k=Math.min(1,1600/Math.max(img.width,img.height)),c=document.createElement('canvas');c.width=Math.round(img.width*k);c.height=Math.round(img.height*k);c.getContext('2d').drawImage(img,0,0,c.width,c.height);
 const data=c.toDataURL('image/jpeg',.85);try{const r=await post('/upload-image',{data,use:'attachment'}),d=await r.json();if(!r.ok)throw Error(d.error);
  attached={id:d.id,data,url:data};$('attImg').src=data;$('att').hidden=false;say('app','Picture attached. Paste numbers to send it, or say "make it the poster".')}catch(e){say('app','Could not attach: '+e.message,1)}};

/* ---- lists of people: "send these with 2 min gap", numbers with names, one per line or separated ---- */
let listT=null;
function showCamp(t){$('campText').textContent=t;$('camp').hidden=false}
let campTimer=null,campPolling=false,campWasRunning=false,campStopping=false,lastCampLog=localStorage.getItem('givelife-camp-last')||'';
async function pollCamp(){if(campPolling)return;campPolling=true;clearTimeout(campTimer);campTimer=null;try{const r=await fetch('/campaign');if(!r.ok)throw Error('Could not check DMs');const c=await r.json();
 if(c.running){campWasRunning=true;const w=c.wait?` · next in ${Math.floor(c.wait/60)}:${String(c.wait%60).padStart(2,'0')}`:'';showCamp(campStopping?`Stopping DM list · ${c.sent}/${c.total} sent`:`DMs ${c.sent}/${c.total} sent${c.skipped?`, ${c.skipped} skipped`:''}${w}${c.current&&c.current!=='Waiting'?' · '+c.current:''}`);setLiveNotice($('campText').textContent);campTimer=setTimeout(pollCamp,3000)}
 else if(!listT){$('camp').hidden=true;if(campWasRunning){campWasRunning=false;campStopping=false;setLiveNotice(`DM list inactive · ${c.sent||0}/${c.total||0} sent`,!!c.failed)}const last=(c.log||[]).slice(-1)[0];if(c.total&&last&&last!==lastCampLog){lastCampLog=last;try{localStorage.setItem('givelife-camp-last',last)}catch(e){}say('app',`DM list done: ${c.sent} sent, ${c.skipped} skipped, ${c.failed} failed.`)}}}catch(e){if(!$('camp').hidden)setLiveNotice('Cannot refresh DM progress. Check your connection.',true)}finally{campPolling=false;if(!campTimer)campTimer=setTimeout(pollCamp,10000)}}
$('campStop').onclick=async()=>{if(listT){clearTimeout(listT);listT=null;$('camp').hidden=true;say('app','Cancelled. Nothing was sent.');return}
 const b=$('campStop');b.disabled=true;try{const r=await post('/campaign',{stop:true}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not stop DMs');campStopping=true;say('app',d.reply);setLiveNotice(d.reply);pollCamp()}catch(e){say('app',e.message,1)}finally{b.disabled=false}};

/* ---- the assistant: quick commands work instantly; anything else goes to the AI ---- */
async function quick(t){const low=t.toLowerCase().trim();
 if(/^(hi+|hello|hey|salam)\W*$/i.test(t))return 'Hi!';
 if(/^(ok|okay|thanks|thank you|theek|done thanks)\W*$/i.test(t))return /thank/i.test(t)?'You’re welcome.':'Okay.';
 // Emergency global hold must bypass AI, draft loading and draft-save failures.
 // It never matches a DM-only pause or a negative request.
 if(/^(?:hold|pause|stop)(?:\s+(?:evv?erything|evrything|everything|all|all\s+sending))?\s*[.!]*$/i.test(t)){
  const response=await post('/hold',{on:true}),data=await response.json();
  if(!response.ok)throw Error(data.error||'Could not confirm the global hold.');
  return data.reply||'Everything is on hold.';
 }
 if(editing)setEditing(false);clearTimeout(timer);await ensureDrafts();await save();
 const response=await post('/command',{text:t,request_id:requestId(),view:view()}),direct=await response.json();
 if(!response.ok)throw Error(direct.error||'Command failed. Nothing was retried.');
 if(direct.handled){applyDrafts(direct);if(direct.donors_changed||direct.volunteers_changed||direct.team_changed)document.dispatchEvent(new Event('donors-changed'));if(direct.job_id)watchGroupJob(direct.job_id,direct.caption||$('group').value);return direct.reply}
 if(/^(dm|group)$/.test(low)){setView(low);return 'Switched to '+low.toUpperCase()+'.'}
 if(/^(new|regenerate|next|naya)$/.test(low)){await freshWording();return 'New wording ready.'}
 if(low==='copy'){$('copy').click();return 'Copied.'}
 if(/^auto(pilot)?\s+(on|off)$/.test(low)){await toggleAuto(/on$/.test(low));return null}
 if(/^(rules?|my rules|show rules|list rules)$/.test(low)){const d=await(await fetch('/rules')).json();return d.items.length?d.items.map(x=>x.text).join('\n'):'No scheduling rules saved.'}
 if(/^(?:\+?92|0)?3\d{9}$/.test(t.replace(/[ ()-]/g,''))){setView('dm');$('dmPhone').value=t;$('dmName').value='';setGender('Brother');return 'Full DM prepared for that number. Nothing was sent.'}
 if(attached&&/\b(papers?|reports?|documents?)\b/i.test(t)&&/\b(this|these|save|use|add)\b/i.test(t)){const r=await post('/upload-image',{data:attached.data,use:'papers'}),d=await r.json();if(!r.ok)throw Error(d.error);clearAttachment();return 'Medical papers saved.'}
 return undefined}

async function act(text){const t=text.trim();if(!t)return;say('you',window.DonorHub?.privateChatText(t)||t);
 clearNextActions();const q=await quick(t);if(q!==undefined){if(q)say('app',q);refreshNextActions();return}
 think(true);let r,d;
 try{await logChain;r=await post('/assistant',{text:t,request_id:requestId(),image:attached?attached.id:null,history:history.slice(-13,-1),screen:{view:view(),dm:{name:$('dmName').value,phone:$('dmPhone').value,gender}}});d=await r.json().catch(()=>({}));if(r.ok&&d.task_id){let finished=false;const until=Date.now()+4*60*1000;while(!finished&&Date.now()<until){await new Promise(res=>setTimeout(res,500));const check=await fetch('/assistant-status/'+d.task_id),task=await check.json();if(!check.ok)throw Error(task.error||'Request no longer tracked. Nothing was retried.');if(task.done){if(task.error)throw Error(task.error);d=task.result;finished=true}}if(!finished)throw Error('The assistant result is not confirmed. Check recent activity; I will not repeat the send.')}}finally{think(false)}
 if(r.status===503){say('app','I did not understand that, and the AI assistant is not connected, so only direct commands work. Try: "34k left", "came 2000", "send hi to Ali", "send main", "fiverr every 30 min", "rules".',1);return}
 if(!r.ok)throw Error(d.error||'The assistant could not answer.');
 if(!d.superseded){applyDrafts(d);if(d.autopilot!=null)paintAuto(d.autopilot);if(d.donors_changed||d.volunteers_changed||d.team_changed)document.dispatchEvent(new Event('donors-changed'))}say('app',d.reply,false,d.turn_id);if(d.job_id)watchGroupJob(d.job_id,d.caption||$('group').value);for(const j of d.jobs||[])watchGroupJob(j.job_id,j.caption||$('group').value);
 refreshNextActions();for(const a of d.actions||[]){
  if(a.type==='prepare_dm'){setView('dm');$('dmPhone').value=a.phone||'';$('dmName').value=a.name||'';setGender(a.gender==='Sister'?'Sister':'Brother')}
  }}
/* A draft is independent of the message caption, and shared between both chat views. */
function saveChatDraft(value){for(const id of ['cmd','histCmd'])if($(id).value!==value)$(id).value=value;try{localStorage.setItem('givelife-chat-draft',value)}catch(e){}resizeComposer()}
function resizeComposer(){for(const id of ['cmd','histCmd']){const input=$(id);input.style.height='40px';input.style.height=Math.min(120,Math.max(40,input.scrollHeight))+'px'}}
try{saveChatDraft(localStorage.getItem('givelife-chat-draft')||'')}catch(e){}
for(const id of ['cmd','histCmd'])$(id).addEventListener('input',()=>saveChatDraft($(id).value));
function hideKeys(){if(isPhone()){document.activeElement?.blur();$('cmd').blur();$('histCmd').blur()}}
async function submitChat(e,id){e.preventDefault();const value=$(id).value;if(!value.trim())return;
 saveChatDraft('');hideKeys();followReplies();requestAnimationFrame(updateChatViewport);
 try{await act(value)}catch(err){if(!$('cmd').value.trim()&&!$('histCmd').value.trim())saveChatDraft(value);say('app',err.message,1)}
 finally{followReplies();requestAnimationFrame(()=>{fitConversation();for(const pane of ['log','histLog'])followChat($(pane),true);rememberScroll()})}
}
$('cmdForm').onsubmit=e=>submitChat(e,'cmd');$('histForm').onsubmit=e=>submitChat(e,'histCmd');
for(const id of ['cmd','histCmd'])$(id).addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();$(id).form.requestSubmit()}});
let viewportFrame=0;
function updateChatViewport(){cancelAnimationFrame(viewportFrame);viewportFrame=requestAnimationFrame(()=>{const v=window.visualViewport;document.documentElement.style.setProperty('--chat-height',Math.round(v?v.height:innerHeight)+'px');document.documentElement.style.setProperty('--chat-top',Math.round(v?v.offsetTop:0)+'px');if($('hist').open){const el=$('histLog');if(scrollState.histLog.follow)followChat(el,history.at(-1)?.who==='app');else el.scrollTop=scrollState.histLog.top}})}
if(window.visualViewport){visualViewport.addEventListener('resize',updateChatViewport);visualViewport.addEventListener('scroll',updateChatViewport)}addEventListener('resize',updateChatViewport);updateChatViewport();
let correctionTurn=null;
$('feedbackClose').onclick=()=>$('feedbackDialog').close();
$('feedbackForm').onsubmit=async e=>{e.preventDefault();await logChain;const r=await post('/feedback',{turn_id:correctionTurn,correction:$('feedbackText').value,remember:$('feedbackRemember').checked}),d=await r.json();if(!r.ok){$('feedbackStatus').textContent=d.error;return}$('feedbackDialog').close();status(d.warning||('Correction saved'+($('feedbackRemember').checked?' to memory.':'.')),!!d.warning)};
async function showMemory(){Nav.go('settings/memory');if(!$('memoryDialog').open)$('memoryDialog').showModal();const r=await fetch('/knowledge'),d=await r.json();if(Nav.path()!=='settings/memory')return;const box=$('memoryContent');box.textContent='';const stats=document.createElement('p');stats.textContent=d.feedback_count+' confirmed corrections · '+d.archived_turns+' archived turns. Patterns: '+(Object.entries(d.patterns||{}).map(([k,v])=>k+' '+v).join(', ')||'none yet');box.append(stats);for(const item of d.entries||[]){const row=document.createElement('div');row.className='memory-item';const label=document.createElement('p');label.textContent=item.text;const remove=document.createElement('button');remove.type='button';remove.textContent='Forget';remove.onclick=async()=>{await post('/knowledge',{forget:item.id});showMemory()};row.append(label,remove);box.append(row)}if(!$('memoryDialog').open)$('memoryDialog').showModal();Nav.go('settings/memory')}
if($('openMemory'))$('openMemory').onclick=()=>showMemory().catch(e=>status(e.message,1));$('memoryClose').onclick=()=>{$('memoryDialog').close();Nav.go('settings',{replace:true})};$('memoryDialog').addEventListener('cancel',e=>{e.preventDefault();$('memoryClose').click()});
if($('runChatEval'))$('runChatEval').onclick=async()=>{const b=$('runChatEval'),label=$('chatEvalStatus');b.disabled=true;try{const r=await post('/assistant-evaluate',{}),start=await r.json();if(!r.ok)throw Error(start.error);for(let i=0;i<600;i++){const response=await fetch('/assistant-evaluate/'+start.eval_id),task=await response.json();if(!response.ok)throw Error(task.error||'Could not read evaluation.');label.textContent=(task.results||[]).map(x=>x.case+': '+(x.passed?'passed':'FAILED — '+(x.error||((x.calls||[]).join(', ')+' | '+(x.reply||''))))).join('\n')+'\n'+(task.results||[]).length+'/'+task.total+' complete';if(task.done)break;await new Promise(resolve=>setTimeout(resolve,1000))}}catch(e){label.textContent=e.message}finally{b.disabled=false}};


/* ---- autopilot ---- */
let aiAvailable=false;
function paintAuto(on){autoKnown=true;autoOn=!!on;$('auto').setAttribute('aria-checked',String(autoOn));$('auto').querySelector('.lbl').textContent=autoOn?'ON':'OFF';$('auto').disabled=false;$('live').dataset.on=autoOn?'1':'0';paintStatusLine()}
async function toggleAuto(on){const r=await post('/autopilot',{on}),d=await r.json();paintAuto(d.on);say(d.on||!on?'auto':'app',d.reply,!d.on&&on);if(d.on)pollAuto()}
$('auto').onclick=()=>toggleAuto(!autoOn).catch(e=>say('app',e.message,1));
let liveSnapshot=null,checkedAt=0,pollError='',liveNotice=null,lastAnnouncedError='';
function setLiveNotice(text,error=false){liveNotice={text:String(text||''),error,at:Date.now()};paintStatusLine()}
function sinceLabel(timestamp){if(typeof timestamp!=='number'||!Number.isFinite(timestamp)||timestamp<=0)return 'Not checked yet';const s=Math.max(0,Math.floor(Date.now()/1000-timestamp));return s<60?s+'s ago':s<3600?Math.floor(s/60)+'m ago':Math.floor(s/3600)+'h ago'}
function waitLabel(timestamp){const s=Math.max(0,Math.ceil(timestamp-Date.now()/1000));return s<60?s+'s':Math.ceil(s/60)+' min'}
function statusView(st,on){
 if(!st)return {text:on?'Waiting for bot status…':'Auto off',state:on?'loading':'off'};
 let state=st.state||(/^(Sending|Posting|Waiting 60)/i.test(st.now||'')?'sending':/^(On hold|Paused:|Quiet)/i.test(st.now||'')?'paused':on?'idle':'off');
 if(state==='sending'&&st.job?.next_send_at)return {text:'Next: '+(GN[st.job.next_target]||st.job.next_target||'recipient')+' in '+waitLabel(st.job.next_send_at),state};
 if(state==='idle'||state==='off'){
  const candidates=[];if(on&&st.next?.length){const n=st.next[0];if(n.due_at)candidates.push({at:n.due_at,label:GN[n.group]||n.group,type:'Auto'})}
  if(st.scheduled)candidates.push({at:st.scheduled.due_at,label:GN[st.scheduled.label]||st.scheduled.label,type:'Scheduled'});
  candidates.sort((a,b)=>a.at-b.at);const next=candidates[0];
  if(next)return {text:next.at<=Date.now()/1000?next.label+' due · waiting for send check':'Waiting · '+next.type+': '+next.label+' in '+waitLabel(next.at),state};
  return {text:on?'Waiting for next reply check':'Auto off',state};
 }
 let text=st.now||'Waiting for bot status…';if(state==='reading')text=text.replace(/^Reading replies:/,'Reading:');for(const [key,name] of Object.entries(GN)){if(st.job?.next_target===key&&/^Sending to /i.test(text))text='Sending: '+name}
 return {text,state};
}
function paintStatusLine(){const box=$('live');if(!box)return;const offline=!navigator.onLine,wa=$('whatsappConnection')?.dataset.state;
 const error=offline?'No internet':pollError||((wa==='offline'||wa==='error')?'WhatsApp disconnected. Tap WA to reconnect.':'')||(liveNotice?.error&&Date.now()-liveNotice.at<120000?liveNotice.text:'')||(['error','offline'].includes(liveSnapshot?.state)?liveSnapshot.now:'');
 const recent=liveNotice&&Date.now()-liveNotice.at<90000,actual=statusView(liveSnapshot,autoOn);
 const active=['sending','reading','paused','offline','done'].includes(actual.state);
 const text=error||(!autoKnown?'Checking Auto status…':active?actual.text:(watchingJobs.size||operationCount>0)?liveNotice?.text||'Sending…':recent?liveNotice.text:actual.text);
 const state=error?'error':!autoKnown?'loading':actual.state;
 const event=liveSnapshot?.last_event;const eventText=typeof event?.text==='string'?event.text.replace(/\s+/g,' ').trim():'';
 const detail=(eventText?'Last update: '+eventText.slice(0,130)+(eventText.length>130?'…':'')+(event.time?' · '+sinceLabel(event.time):'')+' · ':'')+(!autoKnown?'Waiting for the server':Number.isFinite(liveSnapshot?.last_reply_read)&&liveSnapshot.last_reply_read>0?'Replies read '+sinceLabel(liveSnapshot.last_reply_read):'No reply check recorded')+(checkedAt?' · Synced '+sinceLabel(checkedAt/1000):'');
 if(error!==lastAnnouncedError){lastAnnouncedError=error;$('liveAnnouncement').textContent=error}
 box.dataset.error=error?'1':'0';box.dataset.state=state;$('liveNow').textContent='Auto '+(!autoKnown?'…':autoOn?'ON':'OFF');$('liveMeta').textContent=text;$('liveDetail').textContent=detail;
 $('liveBar').title=$('liveNow').textContent+' · '+text+' · '+detail;$('liveBar').setAttribute('aria-label',$('liveBar').title+' · View details');
}
function refreshLiveDrafts(data,baseline){
 if(data.left!=null&&left===baseline.left){left=data.left;showLeft()}
 const payload=JSON.stringify({group:$('group').value,dm:$('dm').value});
 if(!draftsReady||editing||pendingChats||operationCount||!baseline.wasSaved||payload!==baseline.payload||draftSaved!==baseline.payload)return false;
 if(typeof data.drafts?.group!=='string'||typeof data.drafts?.dm!=='string')return false;
 if(JSON.stringify(data.drafts)!==payload)applyDrafts({...data.drafts,left});return true;
}
let autoPolling=false;
async function pollAuto(){if(autoPolling)return;autoPolling=true;const payload=JSON.stringify({group:$('group').value,dm:$('dm').value}),baseline={payload,wasSaved:payload===draftSaved,left};try{const r=await fetch('/autopilot');if(!r.ok)throw Error('Status unavailable. Tap for details.');const d=await r.json();checkedAt=Date.now();paintGroupTimes(d.last_sent);pollError='';aiAvailable=!!d.ai;liveSnapshot=d.status||null;paintAuto(d.on);paintLive(d.status);refreshLiveDrafts(d,baseline);for(const x of d.log||[]){if(x.time*1000>seenAuto){seenAuto=x.time*1000;if(!x.q&&x.time*1000>Date.now()-15*60000)say('auto',x.text)}}}catch(e){pollError='Cannot reach cloud. Status may be old.';paintStatusLine()}finally{autoPolling=false}}
setInterval(paintStatusLine,1000);
const waObserver=new MutationObserver(paintStatusLine);if($('whatsappConnection'))waObserver.observe($('whatsappConnection'),{attributes:true,attributeFilter:['data-state']});

/* ---- live box: what Auto is doing right now ---- */
const GN={all:'All 6 groups',free:'Freelance groups',main:'GiveLife',community:'Upwork Community',fiverr:'Fiverr',upwork:'Upwork',uet:'Fiverr UET',toprated:'Top Rated'};
const PACE={L1:'Normal pace: donations are coming.',L2:'Donations slowed: posting faster.',L3:'Donations very slow: working at full effort.',L4:'Long quiet spell: easing off so the groups do not get tired.'};
function paintLive(st){const box=$('live');if(!st){$('liveMore').textContent=$('liveMeta').textContent;return}
 box.dataset.pace=st.pace;paintStatusLine();
 const t=st.today||{};
 const more=$('liveMore');more.textContent='';
 const add=(k,v)=>{const d=document.createElement('div'),a=document.createElement('div');a.className='k';a.textContent=k;d.textContent=v;more.append(a,d)};
 if(box.dataset.error==='1')add('Needs attention',$('liveMeta').textContent);
 add('Live activity',st.now||'Waiting for bot status');
 if(st.last_reply_read)add('Last successful reply read',new Date(st.last_reply_read*1000).toLocaleString());
 if(st.last_event?.text)add('Last recorded update',st.last_event.text);
 if(st.pace)add('Pace',PACE[st.pace]||st.pace);
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
$('gear').onclick=()=>{$('set').showModal();loadSet();checkWa();Nav.go('settings')};
function closeSettings(){$('set').close();Nav.leave('settings')}
$('setClose').onclick=closeSettings;
if($('setCloseBottom'))$('setCloseBottom').onclick=closeSettings;
$('set').addEventListener('cancel',e=>{e.preventDefault();closeSettings()});
$('set').addEventListener('close',()=>Nav.leave('settings'));
async function saveDms(){const on=$('swDm').checked;$('swNew').disabled=!on;
 try{const r=await post('/autopilot-settings',{action:'dms',enabled:on,daily:+($('set').dataset.daily||30),new_people:$('swNew').checked}),d=await r.json();if(!r.ok)throw Error(d.error);status('✓ '+d.reply)}catch(e){status(e.message||'Could not save',1);loadSet()}}
$('swDm').onchange=saveDms;$('swNew').onchange=saveDms;
$('aiTest').onclick=async()=>{const b=$('aiTest');b.disabled=true;setNote('aiRes','Asking the assistant…');
 try{const d=await (await fetch('/ai-test')).json();d.ok?setNote('aiRes',`${d.provider||'AI'} answered in ${(d.ms/1000).toFixed(1)} s.`,'ok'):setNote('aiRes',d.error||'Not working.','err')}
 catch(e){setNote('aiRes','Could not reach the server.','err')}finally{b.disabled=false}};
let outT=null;
$('waOut').onclick=async()=>{const b=$('waOut');
 if(!b.classList.contains('arm')){b.classList.add('arm');b.textContent='Tap again to confirm';clearTimeout(outT);outT=setTimeout(()=>{b.classList.remove('arm');b.textContent='Log out'},4000);return}
 clearTimeout(outT);b.classList.remove('arm');b.textContent='Log out';b.disabled=true;
 try{const r=await post('/wa-logout',{confirm:true}),d=await r.json();if(!r.ok)throw Error(d.error);setNote('waRes','Logged out. Use the WhatsApp dot at the top to link again.','ok');say('app','WhatsApp was logged out. Link it again from the WhatsApp dot at the top.')}
 catch(e){setNote('waRes',e.message,'err')}finally{b.disabled=false}};

document.addEventListener('pointerdown',e=>{const menu=document.querySelector('.overflow-tools');if(menu?.open&&!menu.contains(e.target))menu.open=false});

/* ---- no internet: the page still opens, shows the last message, and says Auto keeps running on the server ---- */
function netBanner(){const off=!navigator.onLine;$('offline').hidden=!off;document.body.classList.toggle('isoffline',off);paintStatusLine()}
addEventListener('online',()=>{netBanner();pollAuto();syncChat()});addEventListener('offline',netBanner);netBanner();
const cached=(k,v)=>{try{if(v===undefined)return JSON.parse(localStorage.getItem('givelife-c-'+k)||'null');localStorage.setItem('givelife-c-'+k,JSON.stringify(v))}catch(e){return null}};

/* ---- hide the message to work only with the buttons and chat ---- */
function setNoMsg(on){if(editing)setEditing(false);document.querySelector('.overflow-tools').open=false;if(on)Nav.leave('preview');else Nav.go('preview');document.body.classList.toggle('nomsg',on);$('showMsg').hidden=!on;$('showMsg').setAttribute('aria-expanded',String(!on));const desktop=$('desktopPreview');if(desktop){desktop.setAttribute('aria-pressed',String(!on));desktop.textContent=on?'Message preview':'Back to chat'}if(!on){requestAnimationFrame(fit);flip()}}
if($('desktopPreview'))$('desktopPreview').onclick=()=>smooth(()=>setNoMsg(!document.body.classList.contains('nomsg')));
if($('previewBackBottom'))$('previewBackBottom').onclick=()=>smooth(()=>setNoMsg(true));
$('hideMsg').onclick=e=>{e.stopPropagation();smooth(()=>setNoMsg(true))};$('previewBack').onclick=()=>smooth(()=>setNoMsg(true));$('showMsg').onclick=()=>smooth(()=>setNoMsg(false));
Nav.rendering=true;setNoMsg(true);Nav.rendering=false; /* the start state is not a navigation step */

/* ---- theme: Auto follows the phone/PC setting; Light or Dark is remembered on this device ---- */
function themeNow(){try{const t=localStorage.getItem('givelife-theme');return ['dark','light','system'].includes(t)?t:'dark'}catch(e){return 'dark'}}
function applyTheme(t){const r=document.documentElement;if(t==='light'||t==='dark')r.dataset.theme=t;else delete r.dataset.theme;
 try{localStorage.setItem('givelife-theme',t)}catch(e){}
 document.querySelectorAll('#theme button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.t===t)));
 const m=document.querySelector('meta[name=theme-color]');if(m)m.content=getComputedStyle(r).getPropertyValue('--bg').trim()}
/* The choice is stored at once; only the repaint is animated. */
document.querySelectorAll('#theme button').forEach(b=>b.onclick=()=>{try{localStorage.setItem('givelife-theme',b.dataset.t)}catch(e){}smooth(()=>applyTheme(b.dataset.t))});

matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{if(themeNow()==='system')applyTheme('system')});
applyTheme(themeNow());
document.fonts?.ready.then(()=>{fit();fitConversation()});

function flip(){const m=$(view()+'Preview');m.classList.remove('flip');void m.offsetWidth;m.classList.add('flip')}

function focusChatInput(){if($('hist').open){$('histCmd').focus({preventScroll:true});return}if(isPhone()){openChat();$('histCmd').focus({preventScroll:true});return}if(!document.body.classList.contains('nomsg'))setNoMsg(true);$('cmd').focus({preventScroll:true})}
function openKeyboardHelp(){Nav.go('keyboard');$('keyboardDialog').showModal();$('keyboardClose').focus({preventScroll:true})}
if($('keyboardHelp'))$('keyboardHelp').onclick=openKeyboardHelp;
if($('keyboardClose'))$('keyboardClose').onclick=()=>{$('keyboardDialog').close();Nav.leave('keyboard')};$('keyboardDialog').addEventListener('cancel',e=>{e.preventDefault();$('keyboardClose').click()});
/* Desktop shortcuts do not move controls or steal focus from dialogs. */
document.addEventListener('keydown',e=>{
 if(typeof e.key!=='string'||e.repeat)return;
 const dialog=document.querySelector('dialog[open]');
 if(!isPhone()&&(e.ctrlKey||e.metaKey)&&e.key==='/'&&(!dialog||dialog.id==='hist')){e.preventDefault();focusChatInput();return}
 if(dialog)return;
 if(editing){if(e.key==='Escape'||(e.key==='Enter'&&!e.shiftKey&&!e.isComposing)){e.preventDefault();setEditing(false)}return}
 const inField=['INPUT','TEXTAREA'].includes(document.activeElement.tagName);
 if(e.key==='Escape'&&inField){document.activeElement.blur();return}
 if(inField||e.ctrlKey||e.metaKey||e.altKey||isPhone())return;
 const a={'/':focusChatInput,'?':openKeyboardHelp,g:()=>setView('group'),d:()=>setView('dm'),e:()=>setEditing(true),n:()=>$('fresh').click(),c:()=>$('copy').click(),h:()=>setNoMsg(!document.body.classList.contains('nomsg'))}[e.key.toLowerCase()];
 if(a){e.preventDefault();a()}});

/* ---- show the screen the address names (refresh, Back and Forward all come here) ---- */
// Only UI-opening actions are restorable. Sending, logout, uploads and saves
// never run during routing or refresh.
const smallScreens=[
 {id:'donorAddDialog',suffix:'add',open:()=>$('donorAdd').click()},
 {id:'donorPasteDialog',suffix:'bulk',open:()=>$('donorBulk').click()},
 {id:'donorBatchPicker',suffix:'pace',open:()=>$('donorPace').click()},
 {id:'posterDialog',path:'settings/poster',open:()=>window.DonorHub?.openPoster()}
];
function smallRoute(screen){return screen.path||'donors/'+(Nav.top()==='donors'?Nav.path().split('/')[1]:'all')+'/'+screen.suffix}
function restoreSmallDialog(path,open=false){for(const screen of smallScreens){const dialog=$(screen.id);if(!dialog)continue;
 const target=screen.path?path===screen.path:path.startsWith('donors/')&&path.split('/')[2]===screen.suffix;
 if(dialog.open&&!target)dialog.close();
 if(open&&target&&!dialog.open)screen.open();
}}
addEventListener('DOMContentLoaded',()=>{
 for(const screen of smallScreens){const dialog=$(screen.id);if(!dialog)continue;
  new MutationObserver(()=>{if(dialog.open)Nav.go(smallRoute(screen))}).observe(dialog,{attributes:true,attributeFilter:['open']});
  dialog.addEventListener('close',()=>{const target=smallRoute(screen);if(Nav.path()===target){Nav.go(dialog.dataset.returnRoute||(screen.path?'settings':target.split('/').slice(0,2).join('/')),{replace:true});delete dialog.dataset.returnRoute;renderNav()}});
 }
});
let navigationEpoch=0;
async function renderNav(){
 if($('cloudLogin')?.closest('dialog')?.open)return;
 const epoch=++navigationEpoch,path=Nav.path(),parts=path.split('/'),top=parts[0],notes=top==='donors'&&parts[2]==='notes';
 if(window.FoundationNotes?.isOpen()&&!notes){
  const closed=await window.FoundationNotes.hide(()=>epoch===navigationEpoch);
  if(epoch!==navigationEpoch)return;
  if(!closed){Nav.go(window.FoundationNotes.route(),{replace:true});return}
 }
 Nav.rendering=true;
 try{
  restoreSmallDialog(path);
  if(top!=='chat'&&$('hist').open)closeChat();
  if(top!=='settings'&&$('set').open)$('set').close();
  if(path!=='settings/memory'&&$('memoryDialog').open)$('memoryDialog').close();
  if(top!=='keyboard'&&$('keyboardDialog').open)$('keyboardDialog').close();
  if(top!=='team'&&window.TeamHub?.isOpen())window.TeamHub.hide();
  if(top!=='donors'&&window.DonorHub?.isOpen())window.DonorHub.hide();
  if(top!=='whatsapp'&&$('whatsappDialog')?.open)$('whatsappDialog').close();
  if(top==='preview'&&document.body.classList.contains('nomsg'))setNoMsg(false);
  if(top===''&&!document.body.classList.contains('nomsg'))setNoMsg(true);
  if(top==='chat'&&!$('hist').open)openChat();
  if(top==='settings'&&!$('set').open){$('set').showModal();loadSet();checkWa()}
  if(path==='settings/memory'&&!$('memoryDialog').open){$('memoryDialog').showModal();showMemory().catch(e=>{$('memoryContent').textContent='Could not load memory. Close and try again.'})}
  if(path==='settings/poster')restoreSmallDialog(path,true);
  if(top==='keyboard'&&!$('keyboardDialog').open)openKeyboardHelp();
  if(top==='team'&&!window.TeamHub?.isOpen())window.TeamHub?.show();
  if(top==='donors'){
   window.DonorHub?.show(parts[1]||'all');
   if(!notes)restoreSmallDialog(path,true);
   if(notes&&!window.FoundationNotes?.isOpen())window.FoundationNotes?.show();
  }
  if(top==='whatsapp'&&!$('whatsappDialog')?.open)$('whatsappConnection').click();
 }finally{Nav.rendering=false;clearTimeout(window.studioBootTimer);delete document.documentElement.dataset.uiBoot}
}
// Both popstate and hashchange can fire for the same navigation. Coalesce them.
let navigationFrame=0;
function scheduleNavigation(){cancelAnimationFrame(navigationFrame);navigationFrame=requestAnimationFrame(()=>{renderNav()})}
addEventListener('popstate',scheduleNavigation);
addEventListener('hashchange',scheduleNavigation);
addEventListener('DOMContentLoaded',()=>{renderNav()},{once:true});
addEventListener('studio-unlocked',()=>{renderNav()});
// Dialogs and Back/Forward use the same brief, interruptible entrance.
let previousSurface=document.body.dataset.view+':'+document.body.classList.contains('nomsg');
new MutationObserver(changes=>{
 const surface=document.body.dataset.view+':'+document.body.classList.contains('nomsg');
 if(surface!==previousSurface){previousSurface=surface;moveSurface($('main-workspace'))}
 for(const change of changes)if(change.target.tagName==='DIALOG'&&change.attributeName==='open'){
  surfaceAnimations.get(change.target)?.cancel();if(change.target.open)moveSurface(change.target);else moveSurface([...document.querySelectorAll('dialog[open]')].at(-1)||$('main-workspace'));
 }
}).observe(document.body,{subtree:true,attributes:true,attributeFilter:['open','class','data-view']});
document.addEventListener('click',event=>{
 const tab=event.target.closest?.('[data-tab],[data-bank-nav]');if(tab)requestAnimationFrame(()=>moveSurface($('donorMessages')?.hidden?$('donorTable'):$('donorMessages')));
});

/* ---- start ---- */
setView(localStorage.getItem('givelife-view')==='dm'?'dm':'group');
seenAuto=Number(localStorage.getItem('givelife-seen-auto')||0);addEventListener('beforeunload',()=>localStorage.setItem('givelife-seen-auto',String(seenAuto)));
fetch('/health').then(r=>r.json()).then(d=>{if(d.ai_provider)setNote('aiRes','Currently: '+d.ai_provider+'.')}).catch(()=>{});
ensureDrafts().then(()=>status('✓ Ready')).catch(()=>{const d=cached('drafts');if(d){applyDrafts(d);status('Offline · showing the last saved message',1)}else status('Could not load',1)});
fetch('/left').then(r=>r.json()).then(d=>{left=d.left;cached('left',d.left);showLeft()}).catch(()=>{const l=cached('left');if(l!=null){left=l;showLeft()}});
fetch('/poster').then(r=>r.ok?r.blob():null).then(b=>{if(b){$('poster').src=URL.createObjectURL(b);$('poster').hidden=false;renderSendMode()}}).catch(()=>{});
pollAuto();setInterval(pollAuto,5000);pollCamp();refreshNextActions();





/* Most-used screens, one click from the groups box (near the mouse on desktop). */
document.getElementById('railPreview')?.addEventListener('click',()=>document.getElementById('desktopPreview')?.click());
document.getElementById('railDonors')?.addEventListener('click',()=>document.getElementById('openDonors')?.click());
/* Desktop: Settings sits in the centred footer beside Keyboard shortcuts instead of the far corner. */


/* ---- Cases: save a finished case, open an old one, start a new one from zero ---- */
async function loadCases(){try{const r=await fetch('/cases');if(!r.ok)return;const d=await r.json(),sel=$('caseSelect');if(!sel)return;sel.textContent='';
 for(const c of d.cases){const o=document.createElement('option');o.value=c.id;const done=c.left===0;o.textContent=c.name+(done?' · done ✓':'');o.selected=c.current;sel.append(o)}
 for(const [v,t] of [['__rename','✎ Rename this case…'],['__new','＋ New case from zero…']]){const o=document.createElement('option');o.value=v;o.textContent=t;sel.append(o)}
 const cur=d.cases.find(c=>c.current);sel.dataset.done=String(!!cur&&cur.left===0);sel.title=cur&&cur.left===0?'This case is complete. Start a new case here; this one stays saved.':'Cases'}catch(e){}}
async function caseAct(body){const r=await post('/cases',body),d=await r.json();if(!r.ok)throw Error(d.error||'Could not change the case.');return d}
$('caseSelect')?.addEventListener('change',async e=>{const sel=e.target,v=sel.value;
 try{
  if(v==='__new'){const name=prompt('Name the new case (for example the child\'s name):');if(!name){await loadCases();return}
   const left=prompt('How much is needed for "'+name.trim()+'" (Rs.)?');if(!left){await loadCases();return}
   const n=Number(String(left).replace(/[^\d.]/g,''));await caseAct({action:'new',name,left:n});location.reload();return}
  if(v==='__rename'){const cur=(await (await fetch('/cases')).json()).current,name=prompt('New name for this case:');if(name)await caseAct({action:'rename',id:cur,name});await loadCases();return}
  if(confirm('Open this case? The current one is saved first.')){await caseAct({action:'switch',id:v});location.reload()}else await loadCases()
 }catch(err){alert(err.message);await loadCases()}});
loadCases();


