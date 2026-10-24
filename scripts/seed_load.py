#!/usr/bin/env python3
"""Seed a local Rentra database for the 10b matching/map load test."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import psycopg


MARKER = "%@seed.rentra.test"
T1_EMAIL = "planted-t1@seed.rentra.test"
T1_PASSWORD = "RentraSeedT1-Local-Only-2026!"
L1_ID = "10000000-1000-4000-8000-000000000001"
L2_ID = "10000000-1000-4000-8000-000000000002"
TENANT_COUNT = 50_000
LISTING_COUNT = 20_000


def _local_host(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def _require_local(url: str, label: str) -> None:
    host = _local_host(url)
    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit(f"Refusing: {label} host must be 127.0.0.1 or localhost")


def _auth_request(method: str, path: str, payload: dict, base_url: str, key: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise SystemExit(f"Supabase Auth request failed with HTTP {exc.code}") from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise SystemExit("Supabase Auth request failed") from None


def _ensure_planted_user() -> str:
    base_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base_url or not service_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for the local planted Auth user")
    _require_local(base_url, "SUPABASE_URL")
    result = _auth_request(
        "POST",
        "/auth/v1/admin/users",
        {"email": T1_EMAIL, "password": T1_PASSWORD, "email_confirm": True},
        base_url,
        service_key,
    )
    user_id = result.get("id")
    if not user_id:
        raise SystemExit("Supabase Auth did not return the planted user's id")
    return user_id


SEED_SQL = r"""
CREATE TEMP TABLE seed_users (
    n integer PRIMARY KEY,
    id uuid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL
) ON COMMIT DROP;

INSERT INTO seed_users (n, id, created_at)
SELECT n,
       md5('rentra-load-tenant-' || n::text)::uuid,
       now() - random() * interval '540 days'
FROM generate_series(1, 50000) AS n;

INSERT INTO auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
)
SELECT id, 'authenticated', 'authenticated',
       'tenant-' || lpad(n::text, 5, '0') || '@seed.rentra.test',
       '!seed-disabled-no-login!', created_at,
       '{"provider":"email","providers":["email"]}'::jsonb,
       '{"load_seed":true}'::jsonb, created_at, created_at
FROM seed_users;

INSERT INTO app.profiles (id, whatsapp, created_at)
SELECT id,
       CASE WHEN n <= 8000 OR n % 100 < 65
            THEN '+97798' || lpad((n % 100000000)::text, 8, '0')
            ELSE NULL END,
       created_at
FROM seed_users;

INSERT INTO app.admins (user_id)
SELECT id FROM seed_users WHERE n = 50000;

INSERT INTO app.profiles (id, whatsapp, created_at)
VALUES ('__T1_UUID__'::uuid, '+9779811111111', now() - interval '14 days')
ON CONFLICT (id) DO UPDATE SET whatsapp = EXCLUDED.whatsapp;

WITH sampled_tenants AS MATERIALIZED (
    SELECT seed_users.*, random() AS place_roll,
           random() AS longitude_roll, random() AS latitude_roll
    FROM seed_users
), points AS (
    SELECT sampled_tenants.*,
           CASE WHEN place_roll < 0.10 THEN 80.0 + longitude_roll * 8.3
                WHEN place_roll < 0.28 THEN 85.324 + (longitude_roll - 0.5) * 0.08
                WHEN place_roll < 0.46 THEN 85.325 + (longitude_roll - 0.5) * 0.07
                WHEN place_roll < 0.62 THEN 85.429 + (longitude_roll - 0.5) * 0.07
                WHEN place_roll < 0.78 THEN 83.986 + (longitude_roll - 0.5) * 0.08
                WHEN place_roll < 0.90 THEN 84.436 + (longitude_roll - 0.5) * 0.08
                ELSE 87.272 + (longitude_roll - 0.5) * 0.08 END AS lon,
           CASE WHEN place_roll < 0.10 THEN 26.3 + latitude_roll * 4.2
                WHEN place_roll < 0.28 THEN 27.717 + (latitude_roll - 0.5) * 0.08
                WHEN place_roll < 0.46 THEN 27.659 + (latitude_roll - 0.5) * 0.07
                WHEN place_roll < 0.62 THEN 27.671 + (latitude_roll - 0.5) * 0.07
                WHEN place_roll < 0.78 THEN 28.210 + (latitude_roll - 0.5) * 0.08
                WHEN place_roll < 0.90 THEN 27.677 + (latitude_roll - 0.5) * 0.08
                ELSE 26.453 + (latitude_roll - 0.5) * 0.08 END AS lat
    FROM sampled_tenants
)
INSERT INTO app.tenant_locations
    (user_id, current_point, search_point, search_radius_km, created_at, updated_at)
