# Auth and Access

Status: current V1 access rules follow [`rentra-v1-backend-handoff.md`](../rentra-v1-backend-handoff.md).

## Authentication

- Supabase Auth with Google OAuth.
- Browsing public listings does not require a login.
- The API verifies JWT signatures against the project's JWKS and checks issuer, authenticated audience, and expiry.

## Principals and modes

- **Visitor:** not signed in; can browse public listings, view listing details, and use the map.
- **User:** signed in; can manage their profile, requirements, saved listings, connections, and notifications, and can create and manage listings they own.
- **Admin:** a user listed in `app.admins`; can perform user actions plus the handoff's audited admin actions.

Tenant and landlord are switchable user modes, not stored roles. Switching modes does not delete either side's data. There is no user-suspension role or flag in V1.

## Access rules

| Action | Visitor | User | Admin |
|---|---|---|---|
| Browse and view public-visible listings | Yes | Yes | Yes |
| View own listings at any status | No | Yes | Yes |
| Read or write another user's private listing | No | No | Admin actions only |
| Read public profile contacts | Only for an owner with an active, unsuspended listing | Same rule | Same rule |
| Save, connect, report, or manage own requirements | No | Yes | Yes |
| Create or manage own listings | No | Yes | Yes |
| Suspend listings or resolve reports | No | No | Yes, audited |
| Legal-order data access | No | No | Yes, with an order reference and audit entry |

`app.get_public_profile(p_id)` returns the profile contact fields only when that profile owns at least one listing where `status = 'active' AND suspended_at IS NULL`. Listing phone and point visibility follow the handoff's public-by-product decision.

Owner listing endpoints require authentication and scope every listing lookup and write to the caller. Draft creation is capped at 20 per owner; PATCH requires the current version and validates answer and numeric keys against the active registry. Lifecycle endpoints call the database functions rather than directly updating protected listing fields.

Clearing WhatsApp requires explicit confirmation and archives the owner's active, non-suspended listings in the same transaction. The database profile trigger rejects direct clears while any active listing exists, including suspended listings. Restoring a listing that was active, and reactivating, without a WhatsApp number is rejected with `WHATSAPP_REQUIRED`.

## Database enforcement

- All application tables are in private schema `app`; it is not exposed through PostgREST.
- Row Level Security is enabled for each table. `anon` and `authenticated` have no `app` schema privileges.
- The API connects as `rentra_api`, which has per-table grants, does not own app tables, and cannot bypass RLS.
- Per request transaction, the API sets `app.user_id`. Owner-scoped SQL also includes the owner in its `WHERE` filter.
- The Supabase service role key is not used for database queries. Secrets stay in environment variables and are never logged or committed.
