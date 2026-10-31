"""Retrospective conversation insights: evidence, scope, and quality checks.

Runs without a real AI account or WhatsApp connection.
"""
import json
import unittest
from unittest.mock import patch
import assistant
import chat_runtime
import conversation_insights as ci

REQUESTS = [
 'I need a monthly donor program so supporters can help each month.',
 'How do we convert old donors into recurring donors?',
 'Encourage supporters to introduce interested friends rather than DM everyone.',
 'Please automate 20-person donor batches with a user-selected gap.',
 'The WhatsApp sender must show exactly who received each DM.',
 'Stop repeating the same group appeal after a case is complete.',
 'DeepSeek keeps misunderstanding what I mean in one short prompt.',
 'Learn from my corrections and understand past requests, not just the latest message.',
 'When I say do the same, it should know the previous task without asking again.',
 'The patient medical caption included a symptom I never reported.',
 'Keep each new case separate; never reuse the old medical papers.',
 'Use the verified amount and do not show Rs. 0 donors needed.',
 'Ask GIKI students to volunteer and share verified case posts.',
 'Let team leads track which ambassadors actually shared.',
 'Mobile chat has too many clicks and keyboard focus disappears.',
 'Do not cut off the dropdown or force AI replies into unreadable columns.',
]
ARCHIVE = [{'who':'you','text':t,'time':1000+i} for i,t in enumerate(REQUESTS)]
ARCHIVE += [{'who':'app','text':'The assistant said everything was sent.', 'time':2000}]

class HistoricalAnalysisTests(unittest.TestCase):
 def setUp(self):
  self.review=ci.build_history_review(ARCHIVE,[],limit=6)

 def test_recognizes_future_analysis_not_case_status(self):
  self.assertTrue(ci.wants_review('Read our chat and suggest future improvements.'))
  self.assertTrue(ci.wants_review('Case is ended. Future suggestions'))
  self.assertTrue(ci.wants_review('Analyze past conversations and recommend improvements'))
  self.assertFalse(ci.wants_review('What is the status of the current case?'))
  self.assertFalse(ci.wants_review('Send hi to the volunteer'))
  self.assertFalse(ci.wants_review('Review our chats and then send this to Ali'))

 def test_reads_archived_owner_requests_and_excludes_ai_claims(self):
  self.assertEqual(self.review['owner_turns_examined'],len(REQUESTS))
  self.assertGreaterEqual(len(self.review['themes']),5)
  content=json.dumps(self.review)
  self.assertIn('monthly',content)
  self.assertIn('keyboard',content)
  self.assertNotIn('The assistant said everything was sent.',content)

 def test_old_messages_do_not_become_send_permissions(self):
  hist=[{'who':'you','text':'Last time I said send everyone a DM.'}]
  msg=chat_runtime.context_messages(
    'Read our old chats and recommend future improvements',
    hist, {'case_name':'Yousuf','left':0,'autopilot':False,'history_review':self.review}, [])
  bundled='\n'.join(m['content'] for m in msg)
  self.assertIn('history_review',bundled)
  self.assertIn('Donor growth and sustainable giving',bundled)
  self.assertNotIn('"left": 0',bundled)
  with patch.object(assistant,'client',return_value='fake'),patch.object(
      assistant,'_chat_raw',return_value={'content':'Consider building a monthly-giving and referral workflow.'}) as api:
   assistant.chat('Read our old chats and recommend future improvements',hist,
                  {'history_review':self.review,'case_name':'Yousuf','left':0},[],{})
  self.assertEqual(api.call_args.args[2],[])

 def test_detects_and_replaces_the_exact_shallow_recap_failure(self):
  poor=('Where things stand: case Yousuf closed Rs. 0 left. Auto off. '
        '30 waiting. Stop the batch. Start the next case fresh. '
        'Leave Auto off.')
  self.assertTrue(ci.generic_status_answer(poor,self.review))
  with patch.object(assistant,'client',return_value='fake'),patch.object(
      assistant,'_chat_raw',return_value={'content':poor}):
   result=assistant.chat('Read our chats and give future suggestions',[],
            {'history_review':self.review,'case_name':'Yousuf','left':0},[],{})
  response=result['reply']
  self.assertIn('recurring',response.lower())
  self.assertIn('requests',response.lower())
  self.assertNotIn('Where things stand',response)
  self.assertNotIn('Stop the batch.',response)
  self.assertEqual(result['diagnostics']['tools'],[])

 def test_grounded_response_can_pass_without_replacement(self):
  answer=('Your repeated requests about monthly donors, volunteer ambassadors and '
          'one-prompt context suggest a retention journey, accountable sharing '
          'and task tracking. Measure consented monthly donations and completed tasks.')
  self.assertFalse(ci.generic_status_answer(answer,self.review))

 def test_no_historical_evidence_does_not_invent_past_conversations(self):
  empty=ci.build_history_review([{'who':'app','text':'Many donors supported this case.'}])
  result=ci.evidence_fallback(empty)
  self.assertIn('do not have enough',result.lower())

 def test_sensitive_numbers_are_redacted_from_evidence(self):
  review=ci.build_history_review([
    {'who':'you','text':'Do not send updates to 03001234567, and my key csk-abcdefghijklmnop is private.'}])
  evidence=json.dumps(review)
  self.assertNotIn('03001234567',evidence)
  self.assertNotIn('csk-abcdefghijklmnop',evidence)

if __name__=='__main__':unittest.main()