SELECT id,
       extensions.st_setsrid(extensions.st_makepoint(
           round(lon::numeric, 2)::double precision,
           round(lat::numeric, 2)::double precision), 4326)::extensions.geography,
       extensions.st_setsrid(extensions.st_makepoint(
           round(lon::numeric, 2)::double precision,
           round(lat::numeric, 2)::double precision), 4326)::extensions.geography,
       CASE WHEN n % 6 = 0 THEN 10 + (n % 41) ELSE 5 END,
       created_at, created_at
FROM points;

INSERT INTO app.tenant_locations
    (user_id, current_point, search_point, search_radius_km, created_at, updated_at)
VALUES (
    '__T1_UUID__'::uuid,
    extensions.st_setsrid(extensions.st_makepoint(85.32, 27.66), 4326)::extensions.geography,
    extensions.st_setsrid(extensions.st_makepoint(85.32, 27.66), 4326)::extensions.geography,
    5, now() - interval '14 days', now() - interval '14 days'
);

WITH selected_attributes AS (
    SELECT users.n, users.id AS user_id, attribute.id AS attribute_id,
           attribute.key, attribute.pick_rule,
           row_number() OVER (PARTITION BY users.id ORDER BY md5(users.id::text || attribute.key)) AS rn
    FROM seed_users AS users
    CROSS JOIN app.attributes AS attribute
    WHERE attribute.is_active AND users.n BETWEEN 10001 AND 50000
), chosen AS (
    SELECT * FROM selected_attributes
    WHERE rn <= CASE WHEN n <= 30000 THEN 3 + (n % 2) ELSE 9 END
), option_choices AS (
    SELECT chosen.user_id, chosen.attribute_id, chosen.pick_rule,
           CASE WHEN chosen.n <= 30000 THEN 'must'
                WHEN chosen.rn <= 5 THEN 'must' ELSE 'nice' END AS importance,
           option.id AS option_id,
           row_number() OVER (
               PARTITION BY chosen.user_id, chosen.attribute_id
               ORDER BY md5(chosen.user_id::text || option.id::text)
           ) AS option_rank
    FROM chosen
    JOIN app.attribute_options AS option
      ON option.attribute_id = chosen.attribute_id AND option.is_active
)
INSERT INTO app.requirements (user_id, attribute_id, option_id, pick_rule, importance)
SELECT user_id, attribute_id, option_id, pick_rule, importance
FROM option_choices
WHERE option_rank = 1;

INSERT INTO app.requirement_numeric (user_id, field, value, importance)
SELECT users.id, required.field, required.value, required.importance
FROM seed_users AS users
CROSS JOIN LATERAL (VALUES
    ('rent_amount', (26000 + (users.n % 55) * 1000)::numeric, 'must'),
    ('bedrooms', (1 + users.n % 4)::numeric, 'must'),
    ('bathrooms_total', (1 + users.n % 2)::numeric, 'must'),
    ('size_value', (35 + users.n % 100)::numeric, 'nice'),
    ('max_people', (1 + users.n % 6)::numeric, 'nice')
) AS required(field, value, importance)
JOIN app.numeric_fields AS numeric_field
  ON numeric_field.key = required.field AND numeric_field.is_active
