"""Tool permissions derive from current owner text, never retrieved/tool content."""
import re,math
import manual_commands
import timed_tasks
import draft_flow
from state_shapes import history as valid_history

READ={'find_contact','recent_activity','list_rules','search_memory','list_schedules','get_message','app_status'}
SEND={'send_message','send_appeal','send_dm_appeal','dm_list','dm_donors','dm_group'}

def switch_request(text,subject):
 clauses=re.split(r';|\band(?: then)?\b|\bbut\b',owner_text(text),flags=re.I)
 selected=[c for c in clauses if re.search(r'(?i)\b(?:auto|autopilot)\b' if subject=='auto' else r'(?i)\bdms?\b',c)]
 states=set()
 for clause in selected:
  if re.search(r'(?i)\b(on|enable|start)\b',clause):states.add(True)
  if re.search(r'(?i)\b(off|disable|stop)\b',clause):states.add(False)
 return next(iter(states)) if len(states)==1 else None
def smalltalk(text):
 t=re.sub(r'[^\w\s]','',str(text).casefold()).strip()
 return bool(re.fullmatch(r'(?:hi+|hu|hey+|he+l+o+|yo+|salam|assalamualaikum|how (?:are|r) (?:you|u)|how are you doing|hows it going|everything good|good (?:morning|evening|night)|kya haal hai|kya hal hai|sab theek)',t))
CONFIRM_WORDS=frozenset('yes yeah yep yup y ok okay k sure haan han ha ji jee bilkul theek thik hai chalo please plz pls do it go ahead on proceed carry confirm confirmed kar karo kardo krdo den dein de that this same sahi agree fine good correct right'.split())
CONFIRM_CORE=frozenset('yes yeah yep yup y ok okay k sure haan han ha ji jee bilkul theek thik chalo confirm confirmed proceed kar karo kardo krdo sahi agree'.split())|{'do','go','correct','right','fine','good'}
ASKED=re.compile(r"(?i)\?\s*(?:\W*)$|\b(?:shall i|should i|want me to|would you like|do you want|say (?:yes|confirm)|reply (?:yes|confirm)|let me know|which one|which (?:group|dm|donor|message))\b")
def confirmation(text):
 """A bare yes/ok/haan/kar do. It carries no instruction of its own."""
 words=re.findall(r"[a-z]+",str(text).casefold())
 return 0<len(words)<=5 and all(w in CONFIRM_WORDS for w in words) and any(w in CONFIRM_CORE for w in words)
def _substantive(turn):
 value=turn['text'].strip()
 return turn['who']=='you' and len(value)>=8 and not confirmation(value) and not smalltalk(value)
LIST_ITEM=re.compile(r"(?m)^\s*(?:\*\*)?(?:option \s*)?(?P<n>\d{1,2})[.)]?(?:\*\*)?\s*(?P<t>.*)$")
ORDINALS={'first':1,'1st':1,'pehla':1,'pehli':1,'one':1,'second':2,'2nd':2,'doosra':2,'dusra':2,'two':2,'third':3,'3rd':3,'teesra':3,'three':3,'fourth':4,'4th':4,'four':4,'chautha':4,'fifth':5,'five':5}
CHOICE_FILLERS=frozenset('do go with option number no the one ok okay please karo kar choose pick select use wala ye yeh start run idea suggestion pls plz'.split())
def numbered_items(text):
 """Items of a numbered list in an assistant message (the number may sit on its own line)."""
 lines=str(text).split(chr(10));items={}
 for i,line in enumerate(lines):
  m=LIST_ITEM.match(line)
  if not m:continue
  title=m['t'].strip()
  if not title:title=next((x.strip() for x in lines[i+1:i+3] if x.strip() and not LIST_ITEM.match(x)),'')
  if title and int(m['n']) not in items:items[int(m['n'])]=title
 return items
def choice(text,items):
 """"1", "do 2", "first one", "option 3", "pehla": the numbered suggestion the owner picked, else None."""
 words=re.sub(r"[^\w\s]"," ",str(text).casefold()).split()
 if not words or len(words)>5 or len(items)<2:return None
 picks={int(w) for w in words if w.isdigit() and len(w)<=2}|{ORDINALS[w] for w in words if w in ORDINALS}
 if len(picks)!=1:return None
 if [w for w in words if not w.isdigit() and w not in ORDINALS and w not in CHOICE_FILLERS]:return None
 return items.get(next(iter(picks)))
