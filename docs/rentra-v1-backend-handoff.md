# Rentra V1 Backend Handoff

> **This is the most updated version of the handoff. Take this version into best consideration. It replaces all earlier versions, the old audit, its section 12 overrides, and any conflicting line in `data-model.md`, `overview.md`, `auth-and-access.md`, and `user-flows.md`. After building, update those four docs to match this one.**

Build spec for the coding agent. Section 16 contains the registry seed.

Tags: **[PRODUCT]** decided by the owner. **[ENG]** engineering default, changeable. **[UNVERIFIED]** not confirmed, check before relying on it.

## 1. Stack and build rules

- FastAPI in Docker. Supabase Postgres, Auth (Google OAuth), Storage. Next.js on Cloudflare Workers. Cloudflare in front of the API is a pre-launch item, not a V1 build item.
- Transactional email via Resend. The Maps browser key is used on the frontend. The backend reads `google_maps_key` from env. [PRODUCT]
- All app tables live in schema `app`, which is NOT exposed through PostgREST. RLS is enabled on every table. `anon` and `authenticated` get no privileges on schema `app`. Also run `ALTER DEFAULT PRIVILEGES` so new objects never grant to them.
- API DB role `rentra_api`: LOGIN, NOINHERIT, no BYPASSRLS, not a table owner, granted per table only. Per request, inside the transaction: `select set_config('app.user_id', :uid, true)`. RLS policies read `nullif(current_setting('app.user_id', true), '')::uuid`. App queries also filter by owner in every WHERE (defense in depth).
- The Supabase service role key is never used for DB queries. It is used only for the Storage API and the Auth admin API (delete user). Env only, never logged.
- Connect through the Supabase transaction pooler (port 6543). Disable prepared statement caching in the driver (asyncpg `statement_cache_size=0`, psycopg `prepare_threshold=None`). [UNVERIFIED for the chosen driver, test it.]
- Locks inside jobs use `pg_try_advisory_xact_lock` inside a transaction. Never session-level advisory locks behind the pooler.
- JWT: verify signature against the project's JWKS, check `iss`, `aud=authenticated`, and `exp`. Local Supabase was verified to sign access tokens with ES256 using JWKS.
- Migrations: Supabase CLI SQL migrations in `supabase/migrations`. One table per migration, with its RLS, constraints, and indexes in the same file. [ENG]
- Tests run against a real local Supabase Postgres (`supabase start`), never mocks. [ENG]
- Types: `timestamptz` UTC, `uuid` primary keys (`gen_random_uuid()`), rent as `numeric(12,2)` NPR with `CHECK (rent_amount > 0)`. Enums or CHECK for fixed sets. NOT NULL by default. Every FK has an explicit `ON DELETE` and a child-side index.
- Listing numeric fields and units are specified in section 16.2.

## 2. Access

- Principals: visitor, user, admin. No stored role. Tenant and landlord are switchable modes. Switching never deletes anything, and each side's data stays saved. Authorization is by ownership. [PRODUCT]
- The tenant's own household type is not stored. The tenant only sets must or nice on the landlord's tenant-type options (bachelors, family, all allowed). [PRODUCT]
- Admin = a row in `app.admins`, inserted by SQL only. Admin routes check `admins` in the DB on every request.
- Admin powers: suspend and unsuspend any listing, resolve reports. No user suspension in V1. Every admin action writes `admin_actions(admin_id, action, listing_id, reason, at)`. [PRODUCT]
- Judge-ordered data access: admin only, with a written order. Each access writes `legal_access_log(admin_id, order_reference, scope, at)`. This is enforced by process (a script or procedure), not by the DB, because direct SQL access cannot be forced to log. [PRODUCT]
- Owner routes return 404 (not 403) for IDs the caller does not own.

| Who | Can |
| --- | --- |
| Visitor | browse, listing detail (includes phone), map |
| User | own requirements, matches, save, connect, report (not own listing), create/edit/publish/status/archive/restore/delete own listings, notifications |
| Admin | everything a user can, plus suspend, unsuspend, resolve reports, legal access (logged) |

## 3. Data model

All in schema `app`. Names are guidance, constraints are required.

