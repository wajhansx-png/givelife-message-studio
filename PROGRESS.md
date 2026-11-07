# Stability mission progress
- Pass 1 (done, committed): 19 stale tests fixed; GET catch-all + socket timeout; atomic writes (persist.atomic_write); pruned job tables; text-list double-start guard; singleton race fix; bounded loops.
- Pass 2: `read_drafts()` heals a damaged drafts.json (set aside as `.corrupt`, restored from DB copy) and replaces 27 raw reads; `GET /drafts` no longer serves a damaged file raw; damaged hold/auto/variant files no longer raise (damaged hold = ON so nothing sends, and "resume" clears it); each startup worker is isolated (one failing to start cannot stop the site); timed-scheduler failure logged once, not every minute; volunteer message + team mirror written atomically; REQUEST_JOBS bounded (store keeps dedupe).
- Pass 2 (stores): writes are deliberately never replayed on a stale connection (existing rule + test); the retry thread can never stay marked running after dying; SQLite `put_retry` now keeps and retries a failed write.
- Pass 2 (launcher): a restart that itself fails (e.g. no process slot) counts as a crash and is retried, never raises out of the supervisor.
- Pass 2 (AI): one safe retry on dropped connection/timeout/cut-off reply, then a clear error; empty AI answers are not cached.
- Pass 2 (browser): assistant-result polling survives short network blips (re-reads status only, never repeats the action).
- Tests: tests/test_stability.py (+corrupt files, +store recovery), tests/test_chaos_isolation.py (real HTTP; gateway refused/garbage/500/hang; damaged state files; outage send sends nothing).
- Note: data/studio_state.sqlite is tracked and changes when tests run without DATA_DIR; never commit it.
