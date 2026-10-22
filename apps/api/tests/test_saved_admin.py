"""Saved listings, reports, and admin integration tests against Postgres."""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


PHONE = "+9779800001234"
POINT_SQL = "extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172), 4326)::extensions.geography"


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200, response.text


def create_auth_user() -> dict:
    settings = get_settings()
    email = f"rentra-step8-{uuid.uuid4()}@example.test"
    password = f"T!{uuid.uuid4()}"
    admin_headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
        created = auth.post(
            "/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": password, "email_confirm": True},
        )
        assert created.status_code in (200, 201), created.text
        user_id = created.json()["id"]
        signed_in = auth.post(
            "/auth/v1/token?grant_type=password",
            headers={"apikey": settings.SUPABASE_SERVICE_ROLE_KEY},
            json={"email": email, "password": password},
        )
        assert signed_in.status_code == 200, signed_in.text
    token = signed_in.json()["access_token"]
    return {
        "id": user_id,
        "headers": {
            "Authorization": f"Bearer {token}",
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        },
        "admin_headers": admin_headers,
    }


def delete_auth_user(user: dict) -> None:
    settings = get_settings()
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
        response = auth.delete(
            f"/auth/v1/admin/users/{user['id']}", headers=user["admin_headers"]
        )
    assert response.status_code in (200, 204, 404), response.text


def seed_listing(
    conn: psycopg.Connection,
    owner_id: str,
    *,
    title: str | None = None,
    status: str = "active",
    whatsapp: str = PHONE,
) -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    conn.execute("UPDATE app.profiles SET whatsapp = %s WHERE id = %s", (whatsapp, owner_id))
    listing_id = conn.execute(
        f"""INSERT INTO app.listings (owner_id, title, rent_amount, point)
            VALUES (%s, %s, 24000, {POINT_SQL}) RETURNING id""",
        (owner_id, title or f"Step 8 {uuid.uuid4().hex[:12]}"),
    ).fetchone()[0]
    if status != "draft":
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    if status in {"rented", "sold_out", "unavailable", "archived"}:
        conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    return str(listing_id)


def add_admin(conn: psycopg.Connection, user_id: str) -> None:
    conn.execute("INSERT INTO app.admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))


def test_save_idempotent_and_own_rejected(db_conn, signed_in_pair):
    saver, owner = signed_in_pair
    ensure_profile(saver)
    ensure_profile(owner)
    public_id = seed_listing(db_conn, owner["id"])
    own_id = seed_listing(db_conn, saver["id"])
    db_conn.commit()
    with TestClient(app) as client:
        first = client.post(f"/listings/{public_id}/save", headers=saver["headers"])
        second = client.post(f"/listings/{public_id}/save", headers=saver["headers"])
        own = client.post(f"/listings/{own_id}/save", headers=saver["headers"])
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"listing_id": public_id, "saved": True}
    assert own.status_code == 400
    assert own.json()["detail"]["code"] == "SAVE_OWN_LISTING"
    assert db_conn.execute(
        "SELECT count(*) FROM app.saved_listings WHERE user_id = %s AND listing_id = %s",
        (saver["id"], public_id),
    ).fetchone()[0] == 1
    assert db_conn.execute(
        "SELECT count(*) FROM app.saved_listings WHERE user_id = %s AND listing_id = %s",
        (saver["id"], own_id),
    ).fetchone()[0] == 0


def test_save_non_public_404_and_unsave_after_non_public_ok(db_conn, signed_in_pair):
    saver, owner = signed_in_pair
    ensure_profile(saver)
    ensure_profile(owner)
    private_id = seed_listing(db_conn, owner["id"], status="rented")
    public_id = seed_listing(db_conn, owner["id"])
    missing_id = str(uuid.uuid4())
    db_conn.commit()
    with TestClient(app) as client:
        hidden_save = client.post(f"/listings/{private_id}/save", headers=saver["headers"])
        assert client.post(f"/listings/{public_id}/save", headers=saver["headers"]).status_code == 200
        db_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
        db_conn.execute("SELECT set_config('app.actor', 'owner', true)")
        db_conn.execute("UPDATE app.listings SET status = 'rented' WHERE id = %s", (public_id,))
        db_conn.commit()
        unsaved = client.delete(f"/listings/{public_id}/save", headers=saver["headers"])
        repeated = client.delete(f"/listings/{public_id}/save", headers=saver["headers"])
        missing = client.delete(f"/listings/{missing_id}/save", headers=saver["headers"])
    assert hidden_save.status_code == 404
    assert unsaved.status_code == repeated.status_code == 200
    assert unsaved.json() == repeated.json() == {"listing_id": public_id, "saved": False}
    assert missing.status_code == 404
    assert db_conn.execute(
        "SELECT count(*) FROM app.saved_listings WHERE user_id = %s AND listing_id = %s",
        (saver["id"], public_id),
    ).fetchone()[0] == 0
    assert db_conn.execute(
        "SELECT count(*) FROM app.saved_listings WHERE user_id = %s AND listing_id = %s",
        (saver["id"], private_id),
    ).fetchone()[0] == 0


