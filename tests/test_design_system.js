/* Semantic contrast and safe reply formatting, without WhatsApp or model calls. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const css=fs.readFileSync('studio.css','utf8');
// Merge every top-level token block for a theme in file order (later wins), so the test reads the colours users actually see.
const blocks=(match)=>[...css.matchAll(/(^|\n):root([^{@]*)\{([^}]*)\}/g)].filter(m=>match(m[2].trim())).map(m=>m[3]).join('\n');
const light=blocks(sel=>sel===''||sel===':not([data-theme=dark])'||sel==='[data-theme=light],:root:not([data-theme=dark])'||sel.startsWith('[data-theme=light]'));
const dark=blocks(sel=>sel==='[data-theme=dark]');
const luminance=h=>h.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((n,x,i)=>n+x*[.2126,.7152,.0722][i],0);
const contrast=(a,b)=>{const x=[luminance(a),luminance(b)].sort((a,b)=>a-b);return (x[1]+.05)/(x[0]+.05)};
for(const [name,source] of [['light',light],['dark',dark]]){
 const t=Object.fromEntries([...source.matchAll(/--([\w-]+):\s*(#[a-fA-F0-9]{3,6})(?=;)/g)].map(m=>[m[1],m[2].length===4?'#'+[...m[2].slice(1)].map(x=>x+x).join(''):m[2]]));
 for(const [fg,bg] of [['ink','surface'],['mut','surface'],['mut','surface2'],['gink','gs'],['msgink','msg'],['ok','pill'],['red','surface'],['warn','wbg']])assert(contrast(t[fg],t[bg])>=4.5,`${name} ${fg}/${bg} must meet AA text contrast`);
 assert(contrast(t['on-accent'],t.btn)>=4.5,`${name} primary button text`);
 assert(contrast(t.line2,t.surface)>=3,`${name} control boundary contrast`);
}
const context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync('format.js','utf8'),context);
const render=context.window.chatFormat;
assert(render('**Bold reply**').includes('<strong>Bold reply</strong>'));
assert(render('_Italic_').includes('<em>Italic</em>'));
assert(!render('<img src=x onerror=alert(1)> **safe**').includes('<img'));
assert(!render('<script>alert(1)</script>').includes('<script>'));
assert(render('First\n\nLast').includes('\n\n'),'Paragraph spacing must survive formatting');
assert.equal(context.window.waFormat('*Original caption*'),'<strong>Original caption</strong>','WhatsApp caption formatting stays unchanged');
console.log('Design system passed: light/dark text and control contrast, escaped assistant formatting, paragraph preservation and original WhatsApp formatting.');
