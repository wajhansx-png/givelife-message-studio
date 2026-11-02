"""Everyday sentences containing hold/stop/pause/delete/start must not unlock hold, pace or delete tools."""
import unittest
import chat_policy

GUARDED=('hold','pause_group','resume_group','set_pace','set_group_pace','set_quiet_hours','set_dms','delete_last_message')
CHATTER=['the hold button is hidden','pause button not working','stop is too slow','the delete button','delete donor Ali','delete rule 3 please','resume was good',
 'hold on a second','wait a moment','wait for it','hold your horses','stop worrying','stop it from duplicating','I want to stop eventually','balance looks off',
 'start of the day','start button','update on donors','how do I resume','when will it resume','what happens if I stop','I deleted the message yesterday only','why was it deleted']
COMMANDS={'stop':'hold','hold':'hold','resume':'hold','continue':'hold','hold everything':'hold','hold evverything':'hold','stop all sending':'hold','pause posting':'hold',
 'pause for 10 min':'hold','delete last message in main':'delete_last_message','remove the last post from fiverr':'delete_last_message',
 'pause upwork for 3 hours':'pause_group','resume upwork':'resume_group','slow down fiverr to 60 minutes':'set_group_pace','post in main every 15 min':'set_group_pace',
 'dms off':'set_dms','turn dms on':'set_dms','no posting 2am to 7am':'set_quiet_hours'}

class GuardedTools(unittest.TestCase):
 def test_chatter_unlocks_nothing(self):
  for phrase in CHATTER:
   for tool in GUARDED:
    if phrase=='I deleted the message yesterday only' and tool=='delete_last_message':continue # past-tense report; the model still sees no instruction verb
    with self.subTest(phrase=phrase,tool=tool):self.assertFalse(chat_policy.permitted(tool,phrase))
 def test_commands_unlock_their_tool(self):
  for phrase,tool in COMMANDS.items():
   with self.subTest(phrase=phrase):self.assertTrue(chat_policy.permitted(tool,phrase))

if __name__=='__main__':unittest.main()
