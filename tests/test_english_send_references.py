import unittest

import manual_commands


class EnglishSendReferenceTests(unittest.TestCase):
    def test_instead_of_excludes_the_named_group(self):
        self.assertEqual(manual_commands.parse('send to main instead of upwork'),
                         {'kind': 'appeal', 'target': 'main', 'amount': None})
        self.assertEqual(manual_commands.parse('send to upwork rather than main'),
                         {'kind': 'appeal', 'target': 'upwork', 'amount': None})

    def test_back_references_are_never_posted_as_literal_text(self):
        for text in ('send the same thing to fiverr', 'send same to upwork',
                     'send what you sent to main to upwork too', 'send the last one to fiverr'):
            self.assertIsNone(manual_commands.parse(text), text)

    def test_group_that_already_has_it_is_not_resent(self):
        self.assertIsNone(manual_commands.parse('main got it already, now send fiverr'))

    def test_plain_literal_text_still_sends(self):
        self.assertEqual(manual_commands.parse('send hi to main')['kind'], 'text')


if __name__ == '__main__':
    unittest.main()
