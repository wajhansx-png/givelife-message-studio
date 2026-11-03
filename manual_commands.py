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
 'all':('all 6 groups','all six groups','all the groups','every group','sab groups','sabhi groups','sare groups','saare groups','all groups','all'),
 'test':('givelife test','give life test','test group','test')}
_SEND_RX=re.compile(r'\b(send|resend|post|share|bhejo|bhej|daalo|dalo|sebd|semd)\b|بھیج|ارسال',re.I)
# "the post is old", "good post", "post status" use the word as a noun: they are not a command to send.
NOUN_POST=re.compile(r'(?i)\b(?:the|a|an|this|that|my|our|your|good|bad|nice|old|new|last|first|next|group|main|each|every|his|her|their|latest|current|saved|daily|morning|evening|same|great|late|failed|another)\s+(?:posts?|shares?|sends?)\b|\b(?:posts?|shares?|sends?)\s+(?:count|status|log|history|button|time|date)\b|\b(?:posts?|shares?)\s+(?:is|was|are|were|has|had|failed|status|count|looks|mortem|price|time|date|limit|history|log|numbers?|empty)\b')
class _SendPattern:
 def search(self,text,*args):return _SEND_RX.search(NOUN_POST.sub(' ',str(text)),*args)
 pattern=_SEND_RX.pattern
SEND=_SendPattern()
CONTROL=re.compile(r'^(?:(?:man|please|bhai|bro|yaar|now|abhi|send|resend|post|it|this|that|again|do|go|and|restart|reset|the|gap|timer|message|msg|poster|image|picture|appeal|with|updated|amount|right|away|asap|immediately|fast|quick|only|current|latest|hadith|hadees|haditg|caption|draft|full|proper|correct|sebd|semd|bhejo|abhi|saved|post|posts|new|fresh|next|same|usual|regular|normal|standard|ready|final)(?:\s+|(?=[.!?]*$)))+[.!?]*$',re.I)

def norm(text):
 t=str(text).casefold().replace('give-life','givelife')
 t=re.sub(r'\b(?:guvelife|givelufe|givlife|giveilfe)\b','givelife',t)
 t=re.sub(r'\b(froup|gruo|gruop|goup|grp)\b','group',t)
 t=re.sub(r'\b(?:fiver|fivver|fivrr|fiverrr|fiverr)\b','fiverr',t)
 t=re.sub(r'\b(?:upwrk|upwok|uptwork|upwoek)\b','upwork',t)
 t=re.sub(r'\b(evv?erything|evrything|everythng|everthing)\b','everything',t)
 return re.sub(r'[^\w\s]',' ',t).strip()

def _group_mentions(text):
 t=re.sub(r'\s+',' ',norm(text));matches=[]
 for key,names in ALIASES.items():
  for name in names:
   for m in re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',t):matches.append((m.start(),m.end(),key))
 matches=[m for m in matches if not any(n[0]<=m[0] and n[1]>=m[1] and n[1]-n[0]>m[1]-m[0] for n in matches)]
 keys=list(dict.fromkeys(m[2] for m in matches))
 return keys

GROUP_EXCLUSION=re.compile(r'(?i)\b(?:except(?: for)?|excluding|but not|instead of|rather than|in place of|(?:but|without|skip(?:ping)?|other than|apart from|besides|leave out|leaving out)(?=(?: the)?\s+(?:upwork|fiverr|uet|main|test|community|top|give|free|all))|not(?: to)?)\s+')

# Roman Urdu exclusions: "siwaye upwork" before the group, "upwork ke ilawa" / "upwork chhor ke" after it.
URDU_EXCLUDE_PRE=re.compile(r'(?i)\b(?:siwaye|siwae|siwai|sivaye|siwa|ilawa|alawa)\b\s+')
URDU_EXCLUDE_POST=re.compile(r'(?i)\b(\w+(?:\s+(?:group|grp|wala|wale|ko))*)\s+(?:(?:ke|kay|k)\s+(?:ilawa|alawa|siwa|siwaye|siwae)|(?:chh?or+|chh?od)\s*(?:ke|kay|kar|kr|k)|nikal\s*(?:ke|kar|kr|k))\b')
def english_exclusion(text):
 t=str(text);post=URDU_EXCLUDE_POST.search(t)
 if post and _group_mentions(post[1]):return (t[:post.start()]+' '+t[post.end():]).strip()+' except '+post[1]
 return URDU_EXCLUDE_PRE.sub('except ',t)

