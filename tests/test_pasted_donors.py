import copy, json, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from donor_book import DonorBook
from donor_delivery import DonorDelivery
try:
    from donor_paste import PastedDonors
except ImportError:
    PastedDonors = None


class Store:
    def __init__(self): self.data = {}
    def get(self, key, default=None): return copy.deepcopy(self.data.get(key, default))
    def put(self, key, value): self.data[key] = copy.deepcopy(value)


class PastedDonorTests(unittest.TestCase):
    def test_number_without_name_uses_a_safe_label(self):
        with tempfile.TemporaryDirectory() as folder:
            book=DonorBook(folder)
            helper=PastedDonors(book,None,lambda:'923205069925',lambda label:('', 'Brother'))
            result=helper.preview('03001234567')
            self.assertEqual(result['count'],1)
            self.assertEqual(result['names'],['Donor 1'])
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store()
        self.book = DonorBook(self.folder.name, self.store)
        self.sent = []
        self.times = []
        self.jobs = DonorDelivery(self.folder.name, self.store, self.book, self.send,
            lambda: 'Saved full caption', lambda: True, lambda: False,
            lambda phone: True, lambda name: ('', 'Brother'),
            lambda count: ['Saved wording %d' % i for i in range(count)])

    def tearDown(self): self.folder.cleanup()
    def send(self, body):
        self.sent.append(body)
        self.times.append(time.time())
        return {'code': 'SUCCESS'}
    def helper(self):
        self.assertIsNotNone(PastedDonors, 'Pasted recipient preparation is missing')
        return PastedDonors(self.book, self.jobs, lambda: '923205069925',
            lambda label: (label.split()[0], 'Brother'))
    def start(self, helper, preview, **kwargs):
        with patch('donor_delivery.threading.Thread.start'):
            return helper.start(preview['token'], request_id='pasted-click-test', **kwargs)
    def run_job(self):
        job = self.jobs._load()['jobs'][-1]
        clock = [1000.]
        def wait(seconds): clock[0] += seconds; return False
        with patch('donor_delivery.time.time', side_effect=lambda: clock[0]), patch.object(self.jobs.stop, 'wait', side_effect=wait):
            self.jobs._run(job)

    def test_preview_accepts_both_orders_common_formats_and_deduplicates_privately(self):
        helper = self.helper()
        result = helper.preview('0300 1234567, Michael\nAnne | +44 (7700) 900-123\n0092.300.1234567 / Other')
        self.assertEqual(result['names'], ['Michael', 'Anne'])
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['duplicates'], 1)
        self.assertTrue(result['warnings'])
        public = json.dumps(result)
        for phone in ('1234567', '7700', '0092', '923001234567'):
            self.assertNotIn(phone, public)
        self.assertEqual(self.book.list()['counts']['all'], 0)

    def test_preview_rejects_invalid_ambiguous_self_and_oversized_without_saving(self):
        helper = self.helper()
        invalid = ['', None, 'Michael, invalid', 'Michael 03001234567 03011234567',
            'Me +92 320 5069925', 'Michael ' + 'a' * 121 + ',03001234567',
            '\n'.join('Person, 92300%07d' % i for i in range(21))]
        for text in invalid:
            with self.subTest(text=str(text)[:30]), self.assertRaises(ValueError): helper.preview(text)
        self.assertEqual(self.book.list()['counts']['all'], 0)

    def test_prepared_tokens_expire_and_memory_is_bounded(self):
        helper = self.helper()
        with patch('donor_paste.time.monotonic', return_value=1000.):
            first = helper.preview('Michael,03001234567')
            for i in range(50): helper.preview('Michael,03001234567')
        with self.assertRaises(ValueError): self.start(helper, first)
        with patch('donor_paste.time.monotonic', return_value=2000.):
            last = helper.preview('Anne,03011234567')
        with patch('donor_paste.time.monotonic', return_value=2601.), self.assertRaises(ValueError): self.start(helper, last)
        self.assertFalse(self.sent)

    def test_twenty_valid_recipients_are_accepted_and_new_owner_is_rechecked_before_save(self):
        helper = self.helper()
        result = helper.preview('\n'.join('Person, 92300%07d' % i for i in range(20)))
        self.assertEqual(result['count'], 20)
        own = helper.preview('Michael,03001234567')
        helper.self_phone = lambda: '923001234567'
        with self.assertRaises(ValueError): self.start(helper, own)
        self.assertEqual(self.book.list()['counts']['all'], 0)

    def test_start_validates_gap_poster_and_request_before_saving(self):
        helper = self.helper(); preview = helper.preview('Michael,03001234567')
        for kwargs in ({'gap_seconds': 0}, {'gap_seconds': 59}, {'gap_seconds': 601},
                       {'gap_seconds': True}, {'gap_seconds': float('nan')}, {'poster': 'yes'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.start(helper, preview, **kwargs)
        with self.assertRaises(ValueError): helper.start(preview['token'], request_id='')
        self.assertEqual(self.book.list()['counts']['all'], 0)

    def test_start_preserves_pasted_order_names_variants_and_existing_registry_name(self):
        existing = self.book.add('Saved label', '03011234567')['donor']
        self.book.update(existing['id'], important=True, donated=True, amount=2000, notes='Keep')
        helper = self.helper(); preview = helper.preview('Michael,03001234567\nAnne,03011234567')
        result = self.start(helper, preview)
        self.assertEqual(result['saved']['added'], 1)
        self.assertEqual(result['saved']['duplicates'], 1)
        self.assertEqual(result['job']['gap_seconds'], 240)
        self.assertNotIn('personal_names', json.dumps(result))
        self.assertNotIn('Michael', json.dumps(result['job']))
        self.run_job()
        self.assertEqual([b['phone'] for b in self.sent], ['923001234567', '923011234567'])
        self.assertEqual([b['name'] for b in self.sent], ['Michael', 'Anne'])
        self.assertEqual([b['message'] for b in self.sent], ['Saved wording 0', 'Saved wording 1'])
        self.assertTrue(self.sent[0]['first_in_batch'])
        self.assertEqual(self.times, [1000., 1240.])
        saved = self.book.resolve(existing['id'])
        self.assertEqual((saved['name'], saved['amount'], saved['notes']), ('Saved label', 2000, 'Keep'))
        self.assertNotIn('personal_names', self.jobs.status())

    def test_duplicate_click_is_idempotent_and_changed_options_are_rejected(self):
        helper = self.helper(); preview = helper.preview('Michael,03001234567')
        one = self.start(helper, preview); two = self.start(helper, preview)
        self.assertEqual(one['job']['id'], two['job']['id'])
        self.assertEqual(len(self.jobs._load()['jobs']), 1)
        with self.assertRaises(ValueError): self.start(helper, preview, gap_seconds=120)
        with self.assertRaises(ValueError): helper.start(preview['token'], request_id='another-click')
        self.run_job(); self.assertEqual(len(self.sent), 1)

    def test_failure_consumes_token_and_does_not_retry(self):
        helper = self.helper(); preview = helper.preview('Michael,03001234567')
        with patch.object(self.jobs, 'start', side_effect=ValueError('Disconnected')):
            with self.assertRaises(ValueError): self.start(helper, preview)
        with self.assertRaises(ValueError): self.start(helper, preview)
        self.assertFalse(self.sent)

    def test_dispatch_rechecks_exclusions_and_stops_at_uncertain_without_retry(self):
        helper = self.helper(); preview = helper.preview('Michael,03001234567\nAnne,03011234567\nZaid,03021234567')
        self.start(helper, preview)
        self.jobs.eligible = lambda phone: phone != '923001234567'
        def uncertain(body): self.sent.append(body); return {'code': 'UNCERTAIN'}
        self.jobs.send = uncertain
        self.run_job()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]['name'], 'Anne')
        self.assertEqual(self.jobs.status()['failed'], 1)
        self.assertEqual(self.jobs.status()['skipped'], 1)
        self.start(helper, preview)
        self.assertEqual(len(self.sent), 1)

    def test_duplicate_saved_wording_is_rejected_instead_of_reusing_a_caption(self):
        helper = self.helper(); preview = helper.preview('Michael,03001234567\nAnne,03011234567')
        self.jobs.variants = lambda count: ['Same saved wording'] * count
        with self.assertRaisesRegex(ValueError, 'different messages'):
            self.start(helper, preview)
        self.assertFalse(self.sent)
        self.assertEqual(self.jobs.status()['state'], 'Idle')


