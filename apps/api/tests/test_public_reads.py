"""Public listing, map, and read-limit integration tests against local Postgres."""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import InProcessReadLimiter, app, read_limiter


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200


def create_listing(
    conn: psycopg.Connection,
    owner_id: str,
    rent: int,
    *,
    longitude: float = 85.3249,
    latitude: float = 27.7172,
    status: str = "active",
    suspended: bool = False,
) -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    listing_id = conn.execute(
        """INSERT INTO app.listings (owner_id, title, rent_amount, point)
           VALUES (%s, 'Public rental', %s,
             extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography)
           RETURNING id""",
        (owner_id, rent, longitude, latitude),
    ).fetchone()[0]
    conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    phone_suffix = int(uuid.UUID(owner_id).hex[:14], 16) % 1_000_000_000
    generated_whatsapp = f"+9779{phone_suffix:09d}"
    conn.execute(
        "UPDATE app.profiles SET whatsapp = %s WHERE id = %s AND whatsapp IS NULL",
        (generated_whatsapp, owner_id),
    )
    if status != "active":
        conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    if suspended:
        conn.execute("SELECT set_config('app.actor', 'admin', true)")
        conn.execute(
            "UPDATE app.listings SET suspended_at = now(), suspended_by = %s WHERE id = %s",
            (owner_id, listing_id),
        )
    return str(listing_id)


def read_client() -> TestClient:
    read_limiter.clear()
    return TestClient(app, raise_server_exceptions=False)


