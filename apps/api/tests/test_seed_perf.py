"""Opt-in read-only performance checks for the local 10b seed dataset."""

from __future__ import annotations

import math
import os
import re
import statistics
import time

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row, tuple_row

from rentra_api.config import get_settings
from rentra_api.main import MAP_CLUSTER_SQL, MAP_POINTS_SQL, MATCHES_SQL


T1_ID = ""
L1_ID = "10000000-1000-4000-8000-000000000001"
L2_ID = "10000000-1000-4000-8000-000000000002"
MATCH_TAIL = (None, None, None, None, 21)
MAP_CASES = (
    ("a: low zoom, Kathmandu valley", 8.0, (85.20, 27.55, 85.55, 27.85)),
    ("b: mid zoom, about 10 km", 12.0, (85.28, 27.615, 85.38, 27.705)),
    ("c: high zoom, about 1 km", 16.0, (85.325, 27.6555, 85.335, 27.6645)),
)

pytestmark = pytest.mark.skipif(os.environ.get("SEED_PERF") != "1", reason="set SEED_PERF=1 to run")


def _require_local(database_url: str) -> None:
    host = conninfo_to_dict(database_url).get("host")
    hosts = host.split(",") if host else []
    if not hosts or any(value not in {"127.0.0.1", "localhost"} for value in hosts):
        raise SystemExit("Refusing: database host must be 127.0.0.1 or localhost")


@pytest.fixture(scope="module", autouse=True)
def _require_seeded_local_database(test_database_url):
    global T1_ID
    settings = get_settings()
    _require_local(settings.DATABASE_URL)
    _require_local(test_database_url)
    with psycopg.connect(test_database_url) as conn:
        listing_count = conn.execute("SELECT count(*) FROM app.listings").fetchone()[0]
        l1_exists = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM app.listings WHERE id = %s)", (L1_ID,)
        ).fetchone()[0]
        planted_t1 = conn.execute(
            "SELECT id FROM auth.users WHERE email = %s",
            ("planted-t1@seed.rentra.test",),
        ).fetchone()
    if listing_count < 20000 or not l1_exists:
        pytest.skip("local database does not contain the planted 10b seed rows")
    if planted_t1 is None:
        pytest.skip("local database does not contain the planted T1 user (planted-t1@seed.rentra.test)")
    T1_ID = str(planted_t1[0])


def _matches_params(conn: psycopg.Connection, user_id: str) -> tuple[object, ...]:
    location = conn.cursor(row_factory=tuple_row).execute(
        """SELECT extensions.st_x(search_point::extensions.geometry),
                  extensions.st_y(search_point::extensions.geometry), search_radius_km
           FROM app.tenant_locations WHERE user_id=%s""",
        (user_id,),
    ).fetchone()
    if location is None:
        lng = lat = radius_meters = None
    else:
        lng, lat, radius_km = location
        lng, lat = float(lng), float(lat)
        radius_meters = float(radius_km) * 1000.0
    return (user_id, lng, lat, radius_meters, *MATCH_TAIL, user_id)


def _set_user(conn: psycopg.Connection, user_id: str) -> None:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))


def _map_query(settings, zoom: float, bbox: tuple[float, float, float, float], cap: int):
    west, south, east, north = bbox
    if zoom < settings.MAP_CLUSTER_ZOOM:
        eps = min(0.5, 0.002 * (2 ** (settings.MAP_CLUSTER_ZOOM - zoom)))
        return MAP_CLUSTER_SQL, (west, south, east, north, eps, cap + 1)
    return MAP_POINTS_SQL, (west, south, east, north, cap + 1)


def _p95(values: list[float]) -> float:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def _timed_matches(conn: psycopg.Connection, params: tuple[object, ...]) -> list[float]:
    timings: list[float] = []
    for _ in range(100):
        with conn.transaction():
            _set_user(conn, T1_ID)
            started = time.perf_counter()
            conn.execute(MATCHES_SQL, params).fetchall()
            timings.append((time.perf_counter() - started) * 1000.0)
    return timings


