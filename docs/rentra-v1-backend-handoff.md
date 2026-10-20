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
- Core listing fields (rent, bedrooms, etc.) come from the original spec, which this doc does not repeat. [UNVERIFIED] Reconcile before step 4.

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

- `profiles(id pk = auth.users.id ON DELETE CASCADE, display_name, whatsapp, deletion_requested_at, created_at)`. Created by upsert on first authenticated request. `whatsapp` is E.164 (+977), validated and stored normalized. Shown publicly on active listings. [PRODUCT]
- Onboarding captures two locations for the tenant: current location and search location. Search location is the primary location for matching. If both are the same, that is fine. Store only a coarse area for each, never precise coordinates. The search area is stored as a point with a radius (default 5 km, tenant can adjust). The point is rounded to a coarse grid before storage, never the exact location. A listing's point must fall inside the search circle. [PRODUCT]
- Registry: `attributes(id, key, type yes_no|single|multi, is_active, required_at_publish)`, `attribute_options(id, attribute_id, label, is_exclusive, is_active)`. FKs `ON DELETE RESTRICT`. Never delete, only `is_active=false`. Options are a fixed list that only the owner adds to. Landlords cannot create options. Seed in section 16.
- `listings(id, owner_id FK profiles CASCADE, title, rent_amount, area_id, district_id, point geography(Point,4326), status, archived_from_status, archived_at, status_changed_at, suspended_at, suspended_by, suspended_reason, version int, created_at, updated_at)`. CHECK: point inside Nepal bounding box, no NaN. The bounding box also includes parts of India and Tibet, accepted for V1. Exact pin is public for every listing. [PRODUCT]
- `listing_answers(listing_id, attribute_id, option_id)`, PK is all three. Yes/no attributes store the answer as an option row (Yes / No).
- `listing_numeric(listing_id, field, value)`, for the numeric fields in section 16.
- `listing_photos(id, listing_id, storage_path, position smallint CHECK 1..10, UNIQUE(listing_id, position))`. Photo cap of 10 comes from this constraint, not app code.
- Requirements: `requirements(user_id, attribute_id, option_id, importance must|nice)`, plus numeric requirements `requirement_numeric(user_id, field, value, importance)` for rent max, bedrooms min, max people, and any numeric field in section 16. Each carries its own importance. Pick-one attributes: denormalize `pick_rule` onto the row with a composite FK to the registry, and `UNIQUE (user_id, attribute_id) WHERE importance='must' AND pick_rule='single'`.
- `connections(id, user_id FK CASCADE, listing_id FK CASCADE, created_at, UNIQUE(user_id, listing_id))`. Indexes `(user_id, created_at)` and `(listing_id, created_at)`.
- `notifications(id, user_id FK CASCADE, kind, listing_id, other_user_id, created_at, read_at)`. Typed columns, no jsonb. Powers the in-app notifications sidebar.
- `saved_listings(user_id, listing_id, created_at)`, PK both.
- `reports(id, reporter_id SET NULL, listing_id SET NULL, snapshot_title, snapshot_whatsapp, reason, status open|resolved, resolved_by, resolved_at, created_at)`, `UNIQUE(reporter_id, listing_id)`. Snapshot is copied at submit so evidence survives deletion. Listings only, no profile reports.
- `admins`, `admin_actions`, `legal_access_log`, `job_runs(job, started_at, finished_at, rows, error)`, `storage_deletions(id, bucket, path, attempts, created_at, done_at)`.
- Required indexes: partial on listings `(district_id, rent_amount) WHERE status='active' AND suspended_at IS NULL` and the same for `area_id`; partial GiST on `point` with the same filter; `listing_answers(attribute_id, option_id, listing_id)`; `listings(owner_id, status)`; `listings(status, status_changed_at)`; `listings(archived_at) WHERE status='archived'`.

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
- A DB trigger enforces every row above and rejects all other transitions. The API sets `app.actor` (`owner`, `system`, `admin`) per transaction and the trigger checks it. Each change sets `status_changed_at` and bumps `version`.
- Archive job: one set-based UPDATE, `WHERE status IN (...) AND status_changed_at < now() - interval '30 days' AND suspended_at IS NULL`. This closes the race with a landlord reactivating at day 30.
- Edits: `PATCH` carries `version`. Mismatch returns 409. A trigger bumps `listings.version` on any child write (answers, numeric fields, photos).

