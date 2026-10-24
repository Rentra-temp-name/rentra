"""Drain the storage deletion outbox."""

from __future__ import annotations

import json
import re
import signal
import threading
from urllib.parse import quote

import httpx
import psycopg
from psycopg.rows import dict_row

from rentra_api.config import get_settings
from rentra_api.main import PHOTO_BUCKET, _storage_headers, _storage_object_url


def _bucket_object_url(bucket: str, path: str) -> str:
    if bucket == PHOTO_BUCKET:
        return _storage_object_url(path)
    settings = get_settings()
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='')}"


def delete_object(bucket: str, path: str) -> str:
    """Delete one Storage object, returning only a path-free status code."""
    try:
        response = httpx.delete(
            _bucket_object_url(bucket, path), headers=_storage_headers(), timeout=15
        )
        if 200 <= response.status_code < 300:
            return "ok"
        if response.status_code == 404:
            return "already_gone"
        return f"http_{response.status_code}"
    except httpx.TimeoutException:
        return "timeout"
    except httpx.RequestError:
        return "network"
    except Exception:
        return "network"


def _connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().DATABASE_URL, prepare_threshold=None)


def _safe_error_code(result: str) -> str:
    if result in {"timeout", "network"} or re.fullmatch(r"http_[0-9]{3}", result or ""):
        return result
    return "network"


def run_once(batch_size: int = 50, deleter=delete_object) -> dict[str, int]:
    """Claim a batch, then complete or defer each object in its own transaction."""
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, bucket, path FROM app.claim_storage_deletions(%s)", (batch_size,))
            rows = cur.fetchall()
        conn.commit()

    counts = {"claimed": len(rows), "done": 0, "failed": 0}
    for row in rows:
        try:
            result = deleter(row["bucket"], row["path"])
        except httpx.TimeoutException:
            result = "timeout"
        except Exception:
            result = "network"
        with _connect() as conn:
            if result in {"ok", "already_gone"}:
                conn.execute("SELECT app.complete_storage_deletion(%s)", (row["id"],))
                counts["done"] += 1
            else:
                conn.execute(
                    "SELECT app.fail_storage_deletion(%s, %s)",
                    (row["id"], _safe_error_code(result)),
                )
                counts["failed"] += 1
            conn.commit()
    return counts


def main() -> None:
    stopping = threading.Event()

    def request_stop(_signum, _frame):
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stopping.is_set():
        try:
            counts = run_once()
        except Exception:
            print('{"error":"worker_cycle_failed"}', flush=True)
            stopping.wait(10)
            continue
        print(json.dumps(counts, separators=(",", ":")), flush=True)
        if counts["claimed"] == 0:
            stopping.wait(10)


if __name__ == "__main__":
    main()
