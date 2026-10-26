"""Tool permissions derive from current owner text, never retrieved/tool content."""
import re,math
import manual_commands

READ={'find_contact','recent_activity','list_rules','search_memory'}
SEND={'send_message','send_appeal','send_dm_appeal','dm_list','dm_donors','dm_group'}
def smalltalk(text):
 t=re.sub(r'[^\w\s]','',str(text).casefold()).strip()
 return bool(re.fullmatch(r'(?:hi+|hu|hey+|he+l+o+|yo+|salam|assalamualaikum|how (?:are|r) (?:you|u)|how are you doing|hows it going|everything good|good (?:morning|evening|night)|kya haal hai|kya hal hai|sab theek)',t))
def owner_text(text):
 text=re.sub(r'```[\s\S]*?```',' [quoted data] ',str(text))
 text=re.sub(r'(?m)^\s*>.*$',' [quoted data] ',text)
 text=re.sub(r'"[^"\n]*"|“[^”\n]*”',' [quoted data] ',text)
 text=re.split(r'(?i)(?:message says|text says|transcript|see fn remove|summarize this|analyse this|analyze this)\s*:',text,maxsplit=1)[0]
 return text

def intent(text):
 t=owner_text(text);low=manual_commands.norm(t)
 query=bool(re.search(r'(?i)^(?:what|why|how|did you|have you|was it|when|show (?:me )?(?:what|status))\b',t.strip()))
 negative=bool(re.search(r"(?i)\b(?:don'?t|dont|do not|never|stop)\s+(?:ever\s+)?(?:send|sending|post|posting|share|sharing|dm)\b|\b(preview only|draft only)\b",t))
 sending=bool(manual_commands.SEND.search(t) or re.search(r'(?i)\b(?:snd|snt|sens|sned|semd|sebd)\b',t)) and not negative and not query
 return {'text':t,'send':sending,'query':query,'negative':negative,'batch':sending and bool(re.search(r'(?i)\b(dm|dms|donors?|members?|people|numbers|list)\b',t))}

def permitted(name,text):
 if name in READ:return True
 i=intent(text);t=i['text']
 if name in SEND:return i['send'] and (name not in {'dm_list','dm_donors','dm_group'} or i['batch'])
 if i['query']:return False
 if name=='delete_last_message':return bool(re.search(r'(?i)\b(delete|remove|revoke)\b',t)) and not re.search(r"(?i)\b(dont|don't|do not|never)\b",t)
 if name=='hold':return bool(re.search(r'(?i)\b(hold|wait|pause|stop|resume|continue|unhold|wrong whatsapp|connected now)\b',t))
 if name=='autopilot':return bool(re.search(r'(?i)\b(auto|autopilot)\b.*\b(on|off|enable|disable|start|stop)\b|\b(enable|disable|start|stop)\b.*\b(auto|autopilot)\b',t))
 if name in ('remember','add_rule'):return bool(re.search(r'(?i)\b(remember|always|never|from now|in future|daily|every|quiet|pause|pace|slow|fast|yaad rakho)\b',t))
 if name=='delete_rule':return bool(re.search(r'(?i)\b(forget|delete|remove)\b.*\b(rule|memory|preference)\b',t))
 if name in ('set_left','money_came'):
  return any((p.get('kind')=='money')==(name=='money_came') for p in financial_plans(t))
 if name in ('set_group_pace','set_pace','pause_group','resume_group','set_quiet_hours','set_dms'):return bool(re.search(r'(?i)\b(every|after|pace|speed|slow|fast|pause|resume|quiet|enable|disable|start|stop|on|off)\b',t))
 if name=='edit_dm_name':return bool(re.search(r'(?i)\b(name|call him|call her|greeting)\b',t))
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
