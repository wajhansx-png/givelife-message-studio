"""Tool permissions derive from current owner text, never retrieved/tool content."""
import re,math
import manual_commands
import timed_tasks
import draft_flow

READ={'find_contact','recent_activity','list_rules','search_memory','list_schedules','get_message'}
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
def owner_text(text):
 text=re.sub(r'```[\s\S]*?```',' [quoted data] ',str(text))
 text=re.sub(r'(?m)^\s*>.*$',' [quoted data] ',text)
 text=re.sub(r'"[^"\n]*"|“[^”\n]*”',' [quoted data] ',text)
 text=re.sub(r"(?<!\w)'[^'\n]+'(?!\w)",' [quoted data] ',text)
 text=re.split(r'(?i)(?:message says|text says|transcript|chat log|conversation log|see fixes in logic|see fn remove|summarize this|analyse this|analyze this)\s*:',text,maxsplit=1)[0]
 return text

def intent(text):
 t=owner_text(text);low=manual_commands.norm(t)
 query=manual_commands.question_request(t) or bool(re.search(r'(?i)^show (?:me )?(?:what|status)\b',t.strip()))
 # A request to inspect or draft a send is not itself permission to send.
 inspect=bool(re.match(r'(?i)^\s*(?:please\s+)?(?:show|preview|draft|explain|review|summari[sz]e|analy[sz]e|tell me)\b',t))
 negative=bool(re.search(r"(?i)\b(?:don'?t|dont|do not|never|stop)\s+(?:ever\s+)?(?:send|sending|post|posting|share|sharing|dm)\b|\b(preview only|draft only)\b",t))
 dm_verb=bool(re.match(r'(?i)^\s*dm\s+(?!(?:has|have|had|is|was|looks|needs|should|does|caption|format|structure|name|text|icons|remove|edit|change)\b)\S',t))
 sending=bool(manual_commands.SEND.search(t) or re.search(r'(?i)\b(?:snd|snt|sens|sned|semd|sebd)\b',t) or dm_verb) and not negative and not query and not inspect and not manual_commands.deferred_request(t)
 # "Send a more emotional message" can request wording. An explicit destination
 # or immediate-send phrase disambiguates it; otherwise only prepare the rewrite.
 if draft_flow.editing_request(t) and re.match(r'(?i)^\s*(?:send|sebd|semd|sned|snd)\s+(?:a\s+)?(?:more|less)\b',t) and not manual_commands.groups(t) and not re.search(r'(?i)\b(?:to|in|now|immediately|asap)\b|(?:\+?92|0)3\d{9}',t):sending=False
 return {'text':t,'send':sending,'query':query,'negative':negative,'batch':sending and bool(re.search(r'(?i)\b(dm|dms|donors?|members?|people|numbers|list)\b',t))}

def permitted(name,text):
 if name in READ:return True
 if name=='donor_action':return bool(re.search(r'(?i)\b(donor|donors|important|donated)\b',owner_text(text)))
 i=intent(text);t=i['text']
 if name=='hold' and manual_commands.dm_control(t):return False
 if name=='schedule_task':return (timed_tasks.requested(t) or timed_tasks.cancel_request(t)) and not i['query'] and not i['negative']
 if name in SEND|{'autopilot','hold','delete_last_message','set_left','money_came','set_dms','set_pace','set_group_pace','pause_group','resume_group','set_quiet_hours'} and manual_commands.deferred_request(t):return False
 if name in SEND|{'autopilot','hold','resume_group','pause_group'} and timed_tasks.requested(t):return False
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
 if name=='autopilot':return bool(re.search(r'(?i)\b(auto|autopilot)\b.*\b(on|off|enable|disable|start|stop)\b|\b(enable|disable|start|stop)\b.*\b(auto|autopilot)\b',t))
 if name in ('remember','add_rule'):return bool(re.search(r'(?i)\b(remember|always|never|from now|in future|daily|every|quiet|pause|pace|slow|fast|yaad rakho)\b',t))
 if name=='delete_rule':return bool(re.search(r'(?i)\b(forget|delete|remove)\b.*\b(rule|memory|preference)\b',t))
 if name in ('set_left','money_came'):
  return any((p.get('kind')=='money')==(name=='money_came') for p in financial_plans(t))
 if name in ('set_group_pace','set_pace','pause_group','resume_group','set_quiet_hours','set_dms'):return bool(re.search(r'(?i)\b(every|after|pace|speed|slow|fast|pause|resume|quiet|enable|disable|start|stop|on|off)\b',t))
 if name=='edit_dm_name':return bool(re.search(r'(?i)\b(name|call him|call her|greeting)\b',t))
 if name=='set_message' and draft_flow.editing_request(t):return True
 if name=='new_wording' and draft_flow.editing_request(t):return False
 if name=='new_wording' and re.search(r'(?i)\b(rewrite|shorten|shorter|brief|bold|italic|remove|replace|edit|format)\b',t):return False
 if name=='new_wording':return bool(re.search(r'(?i)\b(fresh|hook|new|rotate|regenerate|next|wording|variant)\b',t)) or i['send']
 if name in ('set_message','new_wording','prepare_dm'):return bool(re.search(r'(?i)\b(edit|change|write|rewrite|draft|prepare|preview|fill|wording|message|caption|structure|format|bold|italic|shorten|improve|new|correct|remove)\b',t)) or i['send']
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


