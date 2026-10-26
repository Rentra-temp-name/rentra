"""WhatsApp clearing and listing lifecycle integration tests against Postgres."""

from __future__ import annotations

import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app, read_limiter


@pytest.fixture(autouse=True)
def clear_read_limiter():
    read_limiter.clear()
    yield
    read_limiter.clear()


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
        assert response.status_code == 200
        if response.json()["whatsapp"] is None:
            response = client.put(
                "/me", headers=user["headers"], json={"whatsapp": "9800001001"}
            )
            assert response.status_code == 200


def insert_listing(
    conn: psycopg.Connection,
    owner_id: str,
    *,
    status: str = "active",
    suspended: bool = False,
) -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    listing_id = conn.execute(
        """INSERT INTO app.listings (owner_id, title, rent_amount, point)
           VALUES (%s, 'WhatsApp test listing', 24000,
               extensions.st_setsrid(
                   extensions.st_makepoint(85.3249, 27.7172), 4326
               )::extensions.geography)
           RETURNING id""",
        (owner_id,),
    ).fetchone()[0]
    if status != "draft":
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
        if status != "active":
            conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    if suspended:
        conn.execute("SELECT set_config('app.actor', 'admin', true)")
        conn.execute(
            "UPDATE app.listings SET suspended_at = now(), suspended_by = %s WHERE id = %s",
            (owner_id, listing_id),
        )
    return str(listing_id)


def api_connection():
    return psycopg.connect(get_settings().DATABASE_URL)


