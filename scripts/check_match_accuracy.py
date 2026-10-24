"""Read-only accuracy and latency audit of matches against a Python oracle."""

from __future__ import annotations

import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from rentra_api.config import get_settings
from rentra_api.main import MATCHES_SQL


RANDOM_SEED = 42
T1_ID = "479abdcd-c6ab-4137-a595-b77274916af0"
MATCH_TAIL = (None, None, None, None, 21)
NUMERIC_FIELDS = {"rent_amount", "bedrooms", "bathrooms_total", "size_value", "max_people"}
BUCKET_NAMES = (
    "no requirements",
    "only nice rows, no musts",
    "5 or more musts",
    "multi-choice must with several options",
    "all five numeric fields",
    "largest search radius",
)
_REPORT_LINES: list[str] = []


def _print(*values: Any) -> None:
    print(*values, flush=True)
    _REPORT_LINES.append(" ".join(str(value) for value in values))


def _require_local(database_url: str, label: str) -> None:
    host = conninfo_to_dict(database_url).get("host")
    hosts = host.split(",") if host else []
    if not hosts or any(value not in {"127.0.0.1", "localhost"} for value in hosts):
        raise SystemExit(f"Refusing: {label} host must be 127.0.0.1 or localhost")


def _matches_params(conn: psycopg.Connection, user_id: str) -> tuple[object, ...]:
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
    return (user_id, lng, lat, radius_meters, *MATCH_TAIL)


def _set_user(conn: psycopg.Connection, user_id: str) -> None:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))


def _load_tenants(conn: psycopg.Connection) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    tenants = {
        str(row["user_id"]): {
            "lng": float(row["lng"]),
            "lat": float(row["lat"]),
            "radius_km": float(row["search_radius_km"]),
            "attributes": [],
            "numeric": [],
        }
        for row in conn.execute(
            """SELECT user_id,
                      extensions.st_x(search_point::extensions.geometry) AS lng,
                      extensions.st_y(search_point::extensions.geometry) AS lat,
                      search_radius_km
               FROM app.tenant_locations"""
        ).fetchall()
    }
    for row in conn.execute(
        """SELECT r.user_id, r.attribute_id, r.option_id, r.importance, r.pick_rule, a.key AS label
           FROM app.requirements r
           JOIN app.attributes a ON a.id = r.attribute_id"""
    ).fetchall():
        tenant = tenants.get(str(row["user_id"]))
        if tenant is not None:
            tenant["attributes"].append(row)
    for row in conn.execute(
        "SELECT user_id, field, value, importance FROM app.requirement_numeric"
    ).fetchall():
        tenant = tenants.get(str(row["user_id"]))
        if tenant is not None:
            tenant["numeric"].append(row)

    buckets: dict[str, set[str]] = {name: set() for name in BUCKET_NAMES}
    by_user_multi: dict[tuple[str, str], int] = defaultdict(int)
    for user_id, tenant in tenants.items():
        attributes = tenant["attributes"]
        numeric = tenant["numeric"]
        all_rows = [*attributes, *numeric]
        must_count = sum(row["importance"] == "must" for row in all_rows)
        if not all_rows:
            buckets[BUCKET_NAMES[0]].add(user_id)
        if all_rows and all(row["importance"] == "nice" for row in all_rows):
            buckets[BUCKET_NAMES[1]].add(user_id)
        if must_count >= 5:
            buckets[BUCKET_NAMES[2]].add(user_id)
        for row in attributes:
            if row["importance"] == "must" and row["pick_rule"] == "multi":
                by_user_multi[(user_id, str(row["attribute_id"]))] += 1
        if {row["field"] for row in numeric} >= NUMERIC_FIELDS:
            buckets[BUCKET_NAMES[4]].add(user_id)

    for (user_id, _attribute_id), count in by_user_multi.items():
        if count >= 2:
            buckets[BUCKET_NAMES[3]].add(user_id)

    if tenants:
        largest_radius = max(tenant["radius_km"] for tenant in tenants.values())
        buckets[BUCKET_NAMES[5]] = {
            user_id for user_id, tenant in tenants.items()
            if tenant["radius_km"] == largest_radius
        }
    return tenants, buckets