def has_group_exclusion(text):
 text=english_exclusion(text);match=GROUP_EXCLUSION.search(str(text))
 return bool(match and _group_mentions(str(text)[:match.start()]))

def groups(text):
 """Resolve explicit exclusions before any aggregate target is dispatched."""
 t=english_exclusion(text)
 exclusion=GROUP_EXCLUSION.search(t)
 if not exclusion:return _group_mentions(t)
 included=_group_mentions(t[:exclusion.start()]);excluded=_group_mentions(t[exclusion.end():])
 if not included:return [] # "send except upwork" names no audience: ask, never send to the excluded group
 if not excluded:return [] # Missing exclusion needs clarification, never an aggregate send.
 production=['main','community','fiverr','upwork','uet','toprated']
 def expand(keys):
  return list(dict.fromkeys(k for key in keys for k in (production if key=='all' else production[1:] if key=='free' else [key])))
 blocked=set(expand(excluded))
 return [key for key in expand(included) if key not in blocked]

def group(text):
 keys=groups(text)
 return keys[0] if len(keys)==1 else None

def control_payload(text):
 text=re.sub(r'(?i)\b(?:dm|a|an|donation|case|urgent)\b','message',str(text))
 if balance_amount(text) is not None:text=re.sub(r'(?i)(?:rs\.?\s*)?\d[\d,]*(?:\.\d+)?\s*k?(?:\s*(?:left|remaining))?','updated amount',text)
 return bool(CONTROL.fullmatch(text.strip()))

def outside_literals(text):
 return re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]+\'(?!\w)',' [text] ',str(text))

def question_request(text):
 if re.search(r'(?i)(?:[;!?]\s*|\band then\s+)(?:please\s+)?(?:send|resend|post|set|change|write|stop|pause|resume)\b',outside_literals(text)):return False
 if re.search(r'\?\s*$',outside_literals(text)) or re.match(r'(?i)^\s*(?:kya|kitn[aei]|kab|kyun|kyon|kaise|kaun|kon|kahan|kidhar|کیا|کتنے|کب)(?:\b|\s)',outside_literals(text)):return True
 return bool(re.match(r'(?i)^\s*(?:what|why|how|when|where|who|did|have|has|was|were|is(?!\s+(?:message|msg|caption|dm|ko|line|ka|ke|mein|me)\b)|are|should|can i|could i|would it|if i|suppose|imagine)\b',outside_literals(text)) or re.match(r'(?i)^\s*(?:(?:can|could|would|will) you\s+)?(?:please\s+)?(?:tell|show|let) me\s+(?:if|whether|when|why|how|what)\b',outside_literals(text)))

URDU_NO=re.compile(r'(?i)(?:^|\s)(?:مت|نہیں|نہ)(?:$|\s)|\b(?:mat|nahi|nahin|nhi|mt)\b|\bno\s+(?:need\s+to\s+)?(?:send|post|share|dm|sending|posting)\b')
def negated_send(text):
 """"main me mat bhejo", "post nahi karna", "no send to main": a refusal that uses a send word."""
 t=outside_literals(text);return bool(SEND.search(t) and URDU_NO.search(t))

def deferred_request(text):
 return bool(re.search(r'(?i)\b(?:only after|after i (?:confirm|say|approve|check)|pehle\b.*\b(?:phir|then)|if|unless|once (?:he|she|they|it|i|you|we|the|a|amount|money|donation|someone)|until|when|agar|jab|jaise hi|warna|later|not now|tomorrow|tonight|kal|parso|baje|subah|shaam|raat ko|aaj raat|dopahar|this (?:morning|afternoon|evening)|in the (?:morning|evening)|baad mein|baad me|thori der baad|thodi der baad|\d+(?:\.?\d+)? *(?:min\w*|ghant\w*|hours?|hrs?) *(?:ke )?baad|(?:ek|aik|do|teen|aadhe) ghant\w* (?:ke )?baad|(?:in|after) (?:a|an|one|half an|a couple of|couple of|two|three) (?:hours?|hrs?|mins?|minutes?|days?)|(?:in|after) half an hour|next (?:day|week|month)|in\s+\d+(?:\.\d+)?\s*(?:min(?:ute)?s?|hours?|days?)|after\s+\d+(?:\.\d+)?\s*(?:min(?:ute)?s?|hours?|days?))\b|\bat\s+\d|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b',outside_literals(text)))