def followup(text,history):
 """Resolve a short reply ("yes", "do it", "kar do", "all groups") against the question it answers.

 The previous owner request supplies the MEANING; the current reply is the owner's confirmation.
 A send is inherited only when the assistant's last turn actually asked about sending, and a reply
 that is not shaped like an answer is never expanded. Returns the text to use for permission checks.
 """
 value=str(text).strip();turns=valid_history(history)
 if turns and turns[-1]['who']=='you' and turns[-1]['text'].strip()==value:turns=turns[:-1]
 plain={'text':value,'inherited':False,'prev':'','asked':''}
 if not value or not turns or turns[-1]['who']=='you':return plain
 last=turns[-1]
 if last['who']=='app' and draft_flow.selected_option(value,valid_history(history)) is None:
  picked=choice(value,numbered_items(last['text']))
  if picked:return {'text':picked,'inherited':True,'prev':picked,'asked':last['text'][-300:]}
 if last['who']!='app' or not ASKED.search(last['text'][-400:]):return plain
 answer=confirmation(value)
 if len(numbered_items(last['text']))>=2 and (answer or re.search(r'\d',value)):return plain # an ambiguous reply to a list of options: the model must ask which one
 if not answer and (len(value.split())>6 or smalltalk(value) or intent(value)['send'] or QUESTION.search(value) or re.search(r'(?i)\b(?:send|post|dm|edit|change|set|delete|add|remove|stop|pause|hold|start|resume)\b',value)):return plain
 prev=next((t['text'].strip() for t in reversed(turns[:-1]) if _substantive(t)),'')
 if not prev or intent(prev)['query']:return plain
 asked_send=bool(re.search(r'(?i)\b(?:send|post|dm|message|share|resend|bhej\w*)\b',last['text']))
 effective=prev if answer else prev+'. '+value
 if intent(effective)['send'] and not asked_send:return plain
 return {'text':effective,'inherited':True,'prev':prev,'asked':last['text'][-300:]}

def variant_request(text):
 """A request to rewrite a pasted message into several versions, not a single draft edit."""
 t=owner_text(text)
 if re.search(r'(?i)\b(?:send|post|dm)\b',t) and not re.search(r'(?i)\bsend\s+(?:me|us)\b',t) and not re.search(r'(?i)\b(?:generate|make|create|write|rewrite|give|show|prepare|produce)\b',t):return False
 return bool(
  re.search(r'(?i)\b(?:generate|make|create|write|rewrite|give|show|prepare|produce)\b.{0,120}\b(?:10|ten|\d{1,2})\b.{0,50}\b(?:versions?|variants?|wordings?|rewrites?)\b',t)
  or re.search(r'(?i)\b(?:10|ten|\d{1,2})\b.{0,40}\b(?:versions?|variants?|wordings?|rewrites?)\b',t))
def owner_text(text):
 text=re.sub(r'```[\s\S]*?```',' [quoted data] ',str(text))
 text=re.sub(r'(?m)^\s*>.*$',' [quoted data] ',text)
 text=re.sub(r'"[^"\n]*"|“[^”\n]*”',' [quoted data] ',text)
 text=re.sub(r"(?<!\w)'[^'\n]+'(?!\w)",' [quoted data] ',text)
 text=re.split(r'(?i)(?:message says|text says|transcript|chat log|conversation log|see fixes in logic|see fn remove|summarize this|analyse this|analyze this)\s*:',text,maxsplit=1)[0]
 return text