- `profiles(id pk = auth.users.id ON DELETE CASCADE, display_name, whatsapp, deletion_requested_at, created_at)`. Created by upsert on first authenticated request. `whatsapp` is E.164 (+977), validated and stored normalized. Shown publicly on active listings. Clearing it requires confirmation and archives the owner's active non-suspended listings; an active suspended listing blocks clearing. [PRODUCT]
- Onboarding captures two locations for the tenant: current location and search location. Search location is the primary location for matching. If both are the same, that is fine. Store only a coarse area for each, never precise coordinates. The search area is stored as a point with a radius (default 5 km, tenant can adjust). The point is rounded to a coarse grid before storage, never the exact location. A listing's point must fall inside the search circle. [PRODUCT]
- Registry: `attributes(id, key, type yes_no|single|multi, is_active, required_at_publish)`, `attribute_options(id, attribute_id, label, is_exclusive, is_active)`. FKs `ON DELETE RESTRICT`. Never delete, only `is_active=false`. Options are a fixed list that only the owner adds to. Landlords cannot create options. Seed in section 16.
- `listings(id, owner_id FK profiles CASCADE, title, rent_amount numeric(12,2), point geography(Point,4326), status, archived_from_status, archived_at, status_changed_at, suspended_at, suspended_by, suspended_reason, version int, created_at, updated_at)`. Rent is stored here only, not in `listing_numeric`. CHECK: rent is positive; point is inside Nepal bounding box and not NaN. The bounding box also includes parts of India and Tibet, accepted for V1. Exact pin is public for every listing. [PRODUCT]
- `listing_answers(listing_id, attribute_id, option_id)`, PK is all three. Yes/no attributes store the answer as an option row (Yes / No).
- `listing_numeric(listing_id, field, value)`, for the numeric fields in section 16 other than `rent_amount`, which is a listing column.
- `listing_photos(id, listing_id, storage_path, thumb_path, width int NOT NULL CHECK (width > 0), height int NOT NULL CHECK (height > 0), position smallint NOT NULL CONSTRAINT listing_photos_position_check CHECK (position BETWEEN 1 AND 10), CONSTRAINT listing_photos_listing_position_key UNIQUE (listing_id, position) DEFERRABLE INITIALLY DEFERRED)`. Photo cap of 10 comes from the position check constraint, not app code.
- Requirements: `requirements(user_id, attribute_id, option_id, importance must|nice)`, plus `requirement_numeric(user_id, field, value, importance)`. Both tables have RLS, same-migration constraints, indexes, and explicit FK deletes. `requirements` denormalizes `pick_rule`, uses composite FKs to registry, and has `UNIQUE (user_id, attribute_id) WHERE importance='must' AND pick_rule='single'`. Allowed numeric requirements: rent max, bedrooms min, bathrooms_total min, size_value min (sq ft), max_people minimum listing occupancy. Direction is fixed in code. Kitchen, balconies, total floors, road access width, and main-road distance are display-only.
- `connections(id, user_id FK CASCADE, listing_id FK CASCADE, created_at, UNIQUE(user_id, listing_id))`. Indexes `(user_id, created_at)` and `(listing_id, created_at)`.
- `notifications(id, user_id FK CASCADE, kind, listing_id, other_user_id, created_at, read_at)`. Typed columns, no jsonb. Powers the in-app notifications sidebar.
- `saved_listings(user_id, listing_id, created_at)`, PK both.
- `reports(id, reporter_id SET NULL, listing_id SET NULL, snapshot_title, snapshot_whatsapp, reason, status open|resolved, resolved_by, resolved_at, created_at)`, `UNIQUE(reporter_id, listing_id)`. Snapshot is copied at submit so evidence survives deletion. Listings only, no profile reports.
- `admins`, `admin_actions`, `legal_access_log`, `job_runs(job, started_at, finished_at, rows, error)`, `storage_deletions(id, bucket, path, attempts, created_at, done_at)`.
- Required indexes: partial on listings `(rent_amount) WHERE status='active' AND suspended_at IS NULL`; partial GiST on `point` with the same filter; `listing_answers(attribute_id, option_id, listing_id)`; `listings(owner_id, status)`; `listings(status, status_changed_at)`; `listings(archived_at) WHERE status='archived'`.

## 4. Listing lifecycle

Statuses: `draft, active, rented, sold_out, unavailable, archived`. No `deleted`, no `removed`. Suspension is a flag, not a status. A listing is publicly visible only when `status='active' AND suspended_at IS NULL`.

| From | To | Actor |
| --- | --- | --- |
| draft | active (publish) | owner. Requires required fields, all required answers including amenities (compulsory), and a phone on the profile |
| active | rented, sold\_out, unavailable | owner |
| rented, sold\_out, unavailable | active | owner |
| rented, sold\_out, unavailable | archived | system, 30 days after `status_changed_at` |
| draft, active, rented, sold\_out, unavailable | archived (owner archive) | owner. Stores `archived_from_status`, sets `archived_at` |
| archived | previous status (restore) | owner, before purge |
| archived | gone (force delete) | owner, immediate hard delete |
| archived | gone (purge) | system, 30 days after `archived_at` |
| draft | gone (abandoned) | system, untouched for 30 days [ENG] |

