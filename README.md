# Rentra

Rentra is a rental marketplace for Nepal connecting tenants with landlords and property owners.

## Repository layout

- `apps/web` — Next.js web application
- `apps/api` — FastAPI backend
- `supabase` — database and local Supabase configuration (to be added after schema decisions)
- `packages` — shared packages (to be added as needed)
- `docs` — product, design, architecture, and security documentation

## Local development

Requirements: Node.js 22+, npm 10+, Python 3.12+.

Start the web app:

```sh
cd apps/web
npm install
npm run dev
```

Start the API:

```sh
cd apps/api
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e .
fastapi dev
```

The API health endpoint is available at `/health`. Service integrations remain unconfigured until their credentials and database decisions are supplied.

## Project decisions and open questions

See [`docs`](docs/) for the current MVP scope, user flows, and technical decisions. Values marked TBD remain undecided.

For the real Supabase and tenant/landlord matching handoff checklist, see [`docs/things-to-do-after-setting-everything-up.md`](docs/things-to-do-after-setting-everything-up.md).
