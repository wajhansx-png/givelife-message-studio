const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('app.js','utf8');
const nodes=['main','test','community','free','all'].map(lastGroup=>({dataset:{lastGroup},textContent:'',title:''}));
const now=1800000000000;
class Clock extends Date {static now(){return now}}
const ctx={Date:Clock,Math,Number,Array,GN:{main:'GiveLife'},document:{querySelectorAll:()=>nodes},setInterval(){}};vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('/* Confirmed group-send times.'),src.indexOf('/* ---- send a plain message')),ctx);
ctx.paintGroupTimes();assert(nodes.every(n=>n.textContent==='Checking…'));
ctx.paintGroupTimes({main:now/1000-7200,test:now/1000-30,community:now/1000-600});
assert.equal(nodes[0].textContent,'Sent 2 h ago');assert.equal(nodes[1].textContent,'Sent just now');assert.equal(nodes[2].textContent,'Sent 10 min ago');
assert.equal(nodes[3].textContent,'Latest: 10 min ago','A batch label must identify its most recent individual send, not claim a completed round');
ctx.paintGroupTimes({main:'bad',test:now/1000+1000,community:0});assert(nodes.every(n=>n.textContent==='Not sent yet'));
ctx.paintGroupTimes({main:now/1000-120});ctx.paintGroupTimes();assert.equal(nodes[0].textContent,'Sent 2 min ago','Keep the last real timestamp between polls');
vm.runInContext(src.slice(src.indexOf('function dashboardConversation('),src.indexOf('function drawLog(')),ctx);
const conversation=[{who:'you',text:'old'},{who:'app',text:'old reply'},{who:'you',text:'new'},{who:'app',text:'Full answer\n'.repeat(500)},{who:'auto',text:'real update'}];
const latest=ctx.dashboardConversation(conversation);assert.equal(latest.length,3);assert.equal(latest[1].text,conversation[3].text);assert.equal(conversation.length,5,'History is retained intact');
console.log('Reading and receipts passed: full latest turn, intact history, real ages, missing/future timestamps and truthful batch labels.');