WHERE users.n BETWEEN 30001 AND 50000;

INSERT INTO app.requirements (user_id, attribute_id, option_id, pick_rule, importance)
SELECT '__T1_UUID__'::uuid, attribute.id, option.id, attribute.pick_rule, 'must'
FROM app.attributes AS attribute
JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
WHERE attribute.key = 'furnishing' AND attribute.is_active
  AND option.label = 'fully_furnished' AND option.is_active;

INSERT INTO app.requirement_numeric (user_id, field, value, importance)
SELECT '__T1_UUID__'::uuid, required.field, required.value, 'must'
FROM (VALUES ('bedrooms', 2::numeric), ('rent_amount', 25000::numeric)) AS required(field, value)
JOIN app.numeric_fields AS numeric_field
  ON numeric_field.key = required.field AND numeric_field.is_active;

CREATE TEMP TABLE seed_listing_facts (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    city text NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    bedrooms integer NOT NULL,
    rent_amount numeric NOT NULL,
    furnishing_label text NOT NULL,
    listing_status text NOT NULL,
    status_changed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    photo_count integer NOT NULL,
    suspension_roll double precision NOT NULL
) ON COMMIT DROP;

WITH sampled_listings AS MATERIALIZED (
    SELECT n, random() AS city_roll, random() AS status_roll,
           random() AS longitude_roll, random() AS latitude_roll,
           random() AS bedroom_roll, random() AS rent_roll,
           random() AS furnishing_roll,
           random() AS status_time_roll, random() AS photo_roll,
           random() AS suspension_roll,
           now() - random() * interval '365 days' AS created_at
    FROM generate_series(1, 20000) AS n
)
INSERT INTO seed_listing_facts
SELECT md5('rentra-load-listing-' || n::text)::uuid,
       md5('rentra-load-tenant-' || (((n - 1) % 8000) + 1)::text)::uuid,
           CASE WHEN city_roll < 0.10 THEN 'Rural Nepal'
                WHEN city_roll < 0.28 THEN 'Kathmandu'
                WHEN city_roll < 0.46 THEN 'Lalitpur'
                WHEN city_roll < 0.62 THEN 'Bhaktapur'
                WHEN city_roll < 0.78 THEN 'Pokhara'
                WHEN city_roll < 0.89 THEN 'Bharatpur'
            ELSE 'Biratnagar' END,
       CASE WHEN city_roll < 0.10 THEN 26.3 + latitude_roll * 4.2
            WHEN city_roll < 0.28 THEN 27.717 + (latitude_roll - 0.5) * 0.06
            WHEN city_roll < 0.46 THEN 27.659 + (latitude_roll - 0.5) * 0.05
            WHEN city_roll < 0.62 THEN 27.671 + (latitude_roll - 0.5) * 0.05
            WHEN city_roll < 0.78 THEN 28.210 + (latitude_roll - 0.5) * 0.06
            WHEN city_roll < 0.89 THEN 27.677 + (latitude_roll - 0.5) * 0.06
            ELSE 26.453 + (latitude_roll - 0.5) * 0.06 END,
       CASE WHEN city_roll < 0.10 THEN 80.0 + longitude_roll * 8.3
            WHEN city_roll < 0.28 THEN 85.324 + (longitude_roll - 0.5) * 0.06
            WHEN city_roll < 0.46 THEN 85.325 + (longitude_roll - 0.5) * 0.05
            WHEN city_roll < 0.62 THEN 85.429 + (longitude_roll - 0.5) * 0.05
            WHEN city_roll < 0.78 THEN 83.986 + (longitude_roll - 0.5) * 0.06
            WHEN city_roll < 0.89 THEN 84.436 + (longitude_roll - 0.5) * 0.06
            ELSE 87.272 + (longitude_roll - 0.5) * 0.06 END,
       1 + floor(bedroom_roll * 5)::integer,
       26000 + floor(rent_roll * 120000)::integer,
       (ARRAY['unfurnished', 'semi_furnished', 'fully_furnished'])[
           1 + floor(furnishing_roll * 3)::integer
       ],
       CASE WHEN status_roll < 0.85 THEN 'active'
            WHEN status_roll < 0.91 THEN 'archived'
            WHEN status_roll < 0.96 THEN 'rented' ELSE 'draft' END,
       created_at + status_time_roll * (now() - created_at),
       created_at,
       1 + floor(photo_roll * 5)::integer,
       suspension_roll
