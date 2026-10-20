"""Real local Postgres integration tests for the registry and tenant locations."""

from __future__ import annotations

import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


ATTRIBUTE_KEYS = [
    "tenant_type", "pets", "dietary", "parties", "smoking", "alcohol", "curfew",
    "visitors", "wall_decor", "terrace_access", "religious_events", "floor_level",
    "furnishing", "property_type", "road_type", "separate_living_room",
    "bathroom_attachment", "pooja_room", "study_room", "private_rooftop_terrace",
    "yard_garden", "bike_parking", "car_parking", "ev_charging", "water_supply",
    "hot_water", "backup_power", "internet_fiber", "cooling", "laundry",
    "kitchen_appliances", "elevator", "security", "extras",
]


def ensure_profile(signed_in_user):
    with TestClient(app) as client:
        response = client.get("/me", headers=signed_in_user["headers"])
    assert response.status_code == 200


def insert_location_directly(conn, user_id: str, longitude: float, latitude: float) -> None:
    conn.execute(
        """INSERT INTO app.tenant_locations (user_id, current_point, search_point)
           VALUES (
               %s,
               extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography,
               extensions.st_setsrid(extensions.st_makepoint(85.30, 27.70), 4326)::extensions.geography
           )""",
        (user_id, longitude, latitude),
    )


def test_registry_seed_counts_and_listed_attribute_order(test_database_url):
    with psycopg.connect(test_database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key FROM app.attributes ORDER BY ctid")
            assert [row[0] for row in cur.fetchall()] == ATTRIBUTE_KEYS
            cur.execute("SELECT count(*) FROM app.attributes")
            assert cur.fetchone()[0] == 34
            cur.execute("SELECT count(*) FROM app.attribute_options")
            assert cur.fetchone()[0] == 89
            cur.execute("SELECT count(*) FROM app.numeric_fields")
            assert cur.fetchone()[0] == 12
            cur.execute(
                """SELECT option.label, option.sort_order, option.is_exclusive
                   FROM app.attribute_options AS option
                   JOIN app.attributes AS attribute ON attribute.id = option.attribute_id
                   WHERE attribute.key = 'tenant_type'
                   ORDER BY option.sort_order"""
            )
            assert cur.fetchall() == [
                ("bachelors", 1, False),
                ("family", 2, False),
                ("all_allowed", 3, True),
            ]


def test_get_registry_works_without_authentication():
    with TestClient(app) as client:
        response = client.get("/registry")
    assert response.status_code == 200
    registry = response.json()
    assert len(registry["attributes"]) == 34
    assert sum(len(attribute["options"]) for attribute in registry["attributes"]) == 89
    assert len(registry["numeric_fields"]) == 12


def test_rentra_api_cannot_write_registry(test_database_url):
    with psycopg.connect(get_settings().DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user")
            assert cur.fetchone()[0] == "rentra_api"
            for table in ("app.attributes", "app.attribute_options", "app.numeric_fields"):
                for privilege in ("INSERT", "UPDATE", "DELETE"):
                    cur.execute("SELECT has_table_privilege('rentra_api', %s, %s)", (table, privilege))
                    assert cur.fetchone()[0] is False
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    "INSERT INTO app.attributes (key, type, pick_rule) VALUES ('not_allowed', 'single', 'single')"
                )


def test_anon_and_authenticated_cannot_execute_public_profile(test_database_url):
    with psycopg.connect(test_database_url) as conn, conn.cursor() as cur:
        for role in ("anon", "authenticated"):
            cur.execute(
                "SELECT has_function_privilege(%s, 'app.get_public_profile(uuid)', 'EXECUTE')",
                (role,),
            )
            assert cur.fetchone()[0] is False


def test_database_rejects_unrounded_tenant_points(signed_in_user, test_database_url):
    ensure_profile(signed_in_user)
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_location_directly(conn, signed_in_user["id"], 85.123, 27.70)


def test_database_rejects_tenant_points_outside_nepal(signed_in_user, test_database_url):
    ensure_profile(signed_in_user)
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_location_directly(conn, signed_in_user["id"], 90.00, 27.70)


def test_me_locations_rounds_on_write_and_rejects_unknown_fields_without_echoing_coordinates(signed_in_user):
    payload = {
        "current_point": {"latitude": 27.7172, "longitude": 85.3249},
        "search_point": {"latitude": 27.6812, "longitude": 85.3187},
        "search_radius_km": 5,
    }
    with TestClient(app) as client:
        updated = client.put("/me/locations", headers=signed_in_user["headers"], json=payload)
        unknown = client.put(
            "/me/locations",
            headers=signed_in_user["headers"],
            json={**payload, "unexpected": "field"},
        )
        invalid = client.put(
            "/me/locations",
            headers=signed_in_user["headers"],
            json={
                "current_point": {"latitude": 27.7172, "longitude": 90.1234},
                "search_point": payload["search_point"],
                "search_radius_km": 5,
            },
        )
    assert updated.status_code == 200
    assert updated.json()["current_point"] == {"latitude": 27.72, "longitude": 85.32}
    assert updated.json()["search_point"] == {"latitude": 27.68, "longitude": 85.32}
    assert unknown.status_code == 422
    assert invalid.status_code == 422
    assert "27.7172" not in invalid.text
    assert "90.1234" not in invalid.text


def test_locations_are_isolated_by_owner_in_api_and_rls(signed_in_pair):
    user_a, user_b = signed_in_pair
    payload = {
        "current_point": {"latitude": 27.70, "longitude": 85.30},
        "search_point": {"latitude": 27.75, "longitude": 85.35},
        "search_radius_km": 7,
    }
    with TestClient(app) as client:
        own = client.put("/me/locations", headers=user_b["headers"], json=payload)
        empty = client.get("/me/locations", headers=user_a["headers"])
        visible = client.get("/me/locations", headers=user_b["headers"])
    assert own.status_code == visible.status_code == empty.status_code == 200
    assert empty.json()["current_point"] is None
    assert visible.json()["current_point"] == payload["current_point"]

    with psycopg.connect(get_settings().DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.user_id', %s, true)", (user_a["id"],))
            cur.execute("SELECT user_id FROM app.tenant_locations WHERE user_id = %s", (user_b["id"],))
            assert cur.fetchall() == []
            cur.execute(
                "UPDATE app.tenant_locations SET search_radius_km = 20 WHERE user_id = %s RETURNING user_id",
                (user_b["id"],),
            )
            assert cur.fetchall() == []