def test_me_saved_own_only_keyset_and_wa_link_only_if_visible(db_conn, signed_in_pair):
    tenant, other = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(other)
    visible_id = seed_listing(db_conn, other["id"], title="Visible saved")
    hidden_id = seed_listing(db_conn, other["id"], title="Hidden saved")
    foreign_id = seed_listing(db_conn, tenant["id"], title="Other user's save")
    db_conn.commit()
    with TestClient(app) as client:
        for listing_id in (visible_id, hidden_id):
            assert client.post(f"/listings/{listing_id}/save", headers=tenant["headers"]).status_code == 200
        assert client.post(f"/listings/{foreign_id}/save", headers=other["headers"]).status_code == 200
        db_conn.execute("SELECT set_config('app.user_id', %s, true)", (other["id"],))
        db_conn.execute("SELECT set_config('app.actor', 'owner', true)")
        db_conn.execute("UPDATE app.listings SET status = 'rented' WHERE id = %s", (hidden_id,))
        db_conn.commit()
        first = client.get("/me/saved?page_size=1", headers=tenant["headers"])
        second = client.get(
            "/me/saved", params={"page_size": 1, "cursor": first.json()["next_cursor"]},
            headers=tenant["headers"],
        )
    assert first.status_code == second.status_code == 200
    items = first.json()["saved"] + second.json()["saved"]
    assert {item["id"] for item in items} == {visible_id, hidden_id}
    assert first.json()["saved"][0]["id"] == hidden_id
    assert second.json()["saved"][0]["id"] == visible_id
    visible = next(item for item in items if item["id"] == visible_id)
    hidden = next(item for item in items if item["id"] == hidden_id)
    assert visible["id"] == visible_id and visible["title"] == "Visible saved"
    assert Decimal(str(visible["rent"])) == Decimal("24000.00")
    assert visible["visible"] is True
    assert visible["wa_link"] == "https://wa.me/9779800001234"
    assert hidden["id"] == hidden_id and hidden["title"] == "Hidden saved"
    assert Decimal(str(hidden["rent"])) == Decimal("24000.00")
    assert hidden["visible"] is False and "wa_link" not in hidden
    assert first.json()["next_cursor"] is not None
    assert second.json()["next_cursor"] is None


def test_saved_listing_change_notifies_tenant(db_conn, signed_in_pair):
    saver_one, saver_two = signed_in_pair
    owner = create_auth_user()
    non_saver = create_auth_user()
    try:
        for user in (saver_one, saver_two, owner, non_saver):
            ensure_profile(user)
        title = "Saved rent notification"
        listing_id = seed_listing(db_conn, owner["id"], title=title)
        db_conn.commit()
        with TestClient(app) as client:
            for saver in (saver_one, saver_two):
                assert client.post(f"/listings/{listing_id}/save", headers=saver["headers"]).status_code == 200
            owner_listing = client.get(f"/me/listings/{listing_id}", headers=owner["headers"])
            rent_change = client.patch(
                f"/listings/{listing_id}", headers=owner["headers"],
                json={"version": owner_listing.json()["version"], "rent_amount": 25000},
            )
            assert rent_change.status_code == 200, rent_change.text
            rent_feed = client.get("/me/notifications", headers=saver_one["headers"])
            assert rent_feed.status_code == 200, rent_feed.text
            rent_notification = next(
                item for item in rent_feed.json()["notifications"]
                if item["kind"] == "saved_listing_changed"
            )
            assert rent_notification["kind"] == "saved_listing_changed"
            assert rent_notification["listing"] == {"id": listing_id, "title": title}
            title_change = client.patch(
                f"/listings/{listing_id}", headers=owner["headers"],
                json={"version": rent_change.json()["version"], "title": "Title only"},
            )
            assert title_change.status_code == 200, title_change.text
        rows = db_conn.execute(
            """SELECT user_id, count(*) FROM app.notifications
               WHERE listing_id = %s AND kind = 'saved_listing_changed'
               GROUP BY user_id""",
            (listing_id,),
        ).fetchall()
        assert {str(row[0]): row[1] for row in rows} == {
            saver_one["id"]: 1, saver_two["id"]: 1,
        }
        assert db_conn.execute(
            "SELECT count(*) FROM app.notifications WHERE user_id = %s AND listing_id = %s AND kind = 'saved_listing_changed'",
            (owner["id"], listing_id),
        ).fetchone()[0] == 0
        assert db_conn.execute(
            "SELECT count(*) FROM app.notifications WHERE user_id = %s AND listing_id = %s AND kind = 'saved_listing_changed'",
            (non_saver["id"], listing_id),
        ).fetchone()[0] == 0
    finally:
        delete_auth_user(owner)
        delete_auth_user(non_saver)


