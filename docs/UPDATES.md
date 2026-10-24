Append new entries at the bottom only; never edit or delete older entries. The bottom entry is the current state. Do not restate spec text; see docs/rentra-v1-backend-handoff.md. Full detail lives in git history.

## 2026-10-22: 4b photos done
- Commit: 30578f2e79025d91e33c721829e17bb56cc7af84 — Listing photos (4b): upload, thumbnails, delete, reorder, tests, handoff doc
- Shipped the photo metadata migration, upload/thumbnail/delete/reorder API, tests, and handoff updates.
- Done: steps 1, 2, 3, 4a, 4b, 4c, 5, 7, 8, and polish backlog. Not done: 6, 9, 10. Next: step 6, requirements and matching.
- Known non-blocking test gaps: `test_magic_byte_mismatch_rejected` uses junk, not a valid PNG with JPEG magic; `test_photo_cap_race_two_uploads` lacks a barrier; `test_foreign_user_gets_404_on_photo_routes` does not check no row/object after rejected upload; no invalid reorder-list tests found (partial list, duplicate IDs, IDs from another listing). `test_content_length_precheck` does distinguish: its 6 MiB request exceeds the pre-check threshold, while the 5 MiB + 1 byte test stays below it and exercises the stream cap.
- Reported full pytest run was green before the commit; not independently verified here. Section 13 calls accepted formats jpeg/png/webp; code accepts MPO as JPEG first frame, consistent with JPEG support.
- Pending docs: `data-model.md`, `overview.md`, `auth-and-access.md`, and `user-flows.md` need syncing to the handoff.

## 2026-10-23: step 6 remains incomplete
- Requirements and matching remain in progress. Real-Postgres tests are prepared for user execution; do not mark step 6 done until the user confirms they pass.

## 2026-10-23: step 6 implementation update
- Step 6 remains not done pending user execution and confirmation of the real-Postgres matching tests.

## 2026-10-24: step 6 implementation update
- Step 6 remains not done. Waiting for the user's final green real-Postgres run and confirmation.

## 2026-10-24: step 6 done
- Commit: 5f58d03, requirements and matching.
- User ran the real-Postgres suite: 199 passed, 1 skipped
  (the skipped one is the opt-in EXPLAIN test, EXPLAIN_MATCHES=1).
- Local EXPLAIN at 300 listings: about 20 ms execution, sane plan. This is a sanity check only. Step 10 must prove GiST use for st_dwithin at 20k listings, and watch the RLS subplans and the get_public_profile per-row call.
- Done: steps 1-8 and polish. Not done: 9, 10. Next: step 9.

## 2026-10-24: step 9a done
- SQL jobs: job_runs and storage_deletions tables, three job functions (archive stale, purge archived, purge abandoned drafts), guarded pg_cron schedule, force_delete_listing now also queues thumb paths, purge queues paths only for rows actually deleted.
- Full suite run by user: 207 passed, 1 skipped (opt-in EXPLAIN test).
- Cron schedule is guarded and unverified locally. Verify in step 10 staging.
- A job error returns NULL, so cron shows success. The step 10 last-success metric must read job_runs where error IS NULL.
- Not done: 9b (outbox worker), 9c (DELETE /me and deletion sweep), 10. Next: 9b.
- Commit hash: fill in after commit.

## 2026-10-24: step 9b done
- 9a commit hash: c80fa58.
- Outbox worker: rentra_api/worker.py (python -m rentra_api.worker). Claim function leases rows for 5 minutes with FOR UPDATE SKIP LOCKED, complete and fail functions, exponential backoff capped at 6 hours, 404 counts as success, error text is a short code and never contains a path. The worker cycle survives DB errors and retries after 10s.
- rentra_api has no table grants on storage_deletions. The worker only calls the three SECURITY DEFINER functions.
- Full suite run by user: 214 passed, 1 skipped (opt-in EXPLAIN test).
- Not done: 9c (DELETE /me and account deletion sweep), 10. Next: 9c.
- Commit hash: add in the 9c entry.

## 2026-10-24: step 9c done, step 9 complete
- 9b commit hash: 05082db.
- DELETE /me: strict body {confirm}, missing or false returns 400 CONFIRM_REQUIRED. app.request_account_deletion() sets deletion_requested_at, queues storage and thumb paths, deletes the user's listings in one transaction, then the API calls the Auth admin API. Auth failure returns 202 deletion_pending and the worker sweep finishes it (run_deletion_sweep, users stuck over 5 minutes). Already deleted auth user counts as success.
- PRODUCT RULE: a suspended listing stays in the database for legal work, so an account that owns any suspended listing cannot be deleted. DELETE /me returns 409 ACCOUNT_HAS_SUSPENDED_LISTING and changes nothing. The sweep skips such users too. The lifecycle trigger still guards the admin-suspends-mid-delete race.
- Stale JWT of a deleted auth user gets 401 and never re-creates a profile.
- Full suite run by user: 224 passed, 1 skipped (opt-in EXPLAIN test).
- Known gaps: a user who requested deletion and then somehow got a listing suspended would stay pending (believed unreachable, since all their listings are deleted in the same transaction). Cron schedule is still unverified locally, verify in step 10 staging. A job error returns NULL so cron shows success, the step 10 last-success metric must read job_runs where error IS NULL.
- Not done: 10. Next: step 10.
- Commit hash: add in the step 10 entry.

