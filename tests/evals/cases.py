"""Generate Promptfoo test entries from the single checked-in golden corpus."""
import json
from pathlib import Path

def generate_tests(config=None):
    items=json.loads((Path(__file__).with_name('goldens.json')).read_text(encoding='utf-8'))['cases']
    return [
      {'description':item['id'],
       'vars':{'input':item['input'],'state':item.get('state',{}),'expected':item['expected']},
       'assert':[{'type':'python','value':'file://tests/evals/assertions.py'}]}
      for item in items
    ]