def test_saved_listing_visibility_flip_notifies(db_conn, signed_in_pair):
    owner, saver = signed_in_pair
    ensure_profile(owner)
    ensure_profile(saver)
    title = "Visibility notification"
    listing_id = seed_listing(db_conn, owner["id"], title=title)
    add_admin(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        assert client.post(f"/listings/{listing_id}/save", headers=saver["headers"]).status_code == 200
        rented = client.post(
            f"/listings/{listing_id}/status", headers=owner["headers"], json={"status": "rented"}
        )
        assert rented.status_code == 200
        rented_feed = client.get("/me/notifications", headers=saver["headers"])
        assert rented_feed.status_code == 200, rented_feed.text
        assert rented_feed.json()["notifications"][0]["kind"] == "saved_listing_changed"
        assert rented_feed.json()["notifications"][0]["listing"] == {"id": listing_id, "title": title}
        active = client.post(
            f"/listings/{listing_id}/status", headers=owner["headers"], json={"status": "active"}
        )
        assert active.status_code == 200
        suspended = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=owner["headers"],
            json={"reason": "Review"},
        )
        assert suspended.status_code == 200, suspended.text
        suspended_feed = client.get("/me/notifications", headers=saver["headers"])
        assert suspended_feed.status_code == 200, suspended_feed.text
        changed_items = [
            item for item in suspended_feed.json()["notifications"]
            if item["kind"] == "saved_listing_changed" and item["listing"] is not None
            and item["listing"]["id"] == listing_id
        ]
        assert len(changed_items) == 3
        assert all(item["listing"] == {"id": listing_id, "title": title} for item in changed_items)
        unsuspended = client.post(
            f"/admin/listings/{listing_id}/unsuspend", headers=owner["headers"]
        )
        assert unsuspended.status_code == 200, unsuspended.text
    assert db_conn.execute(
        "SELECT count(*) FROM app.notifications WHERE user_id = %s AND listing_id = %s AND kind = 'saved_listing_changed'",
        (saver["id"], listing_id),
    ).fetchone()[0] == 4
    assert db_conn.execute(
        "SELECT count(*) FROM app.notifications WHERE user_id = %s AND listing_id = %s AND kind = 'saved_listing_changed'",
        (owner["id"], listing_id),
    ).fetchone()[0] == 0


