#!/bin/sh
set -eu

lockdir="/tmp/gmail-import.lock"
result_file="/tmp/gmail-import.result"

if ! mkdir "$lockdir" 2>/dev/null; then
  echo "Sync already running, skipping"
  exit 0
fi

cleanup() {
  rm -f "$result_file"
  rmdir "$lockdir" 2>/dev/null || true
}

on_interrupt() {
  echo "<3> Email backup interrupted" >&2
  exit 2
}

trap cleanup EXIT
trap on_interrupt INT TERM

echo "Starting Gmail import"
rm -f "$result_file"
python3 /usr/local/bin/gmail-import.py

imported_count="unknown"
if [ -f "$result_file" ]; then
  imported_count="$(cat "$result_file" 2>/dev/null || true)"
fi

case "$imported_count" in
  ""|*[!0-9]*)
    imported_count="unknown"
    ;;
esac

echo "<5>Gmail import complete, imported=${imported_count}"
