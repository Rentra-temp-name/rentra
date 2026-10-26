# Rentra V1 Backend Test Report

## Status

- Committed locally as `bc38304` on `rentra-v1-backend`. Not pushed.
- Full suite on a clean database reset: 237 passed, 7 skipped (opt-in tests: `EXPLAIN_MATCHES`, `SEED_PERF`, and pooler), 187.65 s.
- All 46 migrations apply from zero with no errors.

## Test history

| Stage | Passed |
| --- | ---: |
| Step 6 | 199 |
| Step 9a | 207 |
| Step 9b | 214 |
| Step 9c | 224 |
| Step 10a | 231 |
| Step 10b | 233 |
| 30 km default | 235 |
| Current | 237 |

## Method

Tests use real local Supabase Postgres, never mocks. The accuracy oracle in `scripts/check_match_accuracy.py` compares SQL results against an independent calculation.

## Matches performance

| Scenario | Result |
| --- | --- |
| Typical tenants, 20k listings and 50k users | Median about 190 ms, p95 about 220 to 246 ms. The 300 ms target was met. Before the 10b fix, median was about 270 ms. |
| Worst case: 50,000 listings in the circle, every tenant 30 km, 14 requirements (8 musts, 6 nices), original EXPLAIN | 3,640 ms; median 4,471 ms; p95 4,934 ms. |
| Same worst case after lean `match_checks` | Median about 1,740 ms; p95 about 1,830 to 1,900 ms. |

The 10b slowness root cause was RLS re-checking every row while the planner could not use the partial GiST index. The owner accepted the lean `match_checks` result. The original target under 1 s was loosened. Worst case 1.7 s, re-measure on real Supabase. This does not meet the original 1 s target.

Plans B (numeric rewrite) and C (answers rewrite) gave no speedup and were kept because results are verified equal. The real cost inside `match_checks` was never isolated.

## Accuracy

| Run | Tenants | Listings compared | Mismatches |
| --- | ---: | ---: | ---: |
| 10b run | 500 | 1,448,990 | 0 |
| Rerun under load | 100 | 268,825 | 0 |
| Worst-case seed after lean change | 30 | 1,454,513 | 0 |

Coverage gap: the seeds have no tenants for the "only nice rows" and "multi-choice must / all_allowed exclusive" branches. Those branches are covered by pytest only.

## Map performance

At 20k listings, p95 was 134 ms zoomed out (8,620 in bbox), 48 ms mid zoom, and 4 ms street level.

| 50k view | Median | p95 |
| --- | ---: | ---: |
| Valley | 371 ms | 456 ms |
| Mid zoom | 30 ms | 36 ms |
| Street level | 2.7 ms | 3.4 ms |

The 20k map target was 200 ms and was met. The map target is now anything under 1 s. GiST was not selected by the planner locally.

## Seed performance tests

With `SEED_PERF=1`, 5 tests passed in 54.75 s. Limits are matches p95 2500 ms and map p95 1000 ms.

## Design decisions locked

- Default radius is 30 km, with a maximum of 50 km.
- Ordering: score descending, nices met descending (only when musts exist), rent ascending, distance ascending, `created_at` descending, then `id`.
- Ranked misses show only must labels when musts exist.
- Ranked results are capped at 100; perfect results are uncapped.

## Bugs found and fixed during review

- Quadratic correlated subselects.
- False misses for multi-answer listings.
- Ambiguous `id` column.
- Numeric versus bigint on `sum`.
- Missing `AS misses` alias.
- Test sequence grant fix: `connect_listing` is SECURITY DEFINER owned by `postgres`, so the test trigger needs the sequence grant for `postgres` as well as `rentra_api`.

## Open items

- GiST proof.
- Load test with many users.
- Real-Supabase p95.
- Worst-case 1.7 s re-measure on real Supabase.
- DBSCAN input cap unmeasured.
- Pooler test skipped, needs `TEST_POOLER_DATABASE_URL`.
- Docker image build not verified.
- Sentry untested with a real DSN.
- Cron schedule unverified locally.
- Restrict or regenerate the leaked `google_maps_key` before launch.
- It is unexplained why `test_connect_creates_both_notifications_atomically` was green on the earlier clean run before the sequence grant fix.

## Known small test gaps

- Invalid photo reorder lists.
- Junk magic-byte test.
- Photo cap race lacks a barrier.