def test_report_snapshot_and_idempotent_repeat(db_conn, signed_in_pair):
    reporter, owner = signed_in_pair
    ensure_profile(reporter)
    ensure_profile(owner)
    title = "Snapshot title"
    listing_id = seed_listing(db_conn, owner["id"], title=title, whatsapp=PHONE)
    db_conn.commit()
    with TestClient(app) as client:
        first = client.post(
            f"/listings/{listing_id}/report", headers=reporter["headers"],
            json={"reason": "unsafe listing"},
        )
        db_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
        db_conn.execute("SELECT set_config('app.actor', 'owner', true)")
        db_conn.execute("UPDATE app.listings SET title = 'Changed title' WHERE id = %s", (listing_id,))
        db_conn.execute(
            "UPDATE app.profiles SET whatsapp = '+9779811111111' WHERE id = %s",
            (owner["id"],),
        )
        db_conn.commit()
        repeated = client.post(
            f"/listings/{listing_id}/report", headers=reporter["headers"],
            json={"reason": "different repeat reason"},
        )
    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json()
    row = db_conn.execute(
        "SELECT reporter_id, listing_id, snapshot_title, snapshot_whatsapp, reason FROM app.reports WHERE id = %s",
        (first.json()["id"],),
    ).fetchone()
    assert tuple(str(value) if index < 2 and value is not None else value for index, value in enumerate(row)) == (
        reporter["id"], listing_id, title, PHONE, "unsafe listing",
    )
    assert db_conn.execute(
        "SELECT count(*) FROM app.reports WHERE reporter_id = %s AND listing_id = %s",
        (reporter["id"], listing_id),
    ).fetchone()[0] == 1


def test_report_own_rejected_and_non_public_404(db_conn, signed_in_pair):
    reporter, owner = signed_in_pair
    ensure_profile(reporter)
    ensure_profile(owner)
    own_id = seed_listing(db_conn, reporter["id"])
    hidden_id = seed_listing(db_conn, owner["id"], status="rented")
    db_conn.commit()
    with TestClient(app) as client:
        own = client.post(f"/listings/{own_id}/report", headers=reporter["headers"], json={"reason": "bad"})
        hidden = client.post(f"/listings/{hidden_id}/report", headers=reporter["headers"], json={"reason": "bad"})
    assert own.status_code == 400 and own.json()["detail"]["code"] == "REPORT_OWN_LISTING"
    assert hidden.status_code == 404
    assert db_conn.execute(
        "SELECT count(*) FROM app.reports WHERE reporter_id = %s", (reporter["id"],)
    ).fetchone()[0] == 0


def test_report_cap_ten_per_rolling_24h(db_conn, signed_in_pair):
    reporter, owner = signed_in_pair
    ensure_profile(reporter)
    ensure_profile(owner)
    listing_ids = [seed_listing(db_conn, owner["id"]) for _ in range(11)]
    db_conn.commit()
    with TestClient(app) as client:
        created = [
            client.post(f"/listings/{listing_id}/report", headers=reporter["headers"], json={"reason": "issue"})
            for listing_id in listing_ids[:10]
        ]
        assert all(response.status_code == 200 for response in created)
        repeated = client.post(
            f"/listings/{listing_ids[0]}/report", headers=reporter["headers"], json={"reason": "repeat"}
        )
        assert repeated.status_code == 200
        capped = client.post(
            f"/listings/{listing_ids[10]}/report", headers=reporter["headers"], json={"reason": "issue"}
        )
    assert repeated.json() == created[0].json()
    assert capped.status_code == 429
    assert capped.json()["detail"]["code"] == "REPORT_LIMIT"
    assert int(capped.headers["Retry-After"]) >= 1
    db_conn.execute(
        "UPDATE app.reports SET created_at = now() - interval '25 hours' WHERE id = %s",
        (created[0].json()["id"],),
    )
    db_conn.commit()
    with TestClient(app) as client:
        allowed = client.post(
            f"/listings/{listing_ids[10]}/report", headers=reporter["headers"], json={"reason": "issue"}
        )
        repeat_at_cap = client.post(
            f"/listings/{listing_ids[1]}/report", headers=reporter["headers"], json={"reason": "repeat"}
        )
    assert allowed.status_code == repeat_at_cap.status_code == 200
    assert repeat_at_cap.json() == created[1].json()
    assert db_conn.execute(
        "SELECT count(*) FROM app.reports WHERE reporter_id = %s AND created_at >= now() - interval '24 hours'",
        (reporter["id"],),
    ).fetchone()[0] == 10


def test_report_survives_account_deletion(db_conn, signed_in_pair):
    owner, _ = signed_in_pair
    reporter = create_auth_user()
    try:
        ensure_profile(owner)
        ensure_profile(reporter)
        title = "Reporter deletion snapshot"
        listing_id = seed_listing(db_conn, owner["id"], title=title)
        db_conn.commit()
        with TestClient(app) as client:
            created = client.post(
                f"/listings/{listing_id}/report", headers=reporter["headers"],
                json={"reason": "evidence retained"},
            )
        assert created.status_code == 200
        report_id = created.json()["id"]
        delete_auth_user(reporter)
        row = db_conn.execute(
            "SELECT reporter_id, listing_id, snapshot_title, snapshot_whatsapp, reason FROM app.reports WHERE id = %s",
            (report_id,),
        ).fetchone()
        assert row == (None, uuid.UUID(listing_id), title, PHONE, "evidence retained")
    finally:
        delete_auth_user(reporter)


