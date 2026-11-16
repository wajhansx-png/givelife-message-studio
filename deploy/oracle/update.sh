#!/usr/bin/env bash
# Update the app: git pull + rebuild + restart. Run from ~/givelife-message-studio/deploy/oracle
set -euo pipefail
echo "STOP. Never update while DMs are sending: a restart can cut a person in the middle of their messages."
read -r -p "Are all DM batches finished or stopped? Type yes: " ok
[ "$ok" = "yes" ] || { echo "Cancelled."; exit 1; }
cd "$(dirname "$0")"
git pull --ff-only
docker compose build
docker compose up -d
docker compose ps
echo "Done. Check: docker compose logs --tail 30 app"
