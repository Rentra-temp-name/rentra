"""Benchmark the map route SQL against the local seeded listings."""

from __future__ import annotations

import math
import statistics
import time

import psycopg
from psycopg.conninfo import conninfo_to_dict

from rentra_api.config import get_settings
from rentra_api.main import MAP_CLUSTER_SQL, MAP_POINTS_SQL


POINT_INDEX = "listings_public_point_gist_idx"
COUNT_SQL = """SELECT count(*)
                FROM app.listings AS listing
                WHERE listing.status = 'active'
                  AND listing.suspended_at IS NULL
                  AND extensions.st_intersects(
                      listing.point,
                      extensions.st_makeenvelope(%s, %s, %s, %s, 4326)::extensions.geography
                  )"""
CASES = (
    ("a: low zoom, Kathmandu valley", 8.0, (85.20, 27.55, 85.55, 27.85), True),
    ("b: mid zoom, about 10 km", 12.0, (85.28, 27.615, 85.38, 27.705), False),
    ("c: high zoom, about 1 km", 16.0, (85.325, 27.6555, 85.335, 27.6645), True),
)


def _require_local(database_url: str) -> None:
    host = conninfo_to_dict(database_url).get("host")
    hosts = host.split(",") if host else []
    if not hosts or any(value not in {"127.0.0.1", "localhost"} for value in hosts):
        raise SystemExit("Refusing: DATABASE_URL host must be 127.0.0.1 or localhost")


def _fetch_rows(conn: psycopg.Connection, sql: str, params: tuple[object, ...]):
    with conn.transaction():
        return conn.execute(sql, params).fetchall()


def _query_for_case(settings, zoom: float, bbox: tuple[float, float, float, float], cap: int):
    west, south, east, north = bbox
    if zoom < settings.MAP_CLUSTER_ZOOM:
        eps = min(0.5, 0.002 * (2 ** (settings.MAP_CLUSTER_ZOOM - zoom)))
        return MAP_CLUSTER_SQL, (west, south, east, north, eps, cap + 1), "clusters"
    return MAP_POINTS_SQL, (west, south, east, north, cap + 1), "points"


def main() -> None:
    settings = get_settings()
    _require_local(settings.DATABASE_URL)
    cap = settings.MAP_RESPONSE_CAP

    with psycopg.connect(settings.DATABASE_URL) as conn:
        for label, zoom, bbox, explain in CASES:
            sql, params, result_kind = _query_for_case(settings, zoom, bbox, cap)
            inside_count = _fetch_rows(conn, COUNT_SQL, params[:4])[0][0]

            if explain:
                plan_rows = _fetch_rows(conn, "EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
                plan = [row[0] for row in plan_rows]
                print(f"{label} EXPLAIN (ANALYZE, BUFFERS):")
                for line in plan:
                    print(line)
                print(f"{label} uses {POINT_INDEX}: {'yes' if any(POINT_INDEX in line for line in plan) else 'no'}")

            timings_ms: list[float] = []
            rows = []
            for _ in range(100):
                started = time.perf_counter()
                rows = _fetch_rows(conn, sql, params)
                timings_ms.append((time.perf_counter() - started) * 1000.0)

            ordered = sorted(timings_ms)
            p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
            result_count = min(len(rows), cap)
            capped = len(rows) > cap
            print(
                f"{label}: {result_kind}={result_count}, capped={capped}, "
                f"listings_in_bbox={inside_count}, runs=100, "
                f"min={min(ordered):.2f} ms, median={statistics.median(ordered):.2f} ms, "
                f"p95={p95:.2f} ms, max={max(ordered):.2f} ms"
            )


if __name__ == "__main__":
    main()