## 5. Matching

- Each requirement is marked must or nice by the tenant, including numeric ones. Applies uniformly to every attribute. Attributes the tenant doesn't set are ignored. [PRODUCT]
- A must is a hard gate. Any missed must puts the listing in Conflicts, with each miss named.
- Multi-choice must: the listing must have every picked option. Yes/no attributes (pets allowed) are plain yes or no. [PRODUCT]
- Tenant-type options (bachelors, family, all allowed) are a multi attribute on the landlord side. "All allowed" is exclusive, so it satisfies any tenant pick on that attribute. [PRODUCT]
- Tiers:
  - **Perfect match:** all musts met and all nices met.
  - **Strong match:** all musts met, some nices missed. Ranked by percentage of nices met.
  - **Conflict:** one or more musts missed, each miss named. Ranked by fewest misses, then percentage of nices met.
- Missing answer on a must counts as a miss. Optional question with no answer counts as 0 for a nice.
- Ordering: Perfect matches rank by rent asc, then created_at desc, then id. Strong matches rank by nice percentage desc, rent asc, created_at desc, id. Conflicts rank by misses asc, nice percentage desc, rent asc, created_at desc, id.
- Eligible: public-visible listings, not the caller's own, inside the tenant's search area.
- One SQL query, never scored in Python. Strong matches capped at 200, conflicts at 100. Perfect matches are not capped. No pagination.
- Response: `{perfect: [...], strong: [...], conflicts: [{listing, misses: [...]}]}`. Perfect matches show first as tiles, with the "N perfect matches found" message, then strong matches, then conflicts.
- Users with no requirements get the explore feed: eligible listings in their area, keyset paginated, stable daily shuffle `ORDER BY md5(id::text || current_date::text), id`. Nudge CTAs to set preferences.

## 6. Endpoints

Errors are JSON `{code, message}` with stable codes. Generic message outside, detail in logs.

| Route | Auth | Notes |
| --- | --- | --- |
| `GET /health`, `GET /health/ready` | none | ready runs `SELECT 1` as `rentra_api` |
| `GET /profiles/{profile_id}` | none | public profile response contains only `display_name` and `whatsapp`; query runs as `rentra_api` with the target profile scoped through RLS |
| `GET /areas`, `GET /registry` | none |  |
| `GET /listings` | none | keyset, page max 50, includes phone and point, same as detail |
| `GET /listings/{id}` | none | full detail, includes phone and point |
| `GET /map?bbox=&zoom=` | none | bbox and zoom required. Returns server-side clusters at low zoom and individual points at high zoom. Each cluster returns count and centroid. Individual points return id, lat, lng, rent only. Response is capped. [ENG] |
| `GET/PUT /me`, `DELETE /me` | user | delete needs `{confirm:true}` |
| `PUT /me/requirements`, `GET /matches` | user |  |
| `POST/DELETE /listings/{id}/save`, `GET /me/saved` | user |  |
| `POST /listings/{id}/connect`, `GET /me/connections` | user | see section 7 |
| `GET /me/notifications`, `POST /me/notifications/{id}/read` | user | feeds the sidebar |
| `POST /listings` (draft), `GET /me/listings`, `GET /me/listings/{id}` | user | max 20 drafts per user [ENG] |
| `PATCH /listings/{id}`, `POST /listings/{id}/publish`, `POST /listings/{id}/status`, `POST /listings/{id}/archive`, `POST /listings/{id}/restore`, `DELETE /listings/{id}` | owner | `DELETE` is force delete, allowed only on archived listings |
| `POST/DELETE /listings/{id}/photos`, reorder | owner | server-side upload only, see section 9 |
| `POST /listings/{id}/report` | user | not own listing |
| `GET /admin/reports`, `POST /admin/reports/{id}/resolve`, `POST /admin/listings/{id}/suspend`, `POST /admin/listings/{id}/unsuspend` | admin | audited |

Frontend URLs use `/rent/{slug}-{id}`. The API resolves by the trailing id. No slug column. [ENG]

## 7. Connect and notifications