FROM sampled_listings;

UPDATE seed_listing_facts SET id = '__L1_UUID__'::uuid, city = 'Lalitpur', latitude = 27.6588,
       longitude = 85.3247, bedrooms = 2, rent_amount = 22000,
       furnishing_label = 'fully_furnished', listing_status = 'active',
       status_changed_at = now() - interval '10 days',
       created_at = now() - interval '10 days', photo_count = 2, suspension_roll = 1
WHERE id = md5('rentra-load-listing-1')::uuid;

INSERT INTO seed_listing_facts
VALUES ('__L2_UUID__'::uuid, md5('rentra-load-tenant-1')::uuid, 'Lalitpur', 27.6588, 85.3247,
        2, 28000, 'fully_furnished', 'active', now() - interval '9 days',
        now() - interval '9 days', 2, 1);

INSERT INTO app.listings (
    id, owner_id, title, rent_amount, point, status, archived_from_status,
    archived_at, status_changed_at, suspended_at, suspended_by, suspended_reason,
    version, created_at, updated_at
)
SELECT facts.id, facts.owner_id,
       facts.bedrooms || ' bedroom ' || replace(facts.furnishing_label, '_', ' ') || ' flat in ' || facts.city,
       facts.rent_amount,
       extensions.st_setsrid(extensions.st_makepoint(facts.longitude, facts.latitude), 4326)::extensions.geography,
       facts.listing_status,
       CASE WHEN facts.listing_status = 'archived' THEN 'active' END,
       CASE WHEN facts.listing_status = 'archived' THEN facts.status_changed_at END,
       facts.status_changed_at,
       CASE WHEN facts.suspension_roll < 0.02 THEN now() - random() * interval '180 days' END,
       CASE WHEN facts.suspension_roll < 0.02
            THEN md5('rentra-load-tenant-50000')::uuid END,
       CASE WHEN facts.suspension_roll < 0.02 THEN 'load test seed suspension' END,
       1, facts.created_at, now()
FROM seed_listing_facts AS facts
;

INSERT INTO app.listing_numeric (listing_id, field, value)
SELECT facts.id, numeric_field.key,
       CASE numeric_field.key
           WHEN 'bedrooms' THEN facts.bedrooms::numeric
           WHEN 'bathrooms_total' THEN (1 + floor(random() * 3))::numeric
           WHEN 'kitchen_count' THEN (1 + floor(random() * 2))::numeric
           WHEN 'balconies' THEN floor(random() * 4)::numeric
           WHEN 'total_floors' THEN (1 + floor(random() * 6))::numeric
           WHEN 'size_value' THEN (35 + floor(random() * 250))::numeric
           WHEN 'max_people' THEN (1 + floor(random() * 8))::numeric
           WHEN 'road_access_width_ft' THEN (8 + floor(random() * 25))::numeric
           WHEN 'main_road_distance_km' THEN (random() * 5)::numeric
       END
FROM seed_listing_facts AS facts
CROSS JOIN app.numeric_fields AS numeric_field
WHERE numeric_field.is_active AND numeric_field.key <> 'rent_amount';

