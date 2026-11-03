"""Draft-task boundaries shared by tool permissions, runtime and direct reads."""
import re
import hashlib
from state_shapes import mapping, history as valid_history

def active_task(state):
 state=mapping(state);task=mapping(state.get('draft_task'));drafts=mapping(state.get('drafts'))
 value=drafts.get(task.get('kind'))
 if isinstance(value,str) and task.get('hash') and task['hash']!=hashlib.sha256(value.encode()).hexdigest():return {}
 return task

def current_kind(text,state):
 """Explicit draft scope, then persisted work, then the visible screen."""
 t=str(text)
 if re.search(r'(?i)\bdm\b',t):return 'dm'
 if re.search(r'(?i)\b(?:group|givelife|give life)\b',t):return 'group'
 state=mapping(state);task=active_task(state)
 if task.get('kind') in ('group','dm') and task.get('state') in ('editing','ready'):
  return task['kind']
 return 'dm' if mapping(state.get('screen')).get('view')=='dm' else 'group'

TONE=r'(?:shorter|short|longer|long|chh?ota|chh?oti|lamba|lambi|bada|badi|simpler|simple|emotional|urgent|formal|casual|stronger|softer|direct|concise)'
LEAD=r'(?:(?:ok|okay|and|also|now|then|aur|phir|ab)[\s,]+)*'
def refinement(text):
 """A short follow-up that only makes sense against the draft just worked on ("shorter", "isko chota karo", "also add jazzcash", "same for dm")."""
 t=re.sub(r'[.!]+$','',str(text).strip())
 if not t or len(t.split())>9:return False
 if re.fullmatch(r'(?i)'+LEAD+r'(?:make\s+it\s+|isko\s+|ise\s+|is\s+ko\s+|it\s+)?(?:a\s+bit\s+|bit\s+|thoda\s+|thora\s+|bohat\s+|bahut\s+|zyada\s+|more\s+|little\s+|bit\s+more\s+)?'+TONE+r'(?:\s+kar(?:o|\s*do|\s*den|\s*dein)?)?',t):return True
 if re.fullmatch(r'(?i)'+LEAD+r'(?:do\s+the\s+)?same(?:\s+thing)?\s+(?:for|in|on|to)\s+(?:the\s+)?(?:dm|dms|group|groups)',t):return True
 if re.match(r'(?i)^'+LEAD+r'(?:add|include|put|insert|remove|delete|hata(?:o|\s*do)|nikal(?:o|\s*do)|dalo|daal(?:o|\s*do))\b.{2,70}$',t):
  return not re.search(r'(?i)\b(?:last\s+(?:message|post)|rule|schedule|donors?|team|task|volunteers?|contact|group\s+to|to\s+(?:the\s+)?(?:team|donors?|list))\b',t)
 return False

