/* Team screen: updates from the teammate in the centre, tasks with status, and a box to write today's tasks. */
(()=>{
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e};
 const page=make('dialog','team-page');page.id='teamPage';page.setAttribute('aria-label','Team tasks');document.body.append(page);
 const launch=make('button','donor-launch team-launch','Team');launch.type='button';launch.id='openTeam';
 const badge=make('span','team-badge');badge.hidden=true;launch.append(badge);document.querySelector('.brandbar')?.append(launch);
 let data=null,timer=0,lastUnread=0,planText='',toastTimer=0;
 const api=async(body)=>{const r=await fetch('/team',body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Something went wrong.');return d};
 function toast(text,bad){let t=document.getElementById('teamToast');if(!t){t=make('div','team-toast');t.id='teamToast';t.setAttribute('role','status');document.body.append(t)}t.textContent=text;t.dataset.bad=String(!!bad);t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{t.hidden=true},6000)}
 function paintBadge(){const n=data?.unread||0;badge.hidden=!n;badge.textContent=n>9?'9+':String(n);launch.setAttribute('aria-label','Team'+(n?', '+n+' new update'+(n===1?'':'s'):''))}
 async function refresh(quiet){try{const d=await api();const first=data===null;data=d;if(!first&&d.unread>lastUnread){const e=d.feed.find(x=>['update','report','blocked','proof','late'].includes(x.kind));toast(e?e.text:'New update from your teammate',e&&['blocked','late'].includes(e.kind))}lastUnread=d.unread;paintBadge();if(page.open)draw()}catch(e){if(!quiet&&page.open)toast(e.message,true)}}
 async function act(body,ok){try{data={...data,...await api(body)};if(ok)toast(ok);lastUnread=data.unread;paintBadge();draw()}catch(e){toast(e.message,true)}}
 const chip=(s)=>{const c=make('span','team-chip',s==='Reported'?'Needs your check':s);c.dataset.s=s;return c};
 function draw(){
  const scroll=page.querySelector('.team-body')?.scrollTop||0;const typed=page.querySelector('#teamText')?.value;if(typed!==undefined)planText=typed;
  page.textContent='';const shell=make('div','team-shell');
  const head=make('header','team-head');const title=make('div','team-title');title.append(make('h1','','Team'));title.append(make('span','team-sub',data?.member?data.member.name+' · '+(data.paused?'follow-up paused':'follow-up on'):'Add your teammate to start'));
  head.append(title);
  if(data?.member){const p=make('button','tool team-pause',data.paused?'Resume':'Pause');p.type='button';p.onclick=()=>act({action:'pause',on:!data.paused},data.paused?'Follow-up resumed.':'Follow-up paused. Nothing will be sent.');head.append(p)}
  shell.append(head);const body=make('div','team-body');
  if(!data?.member){
   const f=make('form','team-card team-setup');f.append(make('h2','','Who is your teammate?'),make('p','team-hint','Their WhatsApp number stays hidden. The app messages them only about the tasks you confirm.'));
   const n=make('input','');n.name='team_name';n.placeholder='Name';n.autocomplete='off';n.setAttribute('aria-label','Teammate name');const ph=make('input','');ph.name='team_phone';ph.type='tel';ph.placeholder='WhatsApp number';ph.setAttribute('aria-label','Teammate WhatsApp number');
   const b=make('button','primary','Save teammate');b.type='submit';f.append(n,ph,b);f.onsubmit=e=>{e.preventDefault();act({action:'member',name:n.value,phone:ph.value},'Teammate saved.')};body.append(f)}
  else{
   const review=data.tasks.filter(t=>t.status==='Reported');
   if(review.length){const c=make('section','team-card team-review');c.append(make('h2','','Waiting for your check'));
    for(const t of review){const row=make('div','team-item');const txt=make('div','team-text');txt.append(make('strong','','#'+t.no+' '+t.text),make('span','team-say','"'+(t.report_text||'done')+'"'));const pr=make('span','team-proof',t.proof?'Proof ✓':'No proof yet');pr.dataset.ok=String(!!t.proof);txt.append(pr);
     const ok=make('button','primary','Verified ✓');ok.type='button';ok.onclick=()=>act({action:'verify',id:t.id},'Task #'+t.no+' verified.');
     const no=make('button','tool','Not done');no.type='button';no.onclick=()=>{const note=prompt('What should '+data.member.name+' fix? (optional)','');if(note!==null)act({action:'reject',id:t.id,note},'Sent back to '+data.member.name+'.')};
     const acts=make('div','team-actions');acts.append(ok,no);row.append(txt,acts);c.append(row)}body.append(c)}
   const upd=make('section','team-card');upd.append(make('h2','','Updates from '+data.member.name));
   const list=make('div','team-feed');const shown=data.feed.filter(e=>e.kind!=='plan').slice(0,40);
   if(!shown.length)list.append(make('p','team-empty','No updates yet. When '+data.member.name+' replies on WhatsApp, it shows here.'));
   for(const e of shown){const r=make('div','team-ev');r.dataset.kind=e.kind;r.append(make('time','',e.label),make('span','team-ev-text',e.text));list.append(r)}upd.append(list);body.append(upd);
   const tasks=make('section','team-card');tasks.append(make('h2','',"Today's tasks"));
   if(!data.tasks.length)tasks.append(make('p','team-empty','No tasks yet. Write them below.'));
   for(const t of data.tasks){const row=make('div','team-task');row.dataset.s=t.status;const txt=make('div','team-text');txt.append(make('strong','','#'+t.no+' '+t.text),make('span','team-due','Ask '+t.start_label+' · due '+t.due_label));row.append(txt,chip(t.status));
    if(['Waiting','Asked','Late'].includes(t.status)){const c=make('button','tool','Cancel');c.type='button';c.onclick=()=>{if(confirm('Cancel task #'+t.no+'?'))act({action:'cancel',id:t.id},'Task cancelled.')};row.append(c)}tasks.append(row)}
   body.append(tasks);
   const add=make('section','team-card');add.append(make('h2','','Write today\'s tasks'));
   if(data.plan){add.append(make('p','team-hint','Check the plan. Nothing is sent until you press Start.'));
    data.plan.items.forEach((i,k)=>{const r=make('div','team-task');const txt=make('div','team-text');txt.append(make('strong','',(k+1)+'. '+i.text),make('span','team-due','Ask '+i.start_label+' · due '+i.due_label));r.append(txt);add.append(r)});
    const go=make('button','primary','Start tasks');go.type='button';go.onclick=()=>{planText='';act({action:'confirm'},'Tasks started.')};const ds=make('button','tool','Discard');ds.type='button';ds.onclick=()=>act({action:'discard'});const ar=make('div','team-actions');ar.append(go,ds);add.append(ar)}
   else{const ta=make('textarea','');ta.id='teamText';ta.name='team_tasks';ta.rows=5;ta.maxLength=3000;ta.value=planText;ta.placeholder='One task per line, then a deadline. Example:\n1) Post in the 3 groups\n2) Update the sheet\n3) Message the donors\nDeadline 6pm';ta.setAttribute('aria-label','Today\'s tasks');
    const go=make('button','primary','Plan the tasks');go.type='button';go.onclick=()=>act({action:'plan',text:ta.value});add.append(ta,go)}
   body.append(add)}
  shell.append(body);const foot=make('footer','team-foot');const back=make('button','tool team-back','← Back');back.type='button';back.onclick=()=>page.close();foot.append(back);shell.append(foot);page.append(shell);
  const nb=page.querySelector('.team-body');if(nb)nb.scrollTop=scroll;
 }
 async function open(){await refresh(true);if(!data){toast('Could not load the team screen.',true);return}draw();if(!page.open)page.showModal();if(data.unread)try{data={...data,...await api({action:'read'})};lastUnread=0;paintBadge()}catch(e){}clearInterval(timer);timer=setInterval(()=>refresh(true),8000)}
 page.addEventListener('close',()=>{clearInterval(timer);timer=setInterval(()=>refresh(true),45000)});
 page.addEventListener('cancel',e=>{e.preventDefault();page.close()});
 launch.onclick=open;
 document.addEventListener('donors-changed',()=>refresh(true));
 refresh(true);timer=setInterval(()=>refresh(true),45000);
})();
