# Stability mission progress
- Baseline: 19 stale/flaky tests fixed (parallel AI calls, auto-DMs off, explicit Sister greeting, 5s gap, port reuse). Suite green.
- Fixed: GET catch-all + socket timeout; atomic writes for 35 state-file writes (persist.atomic_write); pruned in-memory job tables; text-list double-start guard + crash report; donors()/focus_bank() singleton race (could build two send registries); endless loops (DM template pick, research recovery) bounded; loop failures now logged once.
- Already sound (no change): outbound HTTP timeouts, browser fetch timeout (connection.js), DB retry queue, lease/supervisor, DM batch reconnect waits, uncertain sends never retried.
- Tests added: tests/test_stability.py, test_agent_actions guard test.
