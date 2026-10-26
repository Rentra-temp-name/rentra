"""Account deletion endpoint and sweep integration tests against Postgres."""

from __future__ import annotations

import uuid

import httpx
import psycopg
from starlette.testclient import TestClient

from rentra_api import main
from rentra_api.config import get_settings
from rentra_api.main import app
from rentra_api.worker import run_deletion_sweep


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200


def insert_listing(conn: psycopg.Connection, owner_id: str) -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    return str(conn.execute(
        """INSERT INTO app.listings (owner_id, title, rent_amount, point)
           VALUES (%s, 'Account deletion test', 25000,
             extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172),4326)::extensions.geography)
           RETURNING id""", (owner_id,),
    ).fetchone()[0])


def insert_photo(conn: psycopg.Connection, listing_id: str, prefix: str) -> tuple[str, str]:
    original, thumb = f"{prefix}/original.jpg", f"{prefix}/thumb.jpg"
    conn.execute(
        """INSERT INTO app.listing_photos
           (listing_id, storage_path, thumb_path, width, height, position)
           VALUES (%s, %s, %s, 800, 600, 1)""",
        (listing_id, original, thumb),
    )
    return original, thumb


def add_admin(conn: psycopg.Connection, user_id: str) -> None:
    conn.execute("INSERT INTO app.admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))


def suspend_listing_as_admin(conn: psycopg.Connection, user_id: str, listing_id: str) -> None:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
    conn.execute("SELECT app.admin_suspend_listing(%s, 'Legal review')", (listing_id,))


def unsuspend_listing_as_admin(conn: psycopg.Connection, user_id: str, listing_id: str) -> None:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
    conn.execute("SELECT app.admin_unsuspend_listing(%s)", (listing_id,))


def create_temporary_auth_user() -> tuple[str, dict[str, str], dict[str, str]]:
    settings = get_settings()
    email = f"rentra-delete-{uuid.uuid4()}@example.test"
    password = f"T!{uuid.uuid4()}"
    admin_headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
        created = auth.post("/auth/v1/admin/users", headers=admin_headers,
                            json={"email": email, "password": password, "email_confirm": True})
        assert created.status_code in (200, 201), created.text
        user_id = created.json()["id"]
        signed_in = auth.post("/auth/v1/token?grant_type=password",
                              headers={"apikey": settings.SUPABASE_SERVICE_ROLE_KEY},
                              json={"email": email, "password": password})
        assert signed_in.status_code == 200, signed_in.text
    user_headers = {
        "Authorization": f"Bearer {signed_in.json()['access_token']}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    }
    return user_id, user_headers, admin_headers


def test_delete_me_requires_confirm(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    with TestClient(app) as client:
        missing = client.delete("/me", headers=signed_in_user["headers"])
        false = client.request("DELETE", "/me", headers=signed_in_user["headers"], json={"confirm": False})
        unknown = client.request("DELETE", "/me", headers=signed_in_user["headers"], json={"confirm": True, "extra": 1})
    assert missing.status_code == 400 and missing.json() == {"code": "CONFIRM_REQUIRED"}
    assert false.status_code == 400 and false.json() == {"code": "CONFIRM_REQUIRED"}
    assert unknown.status_code == 422
    assert db_conn.execute("SELECT deletion_requested_at FROM app.profiles WHERE id=%s",
                           (signed_in_user["id"],)).fetchone()[0] is None


def test_delete_me_removes_listings_and_queues_all_photo_paths(db_conn, signed_in_user, monkeypatch):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    second_id = insert_listing(db_conn, signed_in_user["id"])
    prefix_a, prefix_b = str(uuid.uuid4()), str(uuid.uuid4())
    expected = set(insert_photo(db_conn, listing_id, prefix_a) + insert_photo(db_conn, second_id, prefix_b))
    db_conn.commit()
    monkeypatch.setattr(main, "_auth_delete_user", lambda _user_id: "ok")
    with TestClient(app) as client:
        response = client.request("DELETE", "/me", headers=signed_in_user["headers"], json={"confirm": True})
    assert response.status_code == 200 and response.json() == {"deleted": True}
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=ANY(%s)",
                           ([listing_id, second_id],)).fetchone()[0] == 0
    assert {row[0] for row in db_conn.execute(
        "SELECT path FROM app.storage_deletions WHERE path = ANY(%s)", (list(expected),)
    )} == expected


def test_delete_me_blocked_by_suspended_listing(db_conn, signed_in_user, monkeypatch):
    ensure_profile(signed_in_user)
    regular_id = insert_listing(db_conn, signed_in_user["id"])
    suspended_id = insert_listing(db_conn, signed_in_user["id"])
    paths = set(insert_photo(db_conn, regular_id, str(uuid.uuid4()))
                + insert_photo(db_conn, suspended_id, str(uuid.uuid4())))
    add_admin(db_conn, signed_in_user["id"])
    suspend_listing_as_admin(db_conn, signed_in_user["id"], suspended_id)
    db_conn.commit()
    auth_calls = []
    monkeypatch.setattr(main, "_auth_delete_user", lambda user_id: auth_calls.append(user_id) or "ok")
    with TestClient(app) as client:
        response = client.request("DELETE", "/me", headers=signed_in_user["headers"], json={"confirm": True})
    assert response.status_code == 409
    assert response.json() == {
        "code": "ACCOUNT_HAS_SUSPENDED_LISTING",
        "message": "Account cannot be deleted while a listing is suspended",
    }
    assert auth_calls == []
    assert db_conn.execute("SELECT deletion_requested_at FROM app.profiles WHERE id=%s",
                           (signed_in_user["id"],)).fetchone()[0] is None
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=ANY(%s)",
                           ([regular_id, suspended_id],)).fetchone()[0] == 2
    assert db_conn.execute("SELECT count(*) FROM app.storage_deletions WHERE path=ANY(%s)",
                           (list(paths),)).fetchone()[0] == 0


def test_sweep_skips_user_with_suspended_listing(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    regular_id = insert_listing(db_conn, signed_in_user["id"])
    suspended_id = insert_listing(db_conn, signed_in_user["id"])
    paths = set(insert_photo(db_conn, regular_id, str(uuid.uuid4()))
                + insert_photo(db_conn, suspended_id, str(uuid.uuid4())))
    add_admin(db_conn, signed_in_user["id"])
    suspend_listing_as_admin(db_conn, signed_in_user["id"], suspended_id)
    db_conn.execute("UPDATE app.profiles SET deletion_requested_at=now() - interval '10 minutes' WHERE id=%s",
                    (signed_in_user["id"],))
    db_conn.commit()
    auth_calls = []
    run_deletion_sweep(auth_deleter=lambda user_id: auth_calls.append(user_id) or "ok")
    assert signed_in_user["id"] not in auth_calls
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=ANY(%s)",
                           ([regular_id, suspended_id],)).fetchone()[0] == 2
    assert db_conn.execute("SELECT count(*) FROM app.storage_deletions WHERE path=ANY(%s)",
                           (list(paths),)).fetchone()[0] == 0


def test_delete_me_works_after_admin_unsuspends_and_listing_leaves(db_conn, signed_in_user, monkeypatch):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    add_admin(db_conn, signed_in_user["id"])
    suspend_listing_as_admin(db_conn, signed_in_user["id"], listing_id)
    db_conn.commit()
    calls = []
    monkeypatch.setattr(main, "_auth_delete_user", lambda user_id: calls.append(user_id) or "ok")
    with TestClient(app) as client:
        blocked = client.request("DELETE", "/me", headers=signed_in_user["headers"], json={"confirm": True})
    assert blocked.status_code == 409
    assert calls == []
    unsuspend_listing_as_admin(db_conn, signed_in_user["id"], listing_id)
    db_conn.commit()
    with TestClient(app) as client:
        response = client.request("DELETE", "/me", headers=signed_in_user["headers"], json={"confirm": True})
    assert response.status_code == 200 and response.json() == {"deleted": True}
    assert calls == [signed_in_user["id"]]
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=%s", (listing_id,)).fetchone()[0] == 0


def test_delete_me_resumes_after_auth_api_failure(db_conn, signed_in_user, monkeypatch):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.commit()
    monkeypatch.setattr(main, "_auth_delete_user", lambda _user_id: "http_503")
    with TestClient(app) as client:
        response = client.request("DELETE", "/me", headers=signed_in_user["headers"], json={"confirm": True})
    assert response.status_code == 202 and response.json() == {"status": "deletion_pending"}
    marker = db_conn.execute("SELECT deletion_requested_at FROM app.profiles WHERE id=%s",
                             (signed_in_user["id"],)).fetchone()[0]
    assert marker is not None
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=%s", (listing_id,)).fetchone()[0] == 0
    db_conn.execute("UPDATE app.profiles SET deletion_requested_at=now() - interval '10 minutes' WHERE id=%s",
                    (signed_in_user["id"],))
    db_conn.commit()
    called = []
    counts = run_deletion_sweep(auth_deleter=lambda user_id: called.append(user_id) or "already_gone")
    assert signed_in_user["id"] in called
    assert counts["done"] >= 1


def test_delete_me_happy_path_and_stale_jwt_gets_401():
    user_id, headers, admin_headers = create_temporary_auth_user()
    settings = get_settings()
    try:
        with TestClient(app) as client:
            assert client.get("/me", headers=headers).status_code == 200
            deleted = client.request("DELETE", "/me", headers=headers, json={"confirm": True})
            stale = client.get("/me", headers=headers)
        assert deleted.status_code == 200 and deleted.json() == {"deleted": True}
        assert stale.status_code == 401
    finally:
        with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
            cleanup = auth.delete(f"/auth/v1/admin/users/{user_id}", headers=admin_headers)
            assert cleanup.status_code in (200, 204, 404), cleanup.text


def test_report_survives_account_deletion(db_conn, signed_in_user):
    owner = signed_in_user
    reporter_id, reporter_headers, reporter_admin_headers = create_temporary_auth_user()
    reporter = {"id": reporter_id, "headers": reporter_headers}
    settings = get_settings()
    try:
        ensure_profile(owner)
        ensure_profile(reporter)
        title = f"Deletion report snapshot {uuid.uuid4()}"
        listing_id = insert_listing(db_conn, owner["id"])
        db_conn.execute("UPDATE app.listings SET title=%s, status='active' WHERE id=%s", (title, listing_id))
        db_conn.execute("UPDATE app.profiles SET whatsapp='+9779800001234' WHERE id=%s", (owner["id"],))
        db_conn.commit()
        with TestClient(app) as client:
            created = client.post(
                f"/listings/{listing_id}/report", headers=reporter_headers,
                json={"reason": "evidence retained"},
            )
            deleted = client.request("DELETE", "/me", headers=reporter_headers, json={"confirm": True})
        assert created.status_code == 200
        assert deleted.status_code == 200 and deleted.json() == {"deleted": True}
        row = db_conn.execute(
            "SELECT reporter_id, snapshot_title, snapshot_whatsapp FROM app.reports WHERE id=%s",
            (created.json()["id"],),
        ).fetchone()
        assert row == (None, title, "+9779800001234")
    finally:
        with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
            cleanup = auth.delete(
                f"/auth/v1/admin/users/{reporter_id}", headers=reporter_admin_headers
            )
            assert cleanup.status_code in (200, 204, 404), cleanup.text


def test_request_account_deletion_twice_is_noop(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    prefix = str(uuid.uuid4())
    paths = set(insert_photo(db_conn, listing_id, prefix))
    db_conn.commit()

    api_conn = psycopg.connect(get_settings().DATABASE_URL, prepare_threshold=None)
    try:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        api_conn.execute("SELECT app.request_account_deletion()")
        api_conn.commit()
        first_marker = db_conn.execute(
            "SELECT deletion_requested_at FROM app.profiles WHERE id=%s", (signed_in_user["id"],)
        ).fetchone()[0]
        assert first_marker is not None
        assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=%s", (listing_id,)).fetchone()[0] == 0
        assert {row[0] for row in db_conn.execute(
            "SELECT path FROM app.storage_deletions WHERE path=ANY(%s)", (list(paths),)
        )} == paths

        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        api_conn.execute("SELECT app.request_account_deletion()")
        api_conn.commit()
        second_marker = db_conn.execute(
            "SELECT deletion_requested_at FROM app.profiles WHERE id=%s", (signed_in_user["id"],)
        ).fetchone()[0]
        assert second_marker == first_marker
        assert db_conn.execute(
            "SELECT count(*) FROM app.storage_deletions WHERE path=ANY(%s)", (list(paths),)
        ).fetchone()[0] == len(paths)
    finally:
        api_conn.close()


def test_sweep_ignores_recent_deletions(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    paths = set(insert_photo(db_conn, listing_id, str(uuid.uuid4())))
    db_conn.execute(
        "UPDATE app.profiles SET deletion_requested_at=now() - interval '1 minute' WHERE id=%s",
        (signed_in_user["id"],),
    )
    db_conn.commit()

    calls = []
    recent_counts = run_deletion_sweep(
        auth_deleter=lambda user_id: calls.append(user_id) or "ok"
    )
    assert recent_counts["found"] == 0
    assert calls == []
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=%s", (listing_id,)).fetchone()[0] == 1
    assert db_conn.execute(
        "SELECT count(*) FROM app.storage_deletions WHERE path=ANY(%s)", (list(paths),)
    ).fetchone()[0] == 0

    db_conn.execute(
        "UPDATE app.profiles SET deletion_requested_at=now() - interval '10 minutes' WHERE id=%s",
        (signed_in_user["id"],),
    )
    db_conn.commit()
    overdue_calls = []
    overdue_counts = run_deletion_sweep(
        auth_deleter=lambda user_id: overdue_calls.append(user_id) or "ok"
    )
    assert overdue_calls == [signed_in_user["id"]]
    assert overdue_counts["found"] == 1
    assert db_conn.execute("SELECT count(*) FROM app.listings WHERE id=%s", (listing_id,)).fetchone()[0] == 0
    assert {row[0] for row in db_conn.execute(
        "SELECT path FROM app.storage_deletions WHERE path=ANY(%s)", (list(paths),)
    )} == paths
