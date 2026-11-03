/* Comfort helpers for screens built after page load. Reuses the live controls and their handlers. */
(()=>{
 const phone=matchMedia('(max-width:899px)'),still=matchMedia('(prefers-reduced-motion: reduce)');

 /* Accessibility: dialog headers/footers are not page landmarks; long previews must be keyboard-reachable. */
 let queued=0;
 function normalise(){
  queued=0;
  document.querySelectorAll('dialog header:not([role]),dialog footer:not([role]),#messageFocus header:not([role]),#messageFocus footer:not([role])').forEach(e=>e.setAttribute('role','group'));
  document.querySelectorAll('.bank-preview:not([tabindex])').forEach(e=>{e.tabIndex=0;if(!e.hasAttribute('aria-label'))e.setAttribute('aria-label','Message preview')});
 }
 new MutationObserver(()=>{if(!queued)queued=setTimeout(normalise,120)}).observe(document.body,{childList:true,subtree:true});
 normalise();

 /* Smooth screen changes: a short fade-and-rise whenever a screen, tab or message appears. */
 function enter(el){
  if(!el||still.matches||el.classList.contains('cmf-enter'))return;
  el.classList.add('cmf-enter');
  el.addEventListener('animationend',()=>el.classList.remove('cmf-enter'),{once:true});
 }
 const shown=el=>el.tagName==='DIALOG'?el.open:!el.hidden;
 new MutationObserver(records=>{
  for(const r of records){const el=r.target;
   /* Only whole screens: page dialogs and the message editor. Small dialogs and ordinary hidden toggles never animate the page. */
   const screen=(el.tagName==='DIALOG'&&!el.matches('.memory-dialog,.keyboard-dialog,#feedbackDialog'))||el.id==='messageFocus';
   if(!screen||r.attributeName!==(el.tagName==='DIALOG'?'open':'hidden'))continue;
   if(shown(el))enter(el);
   else if(!document.querySelector('dialog[open]:not(.memory-dialog):not(.keyboard-dialog)')&&document.getElementById('messageFocus')?.hidden!==false)enter(document.getElementById('main-workspace'));
  }
 }).observe(document.body,{attributes:true,attributeFilter:['open','hidden'],subtree:true});
 document.addEventListener('click',e=>{
  const t=e.target.closest('.donor-tabs [role=tab],#donorMessagesTab,[data-bank-nav],.bank-back,.bank-back-bottom,[data-view-button]');
  if(!t)return;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
   if(t.matches('[data-bank-nav]'))enter(document.querySelector('#donorMessages .bank-detail'));
   else if(t.matches('#donorMessagesTab'))enter(document.getElementById('donorMessages'));
   else if(t.matches('[data-view-button]'))enter(document.getElementById('card'));
   else enter(document.getElementById('donorTable'));
  }));
 },true);

 /* Donors: Messages lives in the top nav. On phones Test DM and the poster switch move into More,
    so the bottom bar is a single row: Back · Stop · DM ★ · DM all. */
 function placeDonorControls(){
  const head=document.querySelector('.donor-head'),more=document.getElementById('donorNavMore'),bottom=document.querySelector('.donor-bottom');
  const tabs=document.querySelector('.donor-message-tablist'),test=document.getElementById('donorTest'),poster=document.querySelector('.donor-poster-toggle'),toggle=document.getElementById('donorToggle');
  if(!head||!more||!bottom||!tabs)return;
  if(tabs.parentElement!==head)head.insertBefore(tabs,document.getElementById('donorAdd')||more);
  const panel=more.querySelector('.compact-nav-panel');
  if(phone.matches&&panel){if(test)panel.prepend(test);if(poster)panel.append(poster)}
  else if(toggle){if(test)bottom.insertBefore(test,toggle);if(poster)toggle.after(poster)}
 }
 placeDonorControls();phone.addEventListener('change',placeDonorControls);

 /* Donor Messages reader: progress from "Message n of N", → for Next on desktop, swipe left for Next on phones. */
 const box=document.getElementById('donorMessages');
 const nextBtn=()=>box?.querySelector('[data-bank-nav=next]:not(:disabled)');
 function decorateReader(){
  if(!box)return;const head=box.querySelector('.bank-heading'),title=box.querySelector('.bank-current');if(!head||!title)return;
  const m=/(\d+)\s+of\s+(\d+)/.exec(title.textContent||'');
  let bar=box.querySelector(':scope > .bank-progress');
  if(!bar){bar=document.createElement('div');bar.className='bank-progress';bar.setAttribute('aria-hidden','true');bar.append(document.createElement('i'));head.after(bar)}
  bar.firstChild.style.width=m?Math.round(+m[1]/+m[2]*100)+'%':'0%';
  const n=nextBtn();if(n&&!n.title)n.title='Next message (→)';
 }
 if(box){new MutationObserver(()=>requestAnimationFrame(decorateReader)).observe(box,{childList:true});decorateReader()}
 const readerOpen=()=>document.getElementById('donorsPage')?.dataset.panel==='messages'&&document.getElementById('donorsPage')?.open;
 document.addEventListener('keydown',e=>{
  if(e.key!=='ArrowRight'||e.altKey||e.ctrlKey||e.metaKey||!readerOpen())return;
  if(e.target.closest?.('input,textarea,select,[contenteditable=true]'))return;
  const n=nextBtn();if(n){e.preventDefault();n.click()}
 });
 let touch=null;
 box?.addEventListener('touchstart',e=>{if(e.target.closest('.bank-preview')&&e.touches.length===1)touch={x:e.touches[0].clientX,y:e.touches[0].clientY};else touch=null},{passive:true});
 box?.addEventListener('touchend',e=>{if(!touch)return;const t=e.changedTouches[0],dx=t.clientX-touch.x,dy=t.clientY-touch.y;touch=null;
  if(dx<-70&&Math.abs(dy)<45&&!getSelection()?.toString()){const n=nextBtn();if(n)n.click()}},{passive:true});
})();