QUIET=re.compile(r"(?i)\b(?:quiet|silent|no (?:posting|sending|posts)|don.?t (?:post|send)|nothing (?:posts|sends))\b.*\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:to|till|until|se|-)\s*\d{1,2}")
DELEGATE=re.compile(r"(?i)^\s*(?:please\s+)?(?:tell|ask|remind|let)\s+(?:akhtar|(?:the |my )?team ?mate|my team)\s+(?:to|that)\b")
def intent(text):
 t=owner_text(text)
 query=manual_commands.question_request(t) or bool(re.search(r'(?i)^show (?:me )?(?:what|status)\b',t.strip()))
 # A request to inspect or draft a send is not itself permission to send.
 inspect=bool(re.match(r'(?i)^\s*(?:please\s+)?(?:show|preview|draft|explain|review|summari[sz]e|analy[sz]e|tell me)\b',t))
 negative=bool(re.search(r"(?i)\b(?:don'?t|dont|do not|never|stop)\s+(?:ever\s+)?(?:send|sending|resend|resending|re-send|post|posting|repost|share|sharing|forward|bhejo|bhej|dm|dms)\b|\b(preview only|draft only)\b",t))
 dm_verb=bool(re.match(r'(?i)^\s*dm\s+(?!(?:has|have|had|is|was|looks|needs|should|does|caption|format|structure|name|text|icons|remove|edit|change)\b)\S',t))
 sending=bool(manual_commands.SEND.search(t) or re.search(r'(?i)\b(?:snd|snt|sens|sned|semd|sebd)\b',t) or dm_verb) and not negative and not query and not inspect and not manual_commands.deferred_request(t) and not DELEGATE.match(t)
 if re.search(r'(?i)\bsend\s+(?:me|us)\b.{0,50}\b(?:10|ten|\d{1,2})\b.{0,40}\b(?:versions?|variants?|wordings?)\b',t):sending=False
 # "Send a more emotional message" can request wording. An explicit destination
 # or immediate-send phrase disambiguates it; otherwise only prepare the rewrite.
 if draft_flow.editing_request(t) and re.match(r'(?i)^\s*(?:send|sebd|semd|sned|snd)\s+(?:a\s+)?(?:more|less)\b',t) and not manual_commands.groups(t) and not re.search(r'(?i)\b(?:to|in|now|immediately|asap)\b|(?:\+?92|0)3\d{9}',t):sending=False
 return {'text':t,'send':sending,'query':query,'negative':negative,'batch':sending and bool(re.search(r'(?i)\b(dm|dms|donors?|members?|people|numbers|list)\b',t))}

def literal_text_to_person(text):
 """'send hi to wajdan': those words, to a person (not a group), and not a request to write or style a message."""
 plan=manual_commands.parse(text) or {}
 words=plan.get('text','')
 return plan.get('kind')=='text' and bool(plan.get('to')) and not manual_commands.group(plan['to']) and len(words)<=120 and not re.search(r'(?i)\b(message|caption|dm|poster|wording|version|hook|appeal|emotional|stronger|shorter|longer|draft|format|paragraph)\b',words)

APP_WORDS=re.compile(r"(?i)\b(donor|donors|dm|dms|group|groups|send|sent|post|posts|message|messages|caption|poster|left|came|donat\w*|schedul\w*|auto|autopilot|whatsapp|campaign|yousuf|givelife|main|fiverr|upwork|uet|freelance|hold|resume|stop|pause|batch|important|wording|draft|version|rule|rules|gap|pace|status|report|rs|pkr|amount|balance|money|number|numbers|contact|reply|test)\b")
QUESTION=re.compile(r"(?i)^\s*(?:what|why|how|when|where|who|which|is|are|was|were|do|does|did|can|could|should|would|will|tell me|explain|define|meaning of)\b|\?\s*$")
def off_topic(text):
 """Clearly a general question (health, trivia, jokes): question-shaped, with no app words and no numbers.
 Short follow-ups such as "give me suggestions" are about the work and are never shortened."""
 t=owner_text(text)
 return bool(QUESTION.search(t)) and not APP_WORDS.search(t)
def about_the_work(reply):
 """True when the answer itself talks about the campaign: then it must never be shortened."""
 return bool(APP_WORDS.search(str(reply)))
def brief(reply,limit=320):
 """Off-topic answers stay to one or two short sentences and never tack on campaign status."""
 text=re.split(r"(?im)^\s*(?:meanwhile|by the way|btw|also,? your campaign|your campaign|where things stand|current case|campaign status)\b",str(reply))[0].strip()
 text=re.sub(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+","",text)
 text=re.sub(r"\*\*|__|\*","",text)
 sentences=re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])",re.sub(r"\s*\n+\s*"," ",text))
 out=""
 for s_ in sentences:
  s_=s_.strip()
  if not s_:continue
  if out and (len(out)+len(s_)>limit or out.count(".")+out.count("!")+out.count("?")>=2):break
  out=(out+" "+s_).strip()
 return out or text[:limit]