- [PRODUCT] Archived listings are purged 30 days after archiving, no exceptions. The owner can restore or force delete before that.
- Archive is the only way a listing leaves the public view. Force delete is the owner's immediate hard delete of an archived listing.
- Suspended listings: the owner cannot change status, archive, restore, or delete. Jobs skip suspended listings (no auto-archive, no purge), so evidence is never destroyed by a timer.
- Clearing WhatsApp requires `{confirm:true}` through `PUT /me`. In one transaction, every owned active non-suspended listing is archived and then the profile number is cleared. Draft, rented, sold-out, and unavailable listings are unchanged. If an active suspended listing exists, the clear fails with `WHATSAPP_REQUIRED_FOR_ACTIVE_LISTING` and the transaction makes no changes. A profile trigger blocks direct clearing while any active listing exists, including suspended listings. Restoring a listing that was active, and reactivating, require a non-empty WhatsApp number (`WHATSAPP_REQUIRED`).
- A DB trigger enforces every row above and rejects all other transitions. The API sets `app.actor` (`owner`, `system`, `admin`) per transaction and the trigger checks it. Each change sets `status_changed_at` and bumps `version`.
- Archive job: one set-based UPDATE, `WHERE status IN (...) AND status_changed_at < now() - interval '30 days' AND suspended_at IS NULL`. This closes the race with a landlord reactivating at day 30.
- Edits: `PATCH` carries `version`. Mismatch returns 409. A trigger bumps `listings.version` on any child write (answers, numeric fields, photos).

## 5. Matching

- `PUT /me/requirements` fully replaces the tenant requirements. Strict Pydantic rejects unknown fields; registry validation accepts active attributes/options only. Limit: 20 writes per minute per user.
- Every selected option row is a separate check, including each multi-choice must. Missing listing answers fail that check. An `is_exclusive` option on the listing satisfies every pick for that attribute.
- Numeric requirement direction is fixed in code: rent is an upper bound from `listings.rent_amount`; bedrooms, bathrooms_total, size_value (sq ft), and max_people are tenant minima, with listing `max_people` required to be at least the tenant group size. Tenant household type is not stored.
- Eligible listings are public-visible (`active`, not suspended), not owned by the caller, and inside the tenant search circle.
- One SQL query computes every match; never score in Python. Score is must rows met / must rows total. Every must met is perfect. If there are no musts, use the same fraction over nice rows. If there are no requirements, return the daily md5 explore feed, keyset paginated, with a nudge flag.
- Ordering: score desc, then nices met desc only when musts exist, rent asc, created_at desc, id. Perfect is uncapped; ranked is capped at 100. Every ranked result includes named misses.
- Response: `{perfect: [...], ranked: [{listing, misses: [...]}], explore: bool, nudge: bool, explore_listings: [...], next_cursor}`. Explore pages are capped to `page_size` and use a daily keyset on `(md5(id::text || current_date::text), id)`. Listing payloads follow public listing reads and include phone, point, and photos.

## 6. Endpoints

Errors use stable codes where defined. Direct JSON responses return `{code, message}` at the top level. FastAPI `HTTPException` responses put their detail under `detail` (sometimes a `{code, message}` object, sometimes a string); request-validation errors return a `detail` array. Generic message outside, detail in logs.

| Route | Auth | Notes |
| --- | --- | --- |
| `GET /health`, `GET /health/ready` | none | ready runs `SELECT 1` as `rentra_api` |
| `GET /profiles/{profile_id}` | none | public profile response contains only `display_name` and `whatsapp`; query runs as `rentra_api` with the target profile scoped through RLS |
| `GET /areas`, `GET /registry` | none | `/areas` returns an empty collection until an area table exists. |
| `GET /listings` | none | keyset, page max 50, includes phone and point, same as detail |
| `GET /listings/{id}` | none | full detail, includes phone and point. Returns `photos` ordered by position; each item has `id`, `position`, `width`, `height`, `original_url`, and `thumb_url`. |
| `GET /map?bbox=&zoom=` | none | bbox and zoom required. Returns server-side clusters at low zoom and individual points at high zoom. Each cluster returns count and centroid. Individual points return id, lat, lng, rent only. Response is capped. [ENG] |
| `GET/PUT /me`, `DELETE /me` | user | delete needs `{confirm:true}`. `DELETE /me` returns 409 `ACCOUNT_HAS_SUSPENDED_LISTING` while a suspended listing exists, and 202 `deletion_pending` if the Auth API fails (the worker sweep retries). `PUT /me` with `whatsapp:null` or an empty string clears it; the API first returns `WHATSAPP_CLEAR_ARCHIVES_LISTINGS` with the active non-suspended listing count, then requires `{confirm:true}` to archive those listings and clear the number. |
| `PUT /me/requirements`, `GET /matches` | user | Full replacement; active-registry validation, 20 writes/minute. Matches are one SQL query; perfect uncapped, ranked capped at 100, and empty requirements use keyset-paginated explore feed with nudge flag. |
| `POST/DELETE /listings/{id}/save`, `GET /me/saved` | user |  |
| `POST /listings/{id}/connect`, `GET /me/connections` | user | see section 7 |
| `GET /me/connections/profile/{user_id}` | user | connection-scoped profile; see section 7 |
| `GET /me/notifications`, `POST /me/notifications/{id}/read` | user | feeds the sidebar |
| `POST /listings` (draft), `GET /me/listings`, `GET /me/listings/{id}` | user | max 20 drafts per user [ENG]. The owner detail route returns the same position-ordered `photos` array and fields as public detail. |
| `PATCH /listings/{id}`, `POST /listings/{id}/publish`, `POST /listings/{id}/status`, `POST /listings/{id}/archive`, `POST /listings/{id}/restore`, `DELETE /listings/{id}` | owner | `DELETE` is force delete, allowed only on archived listings. PATCH requires `version`; when `answers` or `numeric` is supplied, it replaces the full set, so clients must send the full map. Answer option keys are registry option labels. Point input uses `lat`/`lng`. |
| `POST /listings/{id}/photos` | owner | server-side multipart upload only; suspended and archived listings are locked |
| `DELETE /listings/{id}/photos/{photo_id}` | owner | database row is deleted before best-effort object deletion |
| `POST /listings/{id}/photos/reorder` | owner | sends the complete ordered `photo_ids` list |
| `POST /listings/{id}/report` | user | not own listing |
| `GET /admin/reports`, `POST /admin/reports/{id}/resolve`, `POST /admin/listings/{id}/suspend`, `POST /admin/listings/{id}/unsuspend` | admin | resolve accepts an optional `{note}` (trimmed, up to 500 characters) for its audit reason; audited; non-admins receive the same 404 body as an unknown route |

