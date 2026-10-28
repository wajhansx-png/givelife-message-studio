"""Instant, editable wording bank from the saved DM's verified case facts."""
import copy,hashlib,json,math,re,threading,time
from pathlib import Path
OPENINGS=[
 'Brother, could you help Yousuf get the treatment he needs?',
 'Brother, I am sharing Yousuf’s case with you personally.',
 'Brother, even one contribution can help move Yousuf’s treatment forward.',
 'Brother, please take a moment to read about this little boy.',
 'Brother, can you be part of Yousuf’s treatment fund today?',
 'Brother, a family needs help covering their child’s treatment.',
 'Brother, your support could help Yousuf reach the care he needs.',
 'Brother, may I ask you to help with Yousuf’s medical expenses?',
 'Brother, we are still collecting for Yousuf’s treatment.',
 'Brother, please consider a contribution for Yousuf.',
 'Brother, this is a personal appeal for little Yousuf.',
 'Brother, if you can help today, please consider Yousuf’s case.',
 'Brother, I wanted to bring Yousuf’s treatment needs to your attention.',
 'Brother, can we count on a contribution towards this child’s care?',
 'Brother, please read this short update on Yousuf.',
 'Brother, Yousuf’s treatment fund still needs support.',
 'Brother, a little help from you would support Yousuf’s medical care.',
 'Brother, I am reaching out with a request to help a child.',
 'Brother, could you contribute towards Yousuf’s hospital treatment?',
 'Brother, please help us bring Yousuf closer to treatment.'
]
ASKS=[
 'Could you send Rs. 2,000, or whatever you can manage? 🤲',
 'Please consider Rs. 2,000 today. A smaller contribution is welcome too. 🤲',
 'If you are able, a Rs. 2,000 contribution would help. 🤲',
 'Will you help with Rs. 2,000 towards his care? 🤲',
 'A donation of Rs. 2,000 would move this forward. Please help if you can. 🤲',
 'Please contribute what you can, and share the case if you cannot donate. 🤲',
 'Can you take one Rs. 2,000 share of the treatment fund? 🤲',
 'Your Rs. 2,000 can become part of his treatment. Please consider helping. 🤲',
 'If Rs. 2,000 is possible for you, please send it towards this case. 🤲',
 'Please help with a contribution or share this appeal with someone who can. 🤲'
]
class MessageBank:
 def __init__(self,app):self.app=app;self.path=app.DATA/'donor-messages.json';self.lock=threading.RLock();self.cache=None
 def _source(self):return self.app.get_message('dm')['text']
 def _save(self,data):
  if self.app.STORE:self.app.STORE.put('donor_messages',data)
  self.cache=copy.deepcopy(data);self.path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
 def _build(self,source):
  left=self.app.read_left();p2,p1=math.ceil(left/2000),math.ceil(left/1000);trusted=all(w in source.casefold() for w in ('yous','fluid','brain','kidney'))
  entries=[]
  for i,opening in enumerate(OPENINGS):
   if trusted:
    condition=self.app.DP[1][i%len(self.app.DP[1])]
    if 'hernia' not in source.casefold():condition=re.sub(r'(?i)[,.]?\s*(?:and )?(?:he )?(?:also )?has a hernia[^.]*\.?','.',condition)
    risk=self.app.DP[2][(i*3)%len(self.app.DP[2])] if re.search(r'(?i)paraly',source) and re.search(r'(?i)eyesight|vision',source) else 'Please help with the treatment fund if you are able.'
    # Preserve reported updates and quotations verbatim; do not invent new reports.
    reports=[line.strip() for line in source.split('\n') if re.search(r'(?i)breath|parents? report|hadith|prophet|muslim|bukhari|ﷺ',line)]
    amount=(f'💰 *_Rs. {left:,} left for treatment._*' if i%2 else f'💰 *_Rs. {left:,} still needed for treatment._*')
    options=f'*_{p2} people contributing Rs. 2,000_*\n*_OR {p1} people contributing Rs. 1,000._*'
    text=opening+'\n\n_'+condition+'_ 💔\n\n*'+risk+'*'+('\n\n'+'\n'.join(reports) if reports else '')+'\n\n'+amount+'\n\n'+options+'\n\n'+ASKS[i%len(ASKS)]+'\n\n📲 *03097458815*\nEasypaisa / JazzCash\nWajdan Khan (GiveLife Foundation account)\n\nReply *Done* after donating.'
   else:
    import dm_composer
    body=dm_composer.GREETING.sub('',source,count=1);text=opening+'\n\n'+body+'\n\n'+ASKS[i%len(ASKS)]
   entries.append({'id':f'wording-{i+1:02d}','text':text,'enabled':True})
  return {'fingerprint':hashlib.sha256(source.encode()).hexdigest(),'items':entries,'updated_at':time.time(),'source':'Saved DM case facts; varied wording, not a delivery guarantee'}
 def get(self):
  with self.lock:
   source=self._source();fingerprint=hashlib.sha256(source.encode()).hexdigest()
   if self.cache is None:
    self.cache=self.app.STORE.get('donor_messages') if self.app.STORE else None
    if self.cache is None and self.path.exists():self.cache=json.loads(self.path.read_text(encoding='utf-8'))
   if not isinstance(self.cache,dict) or self.cache.get('fingerprint')!=fingerprint:self._save(self._build(source))
   return copy.deepcopy(self.cache)
 def update(self,ident,text):
  import dm_composer
  if not isinstance(text,str) or len(text)>10000 or not dm_composer.complete(text):raise ValueError('Keep the complete case message, paragraphs, remaining amount and payment details.')
  with self.lock:
   data=self.get();row=next((r for r in data['items'] if r['id']==ident),None)
   if row is None:raise ValueError('Message not found.')
   row['text']=text;data['updated_at']=time.time();self._save(data);return {'saved':True,'item':row}
 def regenerate(self):
  with self.lock:self._save(self._build(self._source()));return self.get()
 def captions(self,count):
  items=[r['text'] for r in self.get()['items'] if r.get('enabled')]
  if len(set(items))<count:raise ValueError('Prepare enough different messages in Messages before starting this batch.')
  return items[:count]