## 2026-10-24: step 10a done
- Step 9c commit hash: e8bfb64.
- Observability (spec section 11): allowlisted JSON logs (message text, args and tracebacks dropped), fresh request id per request (inbound X-Request-ID ignored), Sentry with scrubber (only if SENTRY_DSN set), Prometheus metrics at /metrics (bearer METRICS_TOKEN, 404 if unset), app.get_ops_metrics() for job last success (error IS NULL only) and storage_deletions backlog, new app.connect_listing_counted wrapper so connect_total counts only new rows. httpx and httpcore loggers set to WARNING so URLs never get logged. uvicorn access log disabled, Dockerfile CMD now uvicorn with --no-access-log (fastapi run has no such flag).
- Full suite run by user: 231 passed, 2 skipped (opt-in EXPLAIN test, opt-in pooler test).
- Open: test_api_works_through_transaction_pooler skipped (needs TEST_POOLER_DATABASE_URL), Docker image build not verified (pip network stall), cron schedule unverified locally, Sentry untested against a real DSN.
- Not done: 10b (seed, EXPLAIN GiST proof, p95 at 50k tenants and 20k listings, DBSCAN cap risk). Next: 10b.
- Commit hash: add in the 10b entry.

## 2026-10-24: step 10b done, with open items
- Earlier commits: 9c e8bfb64, 10a acb3486.
- Matching scoring moved into app.match_checks (SECURITY DEFINER, STABLE, fixed search_path, raises MATCH_USER_MISMATCH 42501 if p_uid differs from app.user_id, granted to rentra_api only). MATCHES_SQL no longer does per-row profile lookup; whatsapp joined only for surviving rows.
- Map moved into app.map_clusters and app.map_points (SECURITY DEFINER, rentra_api only). MAP_CLUSTER_SQL and MAP_POINTS_SQL are module constants.
- Migrations: 20261024150000_match_checks_function.sql, 20261024160000_map_functions.sql. Clean db reset applied them with no errors.
- Root cause of slowness: RLS re-checked every row of listings, listing_numeric, listing_answers, listing_photos, and the planner could not use the partial GiST index.
- Results at 20k listings and 50k users: matches T1 median about 190 ms, p95 about 220 to 246 ms (before: median about 270). Map p95 134 ms zoomed out (8,620 in bbox), 48 ms mid zoom, 4 ms street level (before: 242, 25, 124). Targets: matches 300, map 200.
- Accuracy oracle (scripts/check_match_accuracy.py): 500 tenants, 1,448,990 listings compared, 0 mismatches. Rerun of 100 tenants under background load (Windows Update running), 268,825 listings, 0 mismatches. Seed has no tenants for the "only nice rows" and "multi-choice must" buckets, those paths are covered by pytest only.
- Full suite run by user after clean reset: 233 passed, 7 skipped (opt-in tests). test_seed_perf.py with SEED_PERF=1 passed 5 before the reset.
- OPEN: wide-radius heavy tenants (14 requirements, 20 to 50 km radius) take 700 to 880 ms, mixed-sample p95 409 ms (100 tenants), max 1841 ms in the noisy 500 run. Local numbers are indicative only. Re-measure in staging.
- OPEN: GiST not selected at 20k (planner prefers the status index). Speed targets met for typical tenants without it. Revisit in staging. Spec line "prove GiST" is unmet.
- OPEN: DBSCAN clustering has no input cap, only the output is capped (MAP_RESPONSE_CAP, default 500). Nepal-wide zoom 6 view is unmeasured. Grid clustering shelved, revisit only if a wide view gets slow.
- OPEN: load test (many searches at once) deferred to staging, local PC runs app, DB and test together.
- Step 10 is done with logged open items, not fully sealed.
- Not done: sync data-model.md, overview.md, auth-and-access.md, user-flows.md. Spec sections 13 and 15 were updated for step 10 and GiST.
- Commit hash: add in the next entry.

## 2026-10-24: docs synced to handoff
- Step 10b commit hash: 72b36ef.
- data-model.md, overview.md, auth-and-access.md, user-flows.md synced to the handoff (tenant location grid and radius, GiST claim corrected, matching rules, WhatsApp clear flow, account deletion codes).
- Open items unchanged: wide-radius heavy tenants slow, GiST not selected at 20k, DBSCAN input cap unmeasured, load test and real-Supabase p95 in staging.
- Not done: staging run, pre-launch items (spec section 15).
- Commit hash: add in the next entry.