def test_report_survives_listing_purge(db_conn, signed_in_pair):
    reporter, owner = signed_in_pair
    ensure_profile(reporter)
    ensure_profile(owner)
    title = "Purged listing snapshot"
    listing_id = seed_listing(db_conn, owner["id"], title=title)
    db_conn.commit()
    with TestClient(app) as client:
        created = client.post(
            f"/listings/{listing_id}/report", headers=reporter["headers"],
            json={"reason": "keep report"},
        )
        archived = client.post(f"/listings/{listing_id}/archive", headers=owner["headers"])
        assert archived.status_code == 200
        deleted = client.delete(f"/listings/{listing_id}", headers=owner["headers"])
    assert created.status_code == 200
    assert deleted.status_code == 200, deleted.text
    row = db_conn.execute(
        "SELECT reporter_id, listing_id, snapshot_title, snapshot_whatsapp FROM app.reports WHERE id = %s",
        (created.json()["id"],),
    ).fetchone()
    assert row == (uuid.UUID(reporter["id"]), None, title, PHONE)


def test_admin_route_checks_admins_table(db_conn, signed_in_user):
    user = signed_in_user
    ensure_profile(user)
    report_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    db_conn.commit()
    with TestClient(app) as client:
        unknown = client.get("/no-such-admin-route")
        admin_calls = [
            client.get("/admin/reports", headers=user["headers"]),
            client.post(f"/admin/reports/{report_id}/resolve", headers=user["headers"]),
            client.post(f"/admin/listings/{listing_id}/suspend", headers=user["headers"], json={"reason": "check"}),
            client.post(f"/admin/listings/{listing_id}/unsuspend", headers=user["headers"]),
        ]
    assert all(response.status_code == 404 and response.json() == unknown.json() for response in admin_calls)
    add_admin(db_conn, user["id"])
    db_conn.commit()
    with TestClient(app) as client:
        assert client.get("/admin/reports", headers=user["headers"]).status_code == 200
    db_conn.execute("DELETE FROM app.admins WHERE user_id = %s", (user["id"],))
    db_conn.commit()
    with TestClient(app) as client:
        refused = client.get("/admin/reports", headers=user["headers"])
    assert refused.status_code == 404
    assert refused.json() == unknown.json()


def test_admin_actions_audited(db_conn, signed_in_pair):
    admin, owner = signed_in_pair
    ensure_profile(admin)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    no_note_listing_id = seed_listing(db_conn, owner["id"])
    report_id = db_conn.execute(
        """INSERT INTO app.reports (reporter_id, listing_id, snapshot_title, snapshot_whatsapp, reason)
           SELECT %s, %s, title, %s, 'report reason' FROM app.listings WHERE id = %s RETURNING id""",
        (admin["id"], listing_id, PHONE, listing_id),
    ).fetchone()[0]
    no_note_report_id = db_conn.execute(
        """INSERT INTO app.reports (reporter_id, listing_id, snapshot_title, snapshot_whatsapp, reason)
           SELECT %s, %s, title, %s, 'second reporter reason' FROM app.listings WHERE id = %s RETURNING id""",
        (admin["id"], no_note_listing_id, PHONE, no_note_listing_id),
    ).fetchone()[0]
    add_admin(db_conn, admin["id"])
    db_conn.commit()
    with TestClient(app) as client:
        suspended = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=admin["headers"], json={"reason": "policy"}
        )
        assert suspended.status_code == 200
        suspend_conflict = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=admin["headers"], json={"reason": "again"}
        )
        assert suspend_conflict.status_code == 409
        unsuspended = client.post(f"/admin/listings/{listing_id}/unsuspend", headers=admin["headers"])
        assert unsuspended.status_code == 200
        unsuspend_conflict = client.post(f"/admin/listings/{listing_id}/unsuspend", headers=admin["headers"])
        assert unsuspend_conflict.status_code == 409
        resolved = client.post(
            f"/admin/reports/{report_id}/resolve", headers=admin["headers"], json={"note": "moderator note"}
        )
        assert resolved.status_code == 200
        resolved_without_note = client.post(
            f"/admin/reports/{no_note_report_id}/resolve", headers=admin["headers"]
        )
        assert resolved_without_note.status_code == 200
    actions = db_conn.execute(
        "SELECT admin_id, action, listing_id, reason FROM app.admin_actions WHERE admin_id = %s",
        (admin["id"],),
    ).fetchall()
    assert len(actions) == 4
    assert {
        (row[1], str(row[2])): (str(row[0]), row[3]) for row in actions
    } == {
        ("suspend", listing_id): (admin["id"], "policy"),
        ("unsuspend", listing_id): (admin["id"], None),
        ("resolve_report", listing_id): (admin["id"], "moderator note"),
        ("resolve_report", no_note_listing_id): (admin["id"], None),
    }
    resolve_reasons = [row[3] for row in actions if row[1] == "resolve_report"]
    assert "report reason" not in resolve_reasons
    assert "second reporter reason" not in resolve_reasons