def _select_tenants(
    tenants: dict[str, dict[str, Any]], buckets: dict[str, set[str]], limit: int | None = None
) -> tuple[list[str], dict[str, int]]:
    if len(tenants) < 500:
        raise SystemExit(f"Need 500 tenants with locations; found {len(tenants)}")
    if T1_ID not in tenants:
        raise SystemExit(f"Required planted tenant is missing or has no location: {T1_ID}")

    selected = {T1_ID}
    for name in BUCKET_NAMES:
        existing = len(selected & buckets[name])
        needed = max(0, min(50, len(buckets[name])) - existing)
        available = sorted(buckets[name] - selected)
        if needed:
            selected.update(random.sample(available, min(needed, len(available))))

    remaining = sorted(tenants.keys() - selected)
    selected.update(random.sample(remaining, min(max(0, 500 - len(selected)), len(remaining))))
    chosen = sorted(selected)
    if limit is not None:
        limit = min(limit, len(chosen))
        limited = {T1_ID}
        available = [user_id for user_id in chosen if user_id != T1_ID]
        limited.update(random.sample(available, limit - 1))
        chosen = sorted(limited)
    coverage = {name: len(set(chosen) & buckets[name]) for name in BUCKET_NAMES}
    return chosen, coverage


def _load_requirements(conn: psycopg.Connection, user_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attributes = conn.execute(
        """SELECT r.attribute_id, r.option_id, r.importance, r.pick_rule, a.key AS label
           FROM app.requirements r
           JOIN app.attributes a ON a.id = r.attribute_id
           WHERE r.user_id = %s""",
        (user_id,),
    ).fetchall()
    numeric = conn.execute(
        "SELECT field, value, importance FROM app.requirement_numeric WHERE user_id = %s",
        (user_id,),
    ).fetchall()
    return attributes, numeric


def _oracle_rows(
    conn: psycopg.Connection, user_id: str, lng: float, lat: float, radius_km: float
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    attributes, numeric_requirements = _load_requirements(conn, user_id)
    listings = conn.execute(
        """SELECT l.id, l.rent_amount, l.created_at,
                  extensions.st_distance(
                      l.point,
                      extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography,
                      false
                  )::float8 AS distance_m
           FROM app.listings AS l
           WHERE l.status = 'active'
             AND l.suspended_at IS NULL
             AND l.owner_id <> %s
             AND extensions.st_dwithin(
                 l.point,
                 extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography,
                 %s
             )""",
         (lng, lat, user_id, lng, lat, radius_km * 1000.0),
    ).fetchall()
    ids = [row["id"] for row in listings]
    answers: dict[Any, dict[Any, dict[str, Any]]] = defaultdict(lambda: defaultdict(lambda: {"options": set(), "exclusive": False}))
    listing_numeric: dict[Any, dict[str, Decimal]] = defaultdict(dict)
    if ids:
        for row in conn.execute(
            """SELECT la.listing_id, la.attribute_id, la.option_id, ao.is_exclusive
               FROM app.listing_answers la
               JOIN app.attribute_options ao ON ao.id = la.option_id
               WHERE la.listing_id = ANY(%s)""",
            (ids,),
        ).fetchall():
            answer = answers[row["listing_id"]][row["attribute_id"]]
            answer["options"].add(row["option_id"])
            answer["exclusive"] = answer["exclusive"] or row["is_exclusive"]
        for row in conn.execute(
            "SELECT listing_id, field, value FROM app.listing_numeric WHERE listing_id = ANY(%s)",
            (ids,),
        ).fetchall():
            listing_numeric[row["listing_id"]][row["field"]] = row["value"]

    oracle: dict[str, dict[str, Any]] = {}
    for listing in listings:
        listing_id = str(listing["id"])
        must_miss = nice_miss = must_total = nice_total = 0
        miss_labels: set[str] = set()
        for requirement in attributes:
            importance = requirement["importance"]
            if importance == "must":
                must_total += 1
            else:
                nice_total += 1
            answer = answers[listing["id"]][requirement["attribute_id"]]
            met = (
                requirement["option_id"] in answer["options"]
                or answer["exclusive"]
            )
            if not met:
                miss_labels.add(requirement["label"])
                if importance == "must":
                    must_miss += 1
                else:
                    nice_miss += 1

        values = listing_numeric[listing["id"]]
        for requirement in numeric_requirements:
            importance = requirement["importance"]
            field = requirement["field"]
            if importance == "must":
                must_total += 1
            else:
                nice_total += 1
            if field == "rent_amount":
                missed = listing["rent_amount"] > requirement["value"]
            else:
                missed = values.get(field, 0) < requirement["value"]
            if missed:
                miss_labels.add(field)
                if importance == "must":
                    must_miss += 1
                else:
                    nice_miss += 1

        if must_total:
            score = (must_total - must_miss) / must_total
        elif nice_total:
            score = (nice_total - nice_miss) / nice_total
        else:
            score = 1.0
        perfect = (must_total > 0 and must_miss == 0) or (
            must_total == 0 and nice_total > 0 and nice_miss == 0
        )
        oracle[listing_id] = {
            "must_total": must_total,
            "nice_total": nice_total,
            "must_miss": must_miss,
            "nice_miss": nice_miss,
            "miss_labels": miss_labels,
            "perfect_flag": perfect,
            "explore_flag": must_total == 0 and nice_total == 0,
            "score": score,
            "nice_met": nice_total - nice_miss,
            "rent_amount": listing["rent_amount"],
            "distance_m": listing["distance_m"],
            "created_at": listing["created_at"],
        }
    return oracle, attributes, numeric_requirements


def _record(mismatches: list[dict[str, Any]], tenant: str, listing: str, field: str, expected: Any, got: Any) -> None:
    mismatch = {
        "tenant": tenant,
        "listing": listing,
        "field": field,
        "expected": expected,
        "got": got,
    }
    mismatches.append(mismatch)
    _print_new_mismatches(tenant, [mismatch])


def _compare_checks(
    tenant_id: str,
    oracle: dict[str, dict[str, Any]],
    check_rows: list[tuple],
    mismatches: list[dict[str, Any]],
) -> None:
    actual = {str(row[0]): row for row in check_rows}
    expected_ids = set(oracle)
    actual_ids = set(actual)
    if expected_ids != actual_ids:
        _record(
            mismatches,
            tenant_id,
            "*",
            "listing_ids",
            sorted(expected_ids - actual_ids),
            sorted(actual_ids - expected_ids),
        )
    for listing_id in sorted(expected_ids | actual_ids):
        expected = oracle.get(listing_id)
        row = actual.get(listing_id)
        if expected is None or row is None:
            continue
        got = {
            "must_miss": row[7],
            "nice_miss": row[8],
            "must_total": row[9],
            "nice_total": row[10],
            "miss_labels": {item["field"] for item in (row[11] or [])},
        }
        for field in ("must_total", "nice_total", "must_miss", "nice_miss", "miss_labels"):
            if expected[field] != got[field]:
                _record(
                    mismatches,
                    tenant_id,
                    listing_id,
                    field,
                    sorted(expected[field]) if isinstance(expected[field], set) else expected[field],
                    sorted(got[field]) if isinstance(got[field], set) else got[field],
                )


def _sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    created = row["created_at"]
    created_stamp = created.timestamp() if isinstance(created, datetime) else 0.0
    nice_tiebreak = -row["nice_met"] if row["must_total"] > 0 else 0
    return (-row["score"], nice_tiebreak, row["rent_amount"], row["distance_m"], -created_stamp, row["id"])


def _compare_final(
    tenant_id: str,
    oracle: dict[str, dict[str, Any]],
    final_rows: list[tuple],
    mismatches: list[dict[str, Any]],
    has_requirements: bool,
) -> None:
    actual_ids = [str(row[0]) for row in final_rows]
    if has_requirements:
        perfect = sorted(
            ((listing_id, row) for listing_id, row in oracle.items() if row["perfect_flag"]),
            key=lambda item: _sort_key({**item[1], "id": item[0]}),
        )
        ranked = sorted(
            ((listing_id, row) for listing_id, row in oracle.items() if not row["perfect_flag"]),
            key=lambda item: _sort_key({**item[1], "id": item[0]}),
        )[:100]
        expected_ids = [listing_id for listing_id, _ in (*perfect, *ranked)]
        if actual_ids != expected_ids:
            _record(mismatches, tenant_id, "*", "final_id_order", expected_ids, actual_ids)
        return

    if len(actual_ids) != len(set(actual_ids)):
        _record(mismatches, tenant_id, "*", "explore_duplicates", "unique ids", actual_ids)
    if len(actual_ids) > 21:
        _record(mismatches, tenant_id, "*", "explore_count", "<= 21", len(actual_ids))
    outside = sorted(set(actual_ids) - set(oracle))
    if outside:
        _record(mismatches, tenant_id, "*", "explore_outside_radius", [], outside)


def _timing_summary(timings: list[tuple[str, float]]) -> None:
    values = [elapsed for _, elapsed in timings]
    ordered = sorted(values)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    _print(
        f"MATCHES_SQL timing ms: min={min(ordered):.2f}, median={statistics.median(ordered):.2f}, "
        f"p95={p95:.2f}, max={max(ordered):.2f}"
    )
    slowest = sorted(timings, key=lambda item: item[1], reverse=True)[:5]
    _print("Five slowest tenants (tenant, ms, requirements, must, nice, radius_km):")
    for user_id, elapsed in slowest:
        meta = _TIMING_META[user_id]
        _print(
            f"  {user_id}, {elapsed:.2f}, {meta['total']}, {meta['must']}, "
            f"{meta['nice']}, {meta['radius_km']:.2f}"
        )


_TIMING_META: dict[str, dict[str, Any]] = {}


def _print_new_mismatches(tenant_id: str, new_mismatches: list[dict[str, Any]]) -> None:
    id_fields = {"listing_ids", "final_id_order", "explore_duplicates", "explore_outside_radius"}
    for mismatch in new_mismatches:
        field = mismatch["field"]
        expected = mismatch["expected"]
        got = mismatch["got"]
        if field in id_fields:
            expected_ids = expected if isinstance(expected, list) else []
            got_ids = got if isinstance(got, list) else []
            _print(
                f"MISMATCH tenant={tenant_id} field={field} "
                f"expected_count={len(expected_ids)} got_count={len(got_ids)} "
                f"expected_ids={expected_ids[:3]} got_ids={got_ids[:3]}"
            )
        elif field == "miss_labels":
            _print(
                f"MISMATCH tenant={tenant_id} listing={mismatch['listing']} field={field} "
                f"expected_count={len(expected)} got_count={len(got)}"
            )
        else:
            _print(
                f"MISMATCH tenant={tenant_id} listing={mismatch['listing']} field={field} "
                f"expected={expected} got={got}"
            )


def main() -> None:
    _REPORT_LINES.clear()
    random.seed(RANDOM_SEED)
    _print(f"Random seed: {RANDOM_SEED}")
    limit_text = os.environ.get("ACCURACY_LIMIT")
    try:
        limit = int(limit_text) if limit_text is not None else None
    except ValueError:
        raise SystemExit("ACCURACY_LIMIT must be a positive integer") from None
    if limit is not None and limit < 1:
        raise SystemExit("ACCURACY_LIMIT must be a positive integer")
    if limit is not None:
        limit = min(limit, 500)
    settings = get_settings()
    superuser_url = os.environ.get("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL
    if not superuser_url:
        raise SystemExit("TEST_DATABASE_URL is required for the independent oracle")
    _require_local(settings.DATABASE_URL, "DATABASE_URL")
    _require_local(superuser_url, "TEST_DATABASE_URL")

    mismatches: list[dict[str, Any]] = []
    timings: list[tuple[str, float]] = []
    total_listings_compared = 0
    started_all = time.perf_counter()
    tenant_wall_times: list[float] = []
    with psycopg.connect(superuser_url, row_factory=dict_row) as oracle_conn:
        tenants, buckets = _load_tenants(oracle_conn)
        selected, coverage = _select_tenants(tenants, buckets, limit)
        _print(f"Tenants selected: {len(selected)}")
        _print("Tenant coverage:")
        for name in BUCKET_NAMES:
            _print(f"  {name}: {coverage[name]}")

        with psycopg.connect(settings.DATABASE_URL) as api_conn:
            for completed, tenant_id in enumerate(selected, start=1):
                tenant_started = time.perf_counter()
                tenant = tenants[tenant_id]
                with api_conn.transaction():
                    _set_user(api_conn, tenant_id)
                    params = _matches_params(api_conn, tenant_id)
                    started = time.perf_counter()
                    final_rows = api_conn.execute(MATCHES_SQL, params).fetchall()
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    check_rows = api_conn.execute(
                        "SELECT * FROM app.match_checks(%s, %s, %s, %s)", params[:4]
                    ).fetchall()
                timings.append((tenant_id, elapsed_ms))
                attributes_count = len(tenant["attributes"])
                numeric_count = len(tenant["numeric"])
                all_rows = [*tenant["attributes"], *tenant["numeric"]]
                must_count = sum(row["importance"] == "must" for row in all_rows)
                nice_count = sum(row["importance"] == "nice" for row in all_rows)
                _TIMING_META[tenant_id] = {
                    "total": attributes_count + numeric_count,
                    "must": must_count,
                    "nice": nice_count,
                    "radius_km": tenant["radius_km"],
                }

                oracle, _attrs, _nums = _oracle_rows(
                    oracle_conn,
                    tenant_id,
                    tenant["lng"],
                    tenant["lat"],
                    tenant["radius_km"],
                )
                total_listings_compared += len(oracle)
                _compare_checks(tenant_id, oracle, check_rows, mismatches)
                _compare_final(
                    tenant_id,
                    oracle,
                    final_rows,
                    mismatches,
                    bool(tenant["attributes"] or tenant["numeric"]),
                )
                tenant_ms = (time.perf_counter() - tenant_started) * 1000.0
                tenant_wall_times.append(tenant_ms)
                if completed % 5 == 0:
                    elapsed_s = time.perf_counter() - started_all
                    avg_ms = sum(tenant_wall_times) / len(tenant_wall_times)
                    eta_s = avg_ms * (len(selected) - completed) / 1000.0
                    _print(
                        f"done {completed}/{len(selected)} | mismatches so far: {len(mismatches)} | "
                        f"last tenant ms: {tenant_ms:.2f} | avg ms: {avg_ms:.2f} | "
                        f"elapsed: {elapsed_s:.1f}s | ETA: {eta_s:.1f}s"
                    )

    _print(f"Tenants checked: {len(selected)}")
    _print(f"Listings compared: {total_listings_compared}")
    _print(f"Mismatch count: {len(mismatches)}")
    _print("First 10 mismatches:")
    for mismatch in mismatches[:10]:
        _print(mismatch)
    _timing_summary(timings)
    total_elapsed = time.perf_counter() - started_all
    _print(f"FINISHED | total elapsed: {total_elapsed:.1f}s | total mismatches: {len(mismatches)}")
    output_path = os.environ.get("ACCURACY_OUT") or "accuracy_out.txt"
    with open(output_path, "w", encoding="utf-8") as report:
        report.write("\n".join(_REPORT_LINES) + "\n")
        report.flush()
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