Frontend URLs use `/rent/{slug}-{id}`. The API resolves by the trailing id. No slug column. [ENG]

## 7. Connect and notifications

- Allowed for a signed-in user on a public-visible listing they do not own. [PRODUCT]
- A tenant's WhatsApp number is optional when connecting. If saved, it is shared with the owner of a listing they connected to; without a number, the owner cannot text them. [PRODUCT]
- The owner of a listing a user connected to can open that connector's name and WhatsApp number, if saved. The connector can open the landlord's profile only while the owner has a connected listing that is public-visible. Other cases return the same 404 as a missing profile.
- One transaction: insert into `connections` with `ON CONFLICT DO NOTHING`. If a row was inserted, insert two notifications in the same transaction: one to the connector (property connected) and one to the owner (profile connected). Both sides see the connection. [PRODUCT]
- Repeat calls on a listing that remains public-visible return the same result and create no new notification. If the listing is no longer public-visible, connect returns 404.
- Cap: 50 new connections per rolling 24 hours per user, counted from `connections.created_at`. Over the cap returns 429 `CONNECT_LIMIT`. The cap is soft under concurrency, accepted.
- Own-listing attempts return 400 `CONNECT_OWN_LISTING`. Returns the owner's WhatsApp link, built server-side as `https://wa.me/<digits>`.
- Connection profile reads the current profile number at request time; clearing it removes it from the connector profile. No number yields `whatsapp:null` and `wa_link:null`.
- Notification items contain `id`, `kind`, `created_at`, `read_at`, `other_user:{id, display_name}` or null, and `listing:{id, title}` or null. User and listing references are joined at read time; account deletion cascades a user's notifications, while deleting the other user or listing sets that item field to null. Notifications never contain phone numbers.
- A single set-based trigger insert adds one `saved_listing_changed` notification for each saver, excluding the listing owner, when rent changes or public visibility flips (`status = 'active' AND suspended_at IS NULL`). Title-only and other non-relevant edits do not notify.
- Notifications are an in-app sidebar only. No push. Tenants are notified when a listing they saved changes. Transactional email goes through Resend. [PRODUCT]

## 8. Jobs, outbox, deletion

- pg\_cron runs the pure SQL jobs: archive, purge, abandoned drafts. [ENG]
- Every job: `pg_try_advisory_xact_lock`, a `job_runs` row, one set-based statement, safe to run twice.
- Purge runs in one transaction: insert the listing's photo paths into `storage_deletions`, then delete the listing. Children cascade.
- A worker process (same image, separate command) drains `storage_deletions` with `FOR UPDATE SKIP LOCKED`, retries with backoff, and treats "already gone" as success. It also runs the account deletion sweep.
- Account deletion is immediate on confirm. [PRODUCT] `DELETE /me`: set `deletion_requested_at`, purge owned listings (photos via outbox), delete the auth user through the Auth admin API (cascades the profile). The sweep retries anything stuck with `deletion_requested_at` set. Every authenticated request already loads the profile, and it rejects requests when `deletion_requested_at` is set, because an old JWT stays valid until it expires. An account that owns any suspended listing cannot be deleted (409 `ACCOUNT_HAS_SUSPENDED_LISTING`). Suspended listings stay in the database for legal work until an admin unsuspends them. [PRODUCT]
- Reports keep a snapshot, so a user deleting their account does not erase the evidence.

## 9. Security rules

