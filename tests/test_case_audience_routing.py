"""Case audience routing and actual dispatch order; fake transport only."""
import copy
import json
import threading
import urllib.error
import urllib.request
import unittest
from unittest.mock import patch

from test_case_run import Base
from test_manual_sends import app
import case_run


class Routing(Base):
    def setUp(self):
        super().setUp()
        self.ids = {}
        for i, (name, group, rank) in enumerate([
            ('Normal low', '', 1), ('Normal high', '', 2),
            ('First cohort later', 'GIKI 1', 2), ('First cohort first', 'GIKI 1', 1),
            ('Second cohort later', 'GIKI 2', 2), ('Second cohort first', 'GIKI 2', 1),
            ('Not a cohort', 'GIKI alumni', 1),
        ]):
            r = self.h.book.add(name, '923004440%03d' % i)['donor']
            self.h.book.update(r['id'], important=True)
            self.h.book.update(r['id'], top_donor=True)
            self.ids[name] = r['id']
        data = self.h.book._load()
        for r, (_, group, rank) in zip(data['records'], [
            ('', '', 1), ('', '', 2), ('', 'GIKI 1', 2), ('', 'GIKI 1', 1),
            ('', 'GIKI 2', 2), ('', 'GIKI 2', 1), ('', 'GIKI alumni', 1),
        ]):
            r.update(group=group, group_order=rank)
            if r['id'] == self.ids['Normal high']:
                r['normal_amount'] = 5000
        self.h.book._save(data)
        self.calls = []
        self.reserved = []
        reserve = self.h.jobs.reserve
        def reserve_messages(count):
            texts = reserve(count)
            self.reserved.extend(texts)
            return texts
        self.h.jobs.reserve = reserve_messages
        self.h.jobs.send = lambda body: self.calls.append(copy.deepcopy(body)) or {'code': 'SUCCESS'}
        self.h.jobs._gap = lambda j: 0
        self.h.jobs._rest = lambda j, b: 0
        self.addCleanup(self.stop_everything)

    def plan(self, enabled):
        self.cr.set_plan({k: {'enabled': k in enabled} for k in (*case_run.ROWS, 'giki1', 'giki2')})

    def expected(self, enabled):
        one = [self.ids[n] for n in ('First cohort first', 'First cohort later')]
        two = [self.ids[n] for n in ('Second cohort first', 'Second cohort later')]
        claimed = (one if 'giki1' in enabled else []) + (two if 'giki2' in enabled else [])
        top = [r['id'] for r in self.h.book.recipients('top') if r['id'] not in claimed]
        return {'giki1': one if 'giki1' in enabled else [],
                'giki2': two if 'giki2' in enabled else [],
                'top': top if 'top' in enabled else []}

    def check_combination(self, enabled):
        self.plan(enabled)
        expected = self.expected(enabled)
        aud = self.cr.summary()['audiences']
        for key, ids in expected.items():
            self.assertEqual(aud[key], ids, key)
        if not enabled:
            self.assertTrue(self.cr.summary()['blockers'])
            self.assertEqual(self.calls, [])
            return
        with patch.object(app, 'set_auto') as group:
            self.approve()
            self.assertTrue(self.tick_until(lambda: not self.h.jobs.active and all(
                self.state()['rows'][k]['state'] in ('done', 'off')
                for k in ('giki1', 'giki2', 'top'))))
            self.assertEqual(group.called, 'group' in enabled)
        appeals = [c for c in self.calls if c['kind'] == 'donor_batch']
        ids = expected['giki1'] + expected['giki2'] + expected['top']
        self.assertEqual([c['phone'] for c in appeals], [self.phone(i) for i in ids])
        self.assertEqual(len(appeals), len({c['phone'] for c in appeals}))
        self.assertTrue(all(c['target'] == 'phone' for c in self.calls))
        self.assertEqual([c['message'] for c in appeals], self.reserved)
        follow = [c for c in self.calls if c['kind'] == 'owner_text']
        self.assertEqual([c['phone'] for c in follow],
                         [self.phone(i) for i in expected['giki1'] + expected['giki2']])
        # zero extra calls: nothing but those appeals and those follow-up questions, all from the main account
        self.assertEqual(len(self.calls), len(appeals) + len(follow), [c['kind'] for c in self.calls])
        self.assertFalse([c for c in self.calls if c.get('line')])

    def test_selected_delivery_preserves_requested_order_before_limit(self):
        ids = [self.ids['Normal high'], self.ids['Normal low']]
        self.h.jobs.start('selected', ids=ids, limit=1, run=False, fresh=True)
        job = self.h.jobs.export_jobs()['jobs'][-1]
        self.assertEqual(job['ids'], ids[:1])

    def test_new_mode_does_not_resume_another_modes_selected_queue(self):
        ids = [self.ids['Normal high'], self.ids['Normal low']]
        self.h.jobs.start('selected', ids=ids[:1], owner='case_giki1', run=False)
        jobs = self.h.jobs.export_jobs()
        jobs['jobs'][-1].update(state='Stopped')
        self.h.jobs.import_jobs(jobs)
        self.h.jobs.active = None
        self.h.jobs.start('selected', ids=ids, owner='case_top', run=False)
        self.assertEqual(self.h.jobs.export_jobs()['jobs'][-1]['ids'], ids)

    def test_legacy_merged_giki_requires_fresh_selection(self):
        st = self.cr._blank()
        st['plan']['giki'] = st['plan'].pop('giki1', copy.deepcopy(st['plan']['top']))
        st['plan'].pop('giki2', None)
        st.update(status='running', approved={'ids': {'giki': list(self.ids.values())}},
                  rows={'giki': {'state': 'running', 'job': 'legacy', 'engine': 'donors'}})
        self.cr._write(st)
        self.h.jobs.active = 'legacy'
        with patch.object(self.h.jobs, 'cancel') as cancel:
            v = self.cr.view()
            cancel.assert_called_once()
        self.h.jobs.active = None
        self.assertEqual(v['status'], 'idle')
        self.assertFalse(v['approved'])
        self.assertFalse(self.state()['plan']['giki1']['enabled'])
        self.assertFalse(self.state()['plan']['giki2']['enabled'])
        self.assertEqual(self.calls, [])

    def test_switching_each_dm_mode_never_inherits_a_stopped_audience(self):
        ids = [self.ids['Normal high'], self.ids['Normal low']]
        for old in ('case_giki1', 'case_giki2', 'case_top'):
            for new in ('case_giki1', 'case_giki2', 'case_top'):
                with self.subTest(old=old, new=new):
                    self.h.jobs.import_jobs({'jobs': []})
                    self.h.jobs.active = None
                    self.h.jobs.start('selected', ids=ids[:1], owner=old, run=False)
                    jobs = self.h.jobs.export_jobs()
                    jobs['jobs'][-1].update(state='Stopped')
                    self.h.jobs.import_jobs(jobs)
                    self.h.jobs.active = None
                    self.h.jobs.start('selected', ids=ids, owner=new, run=False)
                    self.assertEqual(self.h.jobs.export_jobs()['jobs'][-1]['ids'], ids)

    def test_unknown_or_missing_row_cannot_send(self):
        for key in (None, '', 'giki', 'unknown', 'group'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.cr._start_row(self.cr._blank(), key)
        self.assertEqual(self.calls, [])

    def test_manual_dm_endpoint_refuses_missing_or_unknown_audience(self):
        http = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        with patch.object(self.h, 'start_batch', return_value={}) as start:
            for body in ({}, {'scope': None}, {'scope': 'groups'}, {'scope': 'giki'}):
                req = urllib.request.Request(
                    f'http://127.0.0.1:{http.server_port}/donor-delivery',
                    data=json.dumps(body).encode(),
                    headers={'Content-Type': 'application/json',
                             'Authorization': 'Bearer test-only-studio-access-key'},
                )
                with self.subTest(body=body):
                    try:
                        with urllib.request.urlopen(req, timeout=3) as response:
                            status, result = response.status, json.load(response)
                    except urllib.error.HTTPError as response:
                        status, result = response.code, json.load(response)
                    self.assertEqual(status, 400)
                    self.assertIn('audience', result['error'].lower())
            start.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_dm_sender_refuses_group_or_missing_recipient_type(self):
        for body in ({'target': 'main', 'phone': '923001234567'},
                     {'target': 'phone', 'phone': '120363000000000@g.us'},
                     {'phone': '923001234567'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.h.jobs._dispatch({'id': 'fake'}, body, [], 0, 0)
        self.assertEqual(self.calls, [])

    def test_giki_does_not_require_top_flag_or_match_similar_group_names(self):
        first = self.ids['First cohort first']
        self.h.book.update(first, top_donor=False)
        self.plan({'giki1'})
        aud = self.cr.summary()['audiences']
        self.assertIn(first, aud['giki1'])
        self.assertNotIn(self.ids['Not a cohort'], aud['giki1'])

    def test_each_cohort_keeps_its_own_timing(self):
        self.plan({'giki1', 'giki2', 'top'})
        self.cr.set_plan({'giki1': {'gap_minutes': 2, 'batch_size': 3},
                          'giki2': {'gap_minutes': 7, 'batch_size': 4}})
        plan = self.state()['plan']
        self.assertEqual((plan['giki1']['gap_minutes'], plan['giki1']['batch_size']), (2, 3))
        self.assertEqual((plan['giki2']['gap_minutes'], plan['giki2']['batch_size']), (7, 4))
        self.assertEqual((plan['top']['gap_minutes'], plan['top']['batch_size']), (5, 10))
        self.assertEqual(self.calls, [])

    def test_adding_a_cohort_does_not_claim_people_already_approved_for_donors(self):
        self.plan({'top'})
        with patch.object(self.cr, 'tick'):
            self.approve()
        before = self.state()['approved']['ids']['top']
        summary = self.cr.summary('giki1')
        self.assertEqual(summary['audiences']['giki1'], [])
        self.assertIn('No one is waiting in GIKI 1.', summary['blockers'])
        self.assertEqual(self.state()['approved']['ids']['top'], before)

    def test_mode_change_cannot_replace_active_dm_queue(self):
        ids = [self.ids['Normal high'], self.ids['Normal low']]
        self.h.jobs.start('selected', ids=ids[:1], owner='case_giki1', run=False)
        original = self.h.jobs.export_jobs()['jobs'][-1]
        self.h.jobs.active = original['id']
        with self.assertRaisesRegex(ValueError, 'already running'):
            self.h.jobs.start('selected', ids=ids[1:], owner='case_giki2', run=False)
        self.assertEqual(self.h.jobs.active, original['id'])
        self.assertEqual(self.h.jobs.export_jobs()['jobs'], [original])
        self.h.jobs.active = None
        self.assertEqual(self.calls, [])

    def test_pausing_one_cohort_does_not_share_for_it_or_pause_the_other(self):
        self.plan({'giki1', 'giki2'})
        with patch.object(self.cr, 'tick'):
            self.approve()
        st = self.state()
        st['rows']['giki1']['state'] = 'paused'
        st['rows']['giki2']['state'] = 'done'
        for key, name in [('giki1', 'First cohort first'), ('giki2', 'Second cohort first')]:
            did = self.ids[name]
            st['giki'][self.phone(did)] = dict(row=key, id=did, name=name, step='agreed', shared=0)
        self.cr._write(st)
        self.cr._flow()
        self.assertEqual([r[0] for r in self.shared], [self.phone(self.ids['Second cohort first'])])


# All 16 switch combinations of GIKI 1, GIKI 2, Top Donors and Groups (every one its own test).
for _mask in range(16):
    _on = {k for n, k in enumerate(('giki1', 'giki2', 'top', 'group')) if _mask >> n & 1}
    setattr(Routing, 'test_switches_' + ('_'.join(sorted(_on)) or 'all_off'),
            lambda self, e=_on: self.check_combination(e))

if __name__ == '__main__':
    unittest.main()
