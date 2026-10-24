"""Requirements and matching integration tests against real local Postgres."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.main import app


POINT = {"lat": 27.7172, "lng": 85.3249}


def setup_tenant(user):
    with TestClient(app) as client:
        assert client.get("/me", headers=user["headers"]).status_code == 200
        response = client.put("/me/locations", headers=user["headers"], json={
            "current_point": {"latitude": POINT["lat"], "longitude": POINT["lng"]},
            "search_point": {"latitude": POINT["lat"], "longitude": POINT["lng"]},
            "search_radius_km": 5,
        })
        assert response.status_code == 200, response.text


def add_listing(db_conn, owner, *, rent=20000, values=None, answers=None,
                longitude=POINT["lng"], latitude=POINT["lat"], suspended=False,
                created_days_ago=0):
    values = values or {}
    answers = answers or {}
    db_conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
    db_conn.execute("SELECT set_config('app.actor', 'owner', true)")
    listing_id = db_conn.execute(
        """INSERT INTO app.listings(owner_id,title,rent_amount,point,created_at)
           VALUES (%s,'Matching fixture',%s,
             extensions.st_setsrid(extensions.st_makepoint(%s,%s),4326)::extensions.geography,
             now() - (%s * interval '1 day'))
           RETURNING id""", (owner["id"], rent, longitude, latitude, created_days_ago),
    ).fetchone()[0]
    db_conn.execute("UPDATE app.listings SET status='active' WHERE id=%s", (listing_id,))
    db_conn.execute("UPDATE app.profiles SET whatsapp='+9779800001234' WHERE id=%s", (owner["id"],))
    for field, value in values.items():
        db_conn.execute("INSERT INTO app.listing_numeric(listing_id,field,value) VALUES (%s,%s,%s)", (listing_id, field, value))
    for key, labels in answers.items():
        for label in labels:
            db_conn.execute(
                """INSERT INTO app.listing_answers(listing_id,attribute_id,option_id)
                   SELECT %s,a.id,o.id FROM app.attributes a JOIN app.attribute_options o ON o.attribute_id=a.id
                   WHERE a.key=%s AND o.label=%s""", (listing_id, key, label),
            )
    if suspended:
        db_conn.execute("SELECT set_config('app.actor','admin',true)")
        db_conn.execute("UPDATE app.listings SET suspended_at=now(),suspended_by=%s WHERE id=%s", (owner["id"], listing_id))
    return str(listing_id)


def set_requirements(tenant, *, attributes=None, numeric=None):
    with TestClient(app) as client:
        return client.put("/me/requirements", headers=tenant["headers"], json={
            "attributes": attributes or {}, "numeric": numeric or {},
        })


def get_matches(tenant, expect_status=200, **params):
    with TestClient(app) as client:
        response = client.get("/matches", headers=tenant["headers"], params=params)
        assert response.status_code == expect_status, response.text
        return response


def prepare(db_conn, signed_in_pair):
    owner, tenant = signed_in_pair
    with TestClient(app) as client:
        assert client.get("/me", headers=owner["headers"]).status_code == 200
    setup_tenant(tenant)
    return owner, tenant


def test_missed_must_ranks_lower_and_is_named_and_all_musts_met_is_perfect(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    perfect = add_listing(db_conn, owner, answers={"pets": ["yes"]})
    missed = add_listing(db_conn, owner, rent=19000, answers={"pets": ["no"]})
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "must"}}).status_code == 200
    result = get_matches(tenant).json()
    assert [item["id"] for item in result["perfect"]] == [perfect]
    assert {"whatsapp", "point", "photos"}.issubset(result["perfect"][0])
    assert result["ranked"][0]["listing"]["id"] == missed
    assert result["ranked"][0]["misses"] == ["pets: yes"]


def test_nice_only_miss_is_named(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    missed = add_listing(db_conn, owner)
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "nice"}}).status_code == 200
    result = get_matches(tenant).json()
    ranked = next(item for item in result["ranked"] if item["listing"]["id"] == missed)
    assert ranked["misses"] == ["pets: yes"]


def test_ranked_misses_show_only_must_labels_when_musts_exist(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    missed = add_listing(db_conn, owner)
    db_conn.commit()
    assert set_requirements(tenant, attributes={
        "pets": {"yes": "must"}, "tenant_type": {"family": "nice"},
    }).status_code == 200
    ranked = next(row for row in get_matches(tenant).json()["ranked"] if row["listing"]["id"] == missed)
    # nice misses are hidden when the tenant has musts (existing behavior)
    assert set(ranked["misses"]) == {"pets: yes"}


def test_matching_ranks_by_fraction_of_must_rows(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    one_of_two = add_listing(db_conn, owner, answers={"pets": ["yes"]})
    two_of_two = add_listing(db_conn, owner, answers={"pets": ["yes"], "tenant_type": ["bachelors"]})
    db_conn.commit()
    response = set_requirements(tenant, attributes={
        "pets": {"yes": "must"}, "tenant_type": {"bachelors": "must", "family": "must"},
    })
    assert response.status_code == 200
    ranked = get_matches(tenant).json()["ranked"]
    assert [row["listing"]["id"] for row in ranked][:2] == [two_of_two, one_of_two]


def test_nice_tiebreak_among_equal_must_scores_and_no_musts_falls_back_to_nices(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    fewer_nice = add_listing(db_conn, owner, answers={"pets": ["yes"]})
    more_nice = add_listing(db_conn, owner, rent=22000, answers={"pets": ["yes"], "dietary": ["pure_veg_only"]})
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "must"}, "dietary": {"pure_veg_only": "nice"}}).status_code == 200
    perfect_order = [r["id"] for r in get_matches(tenant).json()["perfect"]]
    assert perfect_order[:2] == [more_nice, fewer_nice]
    assert set_requirements(tenant, attributes={"pets": {"yes": "nice"}, "dietary": {"pure_veg_only": "nice"}}).status_code == 200
    response = get_matches(tenant).json()
    assert [r["id"] for r in response["perfect"]] == [more_nice]
    assert response["ranked"][0]["listing"]["id"] == fewer_nice


def test_multichoice_must_checks_each_pick_and_all_allowed_is_generic(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    exclusive = add_listing(db_conn, owner, answers={"tenant_type": ["all_allowed"]})
    partial = add_listing(db_conn, owner, answers={"tenant_type": ["bachelors"]})
    db_conn.commit()
    assert set_requirements(tenant, attributes={"tenant_type": {"bachelors": "must", "family": "must"}}).status_code == 200
    result = get_matches(tenant).json()
    assert exclusive in [r["id"] for r in result["perfect"]]
    assert next(r for r in result["ranked"] if r["listing"]["id"] == partial)["misses"] == ["tenant_type: family"]


def test_multi_answer_listing_does_not_miss_a_selected_option(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    listing_id = add_listing(db_conn, owner, answers={"tenant_type": ["bachelors", "family"]})
    partial = add_listing(db_conn, owner, answers={"tenant_type": ["bachelors"]})
    db_conn.commit()
    assert set_requirements(tenant, attributes={"tenant_type": {"family": "must"}}).status_code == 200
    db_conn.execute("SELECT set_config('app.user_id', %s, true)", (tenant["id"],))
    rows = db_conn.execute(
        "SELECT listing_id::text, misses FROM app.match_misses(%s, %s::uuid[])",
        (tenant["id"], [listing_id, partial]),
    ).fetchall()
    by_listing = {row[0]: row[1] for row in rows}
    assert "tenant_type" not in {m["field"] for m in by_listing.get(listing_id, [])}
    assert "tenant_type" in {m["field"] for m in by_listing[partial]}


@pytest.mark.parametrize("field,listing_value,tenant_value,expected_perfect", [
    ("rent_amount", 18000, 20000, True), ("rent_amount", 22000, 20000, False),
    ("bedrooms", 3, 2, True), ("bedrooms", 1, 2, False),
    ("bathrooms_total", 3, 2, True), ("bathrooms_total", 1, 2, False),
    ("size_value", 900, 800, True), ("size_value", 700, 800, False),
    ("max_people", 5, 4, True), ("max_people", 3, 4, False),
])
def test_numeric_requirement_directions_including_listing_rent(db_conn, signed_in_pair, field, listing_value, tenant_value, expected_perfect):
    owner, tenant = prepare(db_conn, signed_in_pair)
    listing_id = add_listing(db_conn, owner, rent=listing_value if field == "rent_amount" else 20000,
                             values={} if field == "rent_amount" else {field: listing_value})
    db_conn.commit()
    assert set_requirements(tenant, numeric={field: {"value": tenant_value, "importance": "must"}}).status_code == 200
    result = get_matches(tenant).json()
    assert (listing_id in [row["id"] for row in result["perfect"]]) is expected_perfect
    if not expected_perfect:
        assert any(row["listing"]["id"] == listing_id and row["misses"] for row in result["ranked"])


def test_missing_answer_on_must_is_miss(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    listing_id = add_listing(db_conn, owner)
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "must"}}).status_code == 200
    row = next(row for row in get_matches(tenant).json()["ranked"] if row["listing"]["id"] == listing_id)
    assert row["misses"] == ["pets: yes"]


def test_db_rejects_second_single_choice_must(db_conn, signed_in_user):
    with TestClient(app) as client:
        assert client.get("/me", headers=signed_in_user["headers"]).status_code == 200
    attribute_id, rule = db_conn.execute("SELECT id,pick_rule FROM app.attributes WHERE key='dietary'").fetchone()
    option_ids = [row[0] for row in db_conn.execute("SELECT id FROM app.attribute_options WHERE attribute_id=%s ORDER BY sort_order", (attribute_id,)).fetchall()]
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db_conn.transaction():
            db_conn.execute("INSERT INTO app.requirements(user_id,attribute_id,option_id,pick_rule,importance) VALUES (%s,%s,%s,%s,'must')", (signed_in_user["id"],attribute_id,option_ids[0],rule))
            db_conn.execute("INSERT INTO app.requirements(user_id,attribute_id,option_id,pick_rule,importance) VALUES (%s,%s,%s,%s,'must')", (signed_in_user["id"],attribute_id,option_ids[1],rule))


def test_put_rejects_inactive_option(db_conn, signed_in_user):
    with TestClient(app) as client:
        assert client.get("/me", headers=signed_in_user["headers"]).status_code == 200
    option_id = db_conn.execute("SELECT o.id FROM app.attribute_options o JOIN app.attributes a ON a.id=o.attribute_id WHERE a.key='pets' AND o.label='yes'").fetchone()[0]
    db_conn.execute("UPDATE app.attribute_options SET is_active=false WHERE id=%s", (option_id,))
    db_conn.commit()
    try:
        response = set_requirements(signed_in_user, attributes={"pets": {"yes": "must"}})
        assert response.status_code == 422
    finally:
        db_conn.execute("UPDATE app.attribute_options SET is_active=true WHERE id=%s", (option_id,))
        db_conn.commit()


def test_put_rejects_display_only_numeric_fields(signed_in_user):
    response = set_requirements(signed_in_user, numeric={"kitchen_count": {"value": 1, "importance": "nice"}})
    assert response.status_code == 422


def test_retired_numeric_fields_are_inactive_and_references_removed(db_conn):
    rows = db_conn.execute(
        "SELECT key,is_active FROM app.numeric_fields WHERE key IN ('western_commodes','indian_squat_toilets') ORDER BY key"
    ).fetchall()
    assert rows == [("indian_squat_toilets", False), ("western_commodes", False)]
    assert db_conn.execute("SELECT count(*) FROM app.listing_numeric WHERE field IN ('western_commodes','indian_squat_toilets')").fetchone()[0] == 0
    assert db_conn.execute("SELECT count(*) FROM app.requirement_numeric WHERE field IN ('western_commodes','indian_squat_toilets')").fetchone()[0] == 0


def test_own_suspended_and_outside_radius_listings_excluded(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    own = add_listing(db_conn, tenant)
    suspended = add_listing(db_conn, owner, suspended=True)
    outside = add_listing(db_conn, owner, longitude=85.8)
    eligible = add_listing(db_conn, owner)
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "nice"}}).status_code == 200
    result = get_matches(tenant).json()
    ids = {r["id"] for r in result["perfect"] + [x["listing"] for x in result["ranked"]]}
    assert eligible in ids
    assert not {own, suspended, outside} & ids


def test_tiebreak_order_rent_created_at_then_id(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    old = add_listing(db_conn, owner, rent=20000, answers={"pets": ["yes"]}, created_days_ago=2)
    newer = add_listing(db_conn, owner, rent=20000, answers={"pets": ["yes"]}, created_days_ago=1)
    cheaper = add_listing(db_conn, owner, rent=19000, answers={"pets": ["yes"]}, created_days_ago=3)
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "nice"}}).status_code == 200
    ids = [r["id"] for r in get_matches(tenant).json()["perfect"]]
    assert ids[:3] == [cheaper, newer, old]


def test_tiebreak_order_distance_before_created_at(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    closer_older = add_listing(
        db_conn, owner, rent=20000, answers={"pets": ["yes"]}, created_days_ago=4
    )
    farther_newer = add_listing(
        db_conn, owner, rent=20000, answers={"pets": ["yes"]},
        longitude=POINT["lng"] + 0.02, created_days_ago=1,
    )
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "nice"}}).status_code == 200
    ids = [row["id"] for row in get_matches(tenant).json()["perfect"]]
    assert ids[:2] == [closer_older, farther_newer]


def test_ranked_cap_100_and_perfect_uncapped(db_conn, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    perfect = [add_listing(db_conn, owner, answers={"pets": ["yes"]}) for _ in range(102)]
    [add_listing(db_conn, owner, answers={"pets": ["no"]}) for _ in range(102)]
    db_conn.commit()
    assert set_requirements(tenant, attributes={"pets": {"yes": "must"}}).status_code == 200
    result = get_matches(tenant).json()
    assert len(result["perfect"]) == 102
    assert len(result["ranked"]) == 100
    assert {item["id"] for item in result["perfect"]} == set(perfect)


def test_no_requirements_explore_feed_is_keyset_paged_without_gaps_or_duplicates(db_conn, test_database_url, signed_in_pair):
    owner, tenant = prepare(db_conn, signed_in_pair)
    expected = [add_listing(db_conn, owner) for _ in range(7)]
    db_conn.commit()
    assert set_requirements(tenant).status_code == 200
    seen=[]; cursor=None
    with TestClient(app) as client:
        while True:
            params={"page_size": 2}
            if cursor: params["cursor"] = cursor
            response=client.get("/matches", headers=tenant["headers"], params=params)
            assert response.status_code == 200, response.text
            payload=response.json()
            assert payload["explore"] is True and payload["nudge"] is True
            page=payload["explore_listings"]
            assert len(page) <= 2
            seen.extend(item["id"] for item in page)
            cursor=payload["next_cursor"]
            if not cursor: break
    assert len(seen) == len(set(seen)) == len(expected)
    with psycopg.connect(test_database_url) as conn:
        expected_order=[str(row[0]) for row in conn.execute(
            """SELECT id FROM app.listings WHERE owner_id=%s AND status='active'
               ORDER BY md5(id::text||current_date::text),id""", (owner["id"],)
        ).fetchall()]
    assert seen == expected_order


def test_tenant_household_type_is_not_stored(test_database_url):
    with psycopg.connect(test_database_url) as conn:
        columns=conn.execute("""SELECT table_name,column_name FROM information_schema.columns
            WHERE table_schema='app' AND column_name IN ('household_type','tenant_type','group_type')""").fetchall()
    assert columns == []


def test_requirements_put_is_strict_and_rate_limited(monkeypatch, signed_in_user):
    from rentra_api.config import get_settings
    from rentra_api.main import write_limiter
    with TestClient(app) as client:
        assert client.get("/me", headers=signed_in_user["headers"]).status_code == 200
        unknown=client.put("/me/requirements",headers=signed_in_user["headers"],json={"unknown":1})
        assert unknown.status_code == 422
        settings=get_settings()
        monkeypatch.setattr(settings,"WRITE_RATE_LIMIT_USER",1)
        write_limiter.clear()
        first=client.put("/me/requirements",headers=signed_in_user["headers"],json={})
        second=client.put("/me/requirements",headers=signed_in_user["headers"],json={})
    assert first.status_code == 200
    assert second.status_code == 429
