#!/bin/sh
# Railway start command. data/ is the permanent volume (mounted at /app/data).
# First start only: copy the data brought from the PC (track record, journal, candle history) onto it, if it was added.
set -e
mkdir -p data
if [ ! -f data/.seeded ] && [ -d deploy/seed ]; then
  cp -rn deploy/seed/. data/
  date > data/.seeded
  echo "[start] copied the PC data onto the volume"
fi
# daily backups go into the volume too (on a PC they go to the AuEdge-backups folder)
export AUEDGE_BACKUP_DIR="$(pwd)/data/backups"
if [ -z "$AUEDGE_PASSWORD" ]; then
  echo "[start] WARNING: AUEDGE_PASSWORD is not set, so anyone with the link can open AuEdge. Set it in Railway > Variables."
fi
exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level warning --proxy-headers --forwarded-allow-ips="*"
