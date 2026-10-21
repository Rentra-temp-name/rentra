# System Overview

Status: current V1 decisions follow [`rentra-v1-backend-handoff.md`](../rentra-v1-backend-handoff.md).

## Components

- **Frontend (`apps/web`):** Next.js on Cloudflare Workers with OpenNext; Vercel is a later move.
- **Backend (`apps/api`):** FastAPI in Docker. Its hosting provider is still undecided.
- **Database and auth:** Supabase Postgres and Supabase Auth (Google OAuth).
- **Photo storage:** Supabase Storage; uploads go through the API.
- **Email:** Resend for transactional email.
- **Map:** the browser uses the Maps key; the API reads `google_maps_key` from its environment.

## Database boundary

Application tables are in the `app` schema, which is not exposed through PostgREST. `anon` and `authenticated` have no privileges on that schema. The API connects as `rentra_api`, a login role without `BYPASSRLS` and without ownership of application tables. Each request transaction sets `app.user_id`; RLS enforces ownership and public listing visibility, while owner-scoped API queries also include an owner predicate.

The API uses the Supabase transaction pooler. The service role key is reserved for the Auth admin API and Storage API; it is not used for database queries.

## Request flow

1. Visitors browse public pages and publicly visible listings without signing in.
2. Listing reads go through the FastAPI backend. A listing is public only when active and not suspended; public listing details include its point and contact phone as decided in the handoff.
3. Authenticated writes use the caller's profile identity. Listing mutations are scoped to the owner, and row-level security provides a second boundary.
4. A contact action opens a WhatsApp link; Rentra does not provide in-app chat.

Clearing WhatsApp through the profile API requires confirmation. The API archives the owner's active, non-suspended listings before clearing it; an active suspended listing blocks the operation. Restoring a listing that was active, and reactivating, require WhatsApp.

Matching and ranking belong in the backend domain/SQL layer. Secrets are provided through environment variables and are never logged or committed.