def test_clear_without_confirm_is_rejected_and_changes_nothing(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.commit()

    with TestClient(app) as client:
        response = client.put(
            "/me", headers=signed_in_user["headers"], json={"whatsapp": None}
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "WHATSAPP_CLEAR_ARCHIVES_LISTINGS"
    assert response.json()["detail"]["active_listings"] == 1
    assert db_conn.execute(
        "SELECT status FROM app.listings WHERE id = %s", (listing_id,)
    ).fetchone()[0] == "active"
    assert db_conn.execute(
        "SELECT whatsapp FROM app.profiles WHERE id = %s", (signed_in_user["id"],)
    ).fetchone()[0] is not None


def test_confirmed_clear_archives_only_active_non_suspended_listings(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    active_ids = [
        insert_listing(db_conn, signed_in_user["id"]),
        insert_listing(db_conn, signed_in_user["id"]),
    ]
    other_statuses = {
        status: insert_listing(db_conn, signed_in_user["id"], status=status)
        for status in ("draft", "rented", "sold_out", "unavailable")
    }
    db_conn.commit()

    with TestClient(app) as client:
        response = client.put(
            "/me", headers=signed_in_user["headers"], json={"whatsapp": "", "confirm": True}
        )
    assert response.status_code == 200
    assert response.json()["whatsapp"] is None
    for listing_id in active_ids:
        assert db_conn.execute(
            "SELECT status, archived_from_status FROM app.listings WHERE id = %s",
            (listing_id,),
        ).fetchone() == ("archived", "active")
    for status, listing_id in other_statuses.items():
        assert db_conn.execute(
            "SELECT status FROM app.listings WHERE id = %s", (listing_id,)
        ).fetchone()[0] == status


def test_suspended_active_listing_blocks_whatsapp_clear(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"], suspended=True)
    db_conn.commit()

    with TestClient(app) as client:
        response = client.put(
            "/me", headers=signed_in_user["headers"], json={"whatsapp": None, "confirm": True}
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "WHATSAPP_REQUIRED_FOR_ACTIVE_LISTING"
    assert db_conn.execute(
        "SELECT status, suspended_at FROM app.listings WHERE id = %s", (listing_id,)
    ).fetchone()[0] == "active"
    assert db_conn.execute(
        "SELECT whatsapp FROM app.profiles WHERE id = %s", (signed_in_user["id"],)
    ).fetchone()[0] is not None


def test_direct_whatsapp_clear_is_rejected_while_listing_is_active(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    insert_listing(db_conn, signed_in_user["id"])
    db_conn.commit()

    with pytest.raises(psycopg.errors.RaiseException) as error:
        with db_conn.transaction():
            db_conn.execute(
                "UPDATE app.profiles SET whatsapp = NULL WHERE id = %s",
                (signed_in_user["id"],),
            )
    assert error.value.diag.message_primary == "WHATSAPP_REQUIRED_FOR_ACTIVE_LISTING"


def test_restore_and_reactivation_require_whatsapp_then_succeed(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    to_restore_active = insert_listing(db_conn, signed_in_user["id"])
    to_restore_rented = insert_listing(db_conn, signed_in_user["id"], status="rented")
    to_reactivate = insert_listing(db_conn, signed_in_user["id"], status="rented")
    db_conn.execute(
        "UPDATE app.listings SET status = 'archived' WHERE id = %s", (to_restore_active,)
    )
    db_conn.execute(
        "UPDATE app.listings SET status = 'archived' WHERE id = %s", (to_restore_rented,)
    )
    db_conn.commit()

    with TestClient(app) as client:
        cleared = client.put(
            "/me", headers=signed_in_user["headers"], json={"whatsapp": None, "confirm": True}
        )
    assert cleared.status_code == 200

    with api_connection() as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        with pytest.raises(psycopg.errors.RaiseException) as error:
            with conn.transaction():
                conn.execute("SELECT app.restore_listing(%s)", (to_restore_active,))
        assert error.value.diag.message_primary == "WHATSAPP_REQUIRED"
        assert conn.execute(
            "SELECT (app.restore_listing(%s)).status", (to_restore_rented,)
        ).fetchone()[0] == "rented"
        with pytest.raises(psycopg.errors.RaiseException) as error:
            with conn.transaction():
                conn.execute(
                    "SELECT app.set_listing_status(%s, 'active')", (to_reactivate,)
                )
        assert error.value.diag.message_primary == "WHATSAPP_REQUIRED"

    with TestClient(app) as client:
        restored_phone = client.put(
            "/me", headers=signed_in_user["headers"], json={"whatsapp": "9800001002"}
        )
    assert restored_phone.status_code == 200
    with api_connection() as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        assert conn.execute(
            "SELECT (app.restore_listing(%s)).status", (to_restore_active,)
        ).fetchone()[0] == "active"
        assert conn.execute(
            "SELECT (app.set_listing_status(%s, 'active')).status", (to_reactivate,)
        ).fetchone()[0] == "active"


def test_restored_listing_returns_to_public_reads(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.execute("UPDATE app.listings SET status = 'archived' WHERE id = %s", (listing_id,))
    db_conn.commit()

    with TestClient(app) as client:
        hidden = client.get("/listings")
        assert client.get(f"/listings/{listing_id}").status_code == 404
        assert listing_id not in {item["id"] for item in hidden.json()["listings"]}

    with api_connection() as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        conn.execute("SELECT app.restore_listing(%s)", (listing_id,))
    with TestClient(app) as client:
        visible = client.get("/listings")
        detail = client.get(f"/listings/{listing_id}")
    assert listing_id in {item["id"] for item in visible.json()["listings"]}
    assert detail.status_code == 200


def test_whatsapp_clear_never_touches_foreign_listings(db_conn, signed_in_pair):
    owner, foreign_owner = signed_in_pair
    ensure_profile(owner)
    ensure_profile(foreign_owner)
    owner_listing = insert_listing(db_conn, owner["id"])
    foreign_listing = insert_listing(db_conn, foreign_owner["id"])
    db_conn.commit()

    with TestClient(app) as client:
        response = client.put(
            "/me", headers=owner["headers"], json={"whatsapp": None, "confirm": True}
        )
    assert response.status_code == 200
    assert db_conn.execute(
        "SELECT status FROM app.listings WHERE id = %s", (owner_listing,)
    ).fetchone()[0] == "archived"
    assert db_conn.execute(
        "SELECT status FROM app.listings WHERE id = %s", (foreign_listing,)
    ).fetchone()[0] == "active"
    assert db_conn.execute(
        "SELECT whatsapp FROM app.profiles WHERE id = %s", (foreign_owner["id"],)
    ).fetchone()[0] is not None
