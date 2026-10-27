# Chat scheduler

Examples (all times are Pakistan time, PKT / UTC+5):

- `send to GiveLife main tomorrow at 9pm`
- `send to all freelance groups in 10 minutes`
- `send to Fiverr daily at 21:00`
- `send "Your exact caption" to test group at 9pm`
- `start Auto at 8am`
- `turn Auto off at 11pm`
- `show schedules`
- `cancel schedule <8-character ID>`

The reply includes the full date, time, task ID and action. Nothing sends when the schedule is created. Unquoted group sends use the saved caption and poster at execution time. One-time group sends run independently of the Auto switch, with existing group restrictions, hold, connection checks, delivery receipts and 60-second spacing. They wait for an active manual batch instead of interrupting it. Cancelling a running schedule stops remaining recipients; it cannot revoke a dispatched message.

Records use the existing persistent database, or an atomic local file when no database is configured. The single server worker checks due tasks every second while the service is running. It reserves a task before dispatch, tracks the existing send-job receipt, and does not repeat an uncertain dispatch after a restart. Duplicate scheduling requests are coalesced. Successful daily tasks advance to the next day. Tasks delayed over 15 minutes are marked missed, not sent late; daily tasks then advance to their next occurrence.

The server parses the actual owner's instruction. AI tool arguments cannot substitute a different time, recipient or caption. Ambiguous times/actions and unsupported targets require clarification. Existing every-N-minutes Auto rules remain separate.

Limitations: free Render hosting can sleep, restart or be unavailable, so precise-time execution is not guaranteed while the service is asleep. No extra paid service was added. This first scheduler supports known group sends and Auto ON/OFF, not arbitrary AI tasks or timed individual DMs. It is designed for the app's current single server instance, not multiple concurrent replicas.

Validation: `python -m unittest discover -s tests -q` (120 tests, including 15 scheduler and integration cases). These use fake transport and fixed clocks, never real recipients. The integration test schedules through the real chat command path, verifies no early send, advances time, confirms the full caption and poster dispatch through the existing job system, and checks its final receipt while Auto remains off.
