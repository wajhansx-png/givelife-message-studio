# University group finder

Open **Settings → University group finder → Find groups**, or `/group-finder` on the studio host. It uses the studio's existing private access key. Refresh preserves the page, filter and search in the URL. Pasted import text is retained on this device until successfully saved.

## Scope

This release researches public university community invitations. It does not join groups, extract members, message people, change donor/financial records, or add discovered groups to campaign targets. A Ready record is research evidence, not authorization for an unrelated sending workflow.

Four starter institutions are included: LUMS, IBA Karachi, Beaconhouse National University and Institute of Business Management. Their domains were checked against the public institutional websites on 2026-10-30. No student wealth, fee amount or donation likelihood is inferred. Add further institutions and select research targets under Universities.

## Evidence and ranking

Each group stores exact invitation identity, multiple source references, bounded source excerpts, university attribution, a revision number and an audit trail. Invitation tokens remain case-sensitive; tracking parameters do not create new records. Conflicting university attribution needs explicit review. Repeated discovery cannot reset owner permission checks.

Scores are explainable and total at most 100: verified affiliation 30, freshly fetched configured official source 15, relevant society/alumni title 15, checked member posting 10, charity permission 15, checked activity 5, documented annual tuition context up to 10. Scores are prioritization heuristics, not measured probabilities or individual wealth scores.

Ready requires all of the following with affirmative, fresh evidence: affiliation (90 days), invitation validity (7 days), current account membership (24 hours), all-member posting (24 hours), charity approval (30 days). Expiry is evaluated when records are read. Owner exclusion, explicit charity denial or rejected affiliation prevents readiness regardless of score. Denial remains effective until deliberately changed.

Only an actually fetched configured university-domain page can automatically establish source association. A pasted URL, group name, search snippet or page instruction cannot prove posting/charity permission. Reviews require the current revision, evidence description and an explicit confirmation checkbox. Account checks match an exact manually mapped joined-group ID, inspect explicit Boolean announce settings and never assume missing fields mean members can post. Account failures preserve existing evidence.

Optional annual tuition in PKR needs owner-checked official-source evidence. It is contextual metadata, not a donation or a financial-account mutation. Fees expire from ranking after 180 days.

## Search providers

The default **public RSS search feed** requires no API key. It is experimental/best effort, not a supported Google search integration. A live read-only smoke test returned search results, but some advanced queries were ignored by the provider. Site restrictions and relevance are now checked; ignored restrictions, challenge pages and failures are reported rather than presented as verified results or reliable empty searches. This release does not guarantee finding private/unindexed groups, search completeness or a minimum number of suitable communities.

For a supported search API, the optional Brave adapter uses `GROUP_SEARCH_PROVIDER=brave` and server-only `BRAVE_SEARCH_API_KEY`. It was verified with synthetic responses against the documented interface, not a live paid account. No paid provider, plan or billing was configured. Provider credentials are sent only in the subscription header and are stripped across cross-origin redirects; they never enter URLs or research records. See https://api-dashboard.search.brave.com/app/documentation/web-search/get-started.

Import public invitations if a provider is unavailable. Imported links remain unverified. No captcha bypass or hidden browser impersonation is used.

## Reliability and limits

Research runs immediately on explicit Find groups, or on an explicitly enabled 6–168-hour schedule. Default schedule is OFF. Schedules are separate from sending Auto and never change owner sending revisions or DM/group campaign controls. Free sleeping hosts cannot guarantee exact scheduled execution; overdue research runs when the service resumes.

Jobs persist queries, results, source reservations, completed steps, progress and errors. A database transaction serializes claims; expiring leases fence old workers. Evidence, lease validation and discovery counters commit together. Cancellation is checked after fetches and at final completion. Pending source work survives a restart, reuses its logical page reservation and cached search results, and has bounded retry attempts. Five worker claims per job prevent endless restart loops. Repeated request IDs return the same job; changing the scope under the same ID conflicts. Only one research job runs at a time.

Each run allows 1–20 queries and 1–40 logical source pages; defaults are 12 and 20. At most 10 results/query and 20 invitations/page are processed. A run has a 240-second processing budget, bounded network reads (15-second transport watchdog), 512KB response caps, a one-second minimum host interval, safe HTTPS redirects, DNS address checks, pinned TLS connections and crawler-rule checks before source pages, including redirects. Private/reserved addresses, non-text downloads and XML entities are rejected. Search feeds/APIs use their fixed explicit query endpoints; ordinary source pages respect robots rules.

Local development uses transactional SQLite in DATA_DIR. Production uses one new state key `university_group_finder_v1` in the existing CloudStore table with PostgreSQL row locks, avoiding changes to donor schemas. Maximum 5,000 groups, 200 universities, 30 source references/group, 1,000 audit entries and 30 recent jobs. Request-id retention follows the retained job window. An old ID replayed after retention may start new read-only research. Storage/record failures preserve existing data and do not prevent the rest of the studio from starting.

## Verification

Synthetic tests cover identity confusion, generated URL/permission combinations, concurrent independent book instances, stale revisions, source trust, expiry, missing/false permissions, provider failures, robots/redirects, private networks, response caps, slow responses, durable claims, cancellation during final fetch, interrupted fetch recovery, old-worker fencing, API authentication, origin checks and separation from outbound workflows.

Run `python -m unittest discover -s tests -p 'test_*.py' -q`, `pnpm test`, and `pnpm exec playwright test --config playwright.group-finder.config.cjs`. The dedicated browser fixture removes database/model credentials and uses synthetic search and websites. Its authenticated shutdown route exists only in that test fixture. Mobile/tablet/desktop checks use 320, 390, 768 and 1440px viewports. No tests contact WhatsApp recipients or modify production donor/payment data.

Remaining verification limits: live account permission schema/availability and real PostgreSQL concurrency are not exercised by synthetic tests; Brave live integration requires an independently configured account; search-provider coverage and university membership cannot be guaranteed. There is no automatic joining or outreach in this release.
