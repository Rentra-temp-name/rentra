# System Overview

Status: draft. Will change as decisions change.

## Components

- **Frontend (apps/web):** Next.js, deployed on Cloudflare Workers with OpenNext. Moves to Vercel later.
- **Backend (apps/api):** FastAPI, packaged as a Docker container. Host not chosen yet (Render or Railway).
- **Database, auth, storage:** Supabase (Postgres, Google sign-in, file storage for listing photos).
- **Contact:** WhatsApp links to the landlord. No in-app chat.
- **Email:** Resend.
- **Version control:** GitHub.
- **Domain:** Namecheap (name not final).

## How a request flows

1. The visitor loads a page from the Next.js app.
2. Pages that show listings read them from the FastAPI backend.
3. Logged-in actions (save, preferences, create or edit listing) go through the backend, which checks the user's role.
4. The backend reads and writes Supabase. Row Level Security is enforced on every table.
5. Tapping the WhatsApp button opens a WhatsApp link. No data goes through Rentra.

## Principles

- Browsing is open. Login is needed only for actions that change data or depend on a user.
- Business logic (matching and scoring) lives in the backend's domain layer, not in the frontend.
- Everything is configured through environment variables, so changing hosts is a deploy setting.