- Allowed for a signed-in user on a public-visible listing they do not own. [PRODUCT]
- One transaction: insert into `connections` with `ON CONFLICT DO NOTHING`. If a row was inserted, insert two notifications in the same transaction: one to the connector (property connected) and one to the owner (profile connected). Both sides see the connection. [PRODUCT]
- Repeat calls return the same result and create no new notification.
- Cap: 50 new connections per rolling 24 hours per user, counted from `connections.created_at`. Over the cap returns 429 `CONNECT_LIMIT`. The cap is soft under concurrency, accepted.
- Returns the WhatsApp link, built server-side as `https://wa.me/<digits>`.
- Notifications are an in-app sidebar only. No push. Tenants are notified when a listing they saved changes. Transactional email goes through Resend. [PRODUCT]

## 8. Jobs, outbox, deletion

- pg\_cron runs the pure SQL jobs: archive, purge, abandoned drafts. [ENG]
- Every job: `pg_try_advisory_xact_lock`, a `job_runs` row, one set-based statement, safe to run twice.
- Purge runs in one transaction: insert the listing's photo paths into `storage_deletions`, then delete the listing. Children cascade.
- A worker process (same image, separate command) drains `storage_deletions` with `FOR UPDATE SKIP LOCKED`, retries with backoff, and treats "already gone" as success. It also runs the account deletion sweep.
- Account deletion is immediate on confirm. [PRODUCT] `DELETE /me`: set `deletion_requested_at`, purge owned listings (photos via outbox), delete the auth user through the Auth admin API (cascades the profile). The sweep retries anything stuck with `deletion_requested_at` set. Every authenticated request already loads the profile, and it rejects requests when `deletion_requested_at` is set, because an old JWT stays valid until it expires.
- Reports keep a snapshot, so a user deleting their account does not erase the evidence.

## 9. Security rules

- Phone and point are public by product decision. [PRODUCT] The phone appears wherever a listing appears: list, detail, and matches. Phone numbers must never appear in logs, error bodies, or stack traces, since that is about leaking data through the server, not about visibility.
- Mass assignment: `PATCH` uses an explicit field allowlist. Never writable by the client: `owner_id`, `status`, `suspended_*`, `version` (it is only compared), `created_at`.
- Validation at the boundary with strict Pydantic models. Reject NaN and out-of-range coordinates, oversize or malformed bodies, and unknown fields.
- Photo upload goes through the API only. Max 5 MB, jpeg/png/webp, magic-byte check, re-encode with Pillow to strip EXIF, uuid object names, bucket write only through the service key held by the API. [ENG]
- CORS: allowlist of the frontend origin only. No `*`.
- No stack traces in responses. No user-supplied URLs are ever fetched.
- Secrets only in env, including `google_maps_key`. `.env.example` lists names only. Never logged, never committed.
- Accepted risks: public phones and pins can be scraped (rate limits only slow it). A banned user can make a new account (no user suspension in V1).

## 10. Rate limits

- Anonymous reads: 60 per minute per IP. Signed-in reads: 120 per minute per user. Page size max 50. Connect: 50 per rolling 24 hours per user. [PRODUCT: the numbers were proposed and accepted, change them in config.]
- Writes [ENG]: uploads, draft creation, and reports get their own limits (20 per minute per user, reports 10 per day). Drafts capped at 20 per user.
- V1 runs one container with one worker, so an in-process limiter is correct. With N workers each keeps its own counter and the effective limit is N times higher. Move to Redis only when running more than one worker or container.
- Never use Postgres counters for read limits (a DB write per anonymous read is a self-inflicted DoS). Only the connect cap uses the DB.
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

