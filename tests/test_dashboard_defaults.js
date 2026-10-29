/* Check the actual dashboard visibility handler without a live transport. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.js','utf8'),html=fs.readFileSync('index.html','utf8');
let hidden=false,fits=0;
const menu={open:true},show={hidden:false,attrs:{},setAttribute(k,v){this.attrs[k]=v}},nodes={showMsg:show,hideMsg:{},previewBack:{}};
const ctx={$:id=>nodes[id],document:{querySelector:()=>menu,body:{classList:{toggle:(name,on)=>{assert.equal(name,'nomsg');hidden=on}}}},requestAnimationFrame:f=>f(),fit:()=>fits++,flip(){},smooth:change=>change(),setEditing(){throw Error('Not editing');}};
vm.createContext(ctx);
vm.runInContext('let editing=false;'+source.slice(source.indexOf('function setNoMsg('),source.indexOf('/* ---- theme:')),ctx);
assert(hidden,'Every opening starts hidden without consulting an old browser preference');
assert.equal(show.hidden,false);assert.equal(show.attrs['aria-expanded'],'false');assert.equal(menu.open,false);
nodes.showMsg.onclick();assert.equal(hidden,false);assert.equal(show.hidden,true);assert.equal(fits,1);
nodes.hideMsg.onclick({stopPropagation(){}});assert(hidden);assert.equal(show.hidden,false);
assert(html.includes('<body class="nomsg"'),'Avoid flashing the caption before JavaScript loads');
assert(html.includes('id="chips" role="group"'),'Group actions remain visible in the markup');
assert(!html.includes('id="chips" hidden'));assert(!html.includes('id="moreG"'));
assert(!source.includes("$('moreG')"),'No obsolete menu handler should hide the visible send buttons');
console.log('Dashboard defaults passed: hidden at startup, reveal/hide works, all group actions visible.');

