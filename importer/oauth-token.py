#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def env(name: str, alt: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if alt:
        return os.environ.get(alt, "").strip()
    return ""


def post_form(url: str, data: dict) -> dict:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Token endpoint error ({err.code}): {body}") from err


def require_client() -> tuple[str, str]:
    client_id = env("GMAIL_OAUTH_CLIENT_ID", "GOOGLE_CLIENT_ID")
    client_secret = env("GMAIL_OAUTH_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing OAuth client settings. Set GMAIL_OAUTH_CLIENT_ID/GMAIL_OAUTH_CLIENT_SECRET "
            "(or GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)."
        )
    return client_id, client_secret


def print_auth_url() -> None:
    client_id, _ = require_client()
    redirect_uri = env("GMAIL_OAUTH_REDIRECT_URI") or "http://localhost:53682/"
    scope = env("GMAIL_OAUTH_SCOPE") or "https://www.googleapis.com/auth/gmail.readonly"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print("Open this URL in a browser and complete login/consent:\n")
    print(url)
    print("\nAfter consent, copy the full redirected URL and paste it below.")
    redirected = input("Redirected URL: ").strip()
    parsed = urllib.parse.urlparse(redirected)
    code = urllib.parse.parse_qs(parsed.query).get("code", [""])[0].strip()
    if not code:
        raise RuntimeError("No authorization code found in redirected URL.")

    _, client_secret = require_client()
    token = post_form(
        TOKEN_URL,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    refresh_token = token.get("refresh_token", "").strip()
    if not refresh_token:
        raise RuntimeError(
            "No refresh_token returned. Re-consent with prompt=consent, and ensure access_type=offline."
        )

    print("\nSuccess. Add this to your .env:\n")
    print(f"GMAIL_OAUTH_REFRESH_TOKEN={refresh_token}")


def print_access_token() -> None:
    client_id, client_secret = require_client()
    refresh = env("GMAIL_OAUTH_REFRESH_TOKEN")
    if not refresh:
        raise RuntimeError("Missing GMAIL_OAUTH_REFRESH_TOKEN. Run with --init first.")

    token = post_form(
        TOKEN_URL,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
    )
    access_token = token.get("access_token", "").strip()
    if not access_token:
        raise RuntimeError("No access_token returned by token endpoint.")

    sys.stdout.write(access_token)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("--init", "--access-token"):
        print("Usage: oauth-token.py --init | --access-token", file=sys.stderr)
        return 2

    try:
        if sys.argv[1] == "--init":
            print_auth_url()
        else:
            print_access_token()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
