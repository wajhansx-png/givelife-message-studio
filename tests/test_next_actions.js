const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.js','utf8'),slice=source.slice(source.indexOf('let nextActions='),source.indexOf('function status('));
const row=()=>({hidden:true,children:[],set textContent(v){this.children=[]},append(b){this.children.push(b)}});
const rows={chatNextActions:row(),histNextActions:row()};
let gets=0,posts=0,watch=0,resolveSend;const id='a'.repeat(32),action={id,label:'Send to GiveLife main',detail:'Text only'};
const ctx={$:id=>rows[id],document:{createElement:()=>({setAttribute(){}})},fetch:async()=>{gets++;return {ok:true,json:async()=>({items:[{...action,disabled:posts>0}]})}},post:async(url,body)=>{assert.equal(url,'/chat-action');assert.deepEqual(Object.keys(body),['action_id']);posts++;await new Promise(r=>resolveSend=r);return {ok:true,json:async()=>({reply:'Sending saved text.',job_id:'job-one',caption:'Exact draft'})}},say(){},watchGroupJob(){watch++},closeChat(){},setView(){},Set,Array,Error};
vm.createContext(ctx);vm.runInContext(slice,ctx);
(async()=>{
 await ctx.refreshNextActions();assert.equal(posts,0,'Displaying suggested actions never executes them');assert.equal(rows.histNextActions.children[0].textContent,action.label);
 const first=ctx.runNextAction(action),duplicate=ctx.runNextAction(action);await new Promise(r=>setImmediate(r));assert.equal(posts,1);assert(rows.chatNextActions.children[0].disabled);assert(rows.histNextActions.children[0].disabled);resolveSend();await Promise.all([first,duplicate]);assert.equal(watch,1);assert(rows.histNextActions.children[0].disabled,'A started action remains disabled after refresh');
 let resolveRead;ctx.fetch=()=>new Promise(r=>resolveRead=r);const pending=ctx.refreshNextActions();ctx.clearNextActions();resolveRead({ok:true,json:async()=>({items:[action]})});await pending;assert(rows.histNextActions.hidden,'A late response cannot restore buttons from the previous task');
 console.log('Next actions passed: display is read-only, token-only execution, shared duplicate lock, receipt state and stale refresh protection.');
})().catch(e=>{console.error(e);process.exitCode=1});
