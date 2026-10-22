Append new entries at the bottom only; never edit or delete older entries. The bottom entry is the current state. Do not restate spec text; see docs/rentra-v1-backend-handoff.md. Full detail lives in git history.

## 2026-10-22: 4b photos done
- Commit: 30578f2e79025d91e33c721829e17bb56cc7af84 — Listing photos (4b): upload, thumbnails, delete, reorder, tests, handoff doc
- Shipped the photo metadata migration, upload/thumbnail/delete/reorder API, tests, and handoff updates.
- Done: steps 1, 2, 3, 4a, 4b, 4c, 5, 7, 8, and polish backlog. Not done: 6, 9, 10. Next: step 6, requirements and matching.
- Known non-blocking test gaps: `test_magic_byte_mismatch_rejected` uses junk, not a valid PNG with JPEG magic; `test_photo_cap_race_two_uploads` lacks a barrier; `test_foreign_user_gets_404_on_photo_routes` does not check no row/object after rejected upload; no invalid reorder-list tests found (partial list, duplicate IDs, IDs from another listing). `test_content_length_precheck` does distinguish: its 6 MiB request exceeds the pre-check threshold, while the 5 MiB + 1 byte test stays below it and exercises the stream cap.
- Reported full pytest run was green before the commit; not independently verified here. Section 13 calls accepted formats jpeg/png/webp; code accepts MPO as JPEG first frame, consistent with JPEG support.
- Pending docs: `data-model.md`, `overview.md`, `auth-and-access.md`, and `user-flows.md` need syncing to the handoff.
