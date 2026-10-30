"""Bounded public-source discovery with durable claims. Never joins or messages a group."""
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from group_finder import Conflict, normalize_invite, public_url, text

MAX_BYTES = 512_000
LEASE_SECONDS = 360
USER_AGENT = 'GiveLifeResearch/1.0'


class ResearchError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class LostLease(ResearchError):
    def __init__(self): super().__init__('lost_lease', 'Another worker now owns this research job.')


class ResearchCancelled(RuntimeError):
    pass


@dataclass
class Document:
    url: str
    text: str
    content_type: str = 'text/html'


def public_addresses(host):
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({info[4][0] for info in infos})
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ResearchError('private_address', 'Private or reserved network destinations are not allowed.')
        return addresses
    except (OSError, ValueError):
        raise ResearchError('dns_failed', 'The source address could not be verified.')


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, timeout):
        super().__init__(host, timeout=timeout)
        self.ip = ip

    def connect(self):
        # Pin the checked address while keeping TLS certificate/hostname validation.
        raw = socket.create_connection((self.ip, 443), self.timeout)
        self.sock = raw
        try: self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def https_transport(host, ip, path, timeout=8, max_bytes=MAX_BYTES, headers=None):
    connection = PinnedHTTPS(host, ip, timeout)
    deadline = time.monotonic() + 15
    expired = threading.Event()
    wire = []
    def abort():
        expired.set()
        sock = wire[0] if wire else connection.sock
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        connection.close()
    timer = threading.Timer(15, abort)
    timer.daemon = True
    timer.start()
    try:
        connection.request('GET', path, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity',
                           'Accept': 'text/html,application/rss+xml,application/xml,text/plain,application/json', **(headers or {})})
        wire.append(connection.sock)
        response = connection.getresponse()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        length = response_headers.get('content-length', '')
        if length.isdigit() and int(length) > max_bytes:
            raise ResearchError('too_large', 'Source exceeds the research size limit.')
        chunks, length_read = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or expired.is_set(): raise ResearchError('source_time_limit', 'Source exceeded the total read time limit.')
            if wire[0] is not None: wire[0].settimeout(min(timeout, remaining))
            chunk = response.read1(min(65536, max_bytes + 1 - length_read))
            if not chunk: break
            chunks.append(chunk)
            length_read += len(chunk)
            if length_read > max_bytes: raise ResearchError('too_large', 'Source exceeds the research size limit.')
        return response.status, response_headers, b''.join(chunks)
    except (OSError, http.client.HTTPException):
        if expired.is_set(): raise ResearchError('source_time_limit', 'Source exceeded the total read time limit.')
        raise ResearchError('source_unavailable', 'Source could not be read within the time limit.')
    finally:
        timer.cancel()
        connection.close()


