"""Durable donor wording generation, using a fake model and synthetic storage only."""
import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import dm_templates
from donor_messages import MessageBank


class Store:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def put(self, key, value):
        self.data[key] = copy.deepcopy(value)


class GenerationProgressTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.source = dm_templates.build(0, 25000)
        self.versions = [dm_templates.build(i, 25000) for i in range(1, 20)]
        outer = self

        class App:
            DATA = Path(outer.folder.name)
            STORE = Store()
            left = 25000

            def get_message(self, kind):
                return {'text': outer.source}

            def read_left(self):
                return self.left

            def active_case_name(self):
                return 'Yousuf'

        self.app = App()
        self.bank = MessageBank(self.app)

    def tearDown(self):
        self.folder.cleanup()

    def wait(self, state, bank=None):
        bank = bank or self.bank
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            data = bank.get()
            if data.get('generation', {}).get('state') == state and not bank.regeneration_running:
                return data
            time.sleep(.005)
        self.fail('Generation did not finish: ' + str(bank.get().get('generation')))

    def test_start_is_immediate_and_repeated_clicks_or_refresh_use_one_worker(self):
        gate, entered = threading.Event(), threading.Event()

        def generate(source, count, **kwargs):
            entered.set()
            gate.wait(2)
            return self.versions

        with patch('dm_variants.generate', side_effect=generate) as model:
            before = time.monotonic()
            first = self.bank.start_regeneration()
            self.assertLess(time.monotonic() - before, .25)
            self.assertTrue(entered.wait(1))
            try:
                second = self.bank.start_regeneration()
                for _ in range(5):
                    self.bank.get()
                self.assertEqual(first['generation']['id'], second['generation']['id'])
                self.assertEqual(model.call_count, 1)
            finally:
                gate.set()
            data = self.wait('Ready')
        self.assertEqual(data['items'][0]['text'], self.source)
        self.assertEqual(len(data['items']), 20)

    def test_partial_progress_survives_failure_refresh_and_retry_only_requests_missing(self):
        def interrupted(source, count, **kwargs):
            kwargs['progress'](self.versions[:2])
            raise ValueError('Provider unavailable')

        with patch('dm_variants.generate', side_effect=interrupted):
            self.bank.start_regeneration()
            partial = self.wait('Partial')
        self.assertEqual(len(partial['items']), 3)
        self.assertIn('Provider unavailable', partial['generation']['error'])
        restored = MessageBank(self.app)
        self.assertEqual(restored.get()['items'], partial['items'])
        with patch('dm_variants.generate', return_value=self.versions[2:]) as model:
            restored.start_regeneration()
            ready = self.wait('Ready', restored)
        self.assertEqual(model.call_args.args[1], 17)
        self.assertEqual(model.call_args.kwargs['avoid'], [self.source] + self.versions[:2])
        self.assertEqual([row['text'] for row in ready['items']], [self.source] + self.versions)

    def test_successful_partial_batches_continue_without_another_click(self):
        with patch('dm_variants.generate', side_effect=[self.versions[:2], self.versions[2:]]) as model:
            self.bank.start_regeneration()
            ready = self.wait('Ready')
        self.assertEqual(model.call_count, 2)
        self.assertEqual(model.call_args.args[1], 17)
        self.assertEqual(len(ready['items']), 20)

    def test_late_worker_cannot_overwrite_a_new_master_edit(self):
        gate, entered = threading.Event(), threading.Event()

        def generate(source, count, **kwargs):
            entered.set()
            gate.wait(2)
            return self.versions

        with patch('dm_variants.generate', side_effect=generate):
            self.bank.start_regeneration()
            self.assertTrue(entered.wait(1))
            changed = self.source.replace('Brother,', 'Bhai,')
            self.bank.update('wording-01', changed)
            gate.set()
            result = self.wait('Superseded')
        self.assertEqual(result['items'][0]['text'], changed)
        self.assertEqual(len(result['items']), 1)

    def test_pending_generation_resumes_from_saved_progress_after_restart(self):
        data = self.bank.get()
        data.update(mode='custom', items=self.bank._entries([self.source] + self.versions[:2]),
                    generation={'id': 'restart-job', 'source': self.source, 'target': 20,
                                'accepted': self.versions[:2], 'state': 'Generating', 'ready': 3})
        self.bank._save(data)
        restarted = MessageBank(self.app)
        with patch('dm_variants.generate', return_value=self.versions[2:]) as model:
            restarted.get()
            result = self.wait('Ready', restarted)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.call_args.args[1], 17)
        self.assertEqual(len(result['items']), 20)

    def test_balance_update_cancels_stale_generation_without_restoring_old_amount(self):
        gate, entered = threading.Event(), threading.Event()

        def generate(source, count, **kwargs):
            entered.set()
            gate.wait(2)
            return self.versions

        with patch('dm_variants.generate', side_effect=generate):
            self.bank.start_regeneration()
            self.assertTrue(entered.wait(1))
            self.app.left = 23000
            self.bank.get()
            gate.set()
            result = self.wait('Superseded')
        self.assertIn('23,000', result['items'][0]['text'])
        self.assertNotIn('25,000', result['items'][0]['text'])


if __name__ == '__main__':
    unittest.main()