def task_assignment_only(text):
 """A task description is not permission to carry out that described action."""
 owner=owner_text(text).strip()
 task_only=bool(re.match(
  r'(?i)^(?:in\s+(?:the\s+)?tasks?\b|tasks?\s*[:\-]|'
  r'(?:please\s+)?(?:give|assign|add|create|set)\s+(?:a\s+)?tasks?\b)',owner))
 independent=bool(re.search(
  r'(?i)\b(?:and then|then|also)\s+(?:please\s+)?'
  r'(?:send|post|edit|rewrite|save|update|change|start|stop|schedule)\b',owner))
 return task_only and not independent

def permitted(name,text):
 if name in READ:return True
 if task_assignment_only(text) and name!='team_action':return False
 if name=='donor_action':return bool(re.search(r'(?i)\b(donor|donors|important|donated)\b',owner_text(text)))
 if name=='shortcut_action':return bool(re.search(r'(?i)\b(shortcuts?|when i say|macro)\b',owner_text(text)))
 if name=='team_action':return bool(re.search(r'(?i)\b(team|teammate|team mate|tasks?|kaam|akhtar)\b',owner_text(text)))
 if name=='volunteer_action':return bool(re.search(r'(?i)\bvolunteers?\b',owner_text(text)))
 if name=='case_action':return bool(re.search(r'(?i)\bcases?\b',owner_text(text)))
 if name=='send_text_list':return intent(text)['send'] and len(re.findall(r'(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}',owner_text(text)))>=1
 i=intent(text);t=i['text'];variants=variant_request(t)
 if name=='generate_dm_variants':return variants
 if name in ('set_message','new_wording') and variants:return False
 if name=='hold' and manual_commands.dm_control(t):return False
 if name=='schedule_task':return (timed_tasks.requested(t) or timed_tasks.cancel_request(t)) and not i['query'] and not i['negative']
 if name=='set_quiet_hours' and QUIET.search(owner_text(text)):return True
 if name=='schedule_task' and QUIET.search(owner_text(text)):return False
 if name in SEND|{'autopilot','hold','delete_last_message','set_left','money_came','set_dms','set_pace','set_group_pace','pause_group','resume_group','set_quiet_hours'} and manual_commands.deferred_request(t):return False
 if name in SEND|{'autopilot','hold','resume_group','pause_group'} and timed_tasks.requested(t):return False
 if name in ('send_appeal','send_dm_appeal') and literal_text_to_person(t):return False # "send hi to Ali" is those words only, never the poster and saved appeal
 if name=='dm_donors':return i['send'] and bool(re.search(r'(?i)\bdonors?\b',t))
 if name=='dm_group':return i['send'] and bool(re.search(r'(?i)\b(members?|group)\b',t))
 if name=='dm_list':return i['send'] and bool(re.search(r'(?i)\b(list|numbers?|phones?)\b|(?:\+?92|0)3\d{2}',t))
 if name in SEND:return i['send']
 if i['query']:return False
 verbs={'delete_last_message':'delete|remove|revoke','autopilot':'turn|start|stop|enable|disable|change','hold':'hold|pause|stop|resume|continue|unhold','set_dms':'start|stop|enable|disable|change|turn','set_left':'set|change|update|record','money_came':'record|subtract|deduct|change','set_group_pace':'set|change|speed|slow','set_pace':'set|change|speed|slow','pause_group':'pause|stop','resume_group':'resume|start','set_message':'edit|change|rewrite|remove|replace|save'}
 if name in verbs and re.search(r"(?i)\b(?:don'?t|dont|do not|never)\s+(?:"+verbs[name]+r')\b',t):return False
 inspect=bool(re.match(r'(?i)^\s*(?:please\s+)?(?:show|preview|explain|review|summari[sz]e|analy[sz]e|tell me)\b',t))
 if inspect and name not in ('set_message','prepare_dm'):return False
 if name=='delete_last_message':return bool(re.search(r'(?i)\b(delete|remove|revoke)\b',t)) and not re.search(r"(?i)\b(dont|don't|do not|never)\b",t)
 if name=='hold':return bool(re.search(r'(?i)\b(hold|wait|pause|stop|resume|continue|unhold|wrong whatsapp|connected now)\b',t))
 if name=='autopilot':return bool(re.search(r'(?i)\b(?:auto|autopilot)\b',t) and re.search(r'(?i)\b(?:on|off|enable|disable|start|restart|stop|turn|switch|resume|pause)\b',t))
 if name in ('remember','add_rule'):return bool(re.search(r'(?i)\b(remember|always|never|from now|in future|daily|every|quiet|pause|pace|slow|fast|yaad rakho)\b',t))
 if name=='delete_rule':return bool(re.search(r'(?i)\b(forget|delete|remove)\b.*\b(rule|memory|preference)\b',t))
 if name in ('set_left','money_came'):
  return any((p.get('kind')=='money')==(name=='money_came') for p in financial_plans(t))
 if name in ('set_group_pace','set_pace','pause_group','resume_group','set_quiet_hours','set_dms'):return bool(re.search(r'(?i)\b(every|after|pace|speed|slow|fast|pause|resume|quiet|enable|disable|start|stop|on|off)\b',t))
 if name=='edit_dm_name':return bool(re.search(r'(?i)\b(name|call him|call her|greeting)\b',t))
 # A general adjective like "new" in "find new volunteers" cannot authorize
 # a caption edit. Require a genuinely message-directed drafting instruction.
 if name=='set_message':
  return bool(draft_flow.editing_request(t)
   or re.search(r'(?i)\b(?:fix|correct|adjust)\b.{0,70}\b(?:paragraph|line|dm|group|caption|draft|message|wording)\b',t)
   or re.search(r'(?i)\b(?:save|write|create|make|prepare|draft|compose)\b.{0,100}\b(?:caption|message|draft|wording|appeal)\b',t))
 if name=='new_wording':
  if draft_flow.editing_request(t) or re.search(r'(?i)\b(rewrite|shorten|shorter|brief|bold|italic|remove|replace|edit|format)\b',t):return False
  return bool(re.search(r'(?i)\b(?:fresh|new|next|rotate|regenerate|another|different)\b.{0,55}\b(?:caption|message|draft|hook|wording|variant)\b',t)
    or re.search(r'(?i)\b(?:caption|message|draft|hook|wording|variant)\b.{0,55}\b(?:fresh|new|next|rotate|regenerate|another|different)\b',t))
 if name=='prepare_dm':
  return bool(re.search(r'(?i)\b(?:prepare|preview|show|draft|write|make)\b.{0,60}\b(?:dm|direct message|donor message)\b',t))
 return False