class SafeReader:
    def __init__(self, transport=https_transport, sleep=time.sleep):
        self.transport, self.sleep = transport, sleep
        self.last_host, self.robots_cache = {}, {}
        self.lock = threading.RLock()

    def _load(self, url, headers=None, on_redirect=None):
        origin = urlsplit(public_url(url)).hostname
        for _ in range(4):
            url = public_url(url)
            parts = urlsplit(url)
            ips = public_addresses(parts.hostname)
            with self.lock:
                delay = max(0, 1 - (time.monotonic() - self.last_host.get(parts.hostname, 0)))
                if delay: self.sleep(delay)
                self.last_host[parts.hostname] = time.monotonic()
            path = parts.path + ('?' + parts.query if parts.query else '')
            status, response_headers, body = self.transport(parts.hostname, ips[0], path, headers=headers if parts.hostname == origin else None)
            response_headers = {k.lower(): v for k, v in response_headers.items()}
            if len(body) > MAX_BYTES: raise ResearchError('too_large', 'Source exceeds the research size limit.')
            if status in (301, 302, 303, 307, 308):
                location = response_headers.get('location')
                if not location: raise ResearchError('redirect_invalid', 'Source returned an incomplete redirect.')
                url = public_url(urljoin(url, location))
                if on_redirect: on_redirect(url)
                continue
            if status != 200: raise ResearchError('http_' + str(status), 'Source returned HTTP ' + str(status) + '.')
            if response_headers.get('content-encoding', 'identity').lower() not in ('', 'identity'):
                raise ResearchError('encoding_unsupported', 'Compressed responses are not accepted by this research reader.')
            content_type = response_headers.get('content-type', '').split(';')[0].strip().lower()
            if content_type not in ('text/html', 'application/xhtml+xml', 'text/plain', 'application/rss+xml', 'application/xml', 'text/xml', 'application/json'):
                raise ResearchError('unsupported_type', 'This source is not a readable public text page.')
            return Document(url, body.decode('utf-8', errors='replace'), content_type)
        raise ResearchError('redirect_limit', 'The source redirected too many times.')

    def _check_robots(self, url):
        url = public_url(url)
        key = 'https://' + urlsplit(url).hostname
        cached = self.robots_cache.get(key)
        if not cached or time.monotonic() - cached[0] > 3600:
            parser = RobotFileParser()
            try:
                document = self._load(key + '/robots.txt')
                parser.parse(document.text.splitlines())
            except ResearchError as exc:
                if exc.code == 'http_404': parser.parse(['User-agent: *', 'Allow: /'])
                else: raise ResearchError('robots_unavailable', 'Could not verify this source’s crawler rules.')
            cached = self.robots_cache[key] = (time.monotonic(), parser)
        if not cached[1].can_fetch(USER_AGENT, url):
            raise ResearchError('robots_denied', 'The source does not allow this research reader.')

    def fetch(self, url, robots=True, headers=None):
        url = public_url(url)
        if robots: self._check_robots(url)
        return self._load(url, headers, on_redirect=self._check_robots if robots else None)


class SourceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.links, self.parts, self.title_parts = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'): self.skip += 1
        if tag == 'title': self.in_title = True
        if not self.skip and tag == 'a':
            href = dict(attrs).get('href', '')
            if href: self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'): self.skip = max(0, self.skip - 1)
        if tag == 'title': self.in_title = False

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
            if self.in_title: self.title_parts.append(data)


def extract_invites(body):
    parser = SourceParser()
    parser.feed(body[:MAX_BYTES])
    plain = ' '.join(parser.parts)
    links = set()
    candidates = parser.links + re.findall(r'https://chat\.whatsapp\.com/[A-Za-z0-9]{22}(?![A-Za-z0-9])', plain)
    for value in candidates:
        try: links.add(normalize_invite(value))
        except ValueError: pass
    return sorted(links)[:20], ' '.join(parser.title_parts).strip()[:180], plain[:1000]


def parse_rss(body):
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', body, re.I):
        raise ResearchError('provider_invalid', 'Search returned unsupported XML declarations.')
    try: root = ET.fromstring(body)
    except ET.ParseError: raise ResearchError('provider_invalid', 'Public search did not return a usable result feed.')
    if root.tag.lower() != 'rss': raise ResearchError('provider_unavailable', 'Public search returned a challenge or unsupported page.')
    results = []
    for item in root.findall('./channel/item')[:10]:
        try: url = public_url(item.findtext('link', ''))
        except ValueError: continue
        results.append({'url': url, 'title': text(html.unescape(item.findtext('title', '')), 180),
                        'excerpt': text(html.unescape(item.findtext('description', '')), 1000)})
    return results