def _timed_map(
    conn: psycopg.Connection, sql: str, params: tuple[object, ...]
) -> tuple[list[float], list[tuple]]:
    timings: list[float] = []
    rows: list[tuple] = []
    for _ in range(100):
        with conn.transaction():
            started = time.perf_counter()
            rows = conn.execute(sql, params).fetchall()
            timings.append((time.perf_counter() - started) * 1000.0)
    return timings, rows


def test_seed_planted_case():
    settings = get_settings()
    with psycopg.connect(settings.DATABASE_URL, row_factory=dict_row) as conn:
        with conn.transaction():
            _set_user(conn, T1_ID)
            params = _matches_params(conn, T1_ID)
            rows = conn.execute(MATCHES_SQL, params).fetchall()

        l1 = next((row for row in rows if str(row["id"]) == L1_ID), None)
        assert l1 is not None
        assert l1["perfect_flag"] is True
        assert l1["misses"] == []

        l2 = next((row for row in rows if str(row["id"]) == L2_ID), None)
        if l2 is None:
            with conn.transaction():
                _set_user(conn, T1_ID)
                direct = conn.execute(
                    "SELECT * FROM app.match_checks(%s, %s, %s, %s)", params[:4]
                ).fetchall()
            l2 = next((row for row in direct if str(row["id"]) == L2_ID), None)
        assert l2 is not None
        assert "rent_amount" in {miss["field"] for miss in l2["misses"]}
        if str(l2["id"]) in {str(row["id"]) for row in rows}:
            assert l2["perfect_flag"] is False
            assert l2["explore_flag"] is False


def test_seed_matches_p95():
    settings = get_settings()
    with psycopg.connect(settings.DATABASE_URL) as conn:
        with conn.transaction():
            _set_user(conn, T1_ID)
            params = _matches_params(conn, T1_ID)
        timings = _timed_matches(conn, params)
    # Measured median 1.74 s, p95 about 1.9 s, accepted by owner; re-measure on real Supabase.
    assert _p95(timings) < 2500, f"matches p95 was {_p95(timings):.2f} ms"


def test_seed_map_p95():
    settings = get_settings()
    cap = settings.MAP_RESPONSE_CAP
    with psycopg.connect(settings.DATABASE_URL) as conn:
        for label, zoom, bbox in MAP_CASES:
            sql, params = _map_query(settings, zoom, bbox, cap)
            timings, rows = _timed_map(conn, sql, params)
            assert len(rows) <= cap + 1, f"{label} exceeded response cap + 1"
            # worst case 50k listings in one view, owner target under 1 s.
            assert _p95(timings) < 1000, f"{label} p95 was {_p95(timings):.2f} ms"


def test_seed_explain_records_plan():
    settings = get_settings()
    cap = settings.MAP_RESPONSE_CAP
    bbox = MAP_CASES[2][2]
    points_params = (*bbox, cap + 1)
    with psycopg.connect(settings.DATABASE_URL) as conn:
        with conn.transaction():
            _set_user(conn, T1_ID)
            matches_params = _matches_params(conn, T1_ID)
        for label, sql, params, user_id in (
            ("matches", MATCHES_SQL, matches_params, T1_ID),
            ("map points", MAP_POINTS_SQL, points_params, None),
        ):
            with conn.transaction():
                if user_id is not None:
                    _set_user(conn, user_id)
                plan = [row[0] for row in conn.execute(
                    "EXPLAIN (ANALYZE, BUFFERS) " + sql, params
                ).fetchall()]
            assert any("Execution Time:" in line for line in plan), f"{label} plan has no Execution Time"
            if label == "matches":
                # GiST not selected at 20k, planner prefers the status index, revisit in staging.
                assert not any(
                    re.search(r"Seq Scan on (?:app\.)?listings\b", line) for line in plan
                ), "matches plan contains a Seq Scan on app.listings"


def test_seed_map_requires_bbox_cap():
    settings = get_settings()
    cap = settings.MAP_RESPONSE_CAP
    assert isinstance(cap, int) and cap > 0
    sql, params = _map_query(settings, MAP_CASES[0][1], MAP_CASES[0][2], cap)
    assert sql == MAP_CLUSTER_SQL
    assert params[-1] == cap + 1
    with psycopg.connect(settings.DATABASE_URL) as conn:
        with conn.transaction():
            rows = conn.execute(sql, params).fetchall()
    assert len(rows) <= cap + 1
