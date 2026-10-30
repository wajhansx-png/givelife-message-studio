"""Authenticated research commands, separate from every outbound WhatsApp workflow."""
import re
from urllib.parse import parse_qs, urlsplit

from group_finder import GroupBook, text
from group_research import ResearchService, ResearchError, posting_from_group

# Starting research targets, not claims about fees or any individual student's wealth.
# Official domains checked against their public institutional sites on 2026-10-30.
STARTING_UNIVERSITIES = [
    ('LUMS', ['lums.edu.pk'], ['Lahore University of Management Sciences'], 'Lahore'),
    ('IBA Karachi', ['iba.edu.pk'], ['Institute of Business Administration'], 'Karachi'),
    ('Beaconhouse National University', ['bnu.edu.pk'], ['BNU'], 'Lahore'),
    ('Institute of Business Management', ['iobm.edu.pk'], ['IoBM'], 'Karachi'),
]


class GroupFinder:
    def __init__(self, app, book=None, seed=True):
        self.app = app
        self.store = app.STORE
        # The isolated preview uses a non-database fake store. Production's configured CloudStore has connection().
        store = app.STORE if app.STORE is not None and hasattr(app.STORE, 'connection') else None
        self.book = book or GroupBook(app.DATA, store)
        if seed and not self.book.repo.read()['universities']:
            for name, domains, aliases, city in STARTING_UNIVERSITIES:
                self.book.add_university(name, domains, aliases, city)
        self.service = ResearchService(self.book)

    def snapshot(self, path):
        params = parse_qs(urlsplit(path).query)
        result = self.book.list(q=params.get('q', [''])[0], tab=params.get('tab', ['all'])[0],
                                limit=params.get('limit', ['50'])[0], offset=params.get('offset', ['0'])[0])
        return {**result, 'provider': self.service.search.name, 'research_only': True,
                'limits': {'queries_per_run': 20, 'source_pages_per_run': 40, 'groups': 5000},
                'notice': 'Public search is best effort. No groups are joined and no messages are sent. Research schedules run while the cloud service is awake.'}

    def joined_groups(self):
        try: response = self.app.api('/user/my/groups')
        except Exception: raise ResearchError('account_unavailable', 'WhatsApp could not be checked. Reconnect it and try again.')
        if not isinstance(response, dict) or response.get('code') not in (None, 'SUCCESS'):
            raise ResearchError('account_unavailable', 'WhatsApp did not confirm its joined groups. Existing checks were preserved.')
        results = response.get('results')
        if isinstance(results, dict):
            results = next((results[k] for k in ('data', 'groups') if isinstance(results.get(k), list)), None)
        if not isinstance(results, list):
            raise ResearchError('account_unavailable', 'The group list was incomplete. Existing checks were preserved.')
        out = []
        for item in results:
            if not isinstance(item, dict): continue
            jid = str(item.get('JID') or item.get('jid') or item.get('id') or '')
            if not re.fullmatch(r'[0-9-]{5,60}@g\.us', jid): continue
            name = item.get('GroupName')
            name = name.get('Name') if isinstance(name, dict) else item.get('Name') or item.get('name') or item.get('subject')
            out.append({'jid': jid, 'name': text(str(name or 'Unnamed joined group'), 180), 'posting': posting_from_group(item)})
        return out

    def mutate(self, body):
        action = body.get('action')
        if action == 'search':
            job = self.service.start(body.get('university_ids'), body.get('request_id'), body.get('max_queries', 12), body.get('max_pages', 20))
            self.service.start_worker()
            return job
        if action == 'cancel': return self.service.cancel(body.get('id'))
        if action == 'schedule':
            settings = self.service.configure_schedule(body.get('enabled'), body.get('interval_hours', 24), body.get('university_ids'))
            self.service.start_worker()
            self.service.wake.set()
            return settings
        if action == 'university':
            return self.book.add_university(body.get('name'), body.get('domains'), body.get('aliases'), body.get('city', ''), body.get('country', 'Pakistan'))
        if action == 'fee': return self.book.set_fee(body.get('id'), body.get('annual_tuition_pkr'), body.get('source_url'))
        if action == 'import':
            raw = text(body.get('text', ''), 50_000)
            links = list(dict.fromkeys(re.findall(r'https://chat\.whatsapp\.com/[A-Za-z0-9]{22}(?![A-Za-z0-9])', raw)))
            if not links: raise ValueError('Paste at least one valid HTTPS WhatsApp group invitation.')
            if len(links) > 200: raise ValueError('Import at most 200 group links at a time.')
            added = 0
            for link in links:
                row = self.book.discover(link, body.get('university_id'), body.get('source_url') or link, title=body.get('title', ''))
                added += int(row['created'])
            return {'added': added, 'existing': len(links) - added, 'message': 'Links saved for checking; no permissions inferred.'}
        if action == 'review':
            evidence = body.get('evidence')
            if body.get('confirm_observed') is not True or not isinstance(evidence, dict) or evidence.get('kind') not in ('owner_observation', 'admin_confirmation'):
                raise ValueError('Confirm the settings you actually checked. Connected-account checks use their own action.')
            return self.book.review(body.get('id'), body.get('changes'), evidence, body.get('version'))
        if action == 'joined': return {'items': self.joined_groups()}
        if action == 'check_account':
            row = self.book.get(body.get('id'))
            if row['version'] != body.get('version'):
                from group_finder import Conflict
                raise Conflict('This group changed. Refresh its checks before continuing.')
            if not row.get('jid'): raise ValueError('First map this invitation to its exact joined WhatsApp group in Review.')
            groups = self.joined_groups()
            found = next((g for g in groups if g['jid'] == row['jid']), None)
            changes = {'member': 'yes' if found else 'no', 'posting': found['posting'] if found else 'unknown'}
            return self.book.review(row['id'], changes, {'kind': 'account_observation', 'reference': 'Exact group id checked against the linked WhatsApp account group list.'}, row['version'])
        raise ValueError('Choose a supported research action. This module cannot join groups or send messages.')