MULT={'k':1000,'hazar':1000,'hazaar':1000,'hajar':1000,'hazr':1000,'thousand':1000,'lakh':100000,'lac':100000,'lakhs':100000}
UNIT=r'(k|hazar|hazaar|hajar|hazr|thousand|lakhs?|lac)'
def _times(unit):return MULT.get((unit or '').casefold(),1)

def balance_amount(text,allow_with=True):
 """Use an amount bound to balance wording, never a year/group count/phone."""
 t=outside_literals(text)
 # "remaining 5000 is wrong" complains about a number; it never sets it.
 if re.search(r'(?i)\d[0-9,]*\s*(?:k|hazar|lakh|lac)?\s+(?:left |remaining |baqi |bacha )?(?:is |was |looks |seems |hai |tha )?(?:wrong|incorrect|galat|not correct|not right|old|outdated)\b',t):return None
 number=r'(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*'+UNIT+r'?(?!\w)'
 patterns=[number+r'\s*(?:is\s+)?(?:left|remaining|remain|baqi|baki|bacha|bache|bachey|bachi|bachay|bacha hai|rehte|reh gaye)\b',
           r'\b(?:remaining(?:\s+amount)?|amount(?:\s+(?:left|remaining))?|balance|baqi|(?:bache|bachey|bachay|bacha)(?:\s+(?:hain|hai))?)\s*(?:is|to|=|:)?\s*(?:rs\.?\s*)?'+number+r'(?!\s*(?:people|groups?|members?|donors?|dms?|messages?|msgs?|contacts?|numbers?|times?|days?|hours?|hrs?|minutes?|mins?|lines?|words?|versions?))',
           r'\bleft\s*(?:is|=|:)?\s*(?:rs\.?\s*)?(?=\d[\d,]*\s*(?:k|hazar|hazaar|thousand|lakh|lac)\b|\d{3,})'+number+r'(?!\s*(?:people|groups?|members?|minutes?|hours?|messages?|dms?|donors?|times?))',
           *([r'\bwith\s+(?:rs\.?\s*)?'+number+r'(?!\s*(?:people|groups?|members?|minutes?|mins?|mnts?|mints?|hours?|hrs?|secs?|seconds?|days?|donors?|dms?|messages?|msgs?|times?|lines?|words?|versions?|contacts?|numbers?|gap|rest|delay|break|batch\w*))(?!\s*(?:\w+\s+)?(?:gap|rest|delay|break)\b)'] if allow_with else [])]
 candidates=[]
 for pattern in patterns:
  for m in re.finditer(pattern,t,re.I):
   n=float(m[1].replace(',',''))*_times(m[2])
   # A bare small number ("20 left in the batch") is a count, never rupees.
   if n<100 and not m[2] and not re.search(r'(?i)rs\.?',m[0]) and not re.search(r'(?i)\brs\.?\s*$',t[:m.start()]):continue
   if n.is_integer() and 0<=n<=10000000:candidates.append(int(n))
 raw=re.fullmatch(r'(?:rs\.?\s*)?(\d[\d,]*(?:\.\d+)?)\s*'+UNIT+r'?',t.strip(),re.I)
 if raw:
  n=float(raw[1].replace(',',''))*_times(raw[2])
  if n.is_integer() and 0<=n<=10000000 and (n>=100 or raw[2] or re.match(r'(?i)rs\.?',t.strip())):candidates.append(int(n))
 if len(set(candidates))>1:raise ValueError('More than one remaining amount was given. Tell me the single correct balance; nothing was changed or sent.')
 return candidates[0] if candidates else None

def dm_control(text):
 t=norm(text);t=re.sub(r'\bdm\s+s\b','dms',t)
 if not re.search(r'\b(dms?|direct messages|personal messages|private messages|donor messages)\b',t):return None
 if re.search(r'\b(don t|dont|do not|never)\s+(stop|pause|hold|resume|start)\b',t) or URDU_NO.search(t):return None
 # "dm poster off" / "dm without poster" changes the poster, it does not stop the DMs.
 if re.search(r'\b(poster|picture|image|pic)\b',t) and re.search(r'\b(on|off|with|without|no|enable|disable|remove)\b',t) and not re.search(r'\b(hold|pause|stop|resume)\b',t):return None
 if re.search(r'\b(and|plus|also|both)\b.*\b(groups?|posts?|everything)\b',t) and not re.search(r'\b(keep|continue|unchanged|running|unaffected)\b',t):return None
 if re.search(r'\b(hold|pause|stop|disable|off|band)\b',t):return 'stop_dms'
 if re.search(r'\b(resume|unhold|enable|restart|chalu|shuru|dobara)\b',t):return 'resume_dms'
 return None