- Phone and point are public by product decision. [PRODUCT] The phone appears wherever a listing appears: list, detail, and matches. Phone numbers must never appear in logs, error bodies, or stack traces, since that is about leaking data through the server, not about visibility.
- A tenant's saved phone is visible to the owner of a listing they connected to. [PRODUCT]
- Mass assignment: `PATCH` uses an explicit field allowlist. Never writable by the client: `owner_id`, `status`, `suspended_*`, `version` (it is only compared), `created_at`.
- Validation at the boundary with strict Pydantic models. Reject NaN and out-of-range coordinates, oversize or malformed bodies, and unknown fields.
- Photo upload goes through the API only. `Content-Length` is required (missing or non-integer: 411); requests declaring more than 5 MiB plus 64 KiB multipart overhead receive 413 before the body is read. These pre-check responses are top-level `{code, message}` objects. The upload stream is also limited to 5 MiB; stream, image-type, and pixel-limit errors are raised as `HTTPException` and appear under `detail`. JPEG (including MPO, first frame only), PNG, and WebP are accepted by magic-byte/content checks, independent of client type and filename. Pillow enforces a 25,000,000-pixel cap, applies EXIF orientation, then re-encodes originals without metadata and makes thumbnails by fitting the full image inside a fixed 400×300 (4:3) box, padding with the configured bar color as needed. Nothing is stretched or cropped to fill the frame. The original is never resized; the frontend letterboxes originals with CSS `object-fit: contain`. UUID object names are written through the API with the service key. The `listing-photos` bucket is assumed to exist and be public-read. [ENG]
- CORS: allowlist of the frontend origin only. No `*`.
- No stack traces in responses. No user-supplied URLs are ever fetched.
- Secrets only in env, including `google_maps_key`. `.env.example` lists names only. Never logged, never committed.
- Accepted risks: public phones and pins can be scraped (rate limits only slow it). A banned user can make a new account (no user suspension in V1).

## 10. Rate limits

- Anonymous reads: 60 per minute per IP. Signed-in reads: 120 per minute per user. Page size max 50. Connect: 50 per rolling 24 hours per user. [PRODUCT: the numbers were proposed and accepted, change them in config.]
- Writes [ENG]: uploads, draft creation, save/unsave, and reports use the 20-per-minute-per-user write limiter. New reports also use a database-counted cap of 10 per user per rolling 24 hours, based on `reports.created_at`; repeats do not count. Drafts capped at 20 per user.
- V1 runs one container with one worker, so an in-process limiter is correct. With N workers each keeps its own counter and the effective limit is N times higher. Move to Redis only when running more than one worker or container.
- Never use Postgres counters for read limits (a DB write per anonymous read is a self-inflicted DoS). Connect and report caps use the DB.
- Client IP: run uvicorn with proxy headers and trust forwarded headers only from the known proxy. Otherwise every user shares one IP or the header is spoofable.
- Return 429 with `Retry-After`. All limits live in one settings file. Cloudflare edge limits are added before public launch and then take over the read limits.

## 11. Observability

- JSON logs, allowlisted fields only: `ts, level, service, env, version, request_id, route_template, method, status, latency_ms, user_id, event`. Never log request bodies, query strings, headers, phones, coordinates, or IPs. Redact at the logger.
- Error tracker with `send_default_pii` off and a `before_send` scrubber.
- Metrics: RED per route template, 429 count, connect count, job last-success timestamp per job, `storage_deletions` backlog.
- `/health` is liveness. `/health/ready` is readiness and must fail when the DB is down.
- V1-sized alerting: uptime check on `/health/ready`, error tracker alerts, and an alert when a job's last success is older than twice its interval or the outbox backlog stays above 0 for an hour.

## 12. Cut from V1

Boosted listings, reports on profiles, push notifications, Idempotency-Key table, landlord approval, user suspension, listing expiry, account deletion grace period, private pins and grid snap, stored roles, `deleted` and `removed` statuses, Redis, restore after purge, admin-side profile suspension, landlord-created registry options, the archived lease and occupancy items (see section 16).

## 13. Build order

1. **Done.** `rentra_api` role, schema `app`, default privileges, RLS baseline, test harness on local Supabase.
2. **Done.** `profiles`, JWT verification, auth middleware, the deletion-requested check.
3. **Done.** Tenant current and search locations as a point plus radius, registry from section 16, and regression test proving `anon` and `authenticated` cannot execute `app.get_public_profile(uuid)`.
4a. **Done.** Listing schema, lifecycle triggers, version handling, and numeric fields. `app.get_public_profile(p_id)` returns contact details only when that profile owns a publicly visible listing (`status = 'active' AND suspended_at IS NULL`).
4b. **Done.** Photos: store width, height, and thumbnail path; validate jpeg/png/webp bytes and decoded pixel count, apply EXIF orientation, re-encode metadata-free originals, generate fixed-box fit-and-pad thumbnails, and implement upload, delete, and reorder routes.
4c. **Done.** Owner listing routes: create drafts, owner reads, versioned PATCH with registry-validated answers and numeric values, and lifecycle calls through the existing database functions. Enforce the 20-draft cap and 20 writes/minute/user limit.
5. **Done.** Public reads, map with clustering, and rate limits.
6. **Done.** Requirements and matching. `size_unit` is removed; `size_value` is square feet only.
7. **Done.** Connect, notifications sidebar, and connection-scoped profile access.
8. **Done.** Saved listings, reports, admin suspend, audit tables, and saved-listing change notifications.
9. Done. Jobs, outbox worker, account deletion.
10. Observability, then a staging load test at 50k tenants and 20k listings with `EXPLAIN` checks. Prove real GiST index usage and log the DBSCAN clustering input cap risk. Targets: matches p95 300 ms, map p95 200 ms. [UNVERIFIED targets until measured]

