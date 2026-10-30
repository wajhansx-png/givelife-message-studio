# University Group Finder Implementation Plan

**Goal:** Find and rank public university community leads, retain evidence, and verify posting/charity permissions without joining groups or sending messages.

**Architecture:** A separate Python research module uses the existing authenticated server and cloud persistence. Deterministic ranking and eligibility use explicit, expiring observations. A bounded durable research queue discovers public sources; web content is data, never instructions. The existing UI gets one Group finder link and a separate responsive research screen.

**Tech stack:** Python standard library, existing PostgreSQL CloudStore, vanilla JavaScript/CSS, unittest, Playwright. No new paid service or required API key.

**Scope approved by user:** Build the group-finding system described in the preceding conversation. Initial geography Pakistan. Search high-fee university communities without claiming individual wealth. No outreach, joining, scraping members, or financial mutations in this stage.

## Rules
- Public search is best effort; blocked/unavailable providers produce explicit errors, never fake results.
- University, link, membership, posting permission, and charity permission have separate evidence and freshness.
- Public snippets cannot verify posting or charity permission.
- Ready requires fresh affirmative evidence; blocked/revoked permission overrides a high ranking.
- Every mutation is versioned; stale edits conflict. Duplicate identities merge source evidence without resetting verification.
- HTTPS source fetching rejects private/reserved networks and validates redirects; responses, execution time and requests are bounded.
- Jobs and schedule settings persist. Overlapping workers use durable claims; research is repeatable, sending is absent.
- Existing donor, chat, financial and sending workflows remain untouched except necessary navigation/API routing.

## Tasks
- [x] Core: write failing tests for invite normalization, evidence/freshness, deterministic ranking, deduplication, version conflicts, persistence and concurrent updates; implement and verify.
- [x] Research: write failing tests for public search parsing, prompt-injection inertness, safe fetch/redirects, robots, budget limits, partial failures, queue idempotency, cancellation and restart recovery; implement and verify.
- [x] Integration: authenticated APIs and standalone screen; tests for unauthorized access, honest empty/error states, source review and mobile layout. No real messages or donor mutations.
- [x] Verification: focused tests, existing Python/JS regressions, browser checks with synthetic data; review diff and document limits.

## Review focus
- An official-looking group title is not proof of affiliation.
- Conflicting/stale evidence must not quietly become Ready.
- Repeated discovery and repeated start requests must not create duplicate work.
- Provider failure and an empty successful search are different outcomes.
- A refresh/restart must not erase research progress or enable outreach.

## Execution ledger
- Latest GitHub baseline: 9e09f12f786b6c93d64e2d699a0bac5bbce5befb. Local existing worktrees contain unrelated unpublished changes, preserved.
- Native managed worktree failed because chat root is not a Git repository. Created isolated existing-repository worktree at work/university-group-finder; synchronizing text sources from the exact GitHub revision through the connector.
- Public no-key search is optional best effort, not a promised stable search API; manual import and source review remain available on failure.
- 2026-10-30 verification: 470 Python tests completed successfully (one skipped); four existing Vitest tests passed; seven dedicated Playwright tests passed at 320/390/768/1440px. Screenshot review completed. Python/JavaScript syntax and git whitespace checks passed.
- Independent review reproduced three queue races. Added failing regressions, fixed cancellation after final fetch, durable pending-source recovery with cached query results, and atomic lease/evidence/counter writes. Reviewer rechecked and reported no remaining Important findings in those fixes; independently ran 24 research tests successfully.
- Live public-feed check initially hit sandbox Windows network error 10013. After turn-scoped network permission, a read-only query returned nine results. Precise query operators were not reliably honored; added relevance/operator validation and documented provider limitations. Optional Brave adapter uses the official API contract and synthetic verification; no key or paid account configured.
- The user clarified that "restart" meant continuing/completing the WhatsApp group-finder app. Continue publication and live verification. Preserve the newer upstream theme/chat changes from f56f22ce572a27e4214596ec61858160d817fa6a; they do not touch this feature's server/index integration.

- Final combined verification against the latest upstream theme/chat source: 479 Python tests passed (one skipped), four Vitest tests passed, seven browser tests passed with clean teardown. Publication pending live verification.
