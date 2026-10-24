"""Opt-in real-Postgres EXPLAIN for the matches query."""

from __future__ import annotations

import os

import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import MATCHES_SQL, app


POINT = {"latitude": 27.7172, "longitude": 85.3249}


def test_match_checks_is_bound_to_app_user_and_not_public(signed_in_pair, test_database_url):
    user, other_user = signed_in_pair
    with psycopg.connect(get_settings().DATABASE_URL) as api_conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with api_conn.transaction():
                api_conn.execute("SELECT set_config('app.user_id', %s, true)", (user["id"],))
                api_conn.execute(
                    "SELECT * FROM app.match_checks(%s, 85.32, 27.66, 5000)",
                    (other_user["id"],),
                )

    with psycopg.connect(test_database_url) as admin_conn:
        for role in ("anon", "authenticated"):
            has_execute = admin_conn.execute(
                "SELECT has_function_privilege(%s, 'app.match_checks(uuid,double precision,double precision,double precision)', 'EXECUTE')",
                (role,),
            ).fetchone()[0]
            assert has_execute is False
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with admin_conn.transaction():
                    admin_conn.execute(f"SET LOCAL ROLE {role}")
                    admin_conn.execute(
                        "SELECT * FROM app.match_checks(%s, 85.32, 27.66, 5000)",
                        (user["id"],),
                    )


@pytest.mark.skipif(os.environ.get("EXPLAIN_MATCHES") != "1", reason="set EXPLAIN_MATCHES=1 to run")
def test_explain_matches_query(test_database_url, signed_in_pair):
    owner, tenant = signed_in_pair
    with TestClient(app) as client:
        for user in (owner, tenant):
            response = client.get("/me", headers=user["headers"])
            assert response.status_code == 200, response.text
        location = client.put("/me/locations", headers=tenant["headers"], json={
            "current_point": POINT,
            "search_point": POINT,
            "search_radius_km": 5,
        })
        assert location.status_code == 200, location.text
        requirements = client.put("/me/requirements", headers=tenant["headers"], json={
            "attributes": {
                "pets": {"yes": "must"},
                "tenant_type": {"bachelors": "must"},
                "dietary": {"pure_veg_only": "nice"},
            },
            "numeric": {},
        })
        assert requirements.status_code == 200, requirements.text

    with psycopg.connect(test_database_url) as seed_conn:
        seed_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
        seed_conn.execute("SELECT set_config('app.actor', 'owner', true)")
        seed_conn.execute(
            "UPDATE app.profiles SET whatsapp='+9779800001234' WHERE id=%s",
            (owner["id"],),
        )
        for index in range(300):
            latitude = POINT["latitude"] + (index // 20) * 0.0001
            longitude = POINT["longitude"] + (index % 20) * 0.0001
            listing_id = seed_conn.execute(
                """INSERT INTO app.listings(owner_id,title,rent_amount,point)
                   VALUES (%s,%s,%s,
                     extensions.st_setsrid(extensions.st_makepoint(%s,%s),4326)::extensions.geography)
                   RETURNING id""",
                (owner["id"], f"EXPLAIN fixture {index}", 18000 + index,
                 longitude, latitude),
            ).fetchone()[0]
            seed_conn.execute(
                "UPDATE app.listings SET status='active' WHERE id=%s",
                (listing_id,),
            )
            seed_conn.execute(
                """INSERT INTO app.listing_answers(listing_id,attribute_id,option_id)
                   SELECT %s, a.id, o.id
                   FROM (VALUES ('pets', %s), ('tenant_type', %s), ('dietary', %s)) AS answer(key,label)
                   JOIN app.attributes a ON a.key=answer.key
                   JOIN app.attribute_options o ON o.attribute_id=a.id AND o.label=answer.label""",
                (listing_id,
                 "yes" if index % 5 else "no",
                 "bachelors" if index % 4 else "family",
                 "pure_veg_only" if index % 3 else "non_veg_allowed"),
            )
            seed_conn.execute(
                """INSERT INTO app.listing_numeric(listing_id,field,value)
                   VALUES (%s,'bedrooms',%s),(%s,'size_value',%s)""",
                (listing_id, index % 4 + 1, listing_id, 600 + index),
            )
        seed_conn.commit()

    with psycopg.connect(get_settings().DATABASE_URL) as explain_conn:
        explain_conn.execute("SELECT set_config('app.user_id', %s, true)", (tenant["id"],))
        location = explain_conn.execute(
            """SELECT extensions.st_x(search_point::extensions.geometry),
                      extensions.st_y(search_point::extensions.geometry), search_radius_km
               FROM app.tenant_locations WHERE user_id=%s""",
            (tenant["id"],),
        ).fetchone()
        lng, lat, radius_km = location
        params = (
            tenant["id"],
            float(lng), float(lat), float(radius_km) * 1000.0,
            None, None, None, None, 20 + 1,
        )
        plan = explain_conn.execute(
            "EXPLAIN (ANALYZE, BUFFERS) " + MATCHES_SQL,
            params,
        ).fetchall()
        for (line,) in plan:
            print(line)
