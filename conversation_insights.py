"""Evidence-focused historical chat review for GiveLife.

Past chat is read-only evidence, NEVER action authority. This module only processes
messages already saved by the application; it does not claim account-wide access.
"""
import re
from chat_memory import safe_text
from state_shapes import history as valid_history

HISTORY_RE = re.compile(
 r'(?is)\b(?:read|review|analy[sz]e|study|inspect|go through|look (?:through|at)|learn from|based on|from)\b'
 r'.{0,120}\b(?:chats?|conversation|history|past messages?|old messages?|past prompts?|previous requests?|past mistakes?)\b'
 r'|\b(?:chats?|conversation|history|past prompts?|previous requests?|past mistakes?)\b'
 r'.{0,120}\b(?:suggest|recommend|improv|learn|analy[sz]e|review|future|next)\b'
 r'|\b(?:future|next[- ]case|long[- ]term)\s+(?:suggestions?|recommendations?|improvements?|strategy|ideas?)\b'
 r'|\b(?:suggestions?|recommendations?|improvements?)\b.{0,40}\b(?:future|from (?:our|my) chats?|past chats?|old chats?)\b')
ACTION_RE = re.compile(r'(?i)(?:\band then\b|\bthen\b|\balso\b|;)\s*(?:please\s+)?(?:send|post|delete|change|update|set|start|stop|enable|cancel|schedule)\b')
CATEGORIES = (
 ('context_and_ai', 'Repeated instructions and AI understanding',
  r'(?i)\b(?:context|understand|one[- ]prompt|one instruction|remember|mistakes?|not listening|confus|future prompts?|chatbot|deepseek|brain|logic|repeat(?:ed|ing)?|not what i asked)\b'),
 ('donor_growth', 'Donor growth and sustainable giving',
  r'(?i)\b(?:donors?|monthly|recurr(?:ing|ence)|fundrais|referrals?|conversion|donat(?:e|ion|ions)|supporters?|community|course|new people|repeat giving)\b'),
 ('messaging_automation', 'Messages, batches, and scheduling',
  r'(?i)\b(?:send|sending|dms?|whatsapp|batch(?:es)?|auto|autopilot|schedul|interval|every \d+|post(?:ing)?|group(?:s)?|delay|gap|hold|pause|resume)\b'),
 ('case_accuracy', 'Case accuracy and donor trust',
  r'(?i)\b(?:cases?|patients?|children|child|medical|hospital|symptom|diagnos|caption|poster|balance|remaining|rs\.?\s*\d+|complete|closed|proof|receipt|wrong amount|false|facts?)\b'),
 ('volunteer_team', 'Team and volunteer execution',
  r'(?i)\b(?:team(?:mate)?|volunteer|ambassador|societ(?:y|ies)|giki|lums|university|akhtar|delegate|leader|follow[- ]up)\b'),
 ('ui_friction', 'Mobile UI and interaction friction',
  r'(?i)\b(?:ui|ux|mobile|desktop|thumb|click|scroll|keyboard|dropdown|copy|colors?|theme|focus|responsive|screens?|button|input field)\b'),
)
CORRECTION = re.compile(r"(?i)\b(?:wrong|mistake|error|broken|don't|dont|not|fix|instead|again|stop|doesn't|didn't|never|bad|suck|please|failed|confus)\b")
PHONE = re.compile(r'(?<!\d)(?:\+?92[\s-]?|0)3\d{2}[\s-]?\d{7}(?!\d)')
SENSITIVE = re.compile(r'(?i)\b(?:sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,}|csk-[a-z0-9_-]{12,})\b')
SPACE = re.compile(r'\s+')

def wants_review(text):
 """Separate 'what happened just now?' from 'review our past chats and plan ahead'."""
 t=str(text or '').strip()
 return bool(HISTORY_RE.search(t)) and not bool(ACTION_RE.search(t))

def evidence_text(value):
 t=safe_text(value,1200)
 t=SENSITIVE.sub('[credential redacted]',t)
 t=PHONE.sub('[phone redacted]',t)
 return SPACE.sub(' ',t).strip()

def build_history_review(archived,recent=(),limit=6):
 """Topic counts and distinct first-person evidence, not an invented summary.

 Draws from all *available* archived turns (at most the app's retention limit),
 and includes recent owner turns not yet archived. Assistant claims are excluded.
 """
 seen=set()
 owners=[]
 for src,collection in [('archive',archived),('recent',recent)]:
  for row in valid_history(collection):
   if row['who']!='you':continue
   raw=evidence_text(row['text'])
   if len(raw)<14 or len(raw)>950:continue # Skip greetings and enormous pasted transcripts.
   key=SPACE.sub(' ',raw.lower()).strip(' .?!')
   if key in seen:continue
   seen.add(key)
   owners.append({'text':raw,'time':row.get('time') or row.get('t'),
                  'source':src})
 buckets=[]
 for ident,title,pattern in CATEGORIES:
  regex=re.compile(pattern)
  matched=[(i,item) for i,item in enumerate(owners) if regex.search(item['text'])]
  if not matched:continue
  corrected=[(i,item) for i,item in matched if CORRECTION.search(item['text'])]
  # Representative evidence from both early and recent history, with corrections prioritized.
  picks=[]
  for source in (corrected[-2:],matched[:1],matched[-2:]):
   for idx,item in source:
    if idx not in picks:picks.append(idx)
  excerpts=[{'owner_said':owners[i]['text'][:240],'source':owners[i]['source']}
            for i in picks[:4]]
  buckets.append({'id':ident,'theme':title,'distinct_owner_requests':len(matched),
                  'corrections_or_problems':len(corrected),'examples':excerpts})
 buckets.sort(key=lambda row:(row['corrections_or_problems'],row['distinct_owner_requests']),reverse=True)
 return {
  'scope':'App-saved conversation only; historical assistant replies are excluded as evidence.',
  'owner_turns_examined':len(owners),
  'archived_turn_limit':2000,
  'theme_count':len(buckets),
  'themes':buckets[:limit],
  'limitations':'Examples are excerpts, not medical or delivery confirmation. Frequency is number of unique owner messages with topic matches, not number of failures. Only saved chat is available.'
 }

REVIEW_INSTRUCTION=(
 'The owner requests FUTURE STRATEGY FROM THE APP CHAT HISTORY, not a case-status '
 'recap or an incident postmortem limited to the last case. Evaluate the history_review '
 'theme counts and first-person owner evidence. Propose 3-5 specific forward-looking '
 'improvements across recurring themes, prioritizing systemic impact and effort. '
 'For each say which recurring OWNER pattern motivates it, what practical change '
 'would help, and how to verify improvement. Introduce useful next steps beyond '
 'the latest case; avoid simply repeating "stop batch", "Auto off", "Rs. 0", or '
 '"start a new case" as most of the answer. You may mention current case status '
 'only if material, in at most one sentence. Be honest about evidence limits; '
 'do not assert a task was completed or suggest the owner already implemented a '
 'proposal without verified results. Do not perform any sends, edits or state changes.'
)
