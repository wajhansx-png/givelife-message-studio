module.exports=async()=>{
 const port=Number(process.env.GIVELIFE_TEST_PORT||3041);
 try{await fetch(`http://127.0.0.1:${port}/__test/shutdown`,{method:'POST',headers:{Authorization:'Bearer group-finder-preview-only'},signal:AbortSignal.timeout(5000)})}catch(e){}
};
