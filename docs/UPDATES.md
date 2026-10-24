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
