module.exports=async()=>{
 await fetch('http://127.0.0.1:3055/__test/shutdown',{method:'POST',headers:{Authorization:'Bearer manual-fix-preview-key','Content-Type':'application/json'},body:'{}'}).catch(()=>{});
};
