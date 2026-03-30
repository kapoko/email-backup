# Email archive (Dovecot + Gmail API import)

Simple self-hosted archive stack:

- `dovecot/dovecot` for IMAP access (receive/archive only)
- Python importer (one-shot Gmail API job)
- `roundcube/roundcubemail` for web access

## 1) Configure

Edit `.env`:

- `GMAIL_ADDRESS`
- OAuth client credentials (`GMAIL_OAUTH_CLIENT_ID` / `GMAIL_OAUTH_CLIENT_SECRET`, or `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`)
- `ARCHIVE_USER`
- `GMAIL_OAUTH_SCOPE` (defaults to `https://www.googleapis.com/auth/gmail.readonly`)
- `GMAIL_QUERY` (use Gmail search query, e.g. `after:2026/03/30`)

Note: this setup uses the upstream Dovecot image defaults, which expect IMAP password `password`.

## 2) One-time OAuth init (terminal)

Run:

```bash
docker compose run --rm --no-deps --entrypoint /usr/local/bin/oauth-token.py importer --init
```

It prints a Google consent URL. Open it in your browser, then paste the full redirected URL back in the terminal.
The script prints a `GMAIL_OAUTH_REFRESH_TOKEN=...` line; paste that into `.env`.

This project imports using Gmail API with readonly scope and does not call Gmail delete/modify/archive endpoints.

## 3) Start long-running services

```bash
docker compose up -d --build dovecot roundcube
```

## 4) Access archive

- IMAP host: your server IP
- IMAP port: value of `DOVECOT_IMAP_PORT` (default `1143`)
- Username: `ARCHIVE_USER`
- Password: `ARCHIVE_PASSWORD`

Roundcube:

- URL: `http://<server-ip>:<ROUNDCUBE_HTTP_PORT>` (default `8080`)
- Username: `ARCHIVE_USER`
- Password: `ARCHIVE_PASSWORD`

## 5) Run one import job

```bash
docker compose run --rm --no-deps importer
```

The importer container starts, runs one sync, and exits.

Example external cron entry:

```bash
0 2 * * * cd /path/to/email-backup && docker compose run --rm --no-deps importer
```