def test_admin_suspend_hides_listing_from_public_and_locks_owner(db_conn, signed_in_pair):
    admin, owner = signed_in_pair
    ensure_profile(admin)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    add_admin(db_conn, admin["id"])
    db_conn.commit()
    with TestClient(app) as client:
        suspended = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=admin["headers"],
            json={"reason": "review"},
        )
        public = client.get(f"/listings/{listing_id}")
        current = client.get(f"/me/listings/{listing_id}", headers=owner["headers"])
        locked = client.patch(
            f"/listings/{listing_id}", headers=owner["headers"],
            json={"version": current.json()["version"], "title": "Blocked edit"},
        )
    assert suspended.status_code == 200
    assert public.status_code == 404
    assert locked.status_code == 409
    row = db_conn.execute(
        "SELECT suspended_at, suspended_by, suspended_reason FROM app.listings WHERE id = %s",
        (listing_id,),
    ).fetchone()
    assert row[0] is not None and str(row[1]) == admin["id"] and row[2] == "review"


def test_admin_suspend_requires_reason_and_409_cases(db_conn, signed_in_pair):
    admin, owner = signed_in_pair
    ensure_profile(admin)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    add_admin(db_conn, admin["id"])
    db_conn.commit()
    with TestClient(app) as client:
        missing_reason = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=admin["headers"], json={"reason": " "}
        )
        assert missing_reason.status_code == 422
        assert client.post(
            f"/admin/listings/{listing_id}/suspend", headers=admin["headers"], json={"reason": "valid"}
        ).status_code == 200
        already = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=admin["headers"], json={"reason": "again"}
        )
        assert already.status_code == 409
        assert client.post(f"/admin/listings/{listing_id}/unsuspend", headers=admin["headers"]).status_code == 200
        not_suspended = client.post(f"/admin/listings/{listing_id}/unsuspend", headers=admin["headers"])
    assert not_suspended.status_code == 409
    assert db_conn.execute(
        "SELECT suspended_at, suspended_by, suspended_reason FROM app.listings WHERE id = %s",
        (listing_id,),
    ).fetchone() == (None, None, None)
    assert db_conn.execute(
        "SELECT count(*) FROM app.admin_actions WHERE listing_id = %s",
        (listing_id,),
    ).fetchone()[0] == 2


def test_admin_resolve_idempotent_no_second_audit_row(db_conn, signed_in_pair):
    admin, reporter = signed_in_pair
    ensure_profile(admin)
    ensure_profile(reporter)
    listing_id = seed_listing(db_conn, admin["id"])
    report_id = db_conn.execute(
        """INSERT INTO app.reports (reporter_id, listing_id, snapshot_title, snapshot_whatsapp, reason)
           SELECT %s, %s, title, %s, 'test report' FROM app.listings WHERE id = %s RETURNING id""",
        (reporter["id"], listing_id, PHONE, listing_id),
    ).fetchone()[0]
    add_admin(db_conn, admin["id"])
    db_conn.commit()
    with TestClient(app) as client:
        first = client.post(f"/admin/reports/{report_id}/resolve", headers=admin["headers"])
        second = client.post(f"/admin/reports/{report_id}/resolve", headers=admin["headers"])
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "resolved"
    assert str(first.json()["resolved_by"]) == admin["id"]
    report_state = db_conn.execute(
        "SELECT status, resolved_by, resolved_at FROM app.reports WHERE id = %s",
        (report_id,),
    ).fetchone()
    assert report_state[0] == "resolved"
    assert str(report_state[1]) == admin["id"]
    assert report_state[2] is not None
    assert db_conn.execute(
        "SELECT count(*) FROM app.admin_actions WHERE action = 'resolve_report' AND listing_id = %s",
        (listing_id,),
    ).fetchone()[0] == 1


