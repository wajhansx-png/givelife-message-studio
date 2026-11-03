import unittest

import manual_commands


class UrduDmResumeTests(unittest.TestCase):
    def test_urdu_resume_words_resume_dms(self):
        for text in ('dms chalu karo', 'dms dobara shuru karo', 'DMs chalu kar do'):
            self.assertEqual(manual_commands.parse(text), {'kind': 'resume_dms'}, text)

    def test_negated_or_asked_resume_does_nothing(self):
        for text in ('dms chalu mat karo', 'kya dms chalu hain?'):
            self.assertIsNone(manual_commands.parse(text), text)


if __name__ == '__main__':
    unittest.main()