Every route in section 6 must have an owning build step.

**Polish backlog (done)**

- Prune empty keys from the in-process rate limiter.
- Exempt `/health/ready` from the limiter.
- Treat bad or expired tokens on public routes as anonymous.
- Add `FOR SHARE` on the profile row in `publish_listing`, `set_listing_status`, and `restore_listing` via a new migration.

## 14. Tests (all against real Postgres)

**Security**

- `test_anon_and_authenticated_have_no_table_access`
- `test_rentra_api_cannot_bypass_rls`
- `test_phone_shown_on_listing_list_detail_and_matches`
- `test_phone_not_in_logs_or_error_bodies`
- `test_foreign_ids_return_404`
- `test_patch_cannot_set_owner_status_suspended_version`
- `test_connect_own_listing_rejected`
- `test_connect_cap_rolling_24h`
- `test_connect_at_cap_repeat_still_succeeds`
- `test_suspended_listing_hidden_from_public`
- `test_suspended_listing_locked_for_owner`
- `test_jobs_skip_suspended_listings`
- `test_admin_actions_audited`
- `test_admin_route_checks_admins_table`
- `test_admin_suspend_hides_listing_from_public_and_locks_owner`
- `test_admin_suspend_requires_reason_and_409_cases`
- `test_admin_resolve_idempotent_no_second_audit_row`
- `test_admin_actions_not_updatable_or_deletable_by_rentra_api`
- `test_new_routes_require_auth`
- `test_logs_contain_no_phone_coords_ip`
- `test_read_limit_per_ip_and_per_user`
- `test_role_switch_keeps_both_sides_data`
- `test_landlord_cannot_create_registry_option`

**Matching**

- `test_missed_must_ranks_lower_and_is_named`
- `test_all_musts_met_is_perfect`
- `test_matching_ranks_by_must_fraction`
- `test_nice_tiebreak_among_equal_must_scores`
- `test_no_musts_falls_back_to_nices`
- `test_no_requirements_gets_explore_feed_and_nudge`
- `test_multichoice_must_requires_all_picks`
- `test_all_allowed_rule_satisfies_any_tenant_type_pick`
- `test_each_numeric_requirement_direction_including_rent_from_listings`
- `test_missing_answer_on_must_is_miss`
- `test_db_rejects_second_single_choice_must`
- `test_put_rejects_inactive_option`
- `test_own_suspended_and_outside_radius_listings_excluded`
- `test_tiebreak_order`
- `test_ranked_cap_100_and_perfect_uncapped`
- `test_tenant_household_type_not_stored`
- `test_explore_feed_page_size_cursor_no_duplicates_or_gaps`
- `test_requirements_put_strict_and_rate_limited`
- `test_put_rejects_display_only_numeric_fields`
- `test_retired_numeric_fields_are_inactive_and_references_removed`
- `test_size_unit_is_rejected_on_create_and_patch`

**Lifecycle**

- `test_every_illegal_transition_rejected_by_trigger`
- `test_publish_requires_fields_answers_amenities_and_phone`
- `test_archive_job_vs_owner_reactivate_race`
- `test_restore_before_purge_allowed`
- `test_purge_after_30_days_and_restore_after_purge_fails`
- `test_force_delete_archived_is_immediate`
- `test_force_delete_rejected_on_non_archived`
- `test_abandoned_draft_purged`
- `test_version_conflict_409_and_child_write_bumps_version`
- `test_clear_without_confirm_is_rejected_and_changes_nothing`
- `test_confirmed_clear_archives_only_active_non_suspended_listings`
- `test_suspended_active_listing_blocks_whatsapp_clear`
- `test_direct_whatsapp_clear_is_rejected_while_listing_is_active`
- `test_restore_and_reactivation_require_whatsapp_then_succeed`
- `test_restored_listing_returns_to_public_reads`
- `test_whatsapp_clear_never_touches_foreign_listings`

**Owner listing routes**

- `test_owner_full_listing_lifecycle_and_public_phone`
- `test_publish_error_names_missing_answers_numeric_and_whatsapp`
- `test_patch_stale_version_and_valid_patch_bump`
- `test_patch_rejects_invalid_option_wrong_attribute_cardinality_and_rent_numeric`
- `test_foreign_user_gets_not_found_on_all_owner_id_routes`
- `test_suspended_listing_locked_for_owner_on_write_routes`
- `test_draft_cap_twenty`
- `test_write_rate_limit_returns_429`
- `test_phone_never_appears_in_owner_route_error_or_logs`
- `test_patch_rejects_protected_fields` (`field=owner_id`)
- `test_patch_rejects_protected_fields` (`field=status`)
- `test_patch_rejects_protected_fields` (`field=suspended_at`)
- `test_patch_rejects_protected_fields` (`field=suspended_by`)
- `test_patch_rejects_protected_fields` (`field=suspended_reason`)
- `test_patch_rejects_protected_fields` (`field=created_at`)