def contextual_edit(text,history,state):
 """Resolve a short edit against active work; this never authorizes a send."""
 t=str(text).strip()
 if not (refinement(t) or re.match(r'(?i)^(?:fix|correct|adjust|improve)\s+(?:that|this|it|the\s+(?:last|first|previous))\b',t)):return False
 if re.search(r"(?i)\b(?:don'?t|dont|do not|never)\s+(?:edit|change|save|rewrite|replace|update|touch|modify)\b|\b(?:preview only|read only|no changes)\b",t):return False
 if re.search(r'(?i)\b(?:tasks?|teammate|akhtar|schedule|settings|batch|timer|login|connection|donors?|volunteers?|balance)\b',t):return False
 if re.search(r'(?i)\b(?:ui|css|code|dropdown|button|website|screen|layout|bug)\b',t):return False
 task=active_task(state)
 if mapping(mapping(state).get('draft_task')).get('hash') and not task:return False
 if task.get('kind') in ('group','dm') and task.get('state') in ('editing','ready'):return True
 owner=[h for h in valid_history(history)[-14:] if h['who']=='you']
 if not owner:return False
 prior=owner[-1]['text']
 return bool(editing_request(prior) and re.search(r'(?i)\b(?:group|dm|message|caption|draft|hook|paragraph|line|wording)\b',prior))

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
 # Settings talk ("change dm gap to 5 minutes", "remove the poster") never edits the saved wording.
 settings=re.search(r'(?i)\b(?:gap|interval|pace|speed|delay|batch|chunk|(?:message|dm|daily|sending|posting) limit)\b',t) or (re.search(r'(?i)\b(?:limit|daily|poster|picture|image|timer|resume|rest|faster|slower|quiet|silent|night|often|frequency|frequent)\b',t) and not re.search(r'(?i)\b(?:caption|message|wording|lines?|paragraphs?|hook|opening|ending|text|sentence|phrase)\b',t))
 if settings:
  # Settings talk never edits the wording, but "rewrite the caption and set Fiverr pace to 45 minutes" still contains an edit.
  parts=[x for x in re.split(r'(?i)\s+(?:and|then|also|aur)\s+|[;,]\s*',t) if x.strip()]
  return len(parts)>1 and any(editing_request(x) for x in parts)
 if re.match(r'(?i)^(?:bold|bolden|italic|italicize|translate|convert|reformat)\b',t) and not re.search(r'(?i)\b(?:poster|image|picture)\b',t):return True
 if re.search(r'(?i)\b(?:write|make|rewrite|translate|convert|put)\s+(?:it|this|that|the \w+)\s+(?:in|to|into)\s+(?:roman \s*)?(?:urdu|english|hindi)\b',t):return True
 if re.search(r'(?i)\b(?:hadith|hadees|hadis|emojis?|dua|duas|hook|para|paragraph|lines?|naam|opening|ending|heading|title)\b',t) and re.search(r'(?i)\b(?:hata(?: do|o)?|nikal(?:o| do)?|banao|badlo|badal do|likho|likh do|add karo|dalo|daalo|daal do|change karo|remove karo|karo)\b',t) and not re.search(r'(?i)\b(?:poster|image|picture|gap|rules?|donors?|schedule|pace)\b',t):return True
 if re.search(r'(?i)\b(?:isko|ise|is ko)\b.*\b(?:emotional|short|chh?ota|simple|strong|naram|lamba|banao)\b',t):return True
 if not re.search(r'\d',t) and re.search(r'(?i)\b(?:message|msg|caption|dm|line|lines|paragraph|amount|wording)\b.*\b(?:karo|kar do|likho|likh do|badlo|hatao|hata do|nikalo|nikal do|dalo|daalo|chh?ota|bada)\b',t):return True
 if re.search(r'(?i)^show\b.*\b(?:first|before)\b.*\b(?:make|write|prepare|draft|compose)\b',t):return True
 if re.search(r"(?i)^(?:let s|lets|let's)\s+(?:send|post)\b.*\b(?:message|caption)\b",t):return True
 if re.fullmatch(r'(?i)(?:(?:show|write|make|give)(?: me)?\s+)?(?:a\s+)?(?:new|fresh)\s+(?:(?:group|dm)\s+)?(?:message|caption|draft|wording)[.!]*',t):return True
 if re.match(r'(?i)^(?:remember|always|never|from now|in future)\b',t) and not re.search(r'(?i)\band\s+(?:rewrite|change|edit|make)\b',t):return False
 if re.match(r'(?i)^(?:what|why|how|did|have|is(?!\s+(?:message|msg|caption|dm|ko|line|ka|ke|mein|me)\b)|can|could|show|preview|explain|review|summari[sz]e|analy[sz]e)\b',t):return False
 if re.match(r'(?i)^(?:delete|remove)\b',t) and re.search(r'(?i)\b(?:message|post)\b',t) and not re.search(r'(?i)\b(?:line|words?|paragraph|wording|caption)\b',t):return False
 subject=r'(?:message|dm|caption|draft|hook|opening|lines?|paragraphs?|wording|phrase|sentence|bullet|format|bold|italic|report|icon|emoji|emojis|end|ending|closing|beginning|dua|duas|signature|top|bottom|first line|last line|payment details|amount line)'
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