def test_admin_actions_not_updatable_or_deletable_by_rentra_api(db_conn, signed_in_pair):
    admin, owner = signed_in_pair
    ensure_profile(admin)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    add_admin(db_conn, admin["id"])
    db_conn.commit()
    with TestClient(app) as client:
        response = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=admin["headers"], json={"reason": "audit"}
        )
    assert response.status_code == 200
    action_id = db_conn.execute(
        "SELECT id FROM app.admin_actions WHERE listing_id = %s AND action = 'suspend'",
        (listing_id,),
    ).fetchone()[0]
    api_conn = psycopg.connect(get_settings().DATABASE_URL)
    try:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (admin["id"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            api_conn.execute("UPDATE app.admin_actions SET reason = 'changed' WHERE id = %s", (action_id,))
        api_conn.rollback()
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (admin["id"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            api_conn.execute("DELETE FROM app.admin_actions WHERE id = %s", (action_id,))
        api_conn.rollback()
    finally:
        api_conn.close()
    assert db_conn.execute(
        "SELECT reason FROM app.admin_actions WHERE id = %s", (action_id,)
    ).fetchone()[0] == "audit"


def test_phone_never_in_logs_or_errors_for_report_and_admin_routes(db_conn, signed_in_pair, caplog):
    reporter, owner = signed_in_pair
    ensure_profile(reporter)
    ensure_profile(owner)
    secret_phone = "+9779800011122"
    listing_id = seed_listing(db_conn, owner["id"], whatsapp=secret_phone)
    db_conn.commit()
    with TestClient(app) as client:
        created = client.post(
            f"/listings/{listing_id}/report", headers=reporter["headers"], json={"reason": "secret report"}
        )
        bad_report = client.post(
            f"/listings/{uuid.uuid4()}/report", headers=reporter["headers"], json={"reason": "bad id"}
        )
        not_admin = client.get("/admin/reports", headers=reporter["headers"])
    assert created.status_code == 200 and secret_phone not in created.text
    assert bad_report.status_code == 404 and secret_phone not in bad_report.text
    assert not_admin.status_code == 404 and secret_phone not in not_admin.text
    add_admin(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        reports = client.get("/admin/reports", headers=owner["headers"])
        bad_resolution = client.post(
            f"/admin/reports/{uuid.uuid4()}/resolve", headers=owner["headers"]
        )
        bad_suspend = client.post(
            f"/admin/listings/{listing_id}/suspend", headers=owner["headers"], json={"reason": " "}
        )
        resolved = client.post(
            f"/admin/reports/{created.json()['id']}/resolve", headers=owner["headers"]
        )
    assert reports.status_code == 200
    listed_report = next(item for item in reports.json()["reports"] if item["id"] == created.json()["id"])
    assert listed_report["snapshot_whatsapp"] == secret_phone
    assert bad_resolution.status_code == 404 and secret_phone not in bad_resolution.text
    assert bad_suspend.status_code == 422 and secret_phone not in bad_suspend.text
    assert resolved.status_code == 200 and secret_phone not in resolved.text
    assert secret_phone not in caplog.text


def test_new_routes_require_auth():
    listing_id = str(uuid.uuid4())
    report_id = str(uuid.uuid4())
    with TestClient(app) as client:
        responses = [
            client.post(f"/listings/{listing_id}/save"),
            client.delete(f"/listings/{listing_id}/save"),
            client.get("/me/saved"),
            client.post(f"/listings/{listing_id}/report", json={"reason": "test"}),
            client.get("/admin/reports"),
            client.post(f"/admin/reports/{report_id}/resolve"),
            client.post(f"/admin/listings/{listing_id}/suspend", json={"reason": "test"}),
            client.post(f"/admin/listings/{listing_id}/unsuspend"),
        ]
    assert [response.status_code for response in responses] == [401] * len(responses)
