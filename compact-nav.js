/* Reuse live controls and handlers; this module only groups navigation. */
(()=>{
 const menus=[];
 function menu(parent,id,label){
  const details=document.createElement('details');details.id=id;details.className='compact-nav-menu';
  const summary=document.createElement('summary');summary.textContent='More';summary.setAttribute('aria-label',label);
  const panel=document.createElement('div');panel.className='compact-nav-panel';
  details.append(summary,panel);parent.append(details);menus.push(details);
  details.addEventListener('toggle',()=>{if(details.open)for(const other of menus)if(other!==details)other.open=false});
  panel.addEventListener('click',e=>{if(e.target.closest('button'))details.open=false});
  panel.addEventListener('change',()=>details.open=false);
  details.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();details.open=false;summary.focus()}});
  return panel;
 }
 const bar=document.querySelector('.brandbar');
 if(bar){
  const panel=menu(bar,'mainNavMore','More app options');
  for(const selector of ['#desktopPreview','.case-pick','#keyboardHelp']){
   const control=document.querySelector(selector);if(control)panel.append(control);
  }
  const preview=document.getElementById('desktopPreview');if(preview)preview.textContent='Message preview';
  const caseLabel=panel.querySelector('.case-pick .sr-only');if(caseLabel)caseLabel.classList.remove('sr-only');
  const badge=panel.querySelector('.team-badge'),summary=panel.parentElement.querySelector('summary');
  if(badge){const update=()=>{summary.dataset.unread=String(!badge.hidden);summary.setAttribute('aria-label',badge.hidden?'More app options':'More app options, new Team updates')};new MutationObserver(update).observe(badge,{attributes:true,childList:true,subtree:true});update()}
 }
 document.getElementById('openTeam')?.remove();
 const head=document.querySelector('.donor-head');
 if(head){
  const panel=menu(head,'donorNavMore','More donor options');
  for(const selector of ['.donor-message-tablist','#donorBulk']){
   const control=head.querySelector(selector);if(control)panel.append(control);
  }
  const normal=document.getElementById('donorNormalTotal')?.closest('.donor-total');if(normal)panel.append(normal);
 }
 document.addEventListener('pointerdown',e=>{for(const m of menus)if(m.open&&!m.contains(e.target))m.open=false});
 document.addEventListener('toggle',e=>{if(e.target instanceof HTMLDialogElement&&e.target.open)for(const m of menus)m.open=false},true);
})();
