# Storage, backup and recovery

## What is protected

- HTTP replies restrict framing to this app and explicitly configured HTTPS origins. No universal script CSP is added because the existing app includes inline code.
- Unexpected request errors produce redacted structured logs (request ID, exception type, code location). Request bodies, exception arguments, keys and URL queries are excluded. `GET /ops/status` requires the normal access key and reports storage type, recent error and backup status.
- `GIVELIFE_STORAGE_KEY` is a separate random secret, at least 32 bytes. Preserve it separately from database/backups. Do not rotate or delete it without a tested migration. Changing the login access key does not change storage encryption.
- When configured, current SQLite state values are migrated transactionally to authenticated encryption. Lease ownership remains plaintext metadata. Wrong keys are rejected. Old SQLite plaintext pages are compacted after migration. This does not encrypt temporary working JSON/media, the local GoWA working database, historical provider backups or PostgreSQL JSONB values; provider encryption and database TLS must be verified independently.
- The default local GoWA key database is checkpointed every 60 seconds and after graceful gateway shutdown, encrypted in the existing application store. A missing local file is restored before starting GoWA. Existing working files and custom `GOWA_DB_KEYS_URI` locations are never replaced. A crash can lose up to the last checkpoint interval; this is not zero-loss session replication.

## Enable independent backups

Set `GIVELIFE_STORAGE_KEY`, `GIVELIFE_BACKUP_URL` and, if required, `GIVELIFE_BACKUP_TOKEN` in Render. Never put their values in GitHub or chat.

`GIVELIFE_BACKUP_URL` must be an existing HTTPS directory endpoint accepting PUT uploads (optional Bearer authentication); a generic S3/R2 URL or expiring signed URL is not supported automatically. Confirm its access policy and retention. No paid resource is created by this app.

When both key and destination are configured, a snapshot is created/uploaded at app start and every 24 hours while the service is running. A sleeping Free service cannot guarantee a daily schedule: configure an independent scheduler/provider backup if that guarantee is required. Seven encrypted local snapshots are retained; local copies on Render Free are temporary, not off-site backups. Failed uploads are logged and visible in `/ops/status`; a configured URL alone is not proof of an accepted upload.

Snapshots include the `givelife_studio_state` table, including any saved encrypted GoWA-key checkpoint. They do not include GoWA's separate PostgreSQL session tables or arbitrary local files. Use provider-native whole-database backups and media backups for full disaster recovery. The application snapshot limit is 64 MiB to protect free-instance memory.

Download an authenticated encrypted snapshot using `GET /ops/backup`, or run:

```sh
python backups.py status
python backups.py create /secure/offline-backups
python backups.py restore /secure/offline-backups/studio.backup /restore/new-state.sqlite
```

The CLI restore uses the original storage key, validates the whole encrypted snapshot before writing, refuses an existing destination and creates a NEW SQLite database. It never starts the application, GoWA, a schedule or a send. PostgreSQL restores must use the provider's isolated branch/restore tools; this CLI is not a PostgreSQL in-place restore command.

## Disaster rehearsal and promotion

1. Record the last successful OFF-SITE upload/provider snapshot, its time and the application revision. Verify you have the matching storage key from a separate secure location.
2. Restore to isolated storage with fake WhatsApp and no real AI credentials. Never test deletion on the live database.
3. Check record counts, private Notes, donor records, archived messages and media. Compare checksums/expected records; test an app restart and a new encrypted snapshot.
4. Review pending schedules, active jobs, uncertain delivery records and receipts before connecting real WhatsApp. A stale backup must never be treated as permission to repeat a send.
5. Stop the old sender before promoting restored storage. Use a maintenance window and verify the live `/health`, authenticated `/ops/status` and delivery state. Do not log out or unlink WhatsApp as a generic recovery action.
6. Measure and record actual recovery time and snapshot age; no RTO/RPO guarantee exists until this rehearsal passes against a real off-site/provider backup.

## Capacity and monitoring

HTTP handlers are bounded (32 by default; `HTTP_MAX_WORKERS` supports 1–256). Excess connections receive 503/Retry-After before any action runs. This prevents unlimited thread growth; it does not turn a 0.15-CPU Free instance into a 10,000-user service. Preserve a single sender even if the read-only UI is scaled later. No paid compute or database replica is enabled here.

Use Render application logs plus an independent uptime/error monitor. Configure an actual owner notification destination and trigger a controlled test alert; deployment failure notifications are not equivalent to runtime alerting. This change does not send unsolicited email or WhatsApp alerts.

SQL injection, authorisation and database restoration tests remain necessary. A successful synthetic test is not proof of live replication, provider at-rest encryption, backup retention or real WhatsApp delivery.