def financial_plans(text):
 out=[]
 for part in re.split(r';|\band then\b|\bthen\b|\s+and\s+',owner_text(text),flags=re.I):
  p=manual_commands.parse(part.strip()) or {}
  if p.get('kind') in ('amount','money') or p.get('amount') is not None:out.append(p)
 return out

def validate_args(schema,args,path='arguments'):
 if not isinstance(args,dict):raise ValueError('Tool arguments must be a JSON object.')
 def check(s,v,p):
  kind=s.get('type');types={'string':str,'object':dict,'array':list,'boolean':bool,'integer':int,'number':(int,float)}
  if kind in types and (not isinstance(v,types[kind]) or kind in ('number','integer') and isinstance(v,bool)):raise ValueError(p+' has the wrong type.')
  if 'enum' in s and v not in s['enum']:raise ValueError(p+' is not an allowed value.')
  if kind in ('number','integer') and not math.isfinite(v):raise ValueError(p+' must be finite.')
  if isinstance(v,str) and len(v)>12000:raise ValueError(p+' is too long.')
  if kind=='object':
   props=s.get('properties',{})
   if set(s.get('required',[]))-set(v):raise ValueError(p+' is missing required fields.')
   if s.get('additionalProperties') is False and set(v)-set(props):raise ValueError(p+' has unexpected fields.')
   for k,x in v.items():
    if k in props:check(props[k],x,p+'.'+k)
  if kind=='array':
   if len(v)>100:raise ValueError(p+' has too many items.')
   for j,x in enumerate(v):check(s.get('items',{}),x,p+'['+str(j)+']')
 check(schema,args,path)


