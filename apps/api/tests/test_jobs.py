"""Integration tests for the SQL maintenance jobs."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg
import pytest
from psycopg.rows import dict_row
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


JOBS = {
    "archive": "app.job_archive_stale_listings",
    "archived": "app.job_purge_archived_listings",
    "drafts": "app.job_purge_abandoned_drafts",
}
JOB_RUN_NAMES = {
    "archive": "archive_stale_listings",
    "archived": "purge_archived_listings",
    "drafts": "purge_abandoned_drafts",
}
PHONE = "+9779800001234"


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200


def set_whatsapp(conn, user_id: str, value: str) -> None:
    conn.execute("UPDATE app.profiles SET whatsapp = %s WHERE id = %s", (value, user_id))


def insert_listing(conn, owner_id, status="draft"):
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    listing_id = conn.execute(
        """INSERT INTO app.listings (owner_id, title, rent_amount, point) VALUES
        (%s, 'Job test rental', 24000,
         extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172),4326)::extensions.geography)
        RETURNING id""", (owner_id,),
    ).fetchone()[0]
    if status in ("active", "rented", "sold_out", "unavailable"):
        conn.execute("UPDATE app.listings SET status='active' WHERE id=%s", (listing_id,))
        if status != "active":
            conn.execute("UPDATE app.listings SET status=%s WHERE id=%s", (status, listing_id))
    elif status == "archived":
        conn.execute("UPDATE app.listings SET status='active' WHERE id=%s", (listing_id,))
        conn.execute("UPDATE app.listings SET status='archived' WHERE id=%s", (listing_id,))
    return listing_id


def backdate(conn, listing_id, column, days):
    assert column in {"updated_at", "status_changed_at", "archived_at"}
    conn.execute("SET session_replication_role = replica")
    conn.execute(f"UPDATE app.listings SET {column}=now() - (%s * interval '1 day') WHERE id=%s", (days, listing_id))
    conn.execute("SET session_replication_role = origin")


def add_photo(conn, listing_id, suffix):
    conn.execute(
        """INSERT INTO app.listing_photos
        (listing_id, storage_path, thumb_path, width, height, position)
        VALUES (%s,%s,%s,800,600,1)""",
        (listing_id, f"{suffix}/original.jpg", f"{suffix}/thumb.jpg"),
    )


def run(conn, function):
    return conn.execute(f"SELECT {function}() AS result").fetchone()[0]


def test_each_job_twice_is_noop(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    ids = {"archive": insert_listing(db_conn, signed_in_user["id"], "rented"),
           "archived": insert_listing(db_conn, signed_in_user["id"], "archived"),
           "drafts": insert_listing(db_conn, signed_in_user["id"])}
    backdate(db_conn, ids["archive"], "status_changed_at", 31)
    backdate(db_conn, ids["archived"], "archived_at", 31)
    backdate(db_conn, ids["drafts"], "updated_at", 31)
    db_conn.commit()
    first_job_run_id = db_conn.execute("SELECT COALESCE(max(id), 0) FROM app.job_runs").fetchone()[0]
    for key, fn in JOBS.items():
        assert run(db_conn, fn) == 1
        db_conn.commit()
        assert run(db_conn, fn) == 0
        db_conn.commit()
        with db_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count(*) AS n, bool_or(error IS NOT NULL) AS has_error FROM app.job_runs WHERE job=%s AND id > %s", (JOB_RUN_NAMES[key], first_job_run_id))
            assert cur.fetchone() == {"n": 2, "has_error": False}


def test_job_concurrent_run_second_exits(db_conn, test_database_url):
    before = db_conn.execute("SELECT count(*) FROM app.job_runs WHERE job='archive_stale_listings'").fetchone()[0]
    with db_conn.transaction():
        db_conn.execute("SELECT pg_advisory_xact_lock(hashtext('rentra_job_archive_stale_listings'))")
        with psycopg.connect(test_database_url) as other:
            assert run(other, JOBS["archive"]) is None
    after = db_conn.execute("SELECT count(*) FROM app.job_runs WHERE job='archive_stale_listings'").fetchone()[0]
    assert after == before


def test_jobs_skip_suspended_listings(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    archived = insert_listing(db_conn, signed_in_user["id"], "archived")
    draft = insert_listing(db_conn, signed_in_user["id"])
    rented = insert_listing(db_conn, signed_in_user["id"], "rented")
    for ident, col in ((archived, "archived_at"), (draft, "updated_at"), (rented, "status_changed_at")):
        backdate(db_conn, ident, col, 31)
    db_conn.execute("SELECT set_config('app.actor','admin',true)")
    db_conn.execute("UPDATE app.listings SET suspended_at=now() WHERE id=ANY(%s)", ([archived, draft, rented],))
    db_conn.commit()
    assert run(db_conn, JOBS["archive"]) == 0
    db_conn.commit()
    assert run(db_conn, JOBS["archived"]) == 0
    db_conn.commit()
    assert run(db_conn, JOBS["drafts"]) == 0
    db_conn.commit()
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=ANY(%s)", ([archived, draft, rented],)).fetchone()[0] == 3


def test_archive_job_vs_owner_reactivate_race(db_conn, signed_in_user, test_database_url):
    ensure_profile(signed_in_user)
    set_whatsapp(db_conn, signed_in_user["id"], PHONE)
    db_conn.commit()
    listing_id = insert_listing(db_conn, signed_in_user["id"], "rented")
    backdate(db_conn, listing_id, "status_changed_at", 31)
    db_conn.commit()
    owner_conn = psycopg.connect(test_database_url)
    owner_conn.execute("SELECT set_config('app.user_id',%s,true)", (signed_in_user["id"],))
    owner_conn.execute("SELECT app.set_listing_status(%s,'active')", (listing_id,))
    started = Event()
    def archive():
        with psycopg.connect(test_database_url) as job_conn:
            started.set()
            return run(job_conn, JOBS["archive"])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(archive)
        assert started.wait(5)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        owner_conn.commit()
        assert future.result(timeout=10) == 0
    owner_conn.close()
    assert db_conn.execute("SELECT status FROM app.listings WHERE id=%s", (listing_id,)).fetchone()[0] == "active"


@pytest.mark.parametrize("kind,fn,datecol", [("draft","drafts","updated_at"),("archived","archived","archived_at")])
def test_due_and_recent_purges_queue_both_paths(db_conn, signed_in_user, kind, fn, datecol):
    ensure_profile(signed_in_user)
    due = insert_listing(db_conn, signed_in_user["id"], kind)
    recent = insert_listing(db_conn, signed_in_user["id"], kind)
    due_prefix = str(uuid.uuid4())
    recent_prefix = str(uuid.uuid4())
    add_photo(db_conn, due, due_prefix)
    add_photo(db_conn, recent, recent_prefix)
    backdate(db_conn, due, datecol, 31)
    backdate(db_conn, recent, datecol, 29)
    db_conn.commit()
    assert run(db_conn, JOBS[fn]) == 1
    db_conn.commit()
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=%s", (recent,)).fetchone()[0] == 1
    assert {r[0] for r in db_conn.execute("SELECT path FROM app.storage_deletions WHERE path LIKE %s", (f"{due_prefix}/%",))} == {f"{due_prefix}/original.jpg", f"{due_prefix}/thumb.jpg"}
    assert db_conn.execute("SELECT count(*) FROM app.storage_deletions WHERE path LIKE %s", (f"{recent_prefix}/%",)).fetchone()[0] == 0


def test_force_delete_queues_storage_and_thumb_paths(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    ident = insert_listing(db_conn, signed_in_user["id"], "archived")
    add_photo(db_conn, ident, "force-test")
    db_conn.execute("SELECT set_config('app.user_id',%s,true)", (signed_in_user["id"],))
    db_conn.execute("SELECT app.force_delete_listing(%s)", (ident,))
    db_conn.commit()
    assert {r[0] for r in db_conn.execute("SELECT path FROM app.storage_deletions WHERE path LIKE 'force-test/%'")} == {"force-test/original.jpg", "force-test/thumb.jpg"}


def test_job_error_recorded_in_job_runs(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    ident = insert_listing(db_conn, signed_in_user["id"], "rented")
    backdate(db_conn, ident, "status_changed_at", 31)
    db_conn.commit()
    db_conn.execute("ALTER TABLE app.listings ADD CONSTRAINT jobs_force_error CHECK (status <> 'archived' OR title <> 'Job test rental') NOT VALID")
    db_conn.commit()
    try:
        assert run(db_conn, JOBS["archive"]) is None
        db_conn.commit()
        row = db_conn.execute("SELECT error, finished_at FROM app.job_runs WHERE job='archive_stale_listings' ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] and row[1] is not None
    finally:
        db_conn.execute("ALTER TABLE app.listings DROP CONSTRAINT IF EXISTS jobs_force_error")
        db_conn.commit()