class PastedNameIntegrationTests(unittest.TestCase):
    def test_mutate_update_rejects_stale_timestamp_and_preserves_field_whitelist(self):
        from test_donor_hub import IntegrationTests
        fixture = IntegrationTests(); fixture.setUp()
        try:
            registry = fixture.app.donors()
            with patch('donor_book.time.time', return_value=1000.):
                donor = registry.book.add('Ali', '03001234567')['donor']
            with patch('donor_book.time.time', return_value=1001.):
                registry.book.update(donor['id'], notes='Newer note')
            with self.assertRaises(ValueError):
                registry.mutate({'action': 'update', 'id': donor['id'],
                    'expected_updated_at': 1000., 'notes': 'Stale note'})
            self.assertEqual(registry.book.resolve(donor['id'])['notes'], 'Newer note')
            result = registry.mutate({'action': 'update', 'id': donor['id'],
                'expected_updated_at': 1001., 'notes': 'Accepted note', 'phone': '03011234567'})
            self.assertEqual(result['donor']['notes'], 'Accepted note')
            self.assertEqual(registry.book.resolve(donor['id'])['phone'], '923001234567')
        finally:
            fixture.tearDown()

    def test_explicit_names_personalize_without_reinterpreting_registry_labels(self):
        from test_donor_hub import IntegrationTests
        fixture = IntegrationTests(); fixture.setUp()
        try:
            registry = fixture.app.donors()
            self.assertEqual(registry.personal_name('Michael'), ('', 'Brother'))
            self.assertEqual(registry.personal_name('Michael', explicit=True), ('Michael', 'Brother'))
            self.assertEqual(registry.personal_name('Ayesha', explicit=True), ('Ayesha', 'Sister'))
            for label in ('Jr Accounts', 'Random23', 'Preview demo', 'Ali / shop'):
                self.assertEqual(registry.personal_name(label, explicit=True), ('', 'Brother'))
        finally:
            fixture.tearDown()

    def test_pasted_batch_preserves_daily_fifty_limit_without_outbound_calls(self):
        from test_donor_hub import IntegrationTests
        fixture = IntegrationTests(); fixture.setUp()
        try:
            app = fixture.app; registry = app.donors()
            day = app.datetime.datetime.fromtimestamp(time.time(), app.datetime.timezone(app.datetime.timedelta(hours=5))).date().isoformat()
            app.STORE.put('dm_daily', {'day': day, 'count': 50, 'last': 0})
            preview = registry.pasted.preview('Michael,03001234567')
            with patch('donor_delivery.threading.Thread.start'):
                registry.pasted.start(preview['token'], request_id='daily-cap-pasted-test')
            with patch.object(app, 'send_image') as outbound:
                registry.jobs._run(registry.jobs._load()['jobs'][-1])
                outbound.assert_not_called()
            status = registry.jobs.status()
            self.assertEqual(status['sent'], 0)
            self.assertEqual(status['state'], 'Stopped')
            self.assertIn('50-DM', status['error'])
        finally:
            fixture.tearDown()


if __name__ == '__main__': unittest.main()

