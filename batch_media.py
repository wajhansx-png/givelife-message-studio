"""Private, immutable batch attachments. Never changes the campaign poster."""
import base64,json,re,time,uuid
from pathlib import Path

TYPES={'image/jpeg':('.jpg',b'\xff\xd8\xff'),'image/png':('.png',b'\x89PNG\r\n\x1a\n'),'image/webp':('.webp',b'RIFF'),'application/pdf':('.pdf',b'%PDF-'),'video/mp4':('.mp4',None)}

def save(store,data):
 if not store:raise ValueError('Private attachment storage is unavailable.')
 if not isinstance(data,str):raise ValueError('Choose an image, MP4 video or PDF.')
 match=re.fullmatch(r'data:([^;,]+);base64,([A-Za-z0-9+/=\r\n]+)',data)
 if not match or match[1] not in TYPES:raise ValueError('Choose a JPEG, PNG, WebP image, MP4 video or PDF.')
 try:raw=base64.b64decode(match[2],validate=True)
 except Exception:raise ValueError('The attachment could not be read.') from None
 if not 0<len(raw)<=15_000_000:raise ValueError('Choose a file under 15 MB.')
 ext,magic=TYPES[match[1]]
 if magic and not raw.startswith(magic) or ext=='.mp4' and raw[4:8]!=b'ftyp' or ext=='.webp' and raw[8:12]!=b'WEBP':raise ValueError('The file contents do not match its type.')
 ident=uuid.uuid4().hex
 store.put('batch_media_'+ident,{'mime':match[1],'data':base64.b64encode(raw).decode(),'created':time.time()})
 return ident

def load(store,ident,folder):
 if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose the attachment again.')
 row=store.get('batch_media_'+ident) if store else None
 if isinstance(row,str):
  try:row=json.loads(row)
  except ValueError:row=None
 if not isinstance(row,dict) or row.get('mime') not in TYPES:raise ValueError('The attachment is unavailable. Choose it again.')
 path=Path(folder)/('bulk-'+ident+TYPES[row['mime']][0]);path.write_bytes(base64.b64decode(row['data'],validate=True))
 return path,row['mime']