class PublicSearch:
    name = 'Public search feed (best effort, no API key)'
    def __init__(self, reader): self.reader = reader
    def search(self, query):
        # Fixed public RSS endpoint; no SERP scraping, captcha bypass, or browser impersonation.
        url = 'https://www.bing.com/search?' + urlencode({'q': query, 'format': 'rss', 'count': 8})
        results = parse_rss(self.reader.fetch(url, robots=False).text)
        had_results = bool(results)
        restriction = re.search(r'(?:^|\s)site:([A-Za-z0-9.-]+)', query)
        if restriction:
            domain = restriction[1].lower()
            results = [r for r in results if (urlsplit(r['url']).hostname or '') == domain or (urlsplit(r['url']).hostname or '').endswith('.' + domain)]
        if 'whatsapp' in query.lower() and results:
            results = [r for r in results if re.search(r'whatsapp|societ|welfare|alumni|charit|volunteer|club', r['url'] + ' ' + r['title'] + ' ' + r['excerpt'], re.I)]
        # Some public RSS responses ignore advanced search operators. Never present that as a reliable empty search.
        if had_results and not results:
            raise ResearchError('provider_low_relevance', 'Public search did not honor the requested source restriction. Try another query or configure a search API.')
        return results


class BraveSearch:
    name = 'Brave Search API'
    def __init__(self, reader, key): self.reader, self.key = reader, key
    def search(self, query):
        if not self.key: raise ResearchError('provider_configuration', 'Brave Search is selected but its server API key is not configured.')
        url = 'https://api.search.brave.com/res/v1/web/search?' + urlencode({'q': query, 'count': 10, 'safesearch': 'moderate'})
        document = self.reader.fetch(url, robots=False, headers={'X-Subscription-Token': self.key, 'Accept': 'application/json'})
        try:
            payload = json.loads(document.text)
            rows = payload.get('web', {}).get('results', [])
            if not isinstance(rows, list): raise ValueError('Malformed search results')
            result = []
            for row in rows[:10]:
                if not isinstance(row, dict): continue
                try: url = public_url(row.get('url', ''))
                except ValueError: continue
                result.append({'url': url, 'title': text(row.get('title', ''), 180), 'excerpt': text(row.get('description', ''), 1000)})
            return result
        except (ValueError, TypeError, AttributeError):
            raise ResearchError('provider_invalid', 'The search API returned malformed results.')


def configured_search(reader):
    provider = os.environ.get('GROUP_SEARCH_PROVIDER', 'public').strip().lower()
    if provider == 'brave': return BraveSearch(reader, os.environ.get('BRAVE_SEARCH_API_KEY', ''))
    return PublicSearch(reader)


def posting_from_group(group):
    if not isinstance(group, dict): return 'unknown'
    announce = group.get('GroupAnnounce')
    value = announce.get('IsAnnounce') if isinstance(announce, dict) else group.get('IsAnnounce', group.get('is_announce'))
    return 'admins_only' if value is True else 'all_members' if value is False else 'unknown'


def query_plan(universities):
    out = []
    templates = ['"{name}" "chat.whatsapp.com"', 'site:{domain} whatsapp society',
                 '"{name}" alumni whatsapp group', '"{name}" welfare society whatsapp',
                 '"{name}" student club whatsapp', 'site:{domain} alumni charity volunteer']
    for template in templates:
        for uni in universities:
            name = uni['name'].replace('"', ' ')
            query = template.format(name=name, domain=uni['domains'][0])
            out.append({'university_id': uni['id'], 'query': query,
                        'id': hashlib.sha256((uni['id'] + query).encode()).hexdigest()[:20]})
    return out


