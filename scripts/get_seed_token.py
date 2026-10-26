#!/usr/bin/env python3
"""Print a fresh local Supabase JWT for the planted load-test tenant T1."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


T1_EMAIL = "planted-t1@seed.rentra.test"
T1_PASSWORD = "RentraSeedT1-Local-Only-2026!"


def main() -> None:
    base_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base_url or not service_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for local Supabase Auth")
    if urlparse(base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Refusing: SUPABASE_URL host must be 127.0.0.1 or localhost")

    body = json.dumps({"email": T1_EMAIL, "password": T1_PASSWORD}).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/auth/v1/token?grant_type=password",
        data=body,
        method="POST",
        headers={"apikey": service_key, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            token = json.loads(response.read()).get("access_token")
    except HTTPError as exc:
        raise SystemExit(f"Supabase sign-in failed with HTTP {exc.code}") from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise SystemExit("Supabase sign-in failed") from None
    if not token:
        raise SystemExit("Supabase Auth did not return an access token")
    print(token)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Token request failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
