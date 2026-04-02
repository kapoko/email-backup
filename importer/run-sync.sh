#!/bin/sh
set -eu

lockdir="/tmp/gmail-import.lock"

if ! mkdir "$lockdir" 2>/dev/null; then
  echo "Sync already running, skipping"
  exit 0
fi

cleanup() {
  rmdir "$lockdir" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Starting Gmail import"
python3 /usr/local/bin/gmail-import.py
echo "<5>Gmail import complete"
