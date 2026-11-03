const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('donors.js','utf8');
const line=(start)=>{const a=source.indexOf(start);assert.notEqual(a,-1);return source.slice(a,source.indexOf('\n',a));};
test('opening timing sends nothing; confirmation queues exactly the chosen delay and poster',async()=>{
 const nodes={volStartDelay:{value:'3600'},volTimingStart:{},volTimingNote:{},volTimingAudience:{},volTimingForm:{}};
 nodes.volStartDelay.focus=()=>{};let shown=0,closed=0;const calls=[];
 const ctx={el:id=>nodes[id],volTimingPending:false,volSendPlan:null,vols:{items:[{},{}]},volTiming:{open:false,showModal(){shown++},close(){closed++}},requestId:()=> 'test-1',paintVolunteerTiming(){},notice(){},loadVolunteers:async()=>{},showVolunteers(){},tab:'volunteers',api:async(path,body)=>{calls.push({path,body});return {reply:'Queued'}}};
 vm.createContext(ctx);vm.runInContext(line('function volunteerDelaySeconds('),ctx);vm.runInContext(line('function openVolunteerTiming('),ctx);
 ctx.openVolunteerTiming('Please share this.',false);assert.equal(shown,1);assert.equal(calls.length,0);
 nodes.volStartDelay.value='3600';vm.runInContext(line("el('volTimingForm').onsubmit="),ctx);
 const submit=()=>nodes.volTimingForm.onsubmit({preventDefault(){}});await Promise.all([submit(),submit()]);
 assert.equal(calls.length,2,'one save and one batch request, even after a double tap');
 assert.equal(calls[0].body.text,'Please share this.');assert.equal(calls[1].body.action,'send_all');assert.equal(calls[1].body.delay_seconds,3600);assert.equal(calls[1].body.poster,false);assert.equal(calls[1].body.gap_seconds,180);assert.equal(closed,1);assert.equal(ctx.volTimingPending,false);
});
test('volunteer timing accepts the requested presets and rejects malformed choices',()=>{
 const start=source.indexOf('function volunteerDelaySeconds(');
 assert.notEqual(start,-1,'timing choice must be validated before sending');
 const ctx={Number,Error};vm.createContext(ctx);vm.runInContext(source.slice(start,source.indexOf('\n',start)),ctx);
 for(const seconds of [0,300,600,900,1800,3600,7200])assert.equal(ctx.volunteerDelaySeconds(String(seconds)),seconds);
 for(const bad of ['','5','301','-1','Infinity','abc'])assert.throws(()=>ctx.volunteerDelaySeconds(bad));
});
