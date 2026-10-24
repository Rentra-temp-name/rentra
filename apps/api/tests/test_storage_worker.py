"""Real-Postgres tests for the storage deletion outbox worker."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg.rows import dict_row

from rentra_api.config import get_settings
from rentra_api.worker import run_once


def add_outbox_row(test_database_url: str, path: str, *, attempts: int = 0) -> int:
    with psycopg.connect(test_database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app.storage_deletions (bucket, path, attempts, next_attempt_at) "
                "VALUES ('listing-photos', %s, %s, '-infinity') RETURNING id",
                (path, attempts),
            )
            return cur.fetchone()[0]


def fetch_row(test_database_url: str, row_id: int) -> dict:
    with psycopg.connect(test_database_url) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, path, attempts, done_at, next_attempt_at > now() AS in_future, last_error "
                "FROM app.storage_deletions WHERE id=%s", (row_id,),
            )
            return cur.fetchone()


def test_worker_deletes_and_marks_done(test_database_url):
    path = f"worker/{uuid.uuid4()}.jpg"
    row_id = add_outbox_row(test_database_url, path)
    seen = []
    counts = run_once(deleter=lambda bucket, object_path: seen.append((bucket, object_path)) or "ok")
    row = fetch_row(test_database_url, row_id)
    assert ("listing-photos", path) in seen
    assert row["done_at"] is not None
    assert counts["done"] >= 1


def test_worker_already_gone_counts_as_success(test_database_url):
    path = f"worker/{uuid.uuid4()}.jpg"
    row_id = add_outbox_row(test_database_url, path)
    counts = run_once(deleter=lambda _bucket, _path: "already_gone")
    row = fetch_row(test_database_url, row_id)
    assert row["done_at"] is not None
    assert counts["done"] >= 1


def test_purge_storage_failure_retried_by_outbox(test_database_url):
    path = f"worker/{uuid.uuid4()}.jpg"
    row_id = add_outbox_row(test_database_url, path)
    assert run_once(deleter=lambda _bucket, _path: "http_503")["failed"] >= 1
    failed = fetch_row(test_database_url, row_id)
    assert failed["done_at"] is None
    assert failed["attempts"] == 1
    assert failed["last_error"] == "http_503"
    assert failed["in_future"] is True
    with psycopg.connect(test_database_url) as conn:
        conn.execute("UPDATE app.storage_deletions SET next_attempt_at=now() - interval '1 second' WHERE id=%s", (row_id,))
    counts = run_once(deleter=lambda _bucket, _path: "ok")
    succeeded = fetch_row(test_database_url, row_id)
    assert succeeded["done_at"] is not None
    assert counts["done"] >= 1


def test_claim_skips_rows_locked_by_another_worker(test_database_url):
    path = f"worker/{uuid.uuid4()}.jpg"
    row_id = add_outbox_row(test_database_url, path)
    locked = psycopg.connect(test_database_url)
    locked.execute("SELECT id FROM app.storage_deletions WHERE id=%s FOR UPDATE", (row_id,))
    seen = []
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_once, 1, lambda _bucket, object_path: seen.append(object_path) or "ok")
            counts = future.result(timeout=5)
        assert path not in seen
        assert counts["claimed"] <= 1
        assert fetch_row(test_database_url, row_id)["attempts"] == 0
    finally:
        locked.rollback()
        locked.close()


def test_claim_lease_prevents_double_claim(test_database_url):
    path = f"worker/{uuid.uuid4()}.jpg"
    row_id = add_outbox_row(test_database_url, path)
    api_url = get_settings().DATABASE_URL
    with psycopg.connect(api_url, prepare_threshold=None) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM app.claim_storage_deletions(100)")
            first = cur.fetchall()
            cur.execute("SELECT * FROM app.claim_storage_deletions(100)")
            second = cur.fetchall()
        conn.commit()
    assert any(row["id"] == row_id for row in first)
    assert all(row["id"] != row_id for row in second)


def test_backoff_grows_and_is_capped(test_database_url):
    first_path = f"worker/{uuid.uuid4()}.jpg"
    capped_path = f"worker/{uuid.uuid4()}.jpg"
    first_id = add_outbox_row(test_database_url, first_path, attempts=1)
    capped_id = add_outbox_row(test_database_url, capped_path, attempts=20)
    with psycopg.connect(test_database_url) as conn:
        conn.execute("SELECT app.fail_storage_deletion(%s, 'network')", (first_id,))
        conn.execute("SELECT app.fail_storage_deletion(%s, 'network')", (capped_id,))
    with psycopg.connect(test_database_url) as conn:
        first = conn.execute("SELECT next_attempt_at > now() + interval '1 minute' AND next_attempt_at < now() + interval '3 minutes' FROM app.storage_deletions WHERE id=%s", (first_id,)).fetchone()[0]
        capped = conn.execute("SELECT next_attempt_at > now() + interval '359 minutes' AND next_attempt_at < now() + interval '361 minutes' FROM app.storage_deletions WHERE id=%s", (capped_id,)).fetchone()[0]
    assert first and capped


def test_error_text_never_contains_path(test_database_url):
    path = f"worker/{uuid.uuid4()}.jpg"
    row_id = add_outbox_row(test_database_url, path)
    run_once(deleter=lambda _bucket, object_path: object_path)
    row = fetch_row(test_database_url, row_id)
    assert row["last_error"] == "network"
    assert path not in row["last_error"]
