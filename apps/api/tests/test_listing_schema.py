"""Real Postgres tests for listing tables, visibility, and version triggers."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


def ensure_profile(user) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200


def insert_listing(
    conn: psycopg.Connection,
    owner_id: str,
    *,
    status: str = "draft",
    rent_amount: str = "25000.00",
    longitude: str = "85.3249",
    latitude: str = "27.7172",
    suspended_at=None,
) -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    row = conn.execute(
        """INSERT INTO app.listings
               (owner_id, title, rent_amount, point)
           VALUES (
               %s, 'Test rental', %s,
               extensions.st_setsrid(
                   extensions.st_makepoint(%s::float8, %s::float8), 4326
               )::extensions.geography
           )
           RETURNING id""",
        (owner_id, rent_amount, longitude, latitude),
    ).fetchone()
    listing_id = str(row[0])
    if status != "draft":
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
        if status != "active":
            conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    if suspended_at is not None:
        conn.execute("SELECT set_config('app.actor', 'admin', true)")
        conn.execute(
            "UPDATE app.listings SET suspended_at = %s, suspended_by = %s WHERE id = %s",
            (suspended_at, owner_id, listing_id),
        )
        conn.execute("SELECT set_config('app.actor', 'owner', true)")
    return listing_id


def test_listing_rejects_points_outside_nepal(db_conn: psycopg.Connection, signed_in_user):
    ensure_profile(signed_in_user)
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_listing(db_conn, signed_in_user["id"], longitude="90", latitude="27.7")


def test_listing_rejects_nan_point(db_conn: psycopg.Connection, signed_in_user):
    ensure_profile(signed_in_user)
    with pytest.raises(psycopg.Error):
        insert_listing(db_conn, signed_in_user["id"], longitude="NaN", latitude="27.7")


@pytest.mark.parametrize("rent_amount", ["0", "-1", "NaN"])
def test_listing_rejects_non_positive_or_nan_rent(
    db_conn: psycopg.Connection, signed_in_user, rent_amount: str
):
    ensure_profile(signed_in_user)
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_listing(db_conn, signed_in_user["id"], rent_amount=rent_amount)


def test_listing_numeric_rejects_rent_amount_field(db_conn: psycopg.Connection, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    with pytest.raises(psycopg.errors.CheckViolation):
        db_conn.execute(
            "INSERT INTO app.listing_numeric (listing_id, field, value) VALUES (%s, 'rent_amount', 25000)",
            (listing_id,),
        )


def test_listing_photo_position_is_limited_to_one_through_ten(
    db_conn: psycopg.Connection, signed_in_user
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    for position in range(1, 11):
        storage_path = f"{uuid.uuid4()}.jpg"
        thumb_path = f"{uuid.uuid4()}-thumb.jpg"
        db_conn.execute(
            """INSERT INTO app.listing_photos
                   (listing_id, storage_path, thumb_path, width, height, position)
               VALUES (%s, %s, %s, 100, 100, %s)""",
            (listing_id, storage_path, thumb_path, position),
        )
    overflow_thumb = f"{uuid.uuid4()}-thumb.jpg"
    with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
        db_conn.execute(
            """INSERT INTO app.listing_photos
                   (listing_id, storage_path, thumb_path, width, height, position)
               VALUES (%s, 'overflow.jpg', %s, 100, 100, 11)""",
            (listing_id, overflow_thumb),
        )
    assert exc_info.value.diag.constraint_name == "listing_photos_position_check"


def test_listing_photo_positions_are_unique_per_listing(
    db_conn: psycopg.Connection, signed_in_user
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.execute(
        """INSERT INTO app.listing_photos
               (listing_id, storage_path, thumb_path, width, height, position)
           VALUES (%s, 'one.jpg', 'one-thumb.jpg', 100, 100, 1)""",
        (listing_id,),
    )
    db_conn.commit()
    with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
        with db_conn.transaction():
            db_conn.execute(
                """INSERT INTO app.listing_photos
                       (listing_id, storage_path, thumb_path, width, height, position)
                   VALUES (%s, 'duplicate.jpg', 'duplicate-thumb.jpg', 100, 100, 1)""",
                (listing_id,),
            )
            db_conn.execute("SET CONSTRAINTS app.listing_photos_listing_position_key IMMEDIATE")
    assert exc_info.value.diag.constraint_name == "listing_photos_listing_position_key"


def test_listing_answer_option_must_belong_to_its_attribute(
    db_conn: psycopg.Connection, signed_in_user
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    pets_id = db_conn.execute(
        """SELECT attribute.id
           FROM app.attributes AS attribute
           JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
           WHERE attribute.key = 'pets' AND option.label = 'yes'"""
    ).fetchone()
    pets_id = pets_id[0]
    dietary_other_option_id = db_conn.execute(
        """SELECT option.id
           FROM app.attributes AS attribute
           JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
           WHERE attribute.key = 'dietary'
           ORDER BY option.sort_order
           LIMIT 1"""
    ).fetchone()[0]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db_conn.execute(
            "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
            (listing_id, pets_id, dietary_other_option_id),
        )
    db_conn.rollback()
    # The rollback also clears this test's setup, so no commit is needed.


@pytest.mark.parametrize("attribute_key", ["dietary", "pets"])
def test_single_and_yes_no_attributes_allow_only_one_answer(
    db_conn: psycopg.Connection, signed_in_user, attribute_key: str
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    attribute_id, first_option_id, second_option_id = db_conn.execute(
        """SELECT attribute.id, first_option.id, second_option.id
           FROM app.attributes AS attribute
           JOIN app.attribute_options AS first_option ON first_option.attribute_id = attribute.id
           JOIN app.attribute_options AS second_option ON second_option.attribute_id = attribute.id
           WHERE attribute.key = %s
             AND first_option.sort_order = 1
             AND second_option.sort_order = 2""",
        (attribute_key,),
    ).fetchone()
    db_conn.execute(
        "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
        (listing_id, attribute_id, first_option_id),
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        db_conn.execute(
            "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
            (listing_id, attribute_id, second_option_id),
        )


def test_multi_attribute_allows_multiple_answers(db_conn: psycopg.Connection, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    attribute_id, first_option_id, second_option_id = db_conn.execute(
        """SELECT attribute.id, first_option.id, second_option.id
           FROM app.attributes AS attribute
           JOIN app.attribute_options AS first_option ON first_option.attribute_id = attribute.id
           JOIN app.attribute_options AS second_option ON second_option.attribute_id = attribute.id
           WHERE attribute.key = 'tenant_type'
             AND first_option.sort_order = 1
             AND second_option.sort_order = 2"""
    ).fetchone()

    db_conn.execute(
        "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
        (listing_id, attribute_id, first_option_id),
    )
    db_conn.execute(
        "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
        (listing_id, attribute_id, second_option_id),
    )
    assert db_conn.execute(
        "SELECT count(*) FROM app.listing_answers WHERE listing_id = %s AND attribute_id = %s",
        (listing_id, attribute_id),
    ).fetchone()[0] == 2
    db_conn.commit()


@pytest.mark.parametrize("child_table", ["listing_answers", "listing_numeric", "listing_photos"])
def test_child_insert_update_delete_bumps_listing_version(
    db_conn: psycopg.Connection, signed_in_user, child_table: str
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])

    if child_table == "listing_answers":
        attribute_id, option_id = db_conn.execute(
            """SELECT attribute.id, option.id
               FROM app.attributes AS attribute
               JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
               WHERE attribute.key = 'pets' AND option.label = 'yes'"""
        ).fetchone()
        child_key = (listing_id, attribute_id, option_id)
        insert = "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)"
        update = "UPDATE app.listing_answers SET option_id = %s WHERE listing_id = %s AND attribute_id = %s AND option_id = %s"
        update_args = (option_id, *child_key)
        delete = "DELETE FROM app.listing_answers WHERE listing_id = %s AND attribute_id = %s AND option_id = %s"
        delete_args = child_key
    elif child_table == "listing_numeric":
        child_key = (listing_id, "bedrooms")
        insert = "INSERT INTO app.listing_numeric (listing_id, field, value) VALUES (%s, %s, 2)"
        update = "UPDATE app.listing_numeric SET value = 3 WHERE listing_id = %s AND field = %s"
        update_args = child_key
        delete = "DELETE FROM app.listing_numeric WHERE listing_id = %s AND field = %s"
        delete_args = child_key
    else:
        photo_id = str(uuid.uuid4())
        child_key = (listing_id, photo_id)
        insert = """INSERT INTO app.listing_photos
                     (listing_id, id, storage_path, thumb_path, width, height, position)
                     VALUES (%s, %s, 'one.jpg', 'one-thumb.jpg', 100, 100, 1)"""
        update = "UPDATE app.listing_photos SET storage_path = 'changed.jpg' WHERE listing_id = %s AND id = %s"
        update_args = child_key
        delete = "DELETE FROM app.listing_photos WHERE listing_id = %s AND id = %s"
        delete_args = child_key

    version_sql = "SELECT version FROM app.listings WHERE id = %s"
    before = db_conn.execute(version_sql, (listing_id,)).fetchone()[0]
    db_conn.execute(insert, child_key)
    assert db_conn.execute(version_sql, (listing_id,)).fetchone()[0] == before + 1

    db_conn.execute(update, update_args)
    assert db_conn.execute(version_sql, (listing_id,)).fetchone()[0] == before + 2

    db_conn.execute(delete, delete_args)
    assert db_conn.execute(version_sql, (listing_id,)).fetchone()[0] == before + 3
    db_conn.commit()


def test_deleting_listing_cascades_to_answers_numeric_and_photos(
    db_conn: psycopg.Connection, signed_in_user
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    attribute_id, option_id = db_conn.execute(
        """SELECT attribute.id, option.id
           FROM app.attributes AS attribute
           JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
           WHERE attribute.key = 'tenant_type' AND option.sort_order = 1"""
    ).fetchone()
    db_conn.execute(
        "INSERT INTO app.listing_answers (listing_id, attribute_id, option_id) VALUES (%s, %s, %s)",
        (listing_id, attribute_id, option_id),
    )
    db_conn.execute(
        "INSERT INTO app.listing_numeric (listing_id, field, value) VALUES (%s, 'bedrooms', 2)",
        (listing_id,),
    )
    db_conn.execute(
        """INSERT INTO app.listing_photos
               (listing_id, storage_path, thumb_path, width, height, position)
           VALUES (%s, 'cascade.jpg', 'cascade-thumb.jpg', 100, 100, 1)""",
        (listing_id,),
    )

    db_conn.execute("UPDATE app.listings SET status = 'archived' WHERE id = %s", (listing_id,))
    db_conn.execute("DELETE FROM app.listings WHERE id = %s", (listing_id,))
    assert db_conn.execute(
        "SELECT count(*) FROM app.listing_answers WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == 0
    assert db_conn.execute(
        "SELECT count(*) FROM app.listing_numeric WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == 0
    assert db_conn.execute(
        "SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == 0
    db_conn.commit()


def test_direct_child_delete_still_bumps_listing_version(
    db_conn: psycopg.Connection, signed_in_user
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    photo_id = str(uuid.uuid4())
    db_conn.execute(
        """INSERT INTO app.listing_photos
               (listing_id, id, storage_path, thumb_path, width, height, position)
           VALUES (%s, %s, 'delete.jpg', 'delete-thumb.jpg', 100, 100, 1)""",
        (listing_id, photo_id),
    )
    before = db_conn.execute(
        "SELECT version FROM app.listings WHERE id = %s", (listing_id,)
    ).fetchone()[0]
    db_conn.execute(
        "DELETE FROM app.listing_photos WHERE listing_id = %s AND id = %s",
        (listing_id, photo_id),
    )
    assert db_conn.execute(
        "SELECT version FROM app.listings WHERE id = %s", (listing_id,)
    ).fetchone()[0] == before + 1
    db_conn.commit()


def test_rentra_api_cannot_update_protected_listing_columns(
    db_conn: psycopg.Connection, signed_in_user
):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    db_conn.commit()
    protected_updates = (
        ("status", "status = 'active'"),
        ("suspended_at", "suspended_at = now()"),
        ("suspended_by", "suspended_by = owner_id"),
        ("suspended_reason", "suspended_reason = 'test'"),
        ("version", "version = version + 1"),
        ("owner_id", "owner_id = owner_id"),
        ("created_at", "created_at = now()"),
    )

    with psycopg.connect(get_settings().DATABASE_URL) as runtime_conn:
        runtime_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        runtime_conn.execute("SELECT set_config('app.actor', 'owner', true)")
        for column, assignment in protected_updates:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_conn.transaction():
                    runtime_conn.execute(
                        f"UPDATE app.listings SET {assignment} WHERE owner_id = %s AND id = %s",
                        (signed_in_user["id"], listing_id),
                    )
            assert runtime_conn.execute(
                "SELECT has_column_privilege('rentra_api', 'app.listings', %s, 'UPDATE')",
                (column,),
            ).fetchone()[0] is False


def test_listing_content_update_sets_updated_at(db_conn: psycopg.Connection, signed_in_user):
    ensure_profile(signed_in_user)
    listing_id = insert_listing(db_conn, signed_in_user["id"])
    old_updated_at = db_conn.execute(
        "SELECT updated_at FROM app.listings WHERE id = %s", (listing_id,)
    ).fetchone()[0]
    db_conn.commit()

    with psycopg.connect(get_settings().DATABASE_URL) as runtime_conn:
        runtime_conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        runtime_conn.execute("SELECT set_config('app.actor', 'owner', true)")
        new_updated_at = runtime_conn.execute(
            "UPDATE app.listings SET title = 'Updated rental' WHERE owner_id = %s AND id = %s RETURNING updated_at",
            (signed_in_user["id"], listing_id),
        ).fetchone()[0]
        assert new_updated_at > old_updated_at


def test_public_profile_requires_active_unsuspended_owned_listing(
    db_conn: psycopg.Connection, signed_in_user
):
    ensure_profile(signed_in_user)
    user_id = signed_in_user["id"]
    db_conn.execute("UPDATE app.profiles SET whatsapp = '+9779800000000' WHERE id = %s", (user_id,))

    assert db_conn.execute(
        "SELECT * FROM app.get_public_profile(%s)", (user_id,)
    ).fetchall() == []

    listing_id = insert_listing(db_conn, user_id, status="rented")
    assert db_conn.execute(
        "SELECT * FROM app.get_public_profile(%s)", (user_id,)
    ).fetchall() == []

    db_conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    db_conn.execute("SELECT set_config('app.actor', 'admin', true)")
    db_conn.execute("UPDATE app.listings SET suspended_at = now() WHERE id = %s", (listing_id,))
    assert db_conn.execute(
        "SELECT * FROM app.get_public_profile(%s)", (user_id,)
    ).fetchall() == []

    db_conn.execute("UPDATE app.listings SET suspended_at = NULL WHERE id = %s", (listing_id,))
    assert db_conn.execute(
        "SELECT display_name, whatsapp FROM app.get_public_profile(%s)", (user_id,)
    ).fetchone()[1] == "+9779800000000"
    db_conn.commit()


def test_listing_rls_public_visibility_and_owner_isolation(
    db_conn: psycopg.Connection, signed_in_pair
):
    owner_a, owner_b = signed_in_pair
    ensure_profile(owner_a)
    ensure_profile(owner_b)
    own_draft_id = insert_listing(db_conn, owner_a["id"], status="draft")
    other_draft_id = insert_listing(db_conn, owner_b["id"], status="draft")
    public_id = insert_listing(db_conn, owner_b["id"], status="active")
    other_photo_id = str(uuid.uuid4())
    db_conn.execute(
        """INSERT INTO app.listing_photos
               (listing_id, id, storage_path, thumb_path, width, height, position)
           VALUES (%s, %s, 'other.jpg', 'other-thumb.jpg', 100, 100, 1)""",
        (other_draft_id, other_photo_id),
    )

    db_conn.commit()
    with psycopg.connect(get_settings().DATABASE_URL) as runtime_conn:
        runtime_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_a["id"],))
        runtime_conn.execute("SELECT set_config('app.actor', 'owner', true)")

        own_rows = runtime_conn.execute(
            "SELECT id FROM app.listings WHERE owner_id = %s AND id = %s",
            (owner_a["id"], own_draft_id),
        ).fetchall()
        hidden_rows = runtime_conn.execute(
            "SELECT id FROM app.listings WHERE owner_id = %s AND id = %s",
            (owner_b["id"], other_draft_id),
        ).fetchall()
        public_rows = runtime_conn.execute(
            "SELECT id FROM app.listings WHERE id = %s AND status = 'active' AND suspended_at IS NULL",
            (public_id,),
        ).fetchall()
        assert own_rows == [(uuid.UUID(own_draft_id),)]
        assert hidden_rows == []
        assert public_rows == [(uuid.UUID(public_id),)]
        assert runtime_conn.execute(
            "SELECT id FROM app.listing_photos WHERE listing_id = %s AND id = %s",
            (other_draft_id, other_photo_id),
        ).fetchall() == []

        changed = runtime_conn.execute(
            "UPDATE app.listings SET title = 'not yours' WHERE owner_id = %s AND id = %s",
            (owner_a["id"], other_draft_id),
        )
        assert changed.rowcount == 0

        own_photo_id = str(uuid.uuid4())
        runtime_conn.execute(
            """INSERT INTO app.listing_photos
                   (listing_id, id, storage_path, thumb_path, width, height, position)
               VALUES (%s, %s, 'mine.jpg', 'mine-thumb.jpg', 100, 100, 1)""",
            (own_draft_id, own_photo_id),
        )
        assert runtime_conn.execute(
            "SELECT id FROM app.listing_photos WHERE listing_id = %s AND id = %s",
            (own_draft_id, own_photo_id),
        ).fetchone() == (uuid.UUID(own_photo_id),)

        foreign_photo_id = str(uuid.uuid4())
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with runtime_conn.transaction():
                runtime_conn.execute(
                    """INSERT INTO app.listing_photos
                           (listing_id, id, storage_path, thumb_path, width, height, position)
                       VALUES (%s, %s, 'foreign.jpg', 'foreign-thumb.jpg', 100, 100, 1)""",
                    (other_draft_id, foreign_photo_id),
                )
        runtime_conn.execute(
            "UPDATE app.listings SET title = 'mine' WHERE owner_id = %s AND id = %s",
            (owner_a["id"], own_draft_id),
        )
        assert runtime_conn.execute(
            "SELECT title FROM app.listings WHERE owner_id = %s AND id = %s",
            (owner_a["id"], own_draft_id),
        ).fetchone() == ("mine",)
