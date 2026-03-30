#!/bin/sh
set -eu

if [ -z "${GMAIL_ADDRESS:-}" ] || [ -z "${ARCHIVE_USER:-}" ]; then
  echo "GMAIL_ADDRESS and ARCHIVE_USER must be set" >&2
  exit 1
fi

if [ -z "${GMAIL_OAUTH_CLIENT_ID:-${GOOGLE_CLIENT_ID:-}}" ] || [ -z "${GMAIL_OAUTH_CLIENT_SECRET:-${GOOGLE_CLIENT_SECRET:-}}" ]; then
  echo "Set OAuth client in env (GMAIL_OAUTH_CLIENT_ID/GMAIL_OAUTH_CLIENT_SECRET or GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)" >&2
  exit 1
fi

if [ -z "${GMAIL_OAUTH_REFRESH_TOKEN:-}" ]; then
  echo "GMAIL_OAUTH_REFRESH_TOKEN is not set yet. Run oauth init first." >&2
  exit 1
fi

MAIL_ROOT="${MAIL_ROOT:-/srv/vmail}"
IMPORT_STATE_DB="${IMPORT_STATE_DB:-${MAIL_ROOT}/.gmail-import-state.sqlite}"

mkdir -p /root "${MAIL_ROOT}/${ARCHIVE_USER}" "${MAIL_ROOT}/${ARCHIVE_USER}/mail" "${MAIL_ROOT}/${ARCHIVE_USER}/mail/cur" "${MAIL_ROOT}/${ARCHIVE_USER}/mail/new" "${MAIL_ROOT}/${ARCHIVE_USER}/mail/tmp"
mkdir -p "$(dirname "${IMPORT_STATE_DB}")"

/usr/local/bin/run-sync.sh
