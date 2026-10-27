"""Draft-task boundaries shared by tool permissions, runtime and direct reads."""
import re

def selected_option(text,history):
 """An owner-selected draft option authorizes editing only, never money/sends."""
 match=re.fullmatch(r'(?i)\s*(?:(?:option|number|use|choose)\s*)?#?(\d{1,2})[.!]?\s*',str(text))
 if not match:return None
 items=[h for h in history if isinstance(h,dict) and h.get('who') in ('you','app') and isinstance(h.get('text'),str)]
 if items and items[-1]['who']=='you' and items[-1]['text'].strip()==str(text).strip():items=items[:-1]
 if len(items)<2 or items[-1]['who']!='app':return None
 owner=next((h['text'] for h in reversed(items[:-1]) if h['who']=='you'),'')
 if not re.search(r'(?i)\b(?:hooks?|openings?|versions?|alternatives?|options?)\b',owner) or not re.search(r'(?i)\b(?:show|give|make|write|suggest)\b',owner):return None
 if not re.search(r'(?i)\b(?:hooks?|openings?|captions?|messages?|drafts?|wording)\b',owner):return None
 numbers={int(n) for n in re.findall(r'(?m)^\s*(?:\*\*)?(\d{1,2})[.)](?:\*\*)?\s*',items[-1]['text'])}
 return int(match[1]) if len(numbers)>=2 and int(match[1]) in numbers else None

def option_kind(history,fallback='group'):
 for h in reversed(history):
  if isinstance(h,dict) and h.get('who')=='you' and re.search(r'(?i)\b(?:hooks?|openings?|versions?|alternatives?|options?)\b',str(h.get('text',''))):
   return 'dm' if re.search(r'(?i)\bdm\b',h['text']) else 'group'
 return 'dm' if fallback=='dm' else 'group'

def preview_request(text):
 t=re.sub(r'[^\w\s]',' ',str(text).casefold());t=re.sub(r'\s+',' ',t).strip()
 t=re.sub(r'^(?:please|can you|could you|would you)\s+','',t)
 if t in ('shownhere','showhere','show here','show it here','show','show it','show this','preview'):return 'current'
 m=re.fullmatch(r'(?:show|preview|display)(?: me)?(?: the)?(?: saved| current| latest| updated)?(?: (group|dm))? (?:message|caption|draft)(?: here)?',t)
 return (m[1] or 'current') if m else None

def editing_request(text):
 t=re.sub(r'(?i)^(?:please|kindly|can you|could you|would you)\s+','',str(text).strip())
 if re.search(r'(?i)^show\b.*\b(?:first|before)\b.*\b(?:make|write|prepare|draft|compose)\b',t):return True
 if re.search(r"(?i)^(?:let s|lets|let's)\s+(?:send|post)\b.*\b(?:message|caption)\b",t):return True
 if re.fullmatch(r'(?i)(?:(?:show|write|make|give)(?: me)?\s+)?(?:a\s+)?(?:new|fresh)\s+(?:(?:group|dm)\s+)?(?:message|caption|draft|wording)[.!]*',t):return True
 if re.match(r'(?i)^(?:remember|always|never|from now|in future)\b',t) and not re.search(r'(?i)\band\s+(?:rewrite|change|edit|make)\b',t):return False
 if re.match(r'(?i)^(?:what|why|how|did|have|is|can|could|show|preview|explain|review|summari[sz]e|analy[sz]e)\b',t):return False
 if re.match(r'(?i)^(?:delete|remove)\b',t) and re.search(r'(?i)\b(?:message|post)\b',t) and not re.search(r'(?i)\b(?:line|words?|paragraph|wording|caption)\b',t):return False
 subject=r'(?:message|caption|draft|hook|opening|lines?|paragraphs?|wording|phrase|sentence|bullet|format|bold|italic|report|icon|emoji|emojis)'
 operation=r'(?:write|rewrite|edit|change|replace|remove|delete|add|move|put|make|use|keep|lead|start|shorten|improve|reword)'
 if re.search(r'(?i)\b'+operation+r'\b.*\b'+subject+r'\b',t):return True
 if re.search(r'(?i)\b'+subject+r'\b.*\b'+operation+r'\b',t):return True
 if re.match(r'(?i)^(?:make|keep)\b',t) and re.search(r'(?i)\b(?:short|shorter|long|longer|emotional|urgent|triggered|simple|formal|casual|concise|direct)\b',t):return True
 if re.match(r'(?i)^(?:only|total|entire|whole)\b',t) and re.search(r'(?i)\b(?:\d+|one|two|three|four|five)\s+(?:lines?|words?|sentences?|paragraphs?)\b',t):return True
 if re.search(r'(?i)\b(?:make|change|rewrite|shorten|improve|reword)\s+(?:it|this|that)\b',t):return True
 if re.search(r'(?i)\b(?:move|put)\s+(?:it|this|that)\b.*\b(?:first|top|opening|start|hook)\b',t):return True
 if re.search(r'(?i)\b'+subject+r'\b.*\b(?:old|overused|repeated|boring|wrong|new|fresh|stronger|emotional|urgent|triggered)\b',t):return True
 if re.search(r'(?i)\b(?:more|less|very)\b.*\b(?:emotional|urgency|urgent|triggered|simple|formal)\b.*\b(?:message|caption|wording)\b',t):return True
 if re.fullmatch(r'(?i)(?:too|more|less|much)\s+(?:long|short|shorter|longer|emotional|urgent|formal|simple)[.!]*',t):return True
 return False
