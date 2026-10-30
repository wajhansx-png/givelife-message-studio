/* Team screen: updates from the teammate in the centre, tasks with status, and a box to write today's tasks. */
(()=>{
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e};
 const page=make('dialog','team-page');page.id='teamPage';page.setAttribute('aria-label','Team tasks');document.body.append(page);
 const launch=make('button','donor-launch team-launch','Team');launch.type='button';launch.id='openTeam';
 const badge=make('span','team-badge');badge.hidden=true;launch.append(badge);document.querySelector('.brandbar')?.append(launch);
 let data=null,timer=0,lastUnread=0,planText='',toastTimer=0,addOpen=false;
 const api=async(body)=>{const r=await fetch('/team',body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Something went wrong.');return d};
 function toast(text,bad){let t=document.getElementById('teamToast');if(!t){t=make('div','team-toast');t.id='teamToast';t.setAttribute('role','status')}(page.open?page:document.body).append(t);t.textContent=text;t.dataset.bad=String(!!bad);t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{t.hidden=true},6000)}
 function paintBadge(){const n=data?.unread||0;badge.hidden=!n;badge.textContent=n>9?'9+':String(n);launch.setAttribute('aria-label','Team'+(n?', '+n+' new update'+(n===1?'':'s'):''))}
 async function refresh(quiet){try{const d=await api();const first=data===null;data=d;if(!first&&d.unread>lastUnread){const e=(d.latest||[])[0];toast(e?e.text:'New update from your teammate')}lastUnread=d.unread;paintBadge();if(page.open)draw()}catch(e){console.error('team refresh',e);if(!quiet&&page.open)toast(e.message,true)}}
 let lastError='';
 async function act(body,ok){lastError='';try{data={...data,...await api(body)};if(ok)toast(ok);lastUnread=data.unread;paintBadge();draw(true)}catch(e){lastError=e.message;toast(e.message,true);if(page.open)draw(true)}}
 const chip=(s)=>{const c=make('span','team-chip',s==='Reported'?'Needs your check':s);c.dataset.s=s;return c};
 /* One screen, no scrolling. The summary and the add button always show; rows are trimmed from the least important up until everything fits. */
 const STEPS=['latest','done','left','check','plan'];
 const typing=()=>{const a=document.activeElement;return !!a&&page.contains(a)&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)};
 function draw(force){
  if(!force&&typing())return; /* never rebuild the screen while a field has focus: it would close the phone keyboard */
  const typed=page.querySelector('#teamText')?.value;if(typed!==undefined)planText=typed;
  const lim={latest:3,done:1,left:8,check:4,plan:20};
  let guard=40;
  while(guard--){build(lim);const body=page.querySelector('.team-body');if(!body||body.scrollHeight<=body.clientHeight+1)break;
   let reduced=false;for(const k of STEPS){if(k==='done'?lim.done>0:lim[k]>(k==='plan'||k==='check'?1:0)){if(k==='done')lim.done=0;else lim[k]--;reduced=true;break}}if(!reduced)break}
 }
 function more(n){return n>0?make('p','team-more','+'+n+' more'):null}
 function build(lim){
  page.textContent='';const shell=make('div','team-shell');
  const head=make('header','team-head');const title=make('div','team-title');title.append(make('h1','','Team'));title.append(make('span','team-sub',data?.member?data.member.name+(data.paused?' · paused':''):'Add your teammate to start'));head.append(title);
  if(data?.member){const p=make('button','tool team-pause',data.paused?'Resume':'Pause');p.type='button';p.onclick=()=>act({action:'pause',on:!data.paused},data.paused?'Resumed.':'Paused. Nothing will be sent.');head.append(p)}
  shell.append(head);const body=make('div','team-body');
  if(!data?.member){
   const f=make('form','team-card team-setup');f.append(make('h2','','Who is your teammate?'),make('p','team-hint','Their WhatsApp number stays hidden.'));
   const n=make('input','');n.name='team_name';n.placeholder='Name';n.autocomplete='off';n.setAttribute('aria-label','Teammate name');const ph=make('input','');ph.name='team_phone';ph.type='tel';ph.placeholder='WhatsApp number';ph.setAttribute('aria-label','Teammate WhatsApp number');
   const b=make('button','primary','Save teammate');b.type='submit';f.append(n,ph,b);f.onsubmit=e=>{e.preventDefault();act({action:'member',name:n.value,phone:ph.value},'Teammate saved.')};body.append(f)}
  else if(data.plan||addOpen||planText){
   const add=make('section','team-card team-addbox');
   if(data.plan){add.append(make('h2','','Check the plan'),make('p','team-hint','Nothing is sent until you press Start.'));
    data.plan.items.slice(0,lim.plan).forEach((i,k)=>{const r=make('div','team-task');const txt=make('div','team-text');txt.append(make('strong','',(k+1)+'. '+i.text),make('span','team-due','Ask '+i.start_label+' · due '+i.due_label));r.append(txt);add.append(r)});
    const m=more(data.plan.items.length-lim.plan);if(m)add.append(m);
    const go=make('button','primary','Start tasks');go.type='button';go.onclick=()=>{planText='';addOpen=false;act({action:'confirm'},'Tasks started.')};const ds=make('button','tool','Discard');ds.type='button';ds.onclick=()=>{addOpen=false;act({action:'discard'})};const ar=make('div','team-actions');ar.append(go,ds);add.append(ar)}
   else{add.append(make('h2','','Write today\'s tasks'));const ta=make('textarea','');ta.id='teamText';ta.name='team_tasks';ta.rows=4;ta.maxLength=3000;ta.value=planText;ta.placeholder='One task per line, then a deadline:\n1) Post in the 3 groups\n2) Update the sheet\nDeadline 6pm';ta.setAttribute('aria-label','Today\'s tasks');
    const go=make('button','primary','Plan the tasks');go.type='button';go.onclick=()=>act({action:'plan',text:ta.value});if(lastError)add.append(make('p','team-error',lastError));if(/night|quiet/i.test(lastError)){const nb=make('button','tool','Send at night too');nb.type='button';nb.onclick=()=>act({action:'night',on:true},'Night messages are on. Plan again.');add.append(nb)}const x=make('button','tool','Cancel');x.type='button';x.onclick=()=>{planText='';addOpen=false;draw(true)};const ar=make('div','team-actions');ar.append(go,x);add.append(ta,ar)}
   body.append(add)}
  else{
   const all=data.tasks,done=all.filter(t=>t.status==='Done'),review=all.filter(t=>t.status==='Reported'),left=all.filter(t=>['Waiting','Asked','Late'].includes(t.status)).sort((a,b)=>(b.status==='Late')-(a.status==='Late')||a.due_at-b.due_at);
   const sum=make('section','team-card team-sum');sum.append(make('div','team-big',all.length?done.length+' of '+all.length+' done':'No tasks yet'));
   const bar=make('div','team-bar');const fill=make('i','');fill.style.width=(all.length?Math.round(100*done.length/all.length):0)+'%';bar.append(fill);sum.append(bar);
   const late=left.filter(t=>t.status==='Late').length;const next=left.filter(t=>t.status!=='Late')[0];
   const bits=[];if(left.length)bits.push(left.length+' left');if(late)bits.push(late+' late');if(review.length)bits.push(review.length+' to check');if(next)bits.push('next due '+next.due_label);
   sum.append(make('div','team-line',bits.join(' · ')||(all.length?'All done ✓':'Add tasks below')));if(late)sum.dataset.late='true';body.append(sum);
   if(review.length){const c=make('section','team-card team-review');c.append(make('h2','','Check these'));
    for(const t of review.slice(0,lim.check)){const row=make('div','team-item');const txt=make('div','team-text');txt.append(make('strong','',t.text),make('span','team-say',(t.proof?'Proof ✓ · ':'No proof yet · ')+'"'+(t.report_text||'done')+'"'));
     const ok=make('button','primary','Verified ✓');ok.type='button';ok.onclick=()=>act({action:'verify',id:t.id},'Verified.');
     const no=make('button','tool','Not done');no.type='button';no.onclick=()=>{const note=prompt('What should '+data.member.name+' fix? (optional)','');if(note!==null)act({action:'reject',id:t.id,note},'Sent back.')};
     const acts=make('div','team-actions');acts.append(ok,no);row.append(txt,acts);c.append(row)}
    const m=more(review.length-lim.check);if(m)c.append(m);body.append(c)}
   if(left.length&&lim.left>0){const c=make('section','team-card');c.append(make('h2','','Left'));
    for(const t of left.slice(0,lim.left)){const row=make('div','team-task');row.dataset.s=t.status;const txt=make('div','team-text');txt.append(make('strong','',t.text),make('span','team-due',(t.status==='Late'?'Late · was due ':'Due ')+t.due_label));row.append(txt,chip(t.status));
     const x=make('button','team-x','✕');x.type='button';x.setAttribute('aria-label','Cancel '+t.text);x.onclick=()=>{if(confirm('Cancel this task?'))act({action:'cancel',id:t.id},'Cancelled.')};row.append(x);c.append(row)}
    const m=more(left.length-lim.left);if(m)c.append(m);body.append(c)}
   if(lim.done&&done.length){const c=make('p','team-donelist','Done ✓  '+done.map(t=>t.text).join(' · '));body.append(c)}
   if(lim.latest&&data.latest?.length){const c=make('section','team-card team-latest');
    for(const e of data.latest.slice(0,lim.latest)){const r=make('div','team-ev');r.append(make('time','',e.label),make('span','team-ev-text',e.text));c.append(r)}body.append(c)}
   const b=make('button','primary team-add','+ Add tasks');b.type='button';b.onclick=()=>{addOpen=true;draw(true);page.querySelector('#teamText')?.focus()};body.append(b)}
  shell.append(body);const foot=make('footer','team-foot');const back=make('button','tool team-back','← Back');back.type='button';back.onclick=()=>page.close();foot.append(back);shell.append(foot);page.append(shell);
 }
 async function open(){await refresh(true);if(!data){toast('Could not load the team screen.',true);return}if(!page.open)page.showModal();draw(true);if(data.unread)try{data={...data,...await api({action:'read'})};lastUnread=0;paintBadge()}catch(e){}clearInterval(timer);timer=setInterval(()=>refresh(true),8000)}
 page.addEventListener('close',()=>{clearInterval(timer);timer=setInterval(()=>refresh(true),45000)});
 page.addEventListener('cancel',e=>{e.preventDefault();page.close()});
 let rz=0;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>{if(page.open)draw()},120)});
 launch.onclick=open;
 document.addEventListener('donors-changed',()=>refresh(true));
 refresh(true);timer=setInterval(()=>refresh(true),45000);
})();
