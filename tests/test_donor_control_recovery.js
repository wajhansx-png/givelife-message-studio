const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('donors.js','utf8');
test('clock input uses Pakistan time even on a browser in another zone',()=>{
 const ctx={Date:{parse:Date.parse,now:()=>Date.parse('2026-11-03T10:00:00Z')},Number,Error};vm.createContext(ctx);
 const a=source.indexOf('function resumeClockValue(');vm.runInContext(source.slice(a,source.indexOf('\n',a)),ctx);
 assert.equal(ctx.resumeClockValue('2026-11-03','15:01'),'2026-11-03T15:01');
 assert.throws(()=>ctx.resumeClockValue('2026-11-03','14:59'),/future/);
 assert.throws(()=>ctx.resumeClockValue('','15:01'),/both/);
});
test('Resume opens the choice dialog and never resumes before a choice',async()=>{
 let shown=0,requests=0;
 const nodes={donorToggle:{},donorResumeNow:{focus(){}},donorResumeClock:{hidden:false},donorResumeNote:{},donorResumeSchedule:{}};
 const ctx={el:id=>nodes[id],resumeDialog:{open:false,showModal(){shown++}},api:async()=>{requests++;return {paused:true}},notice(){},poll(){},syncToggle:async()=>{}};
 vm.createContext(ctx);const a=source.indexOf('function openResumeChoice(');
 assert.notEqual(a,-1,'resume must have a choice dialog');
 vm.runInContext(source.slice(a,source.indexOf(' function ',a+10)),ctx);
 ctx.openResumeChoice();assert.equal(shown,1);assert.equal(requests,0);
});
test('failed regeneration preserves unsaved Message 1 and unlocks controls',async()=>{
 const edits=new Map([['master','my new message']]);let paints=0;
 const ctx={bankRegenerating:false,bankSaves:new Set(),bankEdits:edits,bankData:{items:[{id:'master',text:'old'}]},syncBankControls(){paints++},keepBankEdits(){},showMessages(){},notice(){},api:async()=>{throw Error('offline')}};
 vm.createContext(ctx);const start=source.indexOf('regen.onclick=async()=>');
 vm.runInContext('var regen={};'+source.slice(start,source.indexOf(';box.append(head)',start)),ctx);
 await ctx.regen.onclick();assert.equal(ctx.bankRegenerating,false);
 assert.equal(edits.get('master'),'my new message');assert.equal(ctx.bankData.items[0].text,'old');assert.ok(paints>=2);
});
test('a rejected single send releases its lock so controls can be used again',async()=>{
 let notices=0;
 const ctx={sendPending:false,document:{activeElement:null},el:()=>({children:[]}),page:{querySelectorAll:()=>[]},paintDelivery(){},requestId:()=> 'request',singlePosterOn:true,api:async()=>{throw Error('offline')},refresh:async()=>{},notice(){notices++}};
 vm.createContext(ctx);const start=source.indexOf('async function send(scope');
 vm.runInContext(source.slice(start,source.indexOf('\n',start)),ctx);
 await ctx.send('selected',['a']);assert.equal(ctx.sendPending,false);
 await ctx.send('selected',['a']);assert.equal(notices,2);
});
test('delivery polling recovers after a failed status read without resending',async()=>{
 const timers=[],calls=[];
 const ctx={page:{open:true},clearTimeout(){},pollTimer:null,setTimeout(fn,ms){timers.push({fn,ms});return 1},notice(){},api:async path=>{calls.push(path);throw Error('offline')}};
 vm.createContext(ctx);
 const start=source.indexOf('async function poll()');
 vm.runInContext(source.slice(start,source.indexOf('\n',start)),ctx);
 await ctx.poll();
 assert.equal(timers.length,1,'a transient error must schedule another status read');
 assert.equal(calls.length,1);
 ctx.page.open=false;await timers[0].fn();assert.equal(calls.length,1,'closed screen must stop polling');
});
test('message and send requests time out with an actionable uncertainty message',async()=>{
 let timeout,cleared=false;
 const ctx={AbortController,setTimeout(fn){timeout=fn;return 1},clearTimeout(){cleared=true},fetch:(path,opts)=>new Promise((resolve,reject)=>opts.signal?.addEventListener('abort',()=>reject(Object.assign(Error('aborted'),{name:'AbortError'}))))};
 vm.createContext(ctx);const start=source.indexOf('async function api(');
 vm.runInContext(source.slice(start,source.indexOf(' let dismissedJob',start)),ctx);
 const request=ctx.api('/donor-send',{id:'a'});
 assert.equal(typeof timeout,'function','a stalled request must have a timeout');timeout();
 await assert.rejects(request,/not confirmed|check.*before.*retry/i);assert.equal(cleared,true);
});
