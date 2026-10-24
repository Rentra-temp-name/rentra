"""Inspect the seeded user's matches, query plan, and repeated query timings."""

from __future__ import annotations

import math
import statistics
import sys
import time
import psycopg
from psycopg.conninfo import conninfo_to_dict

from rentra_api.config import get_settings
from rentra_api.main import MATCHES_SQL


PARAMS_TAIL = (None, None, None, None, 21)
INDEX_NAMES = (
    "listings_public_point_gist_idx",
    "listings_public_rent_amount_idx",
)


def _require_local(database_url: str) -> None:
    host = conninfo_to_dict(database_url).get("host")
    hosts = host.split(",") if host else []
    if not hosts or any(value not in {"127.0.0.1", "localhost"} for value in hosts):
        raise SystemExit("Refusing: DATABASE_URL host must be 127.0.0.1 or localhost")


def _params(conn: psycopg.Connection, user_id: str) -> tuple[object, ...]:
    location = conn.execute(
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
    return (user_id, lng, lat, radius_meters, *PARAMS_TAIL)


def _set_user(conn: psycopg.Connection, user_id: str) -> None:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} USER_ID")
    user_id = sys.argv[1]
    database_url = get_settings().DATABASE_URL
    _require_local(database_url)
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            _set_user(conn, user_id)
            params = _params(conn, user_id)
            cursor = conn.execute(MATCHES_SQL, params)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
            index = {name: position for position, name in enumerate(columns)}
            print("First 10 matches:")
            for row in rows[:10]:
                misses = row[index["misses"]] or []
                print({
                    "listing_id": row[index["id"]],
                    "perfect_flag": row[index["perfect_flag"]],
                    "explore_flag": row[index["explore_flag"]],
                    "must_total": row[index["must_total"]],
                    "nice_total": row[index["nice_total"]],
                    "miss_labels": [miss.get("field") for miss in misses],
                })

        with conn.transaction():
            _set_user(conn, user_id)
            plan_rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + MATCHES_SQL, params).fetchall()
            plan = [row[0] for row in plan_rows]
            print("EXPLAIN (ANALYZE, BUFFERS):")
            for line in plan:
                print(line)

        plan_text = "\n".join(plan)
        print("Plan summary:")
        for name in INDEX_NAMES:
            print(f"{name}: {'yes' if name in plan_text else 'no'}")
        has_listing_seq_scan = any(
            "Seq Scan on listings" in line or "Seq Scan on app.listings" in line
            for line in plan
        )
        print(f"Seq Scan on app.listings: {'yes' if has_listing_seq_scan else 'no'}")
        execution_time = next((line.strip() for line in plan if "Execution Time:" in line), "Execution Time: unavailable")
        print(execution_time)

        timings_ms: list[float] = []
        for _ in range(20):
            with conn.transaction():
                _set_user(conn, user_id)
                started = time.perf_counter()
                conn.execute(MATCHES_SQL, params).fetchall()
                timings_ms.append((time.perf_counter() - started) * 1000)

    ordered = sorted(timings_ms)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    print(
        "20 query timings (ms): "
        f"min={min(ordered):.2f}, median={statistics.median(ordered):.2f}, "
        f"p95={p95:.2f}, max={max(ordered):.2f}"
    )


if __name__ == "__main__":
    main()