class ResearchService:
    def __init__(self, book, search=None, reader=None):
        self.book = book
        self.reader = reader or SafeReader()
        self.search = search or configured_search(self.reader)
        self.owner = uuid.uuid4().hex
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None

    def _enqueue(self, data, university_ids, request_id, max_queries, max_pages):
        if not isinstance(university_ids, list) or not 1 <= len(university_ids) <= 50 or any(not isinstance(x, str) for x in university_ids):
            raise ValueError('Choose between 1 and 50 universities.')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', request_id): raise ValueError('Use a unique research request id.')
        if type(max_queries) is not int or not 1 <= max_queries <= 20 or type(max_pages) is not int or not 1 <= max_pages <= 40:
            raise ValueError('Use 1–20 queries and 1–40 source pages per run.')
        ids = sorted(set(university_ids))
        unis = [self.book._find(data['universities'], ident) for ident in ids]
        digest = hashlib.sha256(json.dumps([ids, max_queries, max_pages]).encode()).hexdigest()
        prior = data['requests'].get(request_id)
        if prior:
            if prior['digest'] != digest: raise Conflict('This request id belongs to a different research scope.')
            return self.book._find(data['jobs'], prior['job_id'])
        active = next((j for j in data['jobs'] if j['state'] in ('queued', 'running')), None)
        if active: raise Conflict('Research is already running. Stop it or wait for it to finish.')
        plan = query_plan(unis)
        cursor = data['settings'].get('query_cursor', 0) % len(plan)
        queries = (plan[cursor:] + plan[:cursor])[:max_queries]
        data['settings']['query_cursor'] = (cursor + len(queries)) % len(plan)
        job = {'id': uuid.uuid4().hex, 'request_id': request_id, 'state': 'queued', 'phase': 'Waiting for research worker',
               'created_at': self.book.clock(), 'updated_at': self.book.clock(), 'queries': queries,
               'completed_queries': [], 'queries_succeeded': 0, 'pages_read': 0, 'max_pages': max_pages,
               'new_groups': 0, 'links_seen': 0, 'errors': [], 'owner': '', 'lease_until': 0,
               'visited': [], 'cancel_requested': False, 'provider': self.search.name}
        job.update(pending_query=None, pending_source=None, page_attempts=0, successful_queries=[], claim_count=0)
        data['jobs'] = [j for j in data['jobs'] if j['state'] in ('queued', 'running')][-1:] + [j for j in data['jobs'] if j['state'] not in ('queued', 'running')][-29:] + [job]
        data['requests'][request_id] = {'digest': digest, 'job_id': job['id']}
        kept_ids = {j['id'] for j in data['jobs']}
        data['requests'] = {k: v for k, v in data['requests'].items() if v['job_id'] in kept_ids}
        self.book._audit(data, 'research_queued', job['id'])
        return job

    def start(self, university_ids, request_id, max_queries=12, max_pages=20):
        result = self.book.repo.mutate(lambda data: self._enqueue(data, university_ids, request_id, max_queries, max_pages))
        self.wake.set()
        return result

    def claim(self):
        def change(data):
            now = self.book.clock()
            job = next((j for j in data['jobs'] if j['state'] == 'queued' or j['state'] == 'running' and j['lease_until'] <= now), None)
            if job is None: return None
            if job.get('claim_count', 0) >= 5:
                job.update(state='partial' if job['queries_succeeded'] else 'failed', phase='Research interrupted repeatedly. Existing leads were preserved.', updated_at=now)
                job['errors'].append({'code': 'recovery_limit', 'message': 'Research stopped after five worker claims. Start a new run after checking the service.'})
                return None
            job['claim_count'] = job.get('claim_count', 0) + 1
            job.update(state='running', owner=self.owner, lease_until=now + LEASE_SECONDS, updated_at=now, phase='Searching public university sources')
            return job
        return self.book.repo.mutate(change)

    def checkpoint(self, ident, updates):
        def change(data):
            job = self._owned(data, ident)
            if updates.get('state') in ('completed', 'partial', 'failed') and job['cancel_requested']:
                updates.update(state='cancelled', phase='Research stopped; saved sources were preserved')
            job.update(updates, lease_until=self.book.clock() + LEASE_SECONDS, updated_at=self.book.clock())
            return job
        return self.book.repo.mutate(change)

    def _owned(self, data, ident):
        job = self.book._find(data['jobs'], ident)
        if job['state'] != 'running' or job['owner'] != self.owner or job['lease_until'] <= self.book.clock(): raise LostLease()
        return job

    def _check_stop(self, job):
        if job['cancel_requested'] or self.stop_event.is_set(): raise ResearchCancelled()

    def _error(self, ident, exc, **context):
        job = self.checkpoint(ident, {})
        errors = job['errors'] + [{'code': getattr(exc, 'code', 'invalid_source'), 'message': str(exc)[:250], **context}]
        return self.checkpoint(ident, {'errors': errors[-100:]})

    def _save_candidate(self, ident, university_id, invite, source_url, **evidence):
        def guard(data): self._check_stop(self._owned(data, ident))
        def counted(data, created):
            job = self._owned(data, ident)
            job['new_groups'] += int(created)
            job['links_seen'] += 1
            job.update(updated_at=self.book.clock(), lease_until=self.book.clock() + LEASE_SECONDS)
        # Lease check, evidence mutation and counters commit in the SAME storage transaction.
        self.book.discover(invite, university_id, source_url, guard=guard, on_discover=counted, **evidence)
        return self.checkpoint(ident, {})

    def _fetch_page(self, ident, source):
        job = self.checkpoint(ident, {})
        self._check_stop(job)
        recovering = bool(job.get('pending_source'))
        if not recovering and job['pages_read'] >= job['max_pages']: return job
        if job.get('page_attempts', 0) >= job['max_pages'] + 5:
            job = self._error(ident, ResearchError('source_recovery_limit', 'Interrupted source exceeded its recovery budget.'), source=source['url'])
            return self.checkpoint(ident, {'pending_source': None, 'visited': list(dict.fromkeys(job['visited'] + [source['url']]))})
        job = self.checkpoint(ident, {'pending_source': source, 'pages_read': job['pages_read'] + (0 if recovering else 1),
                                     'page_attempts': job.get('page_attempts', 0) + 1})
        try:
            document = self.reader.fetch(source['url'])
        except (ResearchError, ValueError) as exc:
            job = self._error(ident, exc, source=source['url'])
        else:
            # Cancellation with zero extracted links must also be checked after the read.
            self._check_stop(self.checkpoint(ident, {}))
            invites, title, excerpt = extract_invites(document.text)
            for invite in invites:
                job = self._save_candidate(ident, source['university_id'], invite, document.url,
                                           title=title or source.get('title', ''), excerpt=excerpt, source_verified=True)
        job = self.checkpoint(ident, {})
        return self.checkpoint(ident, {'pending_source': None, 'visited': list(dict.fromkeys(job['visited'] + [source['url']]))})

    def cancel(self, ident):
        def change(data):
            job = self.book._find(data['jobs'], ident)
            job['cancel_requested'] = True
            if job['state'] == 'queued': job.update(state='cancelled', phase='Research stopped before starting', updated_at=self.book.clock())
            self.book._audit(data, 'research_stop_requested', ident)
            return job
        return self.book.repo.mutate(change)

    def configure_schedule(self, enabled, interval_hours, university_ids):
        if not isinstance(enabled, bool) or isinstance(interval_hours, bool): raise ValueError('Invalid research schedule.')
        try: hours = float(interval_hours)
        except (ValueError, TypeError): raise ValueError('Choose a research interval between 6 and 168 hours.')
        if not 6 <= hours <= 168: raise ValueError('Choose a research interval between 6 and 168 hours.')
        if not isinstance(university_ids, list) or not 1 <= len(university_ids) <= 50: raise ValueError('Choose universities for research.')
        def change(data):
            for ident in university_ids: self.book._find(data['universities'], ident)
            data['settings'].update(enabled=enabled, interval_hours=hours, university_ids=sorted(set(university_ids)), next_at=self.book.clock() if enabled else 0,
                                    schedule_revision=uuid.uuid4().hex[:12])
            self.book._audit(data, 'research_schedule_changed', 'settings')
            return data['settings']
        return self.book.repo.mutate(change)

    def tick(self):
        def change(data):
            settings = data['settings']
            if not settings['enabled'] or settings['next_at'] > self.book.clock(): return None
            if any(j['state'] in ('queued', 'running') for j in data['jobs']): return None
            due = settings['next_at']
            job = self._enqueue(data, settings['university_ids'], 'scheduled-' + settings.get('schedule_revision', 'initial') + '-' + str(int(due)), 12, 20)
            settings['next_at'] = self.book.clock() + settings['interval_hours'] * 3600
            return job
        return self.book.repo.mutate(change)

    def run_once(self):
        job = self.claim()
        if job is None: return None
        ident, started = job['id'], time.monotonic()
        try:
            self._check_stop(job)
            if job.get('pending_source'): job = self._fetch_page(ident, job['pending_source'])
            for query in job['queries']:
                job = self.checkpoint(ident, {})
                self._check_stop(job)
                if query['id'] in job['completed_queries']: continue
                if time.monotonic() - started > 240:
                    job = self._error(ident, ResearchError('run_time_limit', 'Run reached its bounded time limit. Start another run for remaining research.'))
                    break
                job = self.checkpoint(ident, {'phase': 'Searching: ' + query['query']})
                try:
                    cached = job.get('pending_query')
                    if cached and cached['id'] == query['id']:
                        results = cached['results']
                    else:
                        results = self.search.search(query['query'])
                        if not isinstance(results, list): raise ResearchError('provider_invalid', 'Search results were malformed.')
                        successful = list(dict.fromkeys(job.get('successful_queries', []) + [query['id']]))
                        job = self.checkpoint(ident, {'pending_query': {'id': query['id'], 'results': results[:10]},
                                                     'successful_queries': successful, 'queries_succeeded': len(successful)})
                    for result in results[:10]:
                        job = self.checkpoint(ident, {})
                        self._check_stop(job)
                        if time.monotonic() - started > 240:
                            raise ResearchError('run_time_limit', 'Run reached its bounded time limit.')
                        url = public_url(result['url'])
                        try:
                            invite = normalize_invite(url)
                        except ValueError: invite = None
                        if invite:
                            job = self._save_candidate(ident, query['university_id'], invite, url, title=result.get('title', ''), excerpt=result.get('excerpt', ''))
                            continue
                        if url in job['visited'] or job['pages_read'] >= job['max_pages']: continue
                        job = self._fetch_page(ident, {'url': url, 'university_id': query['university_id'], 'title': result.get('title', '')})
                except (LostLease, ResearchCancelled): raise
                except (ResearchError, ValueError, KeyError, TypeError) as exc:
                    job = self._error(ident, exc, query=query['query'])
                job = self.checkpoint(ident, {})
                job = self.checkpoint(ident, {'completed_queries': list(dict.fromkeys(job['completed_queries'] + [query['id']])), 'pending_query': None})
            state = 'failed' if not job['queries_succeeded'] else 'partial' if job['errors'] else 'completed'
            phase = ('Search unavailable; review the errors or import public links' if state == 'failed' else
                     'Research finished with source errors' if state == 'partial' else 'Research complete; permission checks remain separate')
            return self.checkpoint(ident, {'state': state, 'phase': phase, 'errors': job['errors'][-100:]})
        except ResearchCancelled:
            try: return self.checkpoint(ident, {'state': 'cancelled', 'phase': 'Research stopped; saved sources were preserved'})
            except LostLease: return None
        except LostLease:
            return None
        except Exception:
            try: return self.checkpoint(ident, {'state': 'failed', 'phase': 'Research interrupted. Existing leads were preserved.',
                                               'errors': job['errors'] + [{'code': 'worker_failed', 'message': 'The worker could not complete this run.'}]})
            except LostLease: return None

    def start_worker(self):
        if self.thread and self.thread.is_alive(): return
        def loop():
            while not self.stop_event.is_set():
                try:
                    data = self.book.repo.read()
                    if data['settings']['enabled']: self.tick()
                    if data['settings']['enabled'] or any(j['state'] in ('queued', 'running') for j in data['jobs']): self.run_once()
                except Exception:
                    # Preserve the job and lease on storage failure; another healthy worker can recover it.
                    pass
                self.wake.wait(30)
                self.wake.clear()
        self.thread = threading.Thread(target=loop, daemon=True, name='university-group-research')
        self.thread.start()
