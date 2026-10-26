"""Pure intent parsing. Owner instructions are never outgoing message text."""
import re
ALIASES={
 'main':('givelife foundation','give life foundation','givelife main','give life main','givelife','give life','main'),
 'community':('upwork community 2026','upwork community','community'),
 'fiverr':('fiverr course 2026','fiverr course','fiverr'),
 'upwork':('upwork course 2026','upwork course','upwork'),
 'uet':('fiverr course uet','fiverr uet','uet'),
 'toprated':('top rated upworkers','topratedupworkers','top rated','toprated'),
 'free':('all 5 freelance groups','all five freelance groups','all freelance groups','all freelance','5 freelance','freelance','free'),
 'all':('all 6 groups','all six groups','all groups','all'),
 'test':('givelife test','give life test','test group','test')}
SEND=re.compile(r'\b(send|resend|post|share|bhejo|bhej|daalo|dalo|sebd|semd)\b|بھیج|ارسال',re.I)
CONTROL=re.compile(r'^(?:(?:man|please|bhai|bro|yaar|now|abhi|send|resend|post|it|this|that|again|do|go|and|restart|reset|the|gap|timer|message|msg|poster|image|picture|appeal|with|updated|amount|right|away|asap|immediately|fast|quick|only|current|latest|sebd|semd|bhejo|abhi)\s*)+[.!?]*$',re.I)

def norm(text):
 t=str(text).casefold().replace('give-life','givelife')
 t=re.sub(r'\b(froup|gruo|gruop|goup|grp)\b','group',t)
 return re.sub(r'[^\w\s]',' ',t).strip()

def groups(text):
 t=re.sub(r'\s+',' ',norm(text));matches=[]
 for key,names in ALIASES.items():
  for name in names:
   for m in re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',t):matches.append((m.start(),m.end(),key))
 matches=[m for m in matches if not any(n[0]<=m[0] and n[1]>=m[1] and n[1]-n[0]>m[1]-m[0] for n in matches)]
 keys=list(dict.fromkeys(m[2] for m in matches))
 return keys

def group(text):
 keys=groups(text)
 return keys[0] if len(keys)==1 else None

def control_payload(text):return bool(CONTROL.fullmatch(str(text).strip()))