1. `rentra_api` role, schema `app`, default privileges, RLS baseline, test harness on local Supabase.
2. `profiles`, JWT verification, auth middleware, the deletion-requested check.
3. Tenant current and search locations, registry from section 16 (search area format is open, see section 15). Add a regression test proving `anon` and `authenticated` cannot execute `app.get_public_profile(uuid)`.
4. Listings, lifecycle triggers, photos, version handling, numeric fields. Tighten `app.get_public_profile(p_id)` to return contact details only when that profile owns a publicly visible listing (`status = 'active' AND suspended_at IS NULL`), and test that profiles without one are excluded.
5. Public reads, map with clustering, rate limits.
6. Requirements and matching (perfect, strong, conflicts tiers).
7. Connect, notifications sidebar.
8. Saved, reports, admin suspend, audit tables.
9. Jobs, outbox worker, account deletion.
10. Observability, then a staging load test at 50k tenants and 20k listings with `EXPLAIN` checks. Targets: matches p95 300 ms, map p95 200 ms. [UNVERIFIED targets until measured]

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
- `test_suspended_listing_hidden_from_public`
- `test_suspended_listing_locked_for_owner`
- `test_jobs_skip_suspended_listings`
- `test_admin_actions_audited`
- `test_admin_route_checks_admins_table`
- `test_logs_contain_no_phone_coords_ip`
- `test_read_limit_per_ip_and_per_user`
- `test_role_switch_keeps_both_sides_data`
- `test_landlord_cannot_create_registry_option`

**Matching**

- `test_missed_must_goes_to_conflicts_and_is_named`
- `test_all_musts_met_all_nices_met_is_perfect`
- `test_all_musts_met_some_nices_missed_is_strong`
- `test_strong_ranked_by_nice_percentage`
- `test_zero_nices_is_strong_not_perfect`
- `test_multichoice_must_requires_all_picked`
- `test_all_allowed_satisfies_any_tenant_type_pick`
- `test_numeric_requirement_must_vs_nice`
- `test_missing_answer_on_must_is_miss`
- `test_pick_one_second_must_rejected_by_db`
- `test_own_listing_excluded`
- `test_area_and_district_match`
- `test_tiebreak_order_all_tiers`
- `test_strong_and_conflicts_capped_200_100_perfect_uncapped`
- `test_no_requirements_gets_explore_feed`
- `test_tenant_household_type_not_stored`

**Lifecycle**

- `test_every_illegal_transition_rejected_by_trigger`
- `test_publish_requires_fields_answers_amenities_and_phone`
- `test_archive_job_vs_owner_reactivate_race`
- `test_restore_before_purge_allowed`
- `test_purge_after_30_days_and_restore_after_purge_fails`
- `test_force_delete_archived_is_immediate`
- `test_force_delete_rejected_on_non_archived`
- `test_abandoned_draft_purged`
- `test_photo_cap_race_two_uploads`
- `test_version_conflict_409_and_child_write_bumps_version`

**Idempotency and jobs**

- `test_connect_twice_one_row_one_notification`
- `test_connect_creates_both_notifications_atomically`
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

- No district or city seed. The map handles location browsing. Search area is a point with a radius, as decided. The parking-lot doc is also not written.
- Core listing fields live in the original spec and were not part of this review. Reconcile them with section 3 before step 4.
- Cloudflare in front of the API, a privacy policy, and a consent line at publish ("your number and pin are public") are pre-launch items.
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

These are stored in `listing_numeric` for listings and `requirement_numeric` for tenants. Each tenant numeric requirement carries must or nice.

| field | unit | notes |
| --- | --- | --- |
| `rent_amount` | NPR per month | listing rent. Tenant side is a max rent |
| `bedrooms` | count | tenant side is a min |
| `bathrooms_total` | count | |
| `western_commodes` | count | |
| `indian_squat_toilets` | count | |
| `kitchen_count` | count | |
| `balconies` | count | |
| `total_floors` | count | total floors in the building |
| `size_value` | number | paired with `size_unit` |
| `size_unit` | aana, ropani, sq_ft | stored as a listing field, converted in code for display only |
| `max_people` | count | strict occupancy limit. Tenant side is the group size |
| `road_access_width_ft` | feet | |
| `main_road_distance_km` | kilometers | distance to the main bus stop or micro stand |

### 16.3 Removed from V1 (archived, not in the registry)

These stay in the parking-lot doc:

- Rent due date flexibility, payment method, security deposit term, utility billing style, notice period, rent hike expectations
- Profession or occupation preference, work-from-home preference, children policy
- Cleaning and sanitation expectations, kitchen usage rules for shared PGs
- Vehicle ownership matching, delivery and guest access restrictions

### 16.4 Decided

- Landlords can select more than one tenant-type option at once (multi attribute).
- Amenities and the core room and layout fields are required at publish, as listed in 16.1.
