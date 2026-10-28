(function(root){
const escape=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
function inline(text,depth=0){
 if(depth>8)return escape(text);
 let out='',i=0;
 while(i<text.length){
  let marker=text.startsWith('```',i)?'```':text[i];
  if(!['```','`','*','_','~'].includes(marker)){out+=escape(text[i++]);continue;}
  const before=i?text[i-1]:'';
  if(i&&/[\p{L}\p{N}]/u.test(before)){out+=escape(text[i++]);continue;}
  let end=text.indexOf(marker,i+marker.length),found=false;
  while(end!==-1){
   const content=text.slice(i+marker.length,end),after=text[end+marker.length]||'';
   if(content&&!/^\s|\s$/.test(content)&&(!after||!/[\p{L}\p{N}]/u.test(after))&&(marker==='```'||!content.includes('\n'))){
    const tag=marker==='*'?'strong':marker==='_'?'em':marker==='~'?'s':'code';
    out+=`<${tag}>${tag==='code'?escape(content):inline(content,depth+1)}</${tag}>`;i=end+marker.length;found=true;break;
   }
   end=text.indexOf(marker,end+marker.length);
  }
  if(!found){out+=escape(marker);i+=marker.length;}
 }
 return out;
}
function format(text){return text.replace(/\r\n/g,'\n').split('\n').map(line=>{
 const bullet=line.match(/^([*-]) (.*)$/),number=line.match(/^(\d+)\. (.*)$/),quote=line.match(/^> (.*)$/);
 if(bullet)return '<span class="wa-list">•  '+inline(bullet[2])+'</span>';
 if(number)return '<span class="wa-list">'+number[1]+'. '+inline(number[2])+'</span>';
 if(quote)return '<span class="wa-quote">'+inline(quote[1])+'</span>';
 return inline(line);
}).join('\n');}
root.waFormat=format;
// Limited assistant Markdown: all text is escaped by the existing formatter. No raw HTML or links.
root.chatFormat=text=>format(String(text).replace(/\*\*([^\n]+?)\*\*/g,'*$1*').replace(/^#{1,6} (.+)$/gm,'*$1*'));
if(typeof module!=='undefined')module.exports=format;
})(typeof window!=='undefined'?window:globalThis);


