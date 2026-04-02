#!/usr/bin/env python3
import base64
import datetime as dt
import json
import os
import random
import ssl
import sqlite3
import string
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def log(message: str) -> None:
    print(f"[{now_iso()}] {message}", flush=True)


def bool_env(name: str, default: bool = False) -> bool:
    raw = env(name, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")


def get_access_token() -> str:
    proc = subprocess.run(
        ["/usr/local/bin/oauth-token.py", "--access-token"],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or "token helper failed"
        raise RuntimeError(err)
    token = proc.stdout.strip()
    if not token:
        raise RuntimeError("empty access token returned")
    return token


def api_get(path: str, token: str, query: dict | None = None) -> dict:
    query = query or {}
    qs = urllib.parse.urlencode(query)
    url = f"{API_BASE}{path}"
    if qs:
        url = f"{url}?{qs}"

    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"gmail api error ({err.code}) at {path}: {body}") from err
    except urllib.error.URLError as err:
        reason = getattr(err, "reason", err)
        raise RuntimeError(f"gmail transport error at {path}: {reason}") from err
    except (TimeoutError, ssl.SSLError) as err:
        raise RuntimeError(f"gmail transport error at {path}: {err}") from err


def is_retryable_error(exc: RuntimeError) -> bool:
    msg = str(exc)
    if "gmail transport error" in msg:
        return True
    return any(code in msg for code in ("(429)", "(500)", "(502)", "(503)", "(504)"))


def retry_api_get(path: str, token: str, query: dict | None = None, retries: int = 5) -> dict:
    attempt = 0
    delay_s = 1.0
    while True:
        try:
            return api_get(path, token, query)
        except RuntimeError as exc:
            if attempt >= retries or not is_retryable_error(exc):
                raise
            attempt += 1
            sleep_s = min(30.0, delay_s)
            log(f"transient gmail api/transport error; retry={attempt} sleep={sleep_s:.1f}s path={path}")
            time.sleep(sleep_s)
            delay_s *= 2


def api_get_with_refresh(path: str, token: str, query: dict | None = None) -> tuple[dict, str]:
    try:
        return retry_api_get(path, token, query), token
    except RuntimeError as exc:
        if "gmail api error (401)" not in str(exc):
            raise
        log("access token invalid/expired; refreshing and retrying once")
        refreshed = get_access_token()
        return retry_api_get(path, refreshed, query), refreshed


def ensure_maildir(root: str) -> tuple[str, str, str]:
    inbox = os.path.join(root, "mail")
    cur = os.path.join(inbox, "cur")
    new = os.path.join(inbox, "new")
    tmp = os.path.join(inbox, "tmp")
    os.makedirs(cur, exist_ok=True)
    os.makedirs(new, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    return cur, new, tmp


def connect_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS state (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS imported_messages (
          gmail_id TEXT PRIMARY KEY,
          internal_date_ms INTEGER,
          maildir_path TEXT NOT NULL,
          imported_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def state_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def state_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def imported_exists(conn: sqlite3.Connection, gmail_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM imported_messages WHERE gmail_id = ?",
        (gmail_id,),
    ).fetchone()
    return row is not None


def add_padding(raw: str) -> str:
    return raw + "=" * ((4 - len(raw) % 4) % 4)


def random_tag(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def write_mail(tmp_dir: str, cur_dir: str, gmail_id: str, internal_date_ms: int, raw_msg: bytes) -> str:
    host = env("HOSTNAME", "archive")
    ts = max(1, internal_date_ms // 1000)
    uniq = f"{ts}.M{time.time_ns()}P{os.getpid()}.{host}.{random_tag()}"
    tmp_name = f"{uniq}.tmp"
    cur_name = f"{uniq},S={len(raw_msg)}:2,S"

    tmp_path = os.path.join(tmp_dir, tmp_name)
    cur_path = os.path.join(cur_dir, cur_name)

    with open(tmp_path, "wb") as handle:
        handle.write(raw_msg)
    os.replace(tmp_path, cur_path)
    return cur_path


def fetch_message_ids_initial(token: str, batch_size: int, query: str, include_spam_trash: bool) -> tuple[list[str], str]:
    ids: list[str] = []
    page_token = ""
    page = 0
    while True:
        page += 1
        params = {
            "maxResults": str(batch_size),
            "includeSpamTrash": "true" if include_spam_trash else "false",
        }
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        payload, token = api_get_with_refresh("/messages", token, params)
        for item in payload.get("messages", []):
            msg_id = item.get("id", "").strip()
            if msg_id:
                ids.append(msg_id)

        log(f"list-page={page} total_ids={len(ids)}")

        page_token = payload.get("nextPageToken", "")
        if not page_token:
            break
    return ids, token


def fetch_message_ids_from_history(token: str, start_history_id: str, batch_size: int) -> tuple[list[str], str | None, str]:
    ids: set[str] = set()
    page_token = ""
    latest_history = start_history_id
    page = 0

    while True:
        page += 1
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": str(batch_size),
        }
        if page_token:
            params["pageToken"] = page_token

        payload, token = api_get_with_refresh("/history", token, params)
        history = payload.get("history", [])
        for event in history:
            history_id = str(event.get("id", "")).strip()
            if history_id:
                latest_history = history_id
            for added in event.get("messagesAdded", []):
                msg = added.get("message", {})
                msg_id = str(msg.get("id", "")).strip()
                if msg_id:
                    ids.add(msg_id)

        log(f"history-page={page} new_ids={len(ids)}")

        page_token = payload.get("nextPageToken", "")
        if not page_token:
            break

    return list(ids), latest_history, token


def fetch_current_history_id(token: str) -> tuple[str, str]:
    payload, token = api_get_with_refresh("/profile", token)
    history_id = str(payload.get("historyId", "")).strip()
    if not history_id:
        raise RuntimeError("gmail profile missing historyId")
    return history_id, token


def import_message(
    conn: sqlite3.Connection,
    token: str,
    gmail_id: str,
    tmp_dir: str,
    cur_dir: str,
    include_spam_trash: bool,
) -> tuple[bool, str]:
    if imported_exists(conn, gmail_id):
        return False, token

    try:
        msg, token = api_get_with_refresh(f"/messages/{gmail_id}", token, {"format": "raw"})
    except RuntimeError as exc:
        if "gmail api error (404)" in str(exc):
            log(f"skip missing message id={gmail_id}")
            return False, token
        raise

    raw_b64 = msg.get("raw", "")
    if not raw_b64:
        raise RuntimeError(f"message {gmail_id} has no raw payload")

    if not include_spam_trash:
        labels = set(msg.get("labelIds", []))
        if "SPAM" in labels or "TRASH" in labels:
            return False, token

    raw = base64.urlsafe_b64decode(add_padding(raw_b64))
    internal_date_ms = int(str(msg.get("internalDate", "0")) or "0")
    mail_path = write_mail(tmp_dir, cur_dir, gmail_id, internal_date_ms, raw)

    conn.execute(
        "INSERT INTO imported_messages(gmail_id, internal_date_ms, maildir_path, imported_at) VALUES(?, ?, ?, ?)",
        (gmail_id, internal_date_ms, mail_path, now_iso()),
    )
    return True, token


def main() -> int:
    archive_user = env("ARCHIVE_USER")
    if not archive_user:
        print("ARCHIVE_USER is required", file=sys.stderr)
        return 1

    mail_root = env("MAIL_ROOT", "/srv/vmail")
    user_root = os.path.join(mail_root, archive_user)
    db_path = env("IMPORT_STATE_DB", os.path.join(mail_root, ".gmail-import-state.sqlite"))
    query = env("GMAIL_QUERY")
    include_spam_trash = bool_env("GMAIL_INCLUDE_SPAM_TRASH", False)
    batch_size = int(env("GMAIL_BATCH_SIZE", "200"))
    progress_every = int(env("GMAIL_PROGRESS_EVERY", "25"))
    if batch_size < 1 or batch_size > 500:
        batch_size = 200
    if progress_every < 1:
        progress_every = 25

    log(f"gmail-import start query={query or '<empty>'} include_spam_trash={str(include_spam_trash).lower()} batch_size={batch_size}")

    token = get_access_token()
    current_history, token = fetch_current_history_id(token)

    cur_dir, _new_dir, tmp_dir = ensure_maildir(user_root)
    conn = connect_db(db_path)

    imported_count = 0
    scanned_count = 0

    try:
        start_history = state_get(conn, "last_history_id")
        filter_signature = json.dumps(
            {
                "query": query,
                "include_spam_trash": include_spam_trash,
            },
            sort_keys=True,
        )
        saved_filter_signature = state_get(conn, "filter_signature")

        history_eligible = not query

        if start_history and saved_filter_signature == filter_signature and history_eligible:
            try:
                ids, _latest, token = fetch_message_ids_from_history(token, start_history, batch_size)
            except RuntimeError as exc:
                if "(404)" in str(exc):
                    log("history checkpoint expired, falling back to full list")
                    ids, token = fetch_message_ids_initial(token, batch_size, query, include_spam_trash)
                else:
                    raise
        elif start_history and saved_filter_signature == filter_signature and not history_eligible:
            log("query is set, skipping history mode and running full list")
            ids, token = fetch_message_ids_initial(token, batch_size, query, include_spam_trash)
        elif start_history and saved_filter_signature != filter_signature:
            log("query/filter changed, running full list backfill")
            ids, token = fetch_message_ids_initial(token, batch_size, query, include_spam_trash)
        else:
            ids, token = fetch_message_ids_initial(token, batch_size, query, include_spam_trash)

        log(f"processing_ids={len(ids)}")

        for gmail_id in ids:
            scanned_count += 1
            imported, token = import_message(conn, token, gmail_id, tmp_dir, cur_dir, include_spam_trash)
            if imported:
                imported_count += 1
            if scanned_count % progress_every == 0:
                log(f"progress scanned={scanned_count} imported={imported_count}")

        state_set(conn, "last_history_id", current_history)
        state_set(conn, "filter_signature", filter_signature)
        conn.commit()
    finally:
        conn.close()

    log(f"done scanned={scanned_count} imported={imported_count} history={current_history}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("interrupted by user (Ctrl+C), exiting")
        raise SystemExit(130)
