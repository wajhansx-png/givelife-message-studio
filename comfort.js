/* Accessibility normaliser for screens that are built after page load.
   Dialog headers/footers are not page landmarks; long previews must be reachable by keyboard. */
(()=>{
 let queued=0;
 function normalise(){
  queued=0;
  document.querySelectorAll('dialog header:not([role]),dialog footer:not([role]),#messageFocus header:not([role]),#messageFocus footer:not([role])').forEach(e=>e.setAttribute('role','group'));
  document.querySelectorAll('.bank-preview:not([tabindex])').forEach(e=>{e.tabIndex=0;if(!e.hasAttribute('aria-label'))e.setAttribute('aria-label','Message preview')});
 }
 function schedule(){if(!queued)queued=setTimeout(normalise,120)}
 new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
 normalise();
})();
