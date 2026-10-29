/* Production desktop navigation: no transport or real sends. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.js','utf8');let hidden=false,focus='',keydown,changes=0,openDialog=null;
const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{id,open:false,hidden:false,attrs:{},setAttribute(k,v){this.attrs[k]=v},focus(){focus=id},showModal(){this.open=true;openDialog=this},close(){this.open=false;openDialog=null}});return nodes.get(id)}
const ctx={Nav:{go(){},leave(){},path(){return ''},top(){return ''}},addEventListener(){},smooth:f=>f(),$:node,isPhone:()=>false,document:{activeElement:{tagName:'BODY'},body:{classList:{contains:()=>hidden,toggle:(n,on)=>hidden=on}},querySelector:s=>s==='.overflow-tools'?node('menu'):openDialog,addEventListener:(type,fn)=>{if(type==='keydown')keydown=fn}},requestAnimationFrame:f=>f(),fit(){},flip(){},setView(){changes++},setEditing(){changes++},openChat(){},console};
vm.createContext(ctx);
vm.runInContext('let editing=false;'+source.slice(source.indexOf('function setNoMsg('),source.indexOf("if($('desktopPreview'))",source.indexOf('function setNoMsg(')))+source.slice(source.indexOf('function focusChatInput('),source.indexOf('/* ---- start ---- */')),ctx);
const key=(value,extra={})=>keydown({key:value,preventDefault(){},...extra});
key('/',{ctrlKey:true});assert(hidden);assert.equal(focus,'cmd','Ctrl / must reveal the chat before focusing its input');
ctx.setNoMsg(false);assert.equal(node('desktopPreview').attrs['aria-pressed'],'true');assert.equal(node('desktopPreview').textContent,'Back to chat');
key('/');assert(hidden);assert.equal(focus,'cmd');
key('?');assert(node('keyboardDialog').open);assert.equal(focus,'keyboardClose');
focus='keyboardClose';key('/',{ctrlKey:true});assert.equal(focus,'keyboardClose','Do not focus an inert input behind another dialog');
node('keyboardDialog').close();changes=0;key('g',{repeat:true});assert.equal(changes,0,'Held keys must not repeatedly change views or wording');
ctx.document.activeElement.tagName='TEXTAREA';key('g');assert.equal(changes,0,'Typing must not switch views');
console.log('Desktop navigation passed: preview state, focus visibility, shortcut dialog isolation, held keys and typing protection.');
