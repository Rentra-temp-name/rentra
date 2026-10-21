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

### `app.tenant_locations`

Stores current and search points as coarse `geography(Point, 4326)` values and a search radius. Both points are checked against the Nepal bounds and coarse grid. Matching uses the search point and radius.

## Registry

- `app.attributes`: `id`, `key`, `type`, `pick_rule`, `is_active`, `required_at_publish`
- `app.attribute_options`: `id`, `attribute_id`, `label`, `sort_order`, `is_exclusive`, `is_active`
- `app.numeric_fields`: `key`, `unit`, `is_active`

Registry values are owner-managed and are not writable by landlords or `rentra_api`.

## Listings

### `app.listings`

- `id` — UUID primary key
- `owner_id` — profile foreign key, `ON DELETE CASCADE`
- `title`
- `rent_amount` — `numeric(12,2)`, strictly positive; rent is stored here, not in `listing_numeric`
- `size_unit` — nullable: `aana`, `ropani`, or `sq_ft`
- `point` — `geography(Point, 4326)`, checked for NaN and within the Nepal bounding box
- `status` — `draft`, `active`, `rented`, `sold_out`, `unavailable`, or `archived`
- `archived_from_status`, `archived_at`, `status_changed_at`
- `suspended_at`, `suspended_by`, `suspended_reason`
- `version`, `created_at`, `updated_at`

There is no description, `area_id`, or `district_id` column. A listing is public only while active and not suspended. Owners can read their own listings at every status and can write only their own.

### Listing children

- `app.listing_answers(listing_id, attribute_id, option_id)` — composite primary key; listing deletion cascades, registry references are restricted.
- `app.listing_numeric(listing_id, field, value)` — composite primary key; `field` references `app.numeric_fields(key)`. `rent_amount` is excluded because it belongs on the listing.
- `app.listing_photos(id, listing_id, storage_path, position)` — position is 1–10 and unique per listing; listing deletion cascades.

Publicly visible listings' answers, numeric values, and photo metadata are readable. Otherwise, children are owner-readable and writable. Child insert, update, and delete operations increment the parent listing's `version`.

## Listing indexes

- Partial `listings(rent_amount)` index where status is active and `suspended_at IS NULL`
- Partial GiST index on `point` where status is active and `suspended_at IS NULL`
- `listing_answers(attribute_id, option_id, listing_id)`
- `listings(owner_id, status)`
- `listings(status, status_changed_at)`
- Partial `listings(archived_at)` where status is archived
- Child-side indexes for foreign keys

There are no `area_id` or `district_id` columns or indexes. Location matching uses the listing point and the tenant search point/radius. Real GiST usage is proven by the step 10 load test at 20k listings.

## Later tables

Requirements, connections, notifications, saved listings, reports, admin audit records, job runs, and storage deletion outbox tables are described in the handoff but are outside the current listings migration step.
