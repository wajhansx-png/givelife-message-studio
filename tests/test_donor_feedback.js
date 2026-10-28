const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('donors.js','utf8');
const start=source.indexOf('function paintDelivery('),end=source.indexOf('\n function draw(',start);
const context={};vm.createContext(context);vm.runInContext(source.slice(start,end),context);
const button={textContent:'DM',disabled:false,title:'',setAttribute(k,v){this[k]=v}};
const row={dataset:{},querySelector(selector){return selector==='.donor-dm'?button:{textContent:'Ali'}}};
context.paintDelivery(row,'Requesting');assert.equal(button.textContent,'…');assert(button.disabled);assert.notEqual(row.dataset.delivery,'Sent');
context.paintDelivery(row,'Sending');assert(button.disabled);assert(!button.textContent.includes('Sent'));
context.paintDelivery(row,'Sent');assert.equal(button.textContent,'DM sent');assert.equal(button.disabled,false);assert.equal(row.dataset.delivery,'Sent');assert.equal(button['aria-label'],'Send DM again to Ali');
context.paintDelivery(row,'Uncertain');assert.equal(button.textContent,'Check');assert.equal(button.disabled,false);assert.notEqual(row.dataset.delivery,'Sent');
context.paintDelivery(row,'Skipped');assert.equal(button.textContent,'Check');assert.notEqual(row.dataset.delivery,'Sent');
context.paintDelivery(row,'Not sent');assert.equal(button.textContent,'Retry');assert.equal(button.disabled,false);
assert(!source.includes("make('input','donor-notes')"),'Notes are removed from the directory UI');
assert(source.includes("make('button','donor-status'")&&source.includes('donated:!d.donated'),'Donation status toggles in one click');
assert(source.includes("api('/donor-send',{id:ids[0],request_id:requestId()})"),'Individual DM uses the immediate explicit-send endpoint');
assert(source.includes('donorTotalAmount')&&source.includes('data.counts.donated_amount'),'Header displays the server-calculated donated total');
assert(source.includes("if(!active&&j.state!=='Idle')await refresh(true)"),'Confirmed delivery must refresh persisted row state');
console.log('Donor feedback passed: immediate action, pending/confirmed separation, uncertain protection, compact fields, persisted receipt refresh.');

