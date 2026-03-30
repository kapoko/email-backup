#!/bin/sh
set -eu

lockdir="/tmp/gmail-import.lock"

if ! mkdir "$lockdir" 2>/dev/null; then
  echo "Sync already running, skipping"
  exit 0
fi

cleanup() {
  rmdir "$lockdir"
}

trap cleanup EXIT INT TERM

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting Gmail import"
python3 /usr/local/bin/gmail-import.py
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Gmail import complete"
