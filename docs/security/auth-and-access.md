# Auth and Access

Status: current V1 access rules follow [`rentra-v1-backend-handoff.md`](../rentra-v1-backend-handoff.md).

## Authentication

- Supabase Auth with Google OAuth.
- Browsing public listings does not require a login.
- The API verifies JWT signatures against the project's JWKS and checks issuer, authenticated audience, and expiry.

## Principals and modes

- **Visitor:** not signed in; can browse public listings, view listing details, and use the map.
- **User:** signed in; can manage their profile, requirements, saved listings, connections, and notifications, and can create and manage listings they own. `DELETE /me` returns `409 ACCOUNT_HAS_SUSPENDED_LISTING` while the user owns a suspended listing, and `202 deletion_pending` if the Auth API fails (the worker sweep retries).
- **Admin:** a user listed in `app.admins`; can perform user actions plus the handoff's audited admin actions.

Tenant and landlord are switchable user modes, not stored roles. Switching modes does not delete either side's data. There is no user-suspension role or flag in V1.

## Access rules

| Action | Visitor | User | Admin |
|---|---|---|---|
| Browse and view public-visible listings | Yes | Yes | Yes |
| View own listings at any status | No | Yes | Yes |
| Read or write another user's private listing | No | No | Admin actions only |
| Read public profile contacts | Only for an owner with an active, unsuspended listing | Same rule | Same rule |
| Read a connection-scoped profile | No | Only when the connection and listing-visibility rule allows it | Same rule |
| Save, connect, report, or manage own requirements | No | Yes | Yes |
| Create or manage own listings | No | Yes | Yes |
| Suspend listings or resolve reports | No | No | Yes, audited |
| Legal-order data access | No | No | Yes, with an order reference and audit entry |

`app.get_public_profile(p_id)` returns the profile contact fields only when that profile owns at least one listing where `status = 'active' AND suspended_at IS NULL`. Listing phone and point visibility follow the handoff's public-by-product decision.

`app.get_connected_profile(p_other_id)` returns only `display_name`, `whatsapp`, and `wa_link`. A listing owner may view a connector's profile regardless of listing status. A connector may view a landlord only while that landlord has a connected listing that is public-visible. Otherwise the route returns the same 404 as a missing profile. The connector's WhatsApp number is read live, so clearing it removes it from the response; a tenant number is optional when connecting.

Connecting is allowed only on another user's public-visible listing. It creates the connection and both notifications atomically; repeated connects do not add notifications. Notification reads join user and listing display fields at request time, return null for deleted referenced users/listings, and never include phone numbers. Saved listings are private to the saver; changes to rent or public visibility notify savers other than the owner. Reports are only for another user's public-visible listing and preserve a listing title/WhatsApp snapshot. Admin report resolution accepts an optional note, which supplies the audit reason.

Owner listing endpoints require authentication and scope every listing lookup and write to the caller. Draft creation is capped at 20 per owner; PATCH requires the current version and validates answer and numeric keys against the active registry. Supplying answers or numeric replaces that full set; option keys are registry labels and point input uses `lat`/`lng`. Lifecycle endpoints call the database functions rather than directly updating protected listing fields.

Photo reads are available in public-visible listing detail and the owner's detail view; the two photo arrays are identical and position-ordered. Upload, delete, and reorder require the listing owner, and photo writes are locked for suspended or archived listings.

Admin routes check `app.admins` on each request. Admins can suspend/unsuspend listings and resolve reports; each action is recorded in `app.admin_actions`. Non-admins receive the same 404 response as an unknown route. Legal-order data access requires an order reference and a `legal_access_log` entry.

Clearing WhatsApp requires explicit confirmation and archives the owner's active, non-suspended listings in the same transaction. An active suspended listing blocks the clear; a database profile trigger rejects direct clears while any active listing exists, including suspended listings. Restore of a previously active listing and reactivation without WhatsApp return `WHATSAPP_REQUIRED`. Suspended listings cannot be changed, archived, restored, or deleted by their owner; jobs skip them. Archived listings can be restored or force-deleted before the 30-day purge. `PUT /me` with a cleared WhatsApp first returns `WHATSAPP_CLEAR_ARCHIVES_LISTINGS` with the active non-suspended listing count; the client must then send `{confirm:true}` to archive those listings and clear the number.

## Database enforcement

- All application tables are in private schema `app`; it is not exposed through PostgREST.
- Row Level Security is enabled for each table. `anon` and `authenticated` have no `app` schema privileges.
- The API connects as `rentra_api`, which has per-table grants, does not own app tables, and cannot bypass RLS.
- Per request transaction, the API sets `app.user_id`. Owner-scoped SQL also includes the owner in its `WHERE` filter.
- The Supabase service role key is not used for database queries. Secrets stay in environment variables and are never logged or committed.