def test_public_list_detail_show_phone_and_hide_nonpublic_rows(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    db_conn.execute(
        "UPDATE app.profiles SET whatsapp = '+9779800001234' WHERE id = %s",
        (signed_in_user["id"],),
    )
    visible_id = create_listing(db_conn, signed_in_user["id"], 25000)
    rented_id = create_listing(db_conn, signed_in_user["id"], 26000, status="rented")
    suspended_id = create_listing(db_conn, signed_in_user["id"], 27000, suspended=True)
    db_conn.commit()

    with read_client() as client:
        listing_response = client.get("/listings")
        detail_response = client.get(f"/listings/flat-{visible_id}")
        hidden_detail = client.get(f"/listings/{rented_id}")
        suspended_detail = client.get(f"/listings/{suspended_id}")
    assert listing_response.status_code == detail_response.status_code == 200
    listed = next(item for item in listing_response.json()["listings"] if item["id"] == visible_id)
    assert listed["whatsapp"] == "+9779800001234"
    assert listed["point"] == {"latitude": 27.7172, "longitude": 85.3249}
    assert detail_response.json()["whatsapp"] == "+9779800001234"
    assert detail_response.json()["point"] == listed["point"]
    assert hidden_detail.status_code == suspended_detail.status_code == 404
    assert rented_id not in {row["id"] for row in listing_response.json()["listings"]}
    assert suspended_id not in {row["id"] for row in listing_response.json()["listings"]}


def test_keyset_pagination_is_stable(db_conn, signed_in_user):
    ensure_profile(signed_in_user)
    ids = [
        create_listing(db_conn, signed_in_user["id"], rent)
        for rent in (31001, 31002, 31003)
    ]
    db_conn.commit()
    with read_client() as client:
        first = client.get("/listings?page_size=2").json()
        # A new row before the cursor must not repeat or shift the next page.
        create_listing(db_conn, signed_in_user["id"], 10000)
        db_conn.commit()
        second = client.get("/listings", params={"page_size": 2, "cursor": first["next_cursor"]}).json()
    first_ids = {item["id"] for item in first["listings"]}
    second_ids = {item["id"] for item in second["listings"]}
    assert len(first_ids) == 2
    assert first_ids.isdisjoint(second_ids)
    assert ids[2] in second_ids


def test_map_requires_bbox_and_zoom_and_returns_clusters_then_phone_free_points(
    db_conn, signed_in_user, caplog
):
    ensure_profile(signed_in_user)
    db_conn.execute(
        "UPDATE app.profiles SET whatsapp = '+9779800001234' WHERE id = %s",
        (signed_in_user["id"],),
    )
    create_listing(db_conn, signed_in_user["id"], 32001, longitude=85.30, latitude=27.70)
    create_listing(db_conn, signed_in_user["id"], 32002, longitude=85.31, latitude=27.71)
    db_conn.commit()
    with read_client() as client:
        missing_bbox = client.get("/map", params={"zoom": 15})
        missing_zoom = client.get("/map", params={"bbox": "80,26.3,88.3,30.5"})
        invalid = client.get("/map", params={"bbox": "NaN,26.3,88.3,30.5", "zoom": 15})
        clustered = client.get(
            "/map", params={"bbox": "80,26.3,88.3,30.5", "zoom": 5}
        )
        points = client.get(
            "/map", params={"bbox": "80,26.3,88.3,30.5", "zoom": 15}
        )
    assert missing_bbox.status_code == missing_zoom.status_code == invalid.status_code == 422
    assert clustered.status_code == points.status_code == 200
    assert clustered.json()["type"] == "clusters"
    assert all({"count", "latitude", "longitude"} <= cluster.keys() for cluster in clustered.json()["clusters"])
    assert points.json()["type"] == "points"
    assert all(set(point) == {"id", "lat", "lng", "rent"} for point in points.json()["points"])
    assert "+9779800001234" not in points.text + clustered.text + invalid.text
    assert "+9779800001234" not in caplog.text
    assert "NaN" not in invalid.text


def test_map_response_cap_is_enforced(db_conn, signed_in_user, monkeypatch):
    ensure_profile(signed_in_user)
    for index in range(3):
        create_listing(db_conn, signed_in_user["id"], 33000 + index, longitude=85.4 + index / 100, latitude=27.8)
    db_conn.commit()
    monkeypatch.setattr(get_settings(), "MAP_RESPONSE_CAP", 1)
    with read_client() as client:
        response = client.get("/map", params={"bbox": "80,26.3,88.3,30.5", "zoom": 15})
    assert response.status_code == 200
    assert len(response.json()["points"]) == 1
    assert response.json()["capped"] is True


def test_map_functions_are_private_and_preserve_planted_bbox_results(
    db_conn, signed_in_user, test_database_url
):
    ensure_profile(signed_in_user)
    west, south, east, north = 85.2999999, 27.6999999, 85.3000001, 27.7000001
    first_id = create_listing(
        db_conn, signed_in_user["id"], 41001, longitude=85.30, latitude=27.70
    )
    second_id = create_listing(
        db_conn, signed_in_user["id"], 41002, longitude=85.30, latitude=27.70
    )
    db_conn.commit()

    with psycopg.connect(get_settings().DATABASE_URL) as api_conn:
        points = api_conn.execute(
            "SELECT * FROM app.map_points(%s, %s, %s, %s, %s)",
            (west, south, east, north, 20),
        ).fetchall()
        clusters = api_conn.execute(
            "SELECT * FROM app.map_clusters(%s, %s, %s, %s, %s, %s)",
            (west, south, east, north, 0.01, 20),
        ).fetchall()

    assert [str(row[0]) for row in points] == [first_id, second_id]
    assert [(round(row[1], 2), round(row[2], 2), int(row[3])) for row in points] == [
        (27.70, 85.30, 41001),
        (27.70, 85.30, 41002),
    ]
    assert len(clusters) == 1
    assert clusters[0][0] == 2
    assert round(clusters[0][1], 2) == 27.70
    assert round(clusters[0][2], 2) == 85.30

    denied_calls = (
        ("SELECT * FROM app.map_points(%s, %s, %s, %s, %s)", (west, south, east, north, 20)),
        ("SELECT * FROM app.map_clusters(%s, %s, %s, %s, %s, %s)", (west, south, east, north, 0.01, 20)),
    )
    with psycopg.connect(test_database_url) as admin_conn:
        for role in ("anon", "authenticated"):
            for sql, params in denied_calls:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with admin_conn.transaction():
                        admin_conn.execute(f"SET LOCAL ROLE {role}")
                        admin_conn.execute(sql, params)


def test_read_limit_returns_429_retry_after_and_ignores_spoofed_forwarded_ip(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "READ_RATE_LIMIT_ANONYMOUS", 2)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "203.0.113.10/32")
    with read_client() as client:
        assert client.get("/areas", headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 200
        assert client.get("/areas", headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 200
        limited = client.get("/areas", headers={"X-Forwarded-For": "198.51.100.3"})
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


def test_signed_in_read_limit_uses_user_identity(signed_in_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "READ_RATE_LIMIT_USER", 1)
    with read_client() as client:
        first = client.get("/areas", headers=signed_in_user["headers"])
        second = client.get(
            "/areas",
            headers={**signed_in_user["headers"], "X-Forwarded-For": "198.51.100.99"},
        )
    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1


def test_areas_and_registry_are_public():
    with read_client() as client:
        areas = client.get("/areas")
        registry = client.get("/registry")
    assert areas.status_code == registry.status_code == 200
    assert areas.json() == {"areas": []}
    assert "attributes" in registry.json()


def test_explain_uses_partial_public_rent_and_point_indexes(test_database_url):
    with psycopg.connect(test_database_url) as conn:
        conn.execute("SET LOCAL enable_seqscan = off")
        conn.execute("SET LOCAL enable_sort = off")
        rent_plan = "\n".join(
            row[0]
            for row in conn.execute(
                """EXPLAIN SELECT id FROM app.listings
                   WHERE status = 'active' AND suspended_at IS NULL
                   ORDER BY rent_amount, id LIMIT 50"""
            ).fetchall()
        )
        conn.execute("SET LOCAL enable_sort = on")
        point_plan = "\n".join(
            row[0]
            for row in conn.execute(
                """EXPLAIN SELECT id FROM app.listings
                   WHERE status = 'active' AND suspended_at IS NULL
                     AND extensions.st_intersects(
                       point,
                       extensions.st_makeenvelope(85, 27, 86, 28, 4326)::extensions.geography
                     )"""
            ).fetchall()
        )
    assert "listings_public_rent_amount_idx" in rent_plan
    assert "Seq Scan" not in point_plan
    assert "listings_public_" in point_plan

    with psycopg.connect(test_database_url) as conn:
        indexes = dict(
            conn.execute(
                """SELECT indexname, indexdef FROM pg_indexes
                   WHERE schemaname = 'app'
                     AND indexname IN (
                       'listings_public_rent_amount_idx',
                       'listings_public_point_gist_idx'
                     )"""
            ).fetchall()
        )
    assert set(indexes) == {
        "listings_public_rent_amount_idx",
        "listings_public_point_gist_idx",
    }
    for indexdef in indexes.values():
        normalized_indexdef = indexdef.lower().replace("::text", "")
        assert "status = 'active'" in normalized_indexdef
        assert "suspended_at is null" in normalized_indexdef

    # Real GiST usage is proven in the step 10 load test at 20k rows.


def test_limiter_prunes_empty_keys():
    limiter = InProcessReadLimiter()
    limiter._events[("ip", "stale")] = deque()
    limiter._last_sweep = 0
    limiter.allow(("ip", "current"), limit=10, window=60)
    assert ("ip", "stale") not in limiter._events


def test_health_ready_not_rate_limited(monkeypatch):
    monkeypatch.setattr(get_settings(), "READ_RATE_LIMIT_ANONYMOUS", 1)
    with read_client() as client:
        assert client.get("/areas").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/areas").status_code == 429


def test_public_route_bad_token_is_anonymous(monkeypatch):
    monkeypatch.setattr(get_settings(), "READ_RATE_LIMIT_ANONYMOUS", 1)
    with read_client() as client:
        public = client.get("/listings", headers={"Authorization": "Bearer malformed"})
        limited = client.get("/areas")
    assert public.status_code == 200
    assert limited.status_code == 429


def test_public_route_expired_token_is_anonymous(monkeypatch):
    monkeypatch.setattr(get_settings(), "READ_RATE_LIMIT_ANONYMOUS", 1)
    settings = get_settings()
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    class LocalJwksClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_signing_key_from_jwt(self, _token):
            return type("SigningKey", (), {"algorithm_name": "ES256", "key": public_key})()

    monkeypatch.setattr("rentra_api.main.PyJWKClient", LocalJwksClient)
    expired_token = jwt.encode(
        {
            "sub": "expired-user",
            "exp": int(time.time()) - 60,
            "iss": settings.SUPABASE_URL.rstrip("/") + "/auth/v1",
            "aud": "authenticated",
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "local-test-key"},
    )
    with read_client() as client:
        public = client.get("/listings", headers={"Authorization": f"Bearer {expired_token}"})
        limited = client.get("/areas")
    assert public.status_code == 200
    assert limited.status_code == 429


def test_authenticated_route_bad_token_still_401():
    with read_client() as client:
        response = client.get("/me", headers={"Authorization": "Bearer malformed"})
    assert response.status_code == 401
