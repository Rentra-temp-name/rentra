"""Inspect the seeded user's matches, query plan, and repeated query timings."""

from __future__ import annotations

import math
import os
import statistics
import sys
import time
import uuid
import psycopg
from psycopg.conninfo import conninfo_to_dict

from rentra_api.config import get_settings
from rentra_api.main import MATCHES_SQL


PARAMS_TAIL = (None, None, None, None, 21)
PLANTED_T1_EMAIL = "planted-t1@seed.rentra.test"
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
    return (user_id, lng, lat, radius_meters, *PARAMS_TAIL, user_id)


def _set_user(conn: psycopg.Connection, user_id: str) -> None:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))


def _resolve_tenant_id(requested_id: str | None) -> str:
    if requested_id:
        try:
            tenant_uuid = uuid.UUID(requested_id)
        except ValueError:
            raise SystemExit("EXPLAIN_TENANT must be a UUID") from None
        return str(tenant_uuid)
    test_database_url = os.environ.get("TEST_DATABASE_URL", "")
    if not test_database_url:
        raise SystemExit("TEST_DATABASE_URL is required to resolve the planted T1 user")
    _require_local(test_database_url)
    with psycopg.connect(test_database_url) as admin_conn:
        row = admin_conn.execute(
            "SELECT id FROM auth.users WHERE email = %s", (PLANTED_T1_EMAIL,)
        ).fetchone()
    if row is None:
        raise SystemExit("Planted T1 user was not found")
    return str(row[0])


def _run(output) -> None:
    database_url = get_settings().DATABASE_URL
    _require_local(database_url)
    with psycopg.connect(database_url) as conn:
        user_id = _resolve_tenant_id(os.environ.get("EXPLAIN_TENANT"))
        with conn.transaction():
            _set_user(conn, user_id)
            params = _params(conn, user_id)
            if params[3] is None:
                raise SystemExit("Selected tenant has no saved search location")
            radius_km = float(params[3]) / 1000.0
            must_count, nice_count = conn.execute(
                """SELECT count(*) FILTER (WHERE importance = 'must'),
                          count(*) FILTER (WHERE importance = 'nice')
                   FROM (
                       SELECT importance FROM app.requirements WHERE user_id = %s
                       UNION ALL
                       SELECT importance FROM app.requirement_numeric WHERE user_id = %s
                   ) AS requirements""",
                (user_id, user_id),
            ).fetchone()
            listing_count = conn.execute(
                """SELECT count(*)
                   FROM app.listings AS listing
                   WHERE listing.status = 'active'
                     AND listing.suspended_at IS NULL
                     AND extensions.st_dwithin(
                         listing.point,
                         extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography,
                         %s
                     )""",
                (params[1], params[2], params[3]),
            ).fetchone()[0]
            cursor = conn.execute(MATCHES_SQL, params)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
            index = {name: position for position, name in enumerate(columns)}
            perfect_count = sum(
                row[index["perfect_flag"]] and not row[index["explore_flag"]] for row in rows
            )
            ranked_count = sum(
                not row[index["perfect_flag"]] and not row[index["explore_flag"]] for row in rows
            )
            print(f"Tenant user id: {user_id}", file=output, flush=True)
            print(f"Search radius km: {radius_km:g}", file=output, flush=True)
            print(f"Requirements: {must_count} must, {nice_count} nice", file=output, flush=True)
            print(f"Active non-suspended listings inside circle: {listing_count}", file=output, flush=True)
            print(
                f"MATCHES_SQL rows: {perfect_count} perfect, {ranked_count} ranked, {len(rows)} total",
                file=output,
                flush=True,
            )
            print("First 10 matches:", file=output, flush=True)
            for row in rows[:10]:
                misses = row[index["misses"]] or []
                print(
                    {
                        "listing_id": row[index["id"]],
                        "perfect_flag": row[index["perfect_flag"]],
                        "explore_flag": row[index["explore_flag"]],
                        "must_total": row[index["must_total"]],
                        "nice_total": row[index["nice_total"]],
                        "miss_labels": [miss.get("field") for miss in misses],
                    },
                    file=output,
                    flush=True,
                )

        with conn.transaction():
            _set_user(conn, user_id)
            plan_rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + MATCHES_SQL, params).fetchall()
            plan = [row[0] for row in plan_rows]
            print("EXPLAIN (ANALYZE, BUFFERS):", file=output, flush=True)
            for line in plan:
                print(line, file=output, flush=True)

        plan_text = "\n".join(plan)
        print("Plan summary:", file=output, flush=True)
        for name in INDEX_NAMES:
            print(f"{name}: {'yes' if name in plan_text else 'no'}", file=output, flush=True)
        has_listing_seq_scan = any(
            "Seq Scan on listings" in line or "Seq Scan on app.listings" in line
            for line in plan
        )
        print(f"Seq Scan on app.listings: {'yes' if has_listing_seq_scan else 'no'}", file=output, flush=True)
        execution_time = next((line.strip() for line in plan if "Execution Time:" in line), "Execution Time: unavailable")
        print(execution_time, file=output, flush=True)

        timings_ms: list[float] = []
        for run in range(1, 21):
            print(f"Timing run {run} of 20", flush=True)
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
        f"p95={p95:.2f}, max={max(ordered):.2f}",
        file=output,
        flush=True,
    )


def main() -> None:
    output_path = os.environ.get("EXPLAIN_OUT")
    if output_path:
        try:
            output = open(output_path, "w", encoding="utf-8")
        except OSError:
            raise SystemExit("Could not open EXPLAIN_OUT output file") from None
        try:
            _run(output)
        finally:
            output.close()
    else:
        _run(sys.stdout)


if __name__ == "__main__":
    main()
