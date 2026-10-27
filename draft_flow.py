"""Draft-task boundaries shared by tool permissions, runtime and direct reads."""
import re

def preview_request(text):
 t=re.sub(r'[^\w\s]',' ',str(text).casefold());t=re.sub(r'\s+',' ',t).strip()
 t=re.sub(r'^(?:please|can you|could you|would you)\s+','',t)
 if t in ('shownhere','showhere','show here','show it here','show','show it','show this','preview'):return 'current'
 m=re.fullmatch(r'(?:show|preview|display)(?: me)?(?: the)?(?: saved| current| latest| updated)?(?: (group|dm))? (?:message|caption|draft)(?: here)?',t)
 return (m[1] or 'current') if m else None

def editing_request(text):
 t=re.sub(r'(?i)^(?:please|kindly|can you|could you|would you)\s+','',str(text).strip())
 if re.fullmatch(r'(?i)(?:(?:show|write|make|give)(?: me)?\s+)?(?:a\s+)?(?:new|fresh)\s+(?:(?:group|dm)\s+)?(?:message|caption|draft|wording)[.!]*',t):return True
 if re.match(r'(?i)^(?:remember|always|never|from now|in future)\b',t) and not re.search(r'(?i)\band\s+(?:rewrite|change|edit|make)\b',t):return False
 if re.match(r'(?i)^(?:what|why|how|did|have|is|can|could|show|preview|explain|review|summari[sz]e|analy[sz]e)\b',t):return False
 if re.match(r'(?i)^(?:delete|remove)\b',t) and re.search(r'(?i)\b(?:message|post)\b',t) and not re.search(r'(?i)\b(?:line|words?|paragraph|wording|caption)\b',t):return False
 subject=r'(?:message|caption|draft|hook|opening|lines?|paragraphs?|wording|phrase|sentence|bullet|format|bold|italic|report)'
 operation=r'(?:write|rewrite|edit|change|replace|remove|delete|add|move|put|make|use|keep|lead|start|shorten|improve|reword)'
 if re.search(r'(?i)\b'+operation+r'\b.*\b'+subject+r'\b',t):return True
 if re.search(r'(?i)\b(?:make|change|rewrite|shorten|improve|reword)\s+(?:it|this|that)\b',t):return True
 if re.search(r'(?i)\b(?:move|put)\s+(?:it|this|that)\b.*\b(?:first|top|opening|start|hook)\b',t):return True
 if re.search(r'(?i)\b'+subject+r'\b.*\b(?:old|overused|repeated|boring|wrong|new|fresh|stronger|emotional|urgent|triggered)\b',t):return True
 if re.search(r'(?i)\b(?:more|less|very)\b.*\b(?:emotional|urgency|urgent|triggered|simple|formal)\b.*\b(?:message|caption|wording)\b',t):return True
 if re.fullmatch(r'(?i)(?:too|more|less|much)\s+(?:long|short|shorter|longer|emotional|urgent|formal|simple)[.!]*',t):return True
 return False