**Photos**

- `test_photo_upload_stores_row_and_both_objects`
- `test_thumbnail_fit_and_pad` (landscape and portrait)
- `test_exif_stripped_and_orientation_applied`
- `test_magic_byte_mismatch_rejected`
- `test_oversize_rejected_and_nothing_stored`
- `test_content_length_precheck`
- `test_pixel_cap_rejected`
- `test_mpo_jpeg_accepted`
- `test_photo_cap_race_two_uploads`
- `test_photo_cap_race_below_cap_both_succeed`
- `test_photo_cap_ten_enforced_by_db`
- `test_failed_upload_leaves_no_storage_objects`
- `test_photo_write_bumps_listing_version`
- `test_foreign_user_gets_404_on_photo_routes`
- `test_delete_photo_of_other_listing_404`
- `test_suspended_listing_locks_photo_writes`
- `test_archived_listing_rejects_photo_writes`
- `test_reorder_changes_positions_in_db`
- `test_delete_removes_row_and_objects`
- `test_storage_delete_failure_logged_without_path`
- `test_photo_write_rate_limit_returns_429`
- `test_public_detail_shows_photos`
- `test_phone_never_in_logs_or_errors_for_photo_routes`

**Idempotency and jobs**

- `test_connect_twice_one_row_one_notification`
- `test_connect_creates_both_notifications_atomically` (trigger marker survives rollback; connection insert is rolled back)
- `test_connect_non_public_listing_404`
- `test_connect_requires_auth`
- `test_connect_returns_wa_link_digits_only`
- `test_connect_concurrent_double_call_one_row`
- `test_notifications_list_own_only_and_keyset` (excludes another user's notification; checks kind and joined listing fields)
- `test_notification_read_idempotent` (checks stable response timestamp and persisted `read_at`)
- `test_notification_read_foreign_id_404`
- `test_connections_list_own_only_and_wa_link_only_if_public`
- `test_connection_and_notifications_cascade_on_account_delete`
- `test_save_idempotent_and_own_rejected`
- `test_save_non_public_404_and_unsave_after_non_public_ok`
- `test_me_saved_own_only_keyset_and_wa_link_only_if_visible`
- `test_saved_listing_visibility_flip_notifies`
- `test_report_snapshot_and_idempotent_repeat`
- `test_report_own_rejected_and_non_public_404`
- `test_report_cap_ten_per_rolling_24h`
- `test_report_survives_listing_purge`
- `test_phone_never_in_logs_or_errors_for_report_and_admin_routes`
- `test_connect_without_tenant_whatsapp_succeeds`
- `test_landlord_can_open_connector_profile`
- `test_connector_profile_null_whatsapp_when_tenant_has_none`
- `test_connector_whatsapp_cleared_later_disappears`
- `test_connector_profile_foreign_user_404`
- `test_tenant_can_open_landlord_profile_only_while_listing_public`
- `test_connector_phone_never_in_logs_or_errors` (checks successful/error responses, notification and connection feeds, and logs)
- `test_each_job_twice_is_noop`
- `test_job_concurrent_run_second_exits`
- `test_purge_storage_failure_retried_by_outbox`
- `test_delete_me_resumes_after_auth_api_failure`
- `test_delete_me_requires_confirm`
- `test_deleted_account_jwt_rejected`
- `test_report_survives_account_deletion`
- `test_saved_listing_change_notifies_tenant`

**Performance and operability**

- `test_matches_p95_at_50k_20k`
- `test_map_p95_at_20k_and_requires_bbox_cap`
- `test_map_clusters_at_low_zoom_points_at_high_zoom`
- `test_explain_uses_indexes`
- `test_ready_fails_when_db_down`
- `test_job_last_success_reported`
- `test_api_works_through_transaction_pooler`

## 15. Dependencies and pending items

- No district or city seed. The map handles location browsing. Search area is a point with a radius. The parking-lot doc is also not written.
- Real GiST index usage is proven by the step 10 staging load test at 20k listings; small local EXPLAIN fixtures verify partial index availability and predicates, not actual GiST selection.
- Open question: pin-tap phone: listing page only (assumed, unconfirmed).
- Cloudflare in front of the API, a privacy policy, and a consent line at publish ("your number and pin are public") are pre-launch items.
- A consent line at connect ("if you saved a number, it is shared with this landlord") is a pre-launch item. Chat is a future feature.
- Nepal rental law: the AI-generated summary is unverified and needs a Nepali lawyer check before any terms or in-app wording. The Family and Bachelors options stay as registry rows so they can be removed before launch if the team decides. [PRODUCT]
- Legal review of phone publication and legal-order access is deferred until after launch. [PRODUCT]

## 16. Registry seed (V1)

Options are a fixed list. Landlords pick from it. Only the owner adds new options. Every attribute with `required_at_publish = yes` must be answered before a listing can publish. Amenities are compulsory. `pick_rule` is `single` for one choice, `multi` for many, `yes_no` for yes or no.

### 16.1 Attributes

| key | type | pick_rule | required_at_publish | options (in order) |
| --- | --- | --- | --- | --- |
| `tenant_type` | multi | multi | yes | bachelors, family (married couples only), all_allowed (exclusive) |
| `pets` | yes_no | yes_no | no | yes, no |
| `dietary` | single | single | no | non_veg_allowed, pure_veg_only |
| `parties` | single | single | no | parties_allowed, small_gatherings_only, quiet_hours |
| `smoking` | single | single | no | inside_allowed, balcony_outdoor_only, strictly_non_smoking |
| `alcohol` | single | single | no | allowed, not_allowed |
| `curfew` | single | single | no | no_curfew, strict_curfew, negotiable_curfew |
| `visitors` | single | single | no | anytime, daytime_only_no_overnight, family_only_friends_restricted |
| `wall_decor` | single | single | no | drilling_painting_allowed, temporary_decor_only |
| `terrace_access` | single | single | no | open_rooftop, fixed_hours_drying_only |
| `religious_events` | single | single | no | small_pujas_allowed, fire_havan_restricted |
| `floor_level` | single | single | yes | ground, first, second, top, penthouse |
| `furnishing` | single | single | yes | unfurnished, semi_furnished, fully_furnished |
| `property_type` | single | single | yes | full_flat, single_room, whole_house, sharing_room_pg |
| `road_type` | single | single | yes | pitched_blacktop, gravel, dirt |
| `separate_living_room` | single | single | yes | separate_living_room, combined_living_dining, none |
| `bathroom_attachment` | single | single | yes | attached, common, mixed |
| `pooja_room` | yes_no | yes_no | yes | yes, no |
| `study_room` | yes_no | yes_no | yes | yes, no |
| `private_rooftop_terrace` | yes_no | yes_no | yes | yes, no |
| `yard_garden` | yes_no | yes_no | yes | yes, no |
| `bike_parking` | yes_no | yes_no | yes | yes, no |
| `car_parking` | yes_no | yes_no | yes | yes, no |
| `ev_charging` | yes_no | yes_no | yes | yes, no |
| `water_supply` | multi | multi | yes | 24x7_supply, tanker, boring, underground_reserve_tank |
| `hot_water` | single | single | yes | solar_heater, electric_geyser, gas_geyser |
| `backup_power` | single | single | yes | inverter, solar, generator |
| `internet_fiber` | yes_no | yes_no | yes | yes, no |
| `cooling` | multi | multi | yes | ac_installed, ceiling_fans |
| `laundry` | multi | multi | yes | washing_machine, dedicated_space, open_drying |
| `kitchen_appliances` | multi | multi | yes | refrigerator, chimney_exhaust_fan |
| `elevator` | yes_no | yes_no | yes | yes, no |
| `security` | multi | multi | yes | gate_guard, cctv, gated_compound |
| `extras` | multi | multi | yes | garden, kids_play_area, door_to_door_trash_pickup |

Notes per attribute:
- `tenant_type`: "Family" is labeled with the note "married couples only." No separate married option. No gender-based options anywhere.
- `pets`: yes/no only. The small/caged option is dropped.
- `curfew`: the actual terms are discussed in chat after the connect.
- `elevator`: the listing's backup power note covers whether the lift runs on backup.
- `floor_level` and `total_floors`: the floor count is numeric (section 16.2), the floor position is the single choice above.
- Kitchen is a numeric count (section 16.2). It has no categories.

### 16.2 Numeric fields

Listing values are stored in `listing_numeric` except `rent_amount`, stored only on `listings`. `size_value` is square feet only. Numeric requirement fields and directions are fixed in code, not stored in the requirement rows.

| field | unit | notes |
| --- | --- | --- |
| `rent_amount` | NPR per month | listing column; tenant maximum |
| `bedrooms` | count | tenant minimum |
| `bathrooms_total` | count | tenant minimum |
| `size_value` | sq ft | tenant minimum |
| `max_people` | count | tenant group size; listing capacity must be at least this value |
| `kitchen_count` | count | display-only, not a requirement |
| `balconies` | count | display-only, not a requirement |
| `total_floors` | count | display-only, not a requirement |
| `road_access_width_ft` | feet | display-only, not a requirement |
| `main_road_distance_km` | kilometers | display-only, not a requirement |

### 16.3 Removed from V1 (archived, not in the registry)

These stay in the parking-lot doc:

- Rent due date flexibility, payment method, security deposit term, utility billing style, notice period, rent hike expectations
- Profession or occupation preference, work-from-home preference, children policy
- Cleaning and sanitation expectations, kitchen usage rules for shared PGs
- Vehicle ownership matching, delivery and guest access restrictions

### 16.4 Decided

- Landlords can select more than one tenant-type option at once (multi attribute).
- Amenities and the core room and layout fields are required at publish, as listed in 16.1.