WITH answer_attributes AS (
    SELECT facts.id AS listing_id, facts.furnishing_label, attribute.id AS attribute_id,
           attribute.key, attribute.type,
           (attribute.required_at_publish OR random() < 0.18) AS include_attribute,
           random() AS exclusive_roll,
           EXISTS (
               SELECT 1 FROM app.attribute_options exclusive_option
               WHERE exclusive_option.attribute_id = attribute.id
                 AND exclusive_option.is_active AND exclusive_option.is_exclusive
           ) AS has_exclusive,
           1 + floor(random() * 3)::integer AS multi_count
    FROM seed_listing_facts AS facts
    CROSS JOIN app.attributes AS attribute
    WHERE attribute.is_active
), option_candidates AS (
    SELECT answers.listing_id, answers.attribute_id, option.id AS option_id,
           CASE WHEN answers.type = 'multi' AND answers.has_exclusive AND answers.exclusive_roll < 0.03 THEN 1
                WHEN answers.type = 'multi' THEN answers.multi_count ELSE 1 END AS pick_count,
           row_number() OVER (
               PARTITION BY answers.listing_id, answers.attribute_id
               ORDER BY md5(answers.listing_id::text || option.id::text)
           ) AS option_rank
    FROM answer_attributes AS answers
    JOIN app.attribute_options AS option
      ON option.attribute_id = answers.attribute_id AND option.is_active
    JOIN app.attributes AS attribute ON attribute.id = answers.attribute_id
    WHERE answers.include_attribute
      AND (answers.key <> 'furnishing' OR option.label = answers.furnishing_label)
      AND (answers.type <> 'multi'
           OR (answers.has_exclusive AND answers.exclusive_roll < 0.03 AND option.is_exclusive)
           OR ((NOT answers.has_exclusive OR answers.exclusive_roll >= 0.03) AND NOT option.is_exclusive))
)
INSERT INTO app.listing_answers (listing_id, attribute_id, option_id)
SELECT listing_id, attribute_id, option_id
FROM option_candidates
WHERE option_rank <= pick_count;

INSERT INTO app.listing_photos (listing_id, storage_path, thumb_path, position, width, height)
SELECT facts.id,
       'seed-load/' || facts.owner_id::text || '/' || facts.id::text || '/photo-' || photo.position::text || '.webp',
       'seed-load/' || facts.owner_id::text || '/' || facts.id::text || '/thumb-' || photo.position::text || '.webp',
       photo.position,
       1200 + floor(random() * 1000)::integer,
       800 + floor(random() * 800)::integer
FROM seed_listing_facts AS facts
CROSS JOIN LATERAL generate_series(1, facts.photo_count) AS photo(position);

UPDATE app.listings AS listing
SET version = 1
      + (SELECT count(*) FROM app.listing_answers answer WHERE answer.listing_id = listing.id)
      + (SELECT count(*) FROM app.listing_numeric numeric_value WHERE numeric_value.listing_id = listing.id)
      + (SELECT count(*) FROM app.listing_photos photo WHERE photo.listing_id = listing.id),
    updated_at = now()
WHERE listing.id IN (SELECT id FROM seed_listing_facts);

