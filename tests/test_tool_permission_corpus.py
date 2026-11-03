"""Owner phrasings must reach the right tool, and look-alike phrasings must not reach a dangerous one."""
import unittest
import assistant,chat_policy

cases=[
("make the group message shorter","set_message"),("remove the hadith line","set_message"),("add jazzcash number at the end","set_message"),("write a new group message","set_message"),
("change the first line","set_message"),("remove emojis","set_message"),("bold the amount","set_message"),("keep only 3 lines","set_message"),("translate it to urdu","set_message"),
("write it in roman urdu","set_message"),("add dua at the end of dm","set_message"),("dm ko thora emotional karo","set_message"),("group message mein amount bold karo","set_message"),
("make the dm friendlier","set_message"),("rewrite the dm","set_message"),("is message ko chota karo","set_message"),("shorten it","set_message"),("remove the second paragraph","set_message"),
("use brother instead of bro in dm","set_message"),("put the amount in first line","set_message"),("amount first line mein likho","set_message"),
("45k left","set_left"),("set left 30000","set_left"),("amount left is 20k","set_left"),("5000 came","money_came"),("Rs 500 aye","money_came"),("500 aaye hain","money_came"),
("send main","send_appeal"),("post in all groups","send_appeal"),("send to test group","send_appeal"),("send in fiverr and upwork","send_appeal"),("send hi to Ali","send_message"),
("post in main every 15 min","set_group_pace"),("slow down fiverr to 60 minutes","set_group_pace"),("pause upwork for 3 hours","pause_group"),("resume upwork","resume_group"),
("no posting 2am to 7am","set_quiet_hours"),("auto on","autopilot"),("auto off","autopilot"),("turn autopilot off","autopilot"),
("send 20 dms to important donors","donor_action"),("dm donors","dm_donors"),("dm 10 members of fiverr group","dm_group"),
("add donor Ali 03001234567","donor_action"),("mark Ali donated 500","donor_action"),("show important donors","donor_action"),
("send main at 9pm","schedule_task"),("cancel schedule 2","schedule_task"),("cancel all schedules","schedule_task"),
("new case Ahmed 50000","case_action"),("tell akhtar to post","team_action"),("add volunteer Sara 03001234567","volunteer_action"),
("delete last message in main","delete_last_message"),("remember always keep it short","remember"),("forget rule 2","delete_rule"),("hold everything","hold"),("resume","hold"),
("save shortcut hi means send main","shortcut_action"),("when i say go do send main","shortcut_action"),("generate 10 versions of this dm","generate_dm_variants"),
("hadees hata do","set_message"),("emoji hata do","set_message"),("isko aur emotional banao","set_message"),("first line hook banao","set_message"),("isme se hadith nikal do","set_message"),("paragraph 2 hata do","set_message"),("caption chota karo","set_message"),("dua add karo","set_message"),
("new wording for group","new_wording"),("fresh caption","set_message"),("prepare dm for Ali","prepare_dm"),("his name is Sara","edit_dm_name"),
]

FORBIDDEN=[
 ('gap 5 minute karo','set_message'),('rule hata do','set_message'),('pace karo 30 min','set_message'),('poster hata do','set_message'),
 ('what is left','set_left'),('how much came today','money_came'),('3 came','money_came'),('20 left in the batch','set_left'),
 ("don't send it","send_appeal"),('never post again','send_message'),('tell akhtar to post','send_appeal'),('tell akhtar to send','send_message'),
 ('dm poster off','hold'),('dm poster off','set_message'),('change dm gap to 5 minutes','set_message'),('set dm daily limit 30','set_message'),
 ('dm 20 donors with 4 min gap','set_left'),('show me the message','send_appeal'),('what did you send','send_appeal'),
 ('how many dms sent','dm_donors'),('why did dms stop','set_dms'),('hello','set_message'),('thanks','send_appeal'),
]

class ToolPermissionCorpus(unittest.TestCase):
 def test_each_phrase_reaches_its_tool(self):
  for phrase,tool in cases:
   with self.subTest(phrase=phrase,tool=tool):self.assertTrue(chat_policy.permitted(tool,phrase))
 def test_lookalikes_never_reach_a_dangerous_tool(self):
  for phrase,tool in FORBIDDEN:
   with self.subTest(phrase=phrase,tool=tool):self.assertFalse(chat_policy.permitted(tool,phrase))
 def test_every_corpus_tool_exists(self):
  names={t['function']['name'] for t in assistant.CHAT_TOOLS}
  for _,tool in cases:self.assertIn(tool,names)

if __name__=='__main__':unittest.main()
