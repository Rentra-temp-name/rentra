# System Overview

Status: current V1 decisions follow [`rentra-v1-backend-handoff.md`](../rentra-v1-backend-handoff.md).

## Components

- **Frontend (`apps/web`):** Next.js on Cloudflare Workers with OpenNext; Vercel is a later move.
- **Backend (`apps/api`):** FastAPI in Docker. Its hosting provider is still undecided.
- **Database and auth:** Supabase Postgres and Supabase Auth (Google OAuth).
- **Photo storage:** Supabase Storage; uploads go through the API. Public detail and owner detail return the same position-ordered photo array (`id`, `position`, `width`, `height`, `original_url`, `thumb_url`). The API re-encodes originals and creates fixed 400×300 fit-and-pad thumbnails.
- **Tenant home cards:** `MainCard` is shared by For You, New Listings, and Your Saved Listings. It reads title, rent, point, creation date, numeric listing values, and photos from API listing responses; bedroom, bathroom, and size values are hydrated from `numeric`. Size is square feet. The 4:3 card photo area matches the API thumbnail, so the complete fit-and-pad photo is displayed at the card's intended ratio.
- **Featured home card:** `FeaturedCard` renders one selected listing's title, point-derived location, bedroom/bathroom counts, rent, and first image with the existing dark overlay. It receives an API-loaded listing from `TenantHome` and does not issue its own request. The featured selection source is still undecided; no `is_featured` database field or endpoint exists.
- **Listing detail:** `/rent/[listing-slug]` ports the supplied Figma screen inside the existing `AppShell`; the handoff sidebar is omitted, so Rentra's persistent sidebar remains. It loads `GET /listings/{id}` from the trailing UUID in the card link. Title, rent, numeric bedrooms/bathrooms/size, first ordered photo, creation age, landlord display name, and contact actions are API-bound. The endpoint also returns `answers` grouped by attribute key and ordered option labels, but the Amenities and Requirements tiles still show the handoff's sample content; the map artwork and nearby examples are placeholders. There is no listing description or named address field in the current schema; user-specific match badges need a detail match API.
- **Email:** Resend for transactional email.
- **Map:** the browser uses the Maps key; the API reads `google_maps_key` from its environment.

## Database boundary

Application tables are in the `app` schema, which is not exposed through PostgREST. `anon` and `authenticated` have no privileges on that schema. The API connects as `rentra_api`, a login role without `BYPASSRLS` and without ownership of application tables. Each request transaction sets `app.user_id`; RLS enforces ownership and public listing visibility, while owner-scoped API queries also include an owner predicate.

The API uses the Supabase transaction pooler. The service role key is reserved for the Auth admin API and Storage API; it is not used for database queries.

## Request flow

1. Visitors browse public pages and publicly visible listings without signing in.
2. Listing reads go through the FastAPI backend. A listing is public only when active and not suspended; public listing details include its point, contact phone, ordered photos, numeric values, and selected answer labels as decided in the handoff.
3. Authenticated writes use the caller's profile identity. Owner listing routes create drafts, apply versioned edits, and call the database lifecycle functions; PATCH answer/numeric maps replace their full sets, answer keys are option labels, and point input uses `lat`/`lng`. Owners can upload, delete, and reorder up to 10 photos; photo writes are locked for suspended and archived listings. Owner predicates and row-level security provide defense in depth.
4. Users can save listings, connect to another user's public listing, and read their own connections and notifications. Connecting does not require a tenant WhatsApp number; a saved number is shared with that listing's owner. Connection-scoped profile reads expose current contact details only under the handoff's connection rules.
5. Users can report another user's listing. Admins can suspend or unsuspend listings and resolve reports; actions are audited. Saved-listing notifications are generated when rent changes or public visibility flips.
6. A contact action opens a WhatsApp link; Rentra does not provide in-app chat (future feature).

Listing lifecycle states are draft, active, rented, sold_out, unavailable, and archived. Only active, unsuspended listings are public. Owners can publish, change status, archive, restore before purge, or force-delete an archived listing; jobs archive eligible inactive listings and purge archived listings after 30 days. Suspended listings are locked from owner lifecycle changes and skipped by jobs.

Clearing WhatsApp through the profile API requires confirmation. In the same transaction, the API archives the owner's active, non-suspended listings before clearing it; an active suspended listing blocks the operation. A database trigger blocks direct clears while any listing remains active. Restoring a listing that was active, and reactivating, require WhatsApp. `PUT /me` with a cleared WhatsApp first returns `WHATSAPP_CLEAR_ARCHIVES_LISTINGS` with the active non-suspended listing count; the client must then send `{confirm:true}` to archive those listings and clear the number.

Matching and ranking belong in the backend domain/SQL layer. See handoff section 5 for scoring, caps, misses, and the explore feed. Secrets are provided through environment variables and are never logged or committed.
