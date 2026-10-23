# Data Model

Status: current V1 database scope follows [`rentra-v1-backend-handoff.md`](../rentra-v1-backend-handoff.md), which is authoritative over earlier drafts.

All application tables live in the private `app` schema. PostgREST does not expose it. Row Level Security (RLS) is enabled for each table, and `rentra_api` receives explicit table grants. The API sets `app.user_id` inside each request transaction and includes the owner in owner-scoped queries.

## Profiles and locations

### `app.profiles`

- `id` — primary key and foreign key to `auth.users(id)`, `ON DELETE CASCADE`
- `display_name`, `whatsapp`, `deletion_requested_at`, `created_at`
- WhatsApp is stored in normalized Nepal E.164 form.
- Clearing WhatsApp through `PUT /me` requires confirmation and archives the owner's active, non-suspended listings. A suspended active listing prevents clearing; a profile trigger also blocks direct clearing while any active listing exists. Restoring a listing that was active, and reactivating, require WhatsApp.

Public profile contacts are returned only if the profile owns a listing with `status = 'active'` and `suspended_at IS NULL`.
`app.get_connected_profile(p_other_id)` also exposes a profile through an existing connection: a listing owner can read the connector's profile regardless of listing status; a connector can read the owner only while that owner has a publicly visible connected listing. WhatsApp is read live and is null when not saved.

### `app.tenant_locations`

Stores current and search points as coarse `geography(Point, 4326)` values and a search radius. Both points are checked against the Nepal bounds and coarse grid. Matching uses the search point and radius.

## Registry

- `app.attributes`: `id`, `key`, `type`, `pick_rule`, `is_active`, `required_at_publish`
- `app.attribute_options`: `id`, `attribute_id`, `label`, `sort_order`, `is_exclusive`, `is_active`
- `app.numeric_fields`: `key`, `unit`, `is_active`

Registry values are owner-managed and are not writable by landlords or `rentra_api`.
`western_commodes` and `indian_squat_toilets` are retired inactive numeric fields; their listing and requirement references were removed.

## Listings

### `app.listings`

- `id` — UUID primary key
- `owner_id` — profile foreign key, `ON DELETE CASCADE`
- `title`
- `rent_amount` — `numeric(12,2)`, strictly positive; rent is stored here, not in `listing_numeric`
- `point` — `geography(Point, 4326)`, checked for NaN and within the Nepal bounding box
- `status` — `draft`, `active`, `rented`, `sold_out`, `unavailable`, or `archived`
- `archived_from_status`, `archived_at`, `status_changed_at`
- `suspended_at`, `suspended_by`, `suspended_reason`
- `version`, `created_at`, `updated_at`

There is no description field. Location matching uses the listing point and the tenant search point/radius. A listing is public only while active and not suspended. Owners can read their own listings at every status and can write only their own through the versioned owner listing routes; submitted answer and numeric maps replace the full sets, and answer option keys are registry option labels. Point input uses `lat`/`lng`.
`size_value` is stored in square feet only; `app.listings` has no `size_unit` column.

### Listing children

- `app.listing_answers(listing_id, attribute_id, option_id)` — composite primary key; listing deletion cascades, registry references are restricted.
- `app.listing_numeric(listing_id, field, value)` — composite primary key; `field` references `app.numeric_fields(key)`. `rent_amount` is excluded because it belongs on the listing.
- `app.listing_photos(id, listing_id, storage_path, thumb_path, width, height, position)` — `thumb_path` is NOT NULL; width and height are NOT NULL and positive; position is NOT NULL and constrained to 1–10 by `listing_photos_position_check`; `listing_photos_listing_position_key` is unique per listing and DEFERRABLE INITIALLY DEFERRED. Listing deletion cascades.

Publicly visible listings' answers, numeric values, and photo metadata are readable. Otherwise, children are owner-readable and writable. Child insert, update, and delete operations increment the parent listing's `version`.

## Listing indexes

- Partial `listings(rent_amount)` index where status is active and `suspended_at IS NULL`
- Partial GiST index on `point` where status is active and `suspended_at IS NULL`
- `listing_answers(attribute_id, option_id, listing_id)`
- `listings(owner_id, status)`
- `listings(status, status_changed_at)`
- Partial `listings(archived_at)` where status is archived
- Child-side indexes for foreign keys

Location matching uses the listing point and the tenant search point/radius. Real GiST usage is proven by the step 10 load test at 20k listings.

## Other application tables

- `app.requirements` stores one row per selected attribute option with `importance` (`must` or `nice`) and the attribute's `pick_rule`; multi-choice selections are separate rows. `app.requirement_numeric` stores one value and importance per user and numeric field. The API replaces both sets together and accepts active registry fields only.
- `app.connections(user_id, listing_id)` is unique per user/listing. `app.notifications` stores typed sidebar events with nullable listing and other-user references; read-time joins produce the display fields, and deleted references render as null.
- `app.saved_listings(user_id, listing_id)` has a composite primary key.
- `app.reports` stores listing snapshots and an open/resolved state; reporter and listing deletion do not erase the snapshot.
- `app.admins`, `app.admin_actions`, and `app.legal_access_log` support admin authorization and auditing. `app.job_runs` and `app.storage_deletions` support jobs and storage cleanup.

## Requirements and matching

Each selected option is scored as a separate check, including each multi-choice must; an exclusive listing answer satisfies every pick for that attribute. Numeric matching uses rent as the tenant's maximum and bedrooms, bathrooms, `size_value` (sq ft), and `max_people` as tenant minimums. Must rows determine the score when present; otherwise nice rows do. Every must met is perfect. With no musts, a ranked item's misses name missed nice rows; when musts exist, misses name missed must rows only. With no requirements, matching returns the daily shuffled explore feed.
