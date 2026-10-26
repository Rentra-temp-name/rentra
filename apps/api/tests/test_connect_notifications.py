"""Connect and notification integration tests against local Supabase Postgres."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid

import httpx
import psycopg
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


PHONE = "+9779800001234"
POINT_SQL = "extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172), 4326)::extensions.geography"


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200, response.text


def set_whatsapp(conn: psycopg.Connection, user_id: str, value: str | None) -> None:
    conn.execute("UPDATE app.profiles SET whatsapp = %s WHERE id = %s", (value, user_id))


def seed_listing(
    conn: psycopg.Connection,
    owner_id: str,
    *,
    status: str = "active",
    suspended: bool = False,
) -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    set_whatsapp(conn, owner_id, PHONE)
    listing_id = conn.execute(
        f"""INSERT INTO app.listings (owner_id, title, rent_amount, point)
            VALUES (%s, 'Connect fixture', 24000, {POINT_SQL}) RETURNING id""",
        (owner_id,),
    ).fetchone()[0]
    if status != "draft":
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    if status in {"rented", "sold_out", "unavailable", "archived"}:
        conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    if suspended:
        conn.execute("SELECT set_config('app.actor', 'admin', true)")
        conn.execute(
            "UPDATE app.listings SET suspended_at = now(), suspended_by = %s WHERE id = %s",
            (owner_id, listing_id),
        )
        conn.execute("SELECT set_config('app.actor', 'owner', true)")
    return str(listing_id)


def connect(client: TestClient, user: dict, listing_id: str):
    return client.post(f"/listings/{listing_id}/connect", headers=user["headers"])


def create_auth_user() -> dict:
    settings = get_settings()
    email = f"rentra-connect-{uuid.uuid4()}@example.test"
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


def test_connect_twice_one_row_one_notification(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        first = connect(client, connector, listing_id)
        second = connect(client, connector, listing_id)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert db_conn.execute(
        "SELECT count(*) FROM app.connections WHERE user_id = %s AND listing_id = %s",
        (connector["id"], listing_id),
    ).fetchone()[0] == 1
    assert db_conn.execute(
        "SELECT count(*) FROM app.notifications WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == 2


def test_connect_creates_both_notifications_atomically(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    marker_sequence = f"test_notification_marker_{uuid.uuid4().hex}"
    db_conn.execute(f"CREATE SEQUENCE app.{marker_sequence}")
    db_conn.execute(
        f"""CREATE FUNCTION app.test_fail_profile_notification() RETURNS trigger
           LANGUAGE plpgsql AS $$ BEGIN
             IF NEW.kind = 'profile_connected' THEN
               PERFORM nextval('app.{marker_sequence}'::regclass);
               RAISE EXCEPTION 'forced notification failure';
             END IF;
             RETURN NEW;
           END $$"""
    )
    db_conn.execute(
        """CREATE TRIGGER test_fail_profile_notification
           BEFORE INSERT ON app.notifications
           FOR EACH ROW EXECUTE FUNCTION app.test_fail_profile_notification()"""
    )
    db_conn.execute(f"GRANT USAGE, SELECT ON SEQUENCE app.{marker_sequence} TO rentra_api, postgres")
    db_conn.commit()
    try:
        with TestClient(app) as client:
            response = connect(client, connector, listing_id)
        assert response.status_code == 503
        assert db_conn.execute(
            f"SELECT last_value, is_called FROM app.{marker_sequence}"
        ).fetchone() == (1, True)
        assert db_conn.execute(
            "SELECT count(*) FROM app.connections WHERE user_id = %s AND listing_id = %s",
            (connector["id"], listing_id),
        ).fetchone()[0] == 0
    finally:
        db_conn.execute("DROP TRIGGER IF EXISTS test_fail_profile_notification ON app.notifications")
        db_conn.execute("DROP FUNCTION IF EXISTS app.test_fail_profile_notification()")
        db_conn.execute(f"DROP SEQUENCE IF EXISTS app.{marker_sequence}")
        db_conn.commit()


def test_connect_own_listing_rejected(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = seed_listing(db_conn, signed_in_user["id"])
    db_conn.commit()
    with TestClient(app) as client:
        response = connect(client, signed_in_user, listing_id)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CONNECT_OWN_LISTING"


def _seed_cap_listings(conn, owner_id: str, count: int = 52) -> list[str]:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    set_whatsapp(conn, owner_id, PHONE)
    conn.execute(
        f"""INSERT INTO app.listings (owner_id, title, rent_amount, point)
            SELECT %s, 'Cap ' || n, 24000 + n, {POINT_SQL}
            FROM generate_series(1, %s) AS n""",
        (owner_id, count),
    )
    conn.execute(
        "UPDATE app.listings SET status = 'active' WHERE owner_id = %s AND title LIKE 'Cap %%'",
        (owner_id,),
    )
    return [str(row[0]) for row in conn.execute(
        "SELECT id FROM app.listings WHERE owner_id = %s AND title LIKE 'Cap %%' ORDER BY title",
        (owner_id,),
    ).fetchall()]


def test_connect_cap_rolling_24h(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    listing_ids = _seed_cap_listings(db_conn, owner["id"])
    db_conn.execute(
        """INSERT INTO app.connections (user_id, listing_id, created_at)
           SELECT %s, id, now() - interval '25 hours' FROM app.listings
           WHERE id = ANY(%s::uuid[])""",
        (connector["id"], listing_ids[:50]),
    )
    db_conn.commit()
    with TestClient(app) as client:
        assert connect(client, connector, listing_ids[50]).status_code == 200
        db_conn.execute(
            "UPDATE app.connections SET created_at = now() WHERE user_id = %s AND listing_id = ANY(%s::uuid[])",
            (connector["id"], listing_ids[:49]),
        )
        db_conn.commit()
        limited = connect(client, connector, listing_ids[51])
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1
        db_conn.execute(
            "UPDATE app.connections SET created_at = now() - interval '25 hours' WHERE user_id = %s AND listing_id = %s",
            (connector["id"], listing_ids[0]),
        )
        db_conn.commit()
        assert connect(client, connector, listing_ids[51]).status_code == 200


def test_connect_at_cap_repeat_still_succeeds(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    listing_ids = _seed_cap_listings(db_conn, owner["id"], 50)
    db_conn.execute(
        "INSERT INTO app.connections (user_id, listing_id) SELECT %s, unnest(%s::uuid[])",
        (connector["id"], listing_ids),
    )
    db_conn.commit()
    with TestClient(app) as client:
        response = connect(client, connector, listing_ids[0])
    assert response.status_code == 200
    assert db_conn.execute(
        "SELECT count(*) FROM app.connections WHERE user_id = %s", (connector["id"],)
    ).fetchone()[0] == 50


def test_connect_non_public_listing_404(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    listing_ids = [
        seed_listing(db_conn, owner["id"], status="draft"),
        seed_listing(db_conn, owner["id"], status="archived"),
        seed_listing(db_conn, owner["id"], status="rented"),
        seed_listing(db_conn, owner["id"], suspended=True),
    ]
    db_conn.commit()
    with TestClient(app) as client:
        responses = [connect(client, connector, listing_id) for listing_id in listing_ids]
    assert all(response.status_code == 404 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)


def test_connect_requires_auth(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = seed_listing(db_conn, signed_in_user["id"])
    db_conn.commit()
    with TestClient(app) as client:
        connect_response = client.post(f"/listings/{listing_id}/connect")
        connections_response = client.get("/me/connections")
        notifications_response = client.get("/me/notifications")
        profile_response = client.get(f"/me/connections/profile/{uuid.uuid4()}")
        read_response = client.post(f"/me/notifications/{uuid.uuid4()}/read")
    assert all(
        response.status_code == 401
        for response in (
            connect_response, connections_response, notifications_response,
            profile_response, read_response,
        )
    )


def test_connect_returns_wa_link_digits_only(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        response = connect(client, connector, listing_id)
    assert response.status_code == 200
    assert response.json() == {"wa_link": "https://wa.me/9779800001234"}


def test_connect_concurrent_double_call_one_row(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    barrier = Barrier(2)

    def call_connect():
        barrier.wait(timeout=5)
        with TestClient(app) as client:
            return connect(client, connector, listing_id).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: call_connect(), range(2)))
    assert statuses == [200, 200]
    assert db_conn.execute(
        "SELECT count(*) FROM app.connections WHERE user_id = %s AND listing_id = %s",
        (connector["id"], listing_id),
    ).fetchone()[0] == 1
    assert db_conn.execute(
        "SELECT count(*) FROM app.notifications WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == 2


def test_notifications_list_own_only_and_keyset(db_conn, signed_in_pair):
    user, other = signed_in_pair
    ensure_profile(user)
    ensure_profile(other)
    listing_id = seed_listing(db_conn, other["id"])
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    foreign_notification_id = uuid.uuid4()
    db_conn.execute(
        """INSERT INTO app.notifications (id, user_id, kind, listing_id, other_user_id, created_at)
           VALUES (%s, %s, 'property_connected', %s, %s, now() - interval '3 minutes'),
                  (%s, %s, 'property_connected', %s, %s, now() - interval '2 minutes'),
                  (%s, %s, 'property_connected', %s, %s, now() - interval '1 minute'),
                  (%s, %s, 'profile_connected', %s, %s, now())""",
        (ids[0], user["id"], listing_id, other["id"], ids[1], user["id"], listing_id,
         other["id"], ids[2], user["id"], listing_id, other["id"], foreign_notification_id,
         other["id"], listing_id, user["id"]),
    )
    db_conn.commit()
    with TestClient(app) as client:
        first = client.get("/me/notifications?page_size=2", headers=user["headers"])
        second = client.get(
            "/me/notifications", params={"page_size": 2, "cursor": first.json()["next_cursor"]},
            headers=user["headers"],
        )
    assert first.status_code == second.status_code == 200
    first_items = first.json()["notifications"]
    second_items = second.json()["notifications"]
    assert len(first_items) == 2 and len(second_items) == 1
    assert {item["id"] for item in first_items + second_items} == {str(value) for value in ids}
    assert str(foreign_notification_id) not in {
        item["id"] for item in first_items + second_items
    }
    assert all(item["kind"] == "property_connected" for item in first_items + second_items)
    assert all(
        item["listing"] == {"id": listing_id, "title": "Connect fixture"}
        for item in first_items + second_items
    )
    assert all(item["other_user"]["id"] == other["id"] for item in first_items + second_items)
    assert first.json()["unread_count"] == 3


def test_notification_read_idempotent(db_conn, signed_in_pair):
    user, other = signed_in_pair
    ensure_profile(user)
    ensure_profile(other)
    notification_id = db_conn.execute(
        """INSERT INTO app.notifications (user_id, kind, other_user_id)
           VALUES (%s, 'profile_connected', %s) RETURNING id""",
        (user["id"], other["id"]),
    ).fetchone()[0]
    db_conn.commit()
    with TestClient(app) as client:
        path = f"/me/notifications/{notification_id}/read"
        first = client.post(path, headers=user["headers"])
        second = client.post(path, headers=user["headers"])
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    first_read_at = first.json()["read_at"]
    second_read_at = second.json()["read_at"]
    assert first_read_at is not None
    assert second_read_at is not None
    assert first_read_at == second_read_at
    persisted_read_at = db_conn.execute(
        "SELECT read_at FROM app.notifications WHERE id = %s AND user_id = %s",
        (notification_id, user["id"]),
    ).fetchone()[0]
    assert persisted_read_at is not None
    assert persisted_read_at.isoformat() == first_read_at.replace("Z", "+00:00")


def test_notification_read_foreign_id_404(db_conn, signed_in_pair):
    user, other = signed_in_pair
    ensure_profile(user)
    ensure_profile(other)
    notification_id = db_conn.execute(
        """INSERT INTO app.notifications (user_id, kind)
           VALUES (%s, 'profile_connected') RETURNING id""",
        (other["id"],),
    ).fetchone()[0]
    db_conn.commit()
    with TestClient(app) as client:
        response = client.post(
            f"/me/notifications/{notification_id}/read", headers=user["headers"]
        )
    assert response.status_code == 404


def test_connections_list_own_only_and_wa_link_only_if_public(db_conn, signed_in_pair):
    connector, owner = signed_in_pair
    ensure_profile(connector)
    ensure_profile(owner)
    public_id = seed_listing(db_conn, owner["id"])
    hidden_id = seed_listing(db_conn, owner["id"])
    foreign_id = seed_listing(db_conn, connector["id"])
    db_conn.commit()
    with TestClient(app) as client:
        assert connect(client, connector, public_id).status_code == 200
        assert connect(client, connector, hidden_id).status_code == 200
        assert connect(client, owner, foreign_id).status_code == 200
    db_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
    db_conn.execute("SELECT set_config('app.actor', 'owner', true)")
    db_conn.execute("UPDATE app.listings SET status = 'rented' WHERE id = %s", (hidden_id,))
    db_conn.commit()
    with TestClient(app) as client:
        response = client.get(
            "/me/connections?page_size=1", headers=connector["headers"]
        )
        next_page = client.get(
            "/me/connections",
            params={"page_size": 1, "cursor": response.json()["next_cursor"]},
            headers=connector["headers"],
        )
        owner_response = client.get("/me/connections", headers=owner["headers"])
    assert response.status_code == next_page.status_code == owner_response.status_code == 200
    items = response.json()["connections"] + next_page.json()["connections"]
    assert len(response.json()["connections"]) == len(next_page.json()["connections"]) == 1
    assert response.json()["next_cursor"] is not None
    assert {item["listing"]["id"] for item in items} == {public_id, hidden_id}
    assert all(item["listing"].get("wa_link") == "https://wa.me/9779800001234" for item in items if item["listing"]["id"] == public_id)
    hidden = next(item for item in items if item["listing"]["id"] == hidden_id)
    assert "wa_link" not in hidden["listing"]
    assert {item["listing"]["id"] for item in owner_response.json()["connections"]} == {foreign_id}


def test_connection_and_notifications_cascade_on_account_delete(db_conn, signed_in_user):
    connector = create_auth_user()
    owner = signed_in_user
    try:
        ensure_profile(connector)
        ensure_profile(owner)
        listing_id = seed_listing(db_conn, owner["id"])
        db_conn.commit()
        with TestClient(app) as client:
            assert connect(client, connector, listing_id).status_code == 200

        settings = get_settings()
        with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
            deleted = auth.delete(
                f"/auth/v1/admin/users/{connector['id']}",
                headers=connector["admin_headers"],
            )
        assert deleted.status_code in (200, 204), deleted.text

        assert db_conn.execute(
            "SELECT count(*) FROM app.connections WHERE user_id = %s", (connector["id"],)
        ).fetchone()[0] == 0
        assert db_conn.execute(
            "SELECT count(*) FROM app.notifications WHERE user_id = %s", (connector["id"],)
        ).fetchone()[0] == 0
        notification_refs = db_conn.execute(
            """SELECT listing_id, other_user_id FROM app.notifications
               WHERE user_id = %s AND kind = 'profile_connected'""",
            (owner["id"],),
        ).fetchone()
        assert (str(notification_refs[0]), notification_refs[1]) == (listing_id, None)
    finally:
        settings = get_settings()
        with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
            cleanup = auth.delete(
                f"/auth/v1/admin/users/{connector['id']}",
                headers=connector["admin_headers"],
            )
        assert cleanup.status_code in (200, 204, 404), cleanup.text


def test_connect_without_tenant_whatsapp_succeeds(db_conn, signed_in_pair):
    tenant, owner = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(owner)
    set_whatsapp(db_conn, tenant["id"], None)
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        response = connect(client, tenant, listing_id)
    assert response.status_code == 200
    assert response.json()["wa_link"] == "https://wa.me/9779800001234"


def test_landlord_can_open_connector_profile(db_conn, signed_in_pair):
    tenant, owner = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(owner)
    db_conn.execute("UPDATE app.profiles SET display_name = 'Tenant Name', whatsapp = %s WHERE id = %s", (PHONE, tenant["id"]))
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        assert connect(client, tenant, listing_id).status_code == 200
        response = client.get(f"/me/connections/profile/{tenant['id']}", headers=owner["headers"])
    assert response.status_code == 200
    assert response.json() == {
        "display_name": "Tenant Name", "whatsapp": PHONE,
        "wa_link": "https://wa.me/9779800001234",
    }


def test_connector_profile_null_whatsapp_when_tenant_has_none(db_conn, signed_in_pair):
    tenant, owner = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(owner)
    set_whatsapp(db_conn, tenant["id"], None)
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        assert connect(client, tenant, listing_id).status_code == 200
        response = client.get(f"/me/connections/profile/{tenant['id']}", headers=owner["headers"])
    assert response.status_code == 200
    assert response.json()["whatsapp"] is None and response.json()["wa_link"] is None


def test_connector_whatsapp_cleared_later_disappears(db_conn, signed_in_pair):
    tenant, owner = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(owner)
    db_conn.execute("UPDATE app.profiles SET whatsapp = %s WHERE id = %s", (PHONE, tenant["id"]))
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        assert connect(client, tenant, listing_id).status_code == 200
        before = client.get(
            f"/me/connections/profile/{tenant['id']}", headers=owner["headers"]
        )
        assert before.status_code == 200
        assert before.json()["whatsapp"] == PHONE
        assert before.json()["wa_link"] == "https://wa.me/9779800001234"
        cleared = client.put(
            "/me", headers=tenant["headers"], json={"whatsapp": None, "confirm": True}
        )
        assert cleared.status_code == 200, cleared.text
        response = client.get(f"/me/connections/profile/{tenant['id']}", headers=owner["headers"])
    assert response.status_code == 200
    assert response.json()["whatsapp"] is None and response.json()["wa_link"] is None


def test_connector_profile_foreign_user_404(db_conn, signed_in_pair):
    tenant, owner = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(owner)
    db_conn.commit()
    with TestClient(app) as client:
        foreign = client.get(f"/me/connections/profile/{tenant['id']}", headers=owner["headers"])
        missing = client.get(f"/me/connections/profile/{uuid.uuid4()}", headers=owner["headers"])
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_tenant_can_open_landlord_profile_only_while_listing_public(db_conn, signed_in_pair):
    tenant, owner = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    owner_display_name, owner_whatsapp = db_conn.execute(
        "SELECT display_name, whatsapp FROM app.profiles WHERE id = %s", (owner["id"],)
    ).fetchone()
    db_conn.commit()
    with TestClient(app) as client:
        assert connect(client, tenant, listing_id).status_code == 200
        visible = client.get(f"/me/connections/profile/{owner['id']}", headers=tenant["headers"])
    assert visible.status_code == 200
    assert visible.json()["display_name"] == owner_display_name
    assert visible.json()["whatsapp"] == owner_whatsapp
    assert visible.json()["wa_link"] == "https://wa.me/" + "".join(
        character for character in owner_whatsapp if character.isdigit()
    )
    db_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
    db_conn.execute("SELECT set_config('app.actor', 'owner', true)")
    db_conn.execute("UPDATE app.listings SET status = 'rented' WHERE id = %s", (listing_id,))
    db_conn.commit()
    with TestClient(app) as client:
        hidden = client.get(f"/me/connections/profile/{owner['id']}", headers=tenant["headers"])
        missing = client.get(f"/me/connections/profile/{uuid.uuid4()}", headers=tenant["headers"])
    assert hidden.status_code == 404 and hidden.json() == missing.json()


def test_connector_phone_never_in_logs_or_errors(db_conn, signed_in_pair, caplog):
    tenant, owner = signed_in_pair
    ensure_profile(tenant)
    ensure_profile(owner)
    secret_phone = "+9779800012345"
    db_conn.execute("UPDATE app.profiles SET whatsapp = %s WHERE id = %s", (secret_phone, tenant["id"]))
    listing_id = seed_listing(db_conn, owner["id"])
    db_conn.commit()
    with TestClient(app) as client:
        connected = connect(client, tenant, listing_id)
        assert connected.status_code == 200
        notifications = client.get("/me/notifications", headers=tenant["headers"])
        connections = client.get("/me/connections", headers=tenant["headers"])
        own_listing = seed_listing(db_conn, tenant["id"])
        set_whatsapp(db_conn, tenant["id"], secret_phone)
        db_conn.commit()
        failed = connect(client, tenant, own_listing)
        assert failed.status_code == 400
    assert secret_phone not in connected.text
    assert secret_phone not in failed.text
    assert notifications.status_code == 200
    assert connections.status_code == 200
    assert secret_phone not in notifications.text
    assert secret_phone not in connections.text
    assert secret_phone not in caplog.text