def parse(text):
 t=str(text).strip();t=re.sub(r'^(?:please|kindly|can you|could you|would you)\s+(?=send|resend|delete|remove|revoke|text|message)', '',t,flags=re.I);low=norm(t);low=re.sub(r'\s+',' ',low)
 if not t:return None
 if re.search(r'exclusive\s+upwork|37\s*(?:member|members)|120363432572916292|120363431093838536',low):return {'kind':'refuse_target'}
 if re.search(r'\b(don t|dont|do not|never|stop|disable|no)\b.*\b(dm|dms|direct messages)\b',low) or low in ('dm off','dms off','auto dms off'):
  return {'kind':'stop_dms'}
 if low in ('hold','wait','hold on','hold everything','stop everything','pause everything') or re.search(r'wrong (?:whatsapp|number)',low):return {'kind':'hold'}
 if low in ('resume','continue','go ahead','connected','connected now','right one connected','release','unhold'):return {'kind':'resume'}
 # A display-name correction changes the greeting, never the destination or whole caption.
 rename=re.fullmatch(r"(?:(his|her|their)\s+name\s+is|(.+?)\s+name\s+is|(?:change|set)\s+(?:his |her |the )?name\s+to)\s+([A-Za-z][A-Za-z '-]{1,35}?)(?:\s+just\s+(?:in\s+(?:msg|message)\s+)?change\s+name)?[.!]?",t,re.I)
 if rename:return {'kind':'dm_name','to':rename[2] or '', 'name':rename[3].strip()}
 if ('2000' in low.replace(' ','') or '2 000' in low) and ('1000' in low.replace(' ','') or '1 000' in low) and re.search(r'\b(first|before|then|order)\b',low) and re.search(r'\b(message|messages|caption|wording|write|show)\b',low):return {'kind':'donation_order'}
 if re.search(r'\b(don t|dont|do not|remove|delete)\b',low) and re.search(r'\b(write|line|wording|words|caption|this much)\b',low) and re.search(r'\b(came|received|arrived)\b',low):return {'kind':'remove_arrival_line'}
 arrival=re.fullmatch(r'(?:came|got|received|recieved|aya|aaya)\s*(?:rs\.?\s*)?(\d[\d,.]*)\s*(k)?|(?:rs\.?\s*)?(\d[\d,.]*)\s*(k)?\s+(?:came|arrived|received|aya)',t,re.I)
 if arrival:
  amount=float((arrival[1] or arrival[3]).replace(',',''))*(1000 if arrival[2] or arrival[4] else 1)
  if amount.is_integer() and amount>=0:return {'kind':'money','amount':int(amount)}
 if re.match(r'^(delete|remove|revoke)\b',low) and re.search(r'\b(message|messages|msg|post|group)\b',low):return {'kind':'delete','target':group(t)}
 # Explicit quoted text is data, even if it contains a command word.
 q=re.match(r'^(?:please\s+)?(?:send|text|message|bhejo)\s+["“\'](.+?)["”\']\s+(?:to|ko|in)\s+(.+)$',t,re.I|re.S)
 if q:return {'kind':'text','text':q[1],'to':q[2].strip(),'literal':True}
 money=re.search(r'(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(k)?\b',t,re.I)
 amount=None
 if money and not re.search(r'(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}',t):
  if re.search(r'\b(left|remaining|remain|baqi|amount|updated|with)\b',low) or re.fullmatch(r'(?:rs\.?\s*)?\d[\d,.]*\s*k?',t,re.I):
   n=float(money[1].replace(',',''))*(1000 if money[2] else 1)
   if n.is_integer() and 0<=n<=10000000:amount=int(n)
 # A negative, a question about delivery, or a schedule must not dispatch now.
 if re.search(r'\b(don t|dont|do not|never|not now|did you|have you|was it|schedule|daily|every day|tomorrow)\b',low):return None
 if re.search(r'\bat\s+\d|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b',t,re.I):return None
 targets=groups(t);target=targets[0] if len(targets)==1 else None
 if SEND.search(t) and len(targets)>1 and not re.search(r'\b(write|draft|compose|create|rewrite|shorten|improve)\b',low):return {'kind':'appeals','targets':targets,'amount':amount}
 if SEND.search(t) and target:
  if re.search(r'\b(write|draft|compose|create|rewrite|shorten|improve)\b',low):return None
  # Ordinary explicit text, e.g. send hi to GiveLife main, remains text.
  m=re.match(r'^(?:please\s+)?(?:send|text|message|bhejo)\s+(.+?)\s+(?:to|ko)\s+(.+)$',t,re.I|re.S)
  if m and not control_payload(m[1]) and group(m[3]):return {'kind':'text','text':m[1].strip(),'to':group(m[3]),'literal':True}
  return {'kind':'appeal','target':target,'amount':amount}
 if (SEND.search(t) or low.startswith('now send') or low in ('again','do it','go','now')) and control_payload(t):return {'kind':'repeat'}
 if amount is not None and not SEND.search(t):return {'kind':'amount','amount':amount}
 m=re.match(r'^(?:please\s+)?(?:send|text|message|bhejo)\s+(.+?)\s+(?:to|ko)\s+(.+)$',t,re.I|re.S)
 if m:
  if control_payload(m[1]) or re.fullmatch(r'(?i)(?:(?:the|full|current|updated|proper|correct|dm|appeal|message|poster|and|with)\s*)+',m[1]):return {'kind':'appeal_to','to':m[2].strip()}
  return {'kind':'text','text':m[1].strip(),'to':m[2].strip(),'literal':True}
 m=re.match(r'^(?:please\s+)?send\s+(.{1,300})$',t,re.I|re.S)
 if m and not re.search(r'\b(dm|dms|donors?|members?|groups?|restart|gap|timer|poster|message|now|and)\b|^(?:to|in|on)\b',m[1],re.I):return {'kind':'text','text':m[1].strip(),'to':None,'literal':True}
 if target and re.sub(r'\b(group|groups|in|to|on)\b','',low).strip() in [norm(a) for a in ALIASES[target]]:return {'kind':'select','target':target}
 return None
