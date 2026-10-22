"""Lifecycle and publish-integrity tests against local Supabase Postgres."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg
import pytest

from rentra_api.config import get_settings
from starlette.testclient import TestClient
from rentra_api.main import app


STATUSES = ("draft", "active", "rented", "sold_out", "unavailable", "archived")
OWNER_TRANSITIONS = {
    ("draft", "active"),
    ("draft", "archived"),
    ("active", "rented"),
    ("active", "sold_out"),
    ("active", "unavailable"),
    ("active", "archived"),
    ("rented", "active"),
    ("rented", "archived"),
    ("sold_out", "active"),
    ("sold_out", "archived"),
    ("unavailable", "active"),
    ("unavailable", "archived"),
}


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200


def set_actor(conn: psycopg.Connection, user_id: str | None, actor: str) -> None:
    if user_id is not None:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
    conn.execute("SELECT set_config('app.actor', %s, true)", (actor,))


def insert_listing(
    conn: psycopg.Connection,
    owner_id: str,
    *,
    status: str = "draft",
    archived_from: str = "active",
) -> str:
    set_actor(conn, owner_id, "owner")
    listing_id = conn.execute(
        """INSERT INTO app.listings (owner_id, title, rent_amount, point)
           VALUES (
               %s, 'Lifecycle rental', 24000,
               extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172), 4326)
                   ::extensions.geography
           ) RETURNING id""",
        (owner_id,),
    ).fetchone()[0]

    if status == "active":
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    elif status in ("rented", "sold_out", "unavailable"):
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
        conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    elif status == "archived":
        if archived_from == "active" or archived_from in ("rented", "sold_out", "unavailable"):
            conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
        if archived_from in ("rented", "sold_out", "unavailable"):
            conn.execute(
                "UPDATE app.listings SET status = %s WHERE id = %s",
                (archived_from, listing_id),
            )
        conn.execute("UPDATE app.listings SET status = 'archived' WHERE id = %s", (listing_id,))
    elif status != "draft":
        raise AssertionError(f"unsupported fixture status: {status}")
    return str(listing_id)


def expect_db_error(conn: psycopg.Connection, sql: str, args: tuple, error_type) -> Exception:
    with pytest.raises(error_type) as error:
        with conn.transaction():
            conn.execute(sql, args).fetchall()
    return error.value


def runtime_connection():
    return psycopg.connect(get_settings().DATABASE_URL)


def test_every_illegal_transition_rejected_by_trigger(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    invalid_pairs = [
        (old, new)
        for old in STATUSES[:-1]
        for new in STATUSES
        if old != new and (old, new) not in OWNER_TRANSITIONS
    ]
    assert len(invalid_pairs) == 13

    for old_status, new_status in invalid_pairs:
        listing_id = insert_listing(db_conn, signed_in_user["id"], status=old_status)
        with pytest.raises(psycopg.errors.CheckViolation):
            with db_conn.transaction():
                set_actor(db_conn, signed_in_user["id"], "owner")
                db_conn.execute(
                    "UPDATE app.listings SET status = %s WHERE id = %s",
                    (new_status, listing_id),
                )
        assert db_conn.execute(
            "SELECT status FROM app.listings WHERE id = %s", (listing_id,)
        ).fetchone()[0] == old_status

    for archived_from in STATUSES[:-1]:
        for new_status in STATUSES[:-1]:
            if new_status == archived_from:
                continue
            listing_id = insert_listing(
                db_conn,
                signed_in_user["id"],
                status="archived",
                archived_from=archived_from,
            )
            try:
                with db_conn.transaction():
                    set_actor(db_conn, signed_in_user["id"], "owner")
                    db_conn.execute(
                        "UPDATE app.listings SET status = %s WHERE id = %s",
                        (new_status, listing_id),
                    )
            except psycopg.errors.CheckViolation:
                pass
            else:
                db_conn.commit()
                pytest.fail(
                    f"archived from {archived_from} unexpectedly restored to {new_status}"
                )

    for actor in ("", "unknown"):
        listing_id = insert_listing(db_conn, signed_in_user["id"])
        with pytest.raises(psycopg.errors.CheckViolation):
            with db_conn.transaction():
                set_actor(db_conn, signed_in_user["id"], actor)
                db_conn.execute(
                    "UPDATE app.listings SET status = 'active' WHERE id = %s",
                    (listing_id,),
                )
    db_conn.commit()


def test_publish_requires_fields_answers_amenities_and_phone(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.execute("UPDATE app.listings SET title = '' WHERE id = %s", (listing_id,))
    db_conn.execute("UPDATE app.profiles SET whatsapp = NULL WHERE id = %s", (signed_in_user["id"],))
    db_conn.commit()

    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        error = expect_db_error(
            api_conn,
            "SELECT app.publish_listing(%s)",
            (listing_id,),
            psycopg.errors.RaiseException,
        )
        missing = set((error.diag.message_detail or "").split(","))
        assert "title" in missing
        assert "whatsapp" in missing
        assert "attribute:tenant_type" in missing
        assert "numeric:bedrooms" in missing
        assert "numeric:total_floors" in missing
        assert not any("+977" in item for item in missing)

    set_actor(db_conn, signed_in_user["id"], "owner")
    db_conn.execute("UPDATE app.listings SET title = 'Complete listing' WHERE id = %s", (listing_id,))
    required_attributes = db_conn.execute(
        "SELECT id FROM app.attributes WHERE required_at_publish ORDER BY key"
    ).fetchall()
    for (attribute_id,) in required_attributes:
        option_id = db_conn.execute(
            "SELECT id FROM app.attribute_options WHERE attribute_id = %s ORDER BY sort_order LIMIT 1",
            (attribute_id,),
        ).fetchone()[0]
        db_conn.execute(
            "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
            (listing_id, attribute_id, option_id),
        )
    required_numeric_fields = (
        "bedrooms",
        "bathrooms_total",
        "western_commodes",
        "indian_squat_toilets",
        "kitchen_count",
        "balconies",
        "total_floors",
    )
    for field in required_numeric_fields:
        db_conn.execute(
            "INSERT INTO app.listing_numeric (listing_id, field, value) VALUES (%s, %s, 1)",
            (listing_id, field),
        )
    db_conn.commit()

    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        error = expect_db_error(
            api_conn,
            "SELECT app.publish_listing(%s)",
            (listing_id,),
            psycopg.errors.RaiseException,
        )
        assert error.diag.message_detail == "whatsapp"

        db_conn.execute(
            "UPDATE app.profiles SET whatsapp = '+9779800001111' WHERE id = %s",
            (signed_in_user["id"],),
        )
        db_conn.commit()
        status = api_conn.execute(
            "SELECT (app.publish_listing(%s)).status", (listing_id,)
        ).fetchone()[0]
        assert status == "active"
        assert api_conn.execute("SELECT current_setting('app.actor', true)").fetchone()[0] == ""


def test_restore_before_purge_allowed(db_conn: psycopg.Connection, signed_in_user: dict):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"], status="rented")
    db_conn.commit()
    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        archived = api_conn.execute(
            "SELECT (app.archive_listing(%s)).status", (listing_id,)
        ).fetchone()[0]
        assert archived == "archived"
        assert api_conn.execute("SELECT current_setting('app.actor', true)").fetchone()[0] == ""
        restored = api_conn.execute(
            "SELECT (app.restore_listing(%s)).status", (listing_id,)
        ).fetchone()[0]
        assert restored == "rented"
        assert api_conn.execute("SELECT current_setting('app.actor', true)").fetchone()[0] == ""
    assert db_conn.execute(
        "SELECT archived_from_status, archived_at FROM app.listings WHERE id = %s",
        (listing_id,),
    ).fetchone() == (None, None)


def test_force_delete_archived_ok_and_non_archived_rejected(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    active_id = insert_listing(db_conn, signed_in_user["id"], status="active")
    archived_id = insert_listing(db_conn, signed_in_user["id"], status="archived")
    photo_paths = ["owner-one/photo-a.jpg", "owner-one/photo-b.jpg"]
    for position, path in enumerate(photo_paths, start=1):
        db_conn.execute(
            "INSERT INTO app.listing_photos (listing_id, storage_path, position) VALUES (%s, %s, %s)",
            (archived_id, path, position),
        )
    db_conn.commit()

    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        with pytest.raises(psycopg.errors.CheckViolation):
            with api_conn.transaction():
                api_conn.execute("SELECT app.force_delete_listing(%s)", (active_id,)).fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with api_conn.transaction():
                api_conn.execute(
                    "DELETE FROM app.listings WHERE owner_id = %s AND id = %s",
                    (signed_in_user["id"], archived_id),
                )
        result = api_conn.execute(
            "SELECT app.force_delete_listing(%s)", (archived_id,)
        ).fetchone()[0]
        assert result == photo_paths
        assert api_conn.execute("SELECT current_setting('app.actor', true)").fetchone()[0] == ""

    assert db_conn.execute(
        "SELECT 1 FROM app.listings WHERE id = %s", (archived_id,)
    ).fetchone() is None
    db_conn.commit()


def test_suspended_listing_locked_for_owner(db_conn: psycopg.Connection, signed_in_user: dict):
    ensure_profile(signed_in_user)
    active_id = insert_listing(db_conn, signed_in_user["id"], status="active")
    archived_id = insert_listing(db_conn, signed_in_user["id"], status="archived")
    set_actor(db_conn, signed_in_user["id"], "admin")
    db_conn.execute(
        "UPDATE app.listings SET suspended_at = now(), suspended_by = %s, suspended_reason = 'review' WHERE id = %s",
        (signed_in_user["id"], active_id),
    )
    db_conn.execute(
        "UPDATE app.listings SET suspended_at = now(), suspended_by = %s, suspended_reason = 'review' WHERE id = %s",
        (signed_in_user["id"], archived_id),
    )
    db_conn.commit()

    with runtime_connection() as api_conn:
        set_actor(api_conn, signed_in_user["id"], "owner")
        for sql, args in (
            ("SELECT app.set_listing_status(%s, 'rented')", (active_id,)),
            ("SELECT app.archive_listing(%s)", (active_id,)),
            ("SELECT app.restore_listing(%s)", (archived_id,)),
            ("SELECT app.force_delete_listing(%s)", (archived_id,)),
        ):
            with pytest.raises(psycopg.errors.CheckViolation):
                with api_conn.transaction():
                    api_conn.execute(sql, args).fetchall()

    # Admin may change suspension data, but may not change lifecycle status.
    set_actor(db_conn, signed_in_user["id"], "admin")
    with pytest.raises(psycopg.errors.CheckViolation):
        with db_conn.transaction():
            db_conn.execute("UPDATE app.listings SET status = 'rented' WHERE id = %s", (active_id,))
    db_conn.execute(
        "UPDATE app.listings SET suspended_at = NULL, suspended_by = NULL, suspended_reason = NULL WHERE id = %s",
        (active_id,),
    )
    db_conn.commit()


def test_owner_cannot_call_functions_on_foreign_listing(
    db_conn: psycopg.Connection, signed_in_pair
):
    owner, foreign_owner = signed_in_pair
    ensure_profile(owner)
    ensure_profile(foreign_owner)
    listing_id = insert_listing(db_conn, foreign_owner["id"])
    db_conn.commit()
    calls = (
        ("SELECT app.publish_listing(%s)", (listing_id,)),
        ("SELECT app.set_listing_status(%s, 'active')", (listing_id,)),
        ("SELECT app.archive_listing(%s)", (listing_id,)),
        ("SELECT app.restore_listing(%s)", (listing_id,)),
        ("SELECT app.force_delete_listing(%s)", (listing_id,)),
    )
    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
        for sql, args in calls:
            with pytest.raises(psycopg.errors.NoDataFound) as error:
                with api_conn.transaction():
                    api_conn.execute(sql, args).fetchone()
            assert error.value.diag.message_primary == "LISTING_NOT_FOUND"


def test_rentra_api_cannot_update_status_directly(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.commit()
    with runtime_connection() as api_conn:
        set_actor(api_conn, signed_in_user["id"], "owner")
        with pytest.raises(psycopg.errors.CheckViolation) as error:
            with api_conn.transaction():
                api_conn.execute(
                    "SELECT app.set_listing_status(%s, 'active')", (listing_id,)
                ).fetchone()
        assert error.value.diag.message_primary == "LISTING_INVALID_TRANSITION"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with api_conn.transaction():
                api_conn.execute(
                    "UPDATE app.listings SET status = 'active' WHERE owner_id = %s AND id = %s",
                    (signed_in_user["id"], listing_id),
                )


def test_status_change_sets_status_changed_at_and_bumps_version(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"], status="active")
    db_conn.commit()
    before_version, before_changed_at = db_conn.execute(
        "SELECT version, status_changed_at FROM app.listings WHERE id = %s", (listing_id,)
    ).fetchone()
    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        status, version, changed_at = api_conn.execute(
            "SELECT status, version, status_changed_at FROM app.set_listing_status(%s, 'rented')",
            (listing_id,),
        ).fetchone()
        assert status == "rented"
        assert version == before_version + 1
        assert changed_at > before_changed_at
        assert api_conn.execute("SELECT current_setting('app.actor', true)").fetchone()[0] == ""


def test_rentra_api_cannot_delete_directly_and_actor_cannot_grant_protected_updates(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"], status="archived")
    db_conn.commit()
    protected_columns = (
        "status",
        "archived_from_status",
        "archived_at",
        "status_changed_at",
        "suspended_at",
        "suspended_by",
        "suspended_reason",
        "version",
        "owner_id",
    )
    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with api_conn.transaction():
                api_conn.execute(
                    "DELETE FROM app.listings WHERE owner_id = %s AND id = %s",
                    (signed_in_user["id"], listing_id),
                )
        for actor in ("system", "admin"):
            api_conn.execute("SELECT set_config('app.actor', %s, true)", (actor,))
            for column in protected_columns:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with api_conn.transaction():
                        api_conn.execute(
                            f"UPDATE app.listings SET {column} = {column} WHERE owner_id = %s AND id = %s",
                            (signed_in_user["id"], listing_id),
                        )
        api_conn.execute("SELECT set_config('app.actor', 'owner', true)")
        api_conn.execute("SELECT app.force_delete_listing(%s)", (listing_id,))
        assert api_conn.execute("SELECT current_setting('app.actor', true)").fetchone()[0] == ""


def test_anon_and_authenticated_cannot_execute_lifecycle_functions(db_conn: psycopg.Connection):
    functions = (
        ("app.publish_listing(%s)", (str(uuid.uuid4()),)),
        ("app.set_listing_status(%s, %s)", (str(uuid.uuid4()), "active")),
        ("app.archive_listing(%s)", (str(uuid.uuid4()),)),
        ("app.restore_listing(%s)", (str(uuid.uuid4()),)),
        ("app.force_delete_listing(%s)", (str(uuid.uuid4()),)),
    )
    for role in ("anon", "authenticated"):
        with db_conn.transaction():
            db_conn.execute(f"SET LOCAL ROLE {role}")
            for sql, args in functions:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with db_conn.transaction():
                        db_conn.execute(f"SELECT {sql}", args)


def test_system_archive_requires_30_days(db_conn: psycopg.Connection, signed_in_user: dict):
    ensure_profile(signed_in_user)
    recent_id = insert_listing(db_conn, signed_in_user["id"], status="rented")
    set_actor(db_conn, None, "system")
    with pytest.raises(psycopg.errors.CheckViolation):
        with db_conn.transaction():
            db_conn.execute(
                "UPDATE app.listings SET status = 'archived' WHERE id = %s", (recent_id,)
            )

    old_id = insert_listing(db_conn, signed_in_user["id"], status="unavailable")
    with db_conn.transaction():
        db_conn.execute("ALTER TABLE app.listings DISABLE TRIGGER listings_lifecycle_guard")
        db_conn.execute(
            "UPDATE app.listings SET status_changed_at = now() - interval '31 days' WHERE id = %s",
            (old_id,),
        )
        db_conn.execute("ALTER TABLE app.listings ENABLE TRIGGER listings_lifecycle_guard")
    set_actor(db_conn, None, "system")
    db_conn.execute("UPDATE app.listings SET status = 'archived' WHERE id = %s", (old_id,))
    assert db_conn.execute(
        "SELECT status, archived_from_status FROM app.listings WHERE id = %s", (old_id,)
    ).fetchone() == ("archived", "unavailable")
    db_conn.commit()


def test_listing_content_update_bumps_version_once(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.commit()
    with runtime_connection() as api_conn:
        set_actor(api_conn, signed_in_user["id"], "owner")
        before = api_conn.execute(
            "SELECT version FROM app.listings WHERE owner_id = %s AND id = %s",
            (signed_in_user["id"], listing_id),
        ).fetchone()[0]
        api_conn.execute(
            """UPDATE app.listings
               SET title = 'Changed rental', rent_amount = 27000,
                   point = extensions.st_setsrid(
                       extensions.st_makepoint(85.33, 27.72), 4326
                   )::extensions.geography
               WHERE owner_id = %s AND id = %s""",
            (signed_in_user["id"], listing_id),
        )
        after = api_conn.execute(
            "SELECT version FROM app.listings WHERE owner_id = %s AND id = %s",
            (signed_in_user["id"], listing_id),
        ).fetchone()[0]
        assert after == before + 1

        attribute_id, option_id = api_conn.execute(
            """SELECT attribute.id, option.id FROM app.attributes AS attribute
               JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
               WHERE attribute.key = 'pets' AND option.label = 'yes'"""
        ).fetchone()
        api_conn.execute(
            "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
            (listing_id, attribute_id, option_id),
        )
        child_version = api_conn.execute(
            "SELECT version FROM app.listings WHERE owner_id = %s AND id = %s",
            (signed_in_user["id"], listing_id),
        ).fetchone()[0]
        assert child_version == after + 1


def test_public_profile_and_visibility_follow_status_changes(
    db_conn: psycopg.Connection, signed_in_pair
):
    owner, viewer = signed_in_pair
    ensure_profile(owner)
    ensure_profile(viewer)
    listing_id = insert_listing(db_conn, owner["id"], status="active")
    db_conn.execute(
        "UPDATE app.profiles SET whatsapp = '+9779800002222' WHERE id = %s", (owner["id"],)
    )
    db_conn.commit()

    with runtime_connection() as api_conn:
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (viewer["id"],))
        assert api_conn.execute(
            "SELECT id FROM app.listings WHERE owner_id = %s AND id = %s",
            (owner["id"], listing_id),
        ).fetchone() is not None
        assert api_conn.execute(
            "SELECT whatsapp FROM app.get_public_profile(%s)", (owner["id"],)
        ).fetchone() == ("+9779800002222",)

        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
        api_conn.execute("SELECT app.set_listing_status(%s, 'rented')", (listing_id,))
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (viewer["id"],))
        assert api_conn.execute(
            "SELECT id FROM app.listings WHERE owner_id = %s AND id = %s",
            (owner["id"], listing_id),
        ).fetchone() is None
        assert api_conn.execute(
            "SELECT * FROM app.get_public_profile(%s)", (owner["id"],)
        ).fetchall() == []

        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
        api_conn.execute("SELECT app.set_listing_status(%s, 'active')", (listing_id,))
        api_conn.execute("SELECT set_config('app.user_id', %s, true)", (viewer["id"],))
        assert api_conn.execute(
            "SELECT id FROM app.listings WHERE owner_id = %s AND id = %s",
            (owner["id"], listing_id),
        ).fetchone() is not None
        assert api_conn.execute(
            "SELECT whatsapp FROM app.get_public_profile(%s)", (owner["id"],)
        ).fetchone() == ("+9779800002222",)


def test_publish_blocks_while_whatsapp_clear_in_flight(
    db_conn: psycopg.Connection, signed_in_user: dict
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.execute(
        "UPDATE app.profiles SET whatsapp = '+9779800001111' WHERE id = %s",
        (signed_in_user["id"],),
    )
    db_conn.commit()

    with runtime_connection() as clear_conn:
        clear_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        clear_conn.execute("SELECT app.clear_my_whatsapp(true)")
        with ThreadPoolExecutor(max_workers=1) as pool:
            started = Event()

            def publish_after_clear_lock():
                with runtime_connection() as publish_conn:
                    publish_conn.execute(
                        "SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],)
                    )
                    started.set()
                    try:
                        publish_conn.execute("SELECT app.publish_listing(%s)", (listing_id,))
                    except psycopg.errors.RaiseException as exc:
                        return exc.diag.message_primary, exc.diag.message_detail
                    return "PUBLISHED", None

            future = pool.submit(publish_after_clear_lock)
            assert started.wait(timeout=5)
            try:
                future.result(timeout=0.2)
            except TimeoutError:
                pass
            else:
                pytest.fail("publish did not wait for the in-flight WhatsApp clear")
            clear_conn.commit()
            primary, detail = future.result(timeout=10)

    assert primary == "LISTING_PUBLISH_INCOMPLETE"
    assert "whatsapp" in (detail or "").split(",")