"""


def _print_counts(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        """
        WITH marked_users AS (
            SELECT id FROM auth.users WHERE email LIKE %s
        ), marked_listings AS (
            SELECT listing.id FROM app.listings AS listing
            JOIN marked_users AS user_row ON user_row.id = listing.owner_id
        )
        SELECT 'auth.users' AS table_name, count(*) FROM auth.users WHERE email LIKE %s
        UNION ALL SELECT 'app.profiles', count(*) FROM app.profiles WHERE id IN (SELECT id FROM marked_users)
        UNION ALL SELECT 'app.admins', count(*) FROM app.admins WHERE user_id IN (SELECT id FROM marked_users)
        UNION ALL SELECT 'app.tenant_locations', count(*) FROM app.tenant_locations WHERE user_id IN (SELECT id FROM marked_users)
        UNION ALL SELECT 'app.requirements', count(*) FROM app.requirements WHERE user_id IN (SELECT id FROM marked_users)
        UNION ALL SELECT 'app.requirement_numeric', count(*) FROM app.requirement_numeric WHERE user_id IN (SELECT id FROM marked_users)
        UNION ALL SELECT 'app.listings', count(*) FROM app.listings WHERE id IN (SELECT id FROM marked_listings)
        UNION ALL SELECT 'app.listing_answers', count(*) FROM app.listing_answers WHERE listing_id IN (SELECT id FROM marked_listings)
        UNION ALL SELECT 'app.listing_numeric', count(*) FROM app.listing_numeric WHERE listing_id IN (SELECT id FROM marked_listings)
        UNION ALL SELECT 'app.listing_photos', count(*) FROM app.listing_photos WHERE listing_id IN (SELECT id FROM marked_listings)
        UNION ALL SELECT 'app.storage_deletions', count(*) FROM app.storage_deletions WHERE path LIKE 'seed-load/%%'
        """,
        (MARKER, MARKER),
    ).fetchall()
    print("Seed row counts:")
    for table_name, count in rows:
        print(f"  {table_name}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete existing @seed.rentra.test rows first")
    args = parser.parse_args()

    database_url = os.environ.get("TEST_DATABASE_URL", "")
    if not database_url:
        raise SystemExit("TEST_DATABASE_URL is required")
    _require_local(database_url, "TEST_DATABASE_URL")

    started = time.perf_counter()
    try:
        conn = psycopg.connect(database_url)
    except psycopg.Error as exc:
        raise SystemExit(f"Could not connect to TEST_DATABASE_URL: {type(exc).__name__}") from None

    is_superuser = conn.execute(
        "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
    ).fetchone()[0]
    if not is_superuser:
        raise SystemExit("Refusing: connect to the local database as a postgres superuser")

    existing = conn.execute("SELECT count(*) FROM auth.users WHERE email LIKE %s", (MARKER,)).fetchone()[0]
    if existing and not args.reset:
        raise SystemExit("Refusing: seed marker rows already exist; pass --reset to replace them")
    if args.reset and existing:
        conn.execute(
            """DELETE FROM app.storage_deletions AS deletion
               USING auth.users AS marked
               WHERE marked.email LIKE %s
                 AND deletion.path LIKE 'seed-load/' || marked.id::text || '/%%'""",
            (MARKER,),
        )
        conn.execute("DELETE FROM auth.users WHERE email LIKE %s", (MARKER,))
    conn.commit()

    planted_t1_id = _ensure_planted_user()
    with conn.transaction():
        conn.execute("SET session_replication_role = replica")
        sql = SEED_SQL.replace("__T1_UUID__", str(uuid.UUID(planted_t1_id)))
        sql = sql.replace("__L1_UUID__", str(uuid.UUID(L1_ID)))
        sql = sql.replace("__L2_UUID__", str(uuid.UUID(L2_ID)))
        conn.execute(sql, prepare=False)
        conn.execute("SET session_replication_role = origin")
        for table in (
            "auth.users", "app.profiles", "app.admins", "app.tenant_locations", "app.requirements",
            "app.requirement_numeric", "app.listings", "app.listing_answers",
            "app.listing_numeric", "app.listing_photos", "app.storage_deletions",
        ):
            conn.execute(f"ANALYZE {table}")
        _print_counts(conn)
    conn.close()

    print(f"Seed duration: {time.perf_counter() - started:.2f}s")
    print(f"Planted T1 id: {planted_t1_id}")
    print(f"Planted L1 id: {L1_ID}")
    print(f"Planted L2 id: {L2_ID}")
    print("T1 sign-in password: the local-only constant configured in scripts/get_seed_token.py")


if __name__ == "__main__":
    try:
        main()
    except (psycopg.Error, HTTPError, URLError) as exc:
        print(f"Seed failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