def parse(text):
 t=str(text).strip();t=re.sub(r'^(?:please|kindly|can you|could you|would you)\s+(?=(?:send|resend|delete|remove|revoke|text|message)\s+\S)', '',t,flags=re.I);low=norm(t);low=re.sub(r'\s+',' ',low)
 if not t:return None
 if re.search(r'exclusive\s+upwork|37\s*(?:member|members)|120363432572916292|120363431093838536',low):return {'kind':'refuse_target'}
 if question_request(t) or deferred_request(t) or negated_send(t):return None
 control=dm_control(t)
 if control:return {'kind':control}
 if re.search(r'\b(hold|pause|stop)\b',low) and re.search(r'\bdms?\b',low) and re.search(r'\b(and|both|also|plus)\b.*\b(groups?|posts?)\b',low):return {'kind':'hold'}
 if re.search(r"(?i)\b(?:don'?t|dont|do not|never)\s+(?:stop|hold|disable|pause|delete|remove|revoke|change|set|record)\b",t):return None
 if low in ('update','status','report','whats update','what s update','whats upadte','what s upadte','what is the update','nothing sent yet man','nothing sent yet') or re.search(r'\b(freelance|freelamce)\b.*\b(update|rules)\b|\b(update|rules)\b.*\b(freelance|freelamce)\b',low):return {'kind':'status','freelance':bool(re.search(r'freela',low))}
 if re.search(r'\b(fast|faster|slow|slower)\b',low) and re.search(r'\b(send|post|pace|speed|posting|sending)\b',low) and not re.search(r'\b(now|right away|immediately|asap)\b',low) and not re.match(r'(?:send|text|message)\s+.+?\s+(?:to|ko)\s+.+',low):return None # explicit text recipients are resolved below
 if re.search(r'exclusive\s+upwork|37\s*(?:member|members)|120363432572916292|120363431093838536',low):return {'kind':'refuse_target'}
 if re.search(r'\b(don t|dont|do not|never|stop|disable|no)\b.*\b(dm|dms|direct messages)\b',low) or low in ('dm off','dms off','auto dms off'):
  return {'kind':'stop_dms'}
 if low in ('hold','wait','hold on','hold everything','stop everything','pause everything','stop','stop it','stop all','stop now','stop please','pause','ruk','ruk jao','ruko','rok do','rok','band karo','band kar do','bas','stop sending','stop posting','stop the sending','rukk jao','ruk jao ji','sending band karo','posting band karo','sab band karo','sab rok do') or re.search(r'wrong (?:whatsapp|number)',low):return {'kind':'hold'}
 if low in ('resume','continue','go ahead','connected','connected now','right one connected','release','unhold','resume everything','resume all','resume sending','resume posting','continue sending','continue posting','start sending','start posting','chalu karo','chalu kar do','shuru karo','phir chalu karo'):return {'kind':'resume'}
 if re.search(r'\b(?:every|each|after)\s+\d+\s*(?:min|mnt|mint|hour)',low):return None
 # While chatting by plain text: "his name is Wajdan say name hi bro" / "say hi bro" continue that chat.
 say=re.fullmatch(r"(?:(?:his|her|their)\s+name\s+is\s+([A-Za-z][A-Za-z'-]{1,25})\s*[,.]?\s*(?:and\s+|then\s+)?)?(?:say|tell\s+(?:him|her|them))\s+(?:name\s+)?(.{1,160})",t,re.I|re.S)
 if say and not re.search(r'(?i)\b(message|caption|dm|poster|wording|line|lines|version|variant|hook|post|appeal|paragraph|greeting|draft|format)\b',say[2]):return {'kind':'say','name':say[1] or '','text':say[2].strip()}
 # A display-name correction changes the greeting, never the destination or whole caption.
 rename=re.fullmatch(r"(?:(his|her|their)\s+name\s+is|(.+?)\s+name\s+is|(?:change|set)\s+(?:his |her |the )?name\s+to)\s+([A-Za-z][A-Za-z '-]{1,35}?)(?:\s+just\s+(?:in\s+(?:msg|message)\s+)?change\s+name)?[.!]?",t,re.I)
 if rename:return {'kind':'dm_name','to':rename[2] or '', 'name':rename[3].strip()}
 if ('2000' in low.replace(' ','') or '2 000' in low) and ('1000' in low.replace(' ','') or '1 000' in low) and re.search(r'\b(first|before|then|order)\b',low) and re.search(r'\b(message|messages|caption|wording|write|show)\b',low):return {'kind':'donation_order'}
 if re.search(r'\b(don t|dont|do not|remove|delete)\b',low) and re.search(r'\b(write|line|wording|words|caption|this much)\b',low) and re.search(r'\b(came|received|arrived)\b',low):return {'kind':'remove_arrival_line'}
 arrival=re.fullmatch(r'(?:(?:someone|somebody|a donor|donor|he|she|they)\s+(?:sent|gave|paid|donated)|donation(?:\s+of)?|donated|came|got|received|recieved|aya|aaya|aaye|aye|ayi|aayi|mila|mile|(?:paise|paisay|rupay|rupees?)(?:\s+(?:aya|aaya|aaye|aye|mila|mile|aayi|ayi))?)\s*(?:rs\.?\s*)?(\d[\d,.]*)\s*'+UNIT+r'?(?:\s+(?:came in|came|received|donated|aya|aaya|aaye|aye|mila|mile))?|(?:rs\.?\s*)?(\d[\d,.]*)\s*'+UNIT+r'?\s+(?:came in|came|arrived|received|donated|aya|aaya|aye|aaye|ayi|aayi|mila|mile|mil gaye|mil gaya)(?:\s+(?:hain|hai|hue|huay|ho gaye|ho gaya))?',t,re.I)
 if arrival:
  amount=float((arrival[1] or arrival[3]).replace(',',''))*_times(arrival[2] or arrival[4])
  if amount<100 and not (arrival[2] or arrival[4]) and not re.search(r'(?i)\brs\.?',t):return None # "3 came" is a head-count, not rupees
  if amount.is_integer() and amount>=0:return {'kind':'money','amount':int(amount)}
 if re.match(r'^(delete|remove|revoke)\b',low) and not URDU_NO.search(low) and re.search(r'\b(message|messages|msg|post|group)\b',low):return {'kind':'delete','target':group(t)}
 # Explicit quoted text is data, even if it contains a command word.
 q=re.match(r'^(?:please\s+)?(?:send|text|message|bhejo)\s+["“\'](.+?)["”\']\s+(?:to|ko|in)\s+(.+)$',t,re.I|re.S)
 if q:return {'kind':'text','text':q[1],'to':re.sub(r'(?i)\s+(?:fast|quickly|asap|immediately|right now)\s*[!.]*$', '', q[2].strip()).strip(),'literal':True}
 amount=balance_amount(t)
 lead=re.fullmatch(r'(?:now|ab|abhi|only|just|total|so)\s+(.+)',t,re.I)
 if amount is None and lead and not SEND.search(t):amount=balance_amount(lead[1])
 # A trailing speed word does not belong to the recipient's name.
 def recipient(v):
  return re.sub(r'(?i)\s+(?:fast|quickly|asap|immediately|right now)\s*[!.]*$', '', str(v).strip()).strip()
 # "send the same thing to fiverr" points back at an earlier message; the words are not the text to post.
 def back_reference(v):
  return bool(re.fullmatch(r'(?i)(?:the\s+)?(?:same|same\s+(?:thing|one|message|msg|text|post|again)|what\s+(?:you|i|we)\s+(?:sent|posted|wrote|said)(?:\s+(?:to|in)\s+.+?)?|(?:the\s+)?(?:last|previous|earlier|old)\s+(?:one|message|msg|text|post)|that\s+(?:one|message|msg|text|post)|this\s+(?:one))',str(v).strip()))
 explicit_ref=re.match(r'^(?:please\s+)?(?:send|resend|text|message|bhejo|forward|share)\s+(.+?)\s+(?:to|ko|in)\s+(.+)$',t,re.I|re.S)
 if explicit_ref and back_reference(explicit_ref[1]):return None
 # Resolve a literal payload and its destination before scanning aliases inside it.
 explicit=re.match(r'^(?:please\s+)?(?:send|resend|text|message|bhejo)\s+(.+?)\s+(?:to|ko)\s+(.+)$',t,re.I|re.S)
 payload=re.sub(r'(?i)(?:rs\.?\s*)?\d[\d,]*(?:\.\d+)?\s*k?','',explicit[1]) if explicit and amount is not None else explicit[1] if explicit else ''
 if explicit and not control_payload(payload):
  return {'kind':'text','text':explicit[1].strip(),'to':group(recipient(explicit[2])) or recipient(explicit[2]),'literal':True}
 # A negative, a question about delivery, or a schedule must not dispatch now.
 if re.search(r'\b(don t|dont|do not|never|not now|did you|have you|was it|schedule|daily|every day|tomorrow)\b',low):return None
 if re.search(r'\bat\s+\d|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b',t,re.I):return None
 phone_text=re.fullmatch(r'((?:\+?92|0092|0)?3\d{2}[\s-]?\d{7})\s+(?:send|text|message)\s+(.+)',t,re.I|re.S)
 if phone_text and not control_payload(phone_text[2]):return {'kind':'text','to':phone_text[1],'text':phone_text[2],'literal':True}
 targets=groups(t);target=targets[0] if len(targets)==1 else None
 if len(targets)>1 and re.search(r'\b(or|either|whichever|ya)\b',low) and not re.search(r'\b(and|both|plus|aur)\b',low):return None # "main or fiverr" is a choice to confirm, not both
 if target and SEND.search(t) and re.search(r':\s*\S',t) and not re.search(r'^[^:]*["“]',t):return None # "post update in main: case completed" carries its own words, never the saved appeal
 if len(targets)>1 and re.search(r'\b(already|got it|has it|is done|are done|received it)\b',low):return None # "main got it already, now send fiverr": let context decide which group is new
 if SEND.search(t) and has_group_exclusion(t) and not targets:return {'kind':'no_groups'}
 if SEND.search(t) and len(targets)>1 and not re.search(r'\b(write|draft|compose|create|rewrite|shorten|improve)\b',low):return {'kind':'appeals','targets':targets,'amount':amount}
 if SEND.search(t) and target:
  if re.search(r'\b(write|draft|compose|create|rewrite|shorten|improve)\b',low):return None
  # Ordinary explicit text, e.g. send hi to GiveLife main, remains text.
  m=re.match(r'^(?:please\s+)?(?:send|text|message|bhejo)\s+(.+?)\s+(?:to|ko|in)\s+(.+)$',t,re.I|re.S)
  if m and re.search(r'(?i)\s+only\s+',m[2]):m=re.match(r'^(?:send|text|message)\s+(.+?)\s+(?:to|in)\s+(.+?)\s+only\s+.+$',t,re.I|re.S)
  if m and not control_payload(m[1]) and group(m[2]):return {'kind':'text','text':m[1].strip(),'to':group(m[2]),'literal':True}
  return {'kind':'appeal','target':target,'amount':amount}
 if (SEND.search(t) or low.startswith('now send') or low in ('again','do it','go','now','once more','one more time','do it again','repeat','repeat it','send once more','dobara','dubara','phir se','phir se bhejo','dobara bhejo','phir bhejo','dobara bhej do','phir se bhej do','same again','send same again','send it again','send again please','again please')) and control_payload(t) or low in ('once more','one more time','do it again','repeat','repeat it','dobara','dubara','phir se','phir bhejo','phir se bhejo','dobara bhejo','dobara bhej do','phir se bhej do','same again','send same again','send it again','send again please','again please'):return {'kind':'repeat'}
 if amount is not None and not SEND.search(t):return {'kind':'amount','amount':amount}
 m=re.match(r'^(?:please\s+)?(?:send|text|message|bhejo)\s+(.+?)\s+(?:to|ko)\s+(.+)$',t,re.I|re.S)
 if m:
  if control_payload(m[1]) or re.fullmatch(r'(?i)(?:(?:the|full|current|updated|proper|correct|dm|appeal|message|poster|and|with)\s*)+',m[1]):return {'kind':'appeal_to','to':m[2].strip()}
  return {'kind':'text','text':m[1].strip(),'to':m[2].strip(),'literal':True}
 # Unqualified "send jr account" needs contact understanding, never send those words literally.
 # Custom text remains explicit via send <text> to <recipient>, or the assistant with conversation context.
 if target and re.sub(r'\b(group|groups|in|to|on)\b','',low).strip() in [norm(a) for a in ALIASES[target]]:return {'kind':'select','target':target}
 return None

