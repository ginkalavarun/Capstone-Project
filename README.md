# CampusBite

A campus food-delivery platform (student capstone project). Customers browse
restaurants and order dishes; restaurant owners accept, prepare, and assign
deliveries; delivery partners complete them; customers then review, request
refunds, and (optionally) ask AI questions about their own order history.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend (`frontend/`) | React (JavaScript, ES6+) + React Hooks + React Router DOM, built with Vite. State via contexts (auth, cart). |
| Backend (`backend/`) | FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic migrations. PyJWT (HS256) + bcrypt. `openai` SDK for the insights feature. |
| Database | SQLite (file on a persistent Docker volume) with per-connection foreign-key enforcement. All money is integer cents (EUR). |
| Packaging | Docker + Docker Compose (one backend service, **one worker**). |
| Tests | `pytest` (backend, 183 tests), Vitest + Testing Library (frontend, 101 tests). |

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env and replace the placeholder JWT_SECRET with a real one:
python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build
```

- Backend: <http://localhost:8000> (interactive API docs at `/api/v1/docs`).
- Alembic migrations run automatically before the app serves traffic (D11).
- The database file lives at `/data/campusbite.db` inside the named volume
  `campusbite-data` — it survives container recreation.

**Non-destructive shutdown:** `docker compose down` (keeps the volume).
**Never** use `docker compose down -v` while you care about the data —
`-v` deletes the database volume.

> The compose path is fully verified (2026-11-09): `docker compose up
> --build` boots healthy, migrations apply, the database is created
> appuser-owned at `/data/campusbite.db`, and data survives
> `docker compose up --force-recreate` (volume kept, no `-v`). The two
> scaffold Docker tests (container boot, volume persistence) pass in an
> isolated checkout and skip automatically when no docker CLI is present.
> On a machine where Docker IS installed, note that those tests reuse the
> local compose project (same volume) and run `app.seed` — if your dev
> database has real data you may prefer to run them from a throwaway copy.

## Creating accounts

Customers self-register in the app. **Owners, their restaurants, and
delivery partners are provisioned with a local CLI** — there is deliberately
no public privileged registration (D2).

**If you run the Docker compose stack**, provision *inside the container* so
the accounts land in the same database the app uses (`$DATABASE_URL` inside
the container, i.e. `/data/campusbite.db`):

```bash
docker compose exec -T backend python -m app.provision owner \
  --email sam@example.org --name "Sam Kapoor" \
  --restaurant "Slice House" --address "10 Green Line, Block A" \
  --fee-cents 200
docker compose exec -T backend python -m app.provision partner \
  --email dana@example.org --name "Dana Kim"
```

For **local (non-Docker) development** use the same CLI from the venv:

```bash
cd backend
source .venv/bin/activate   # see "Local development" below

# Restaurant owner + their restaurant (one transaction, D24):
python -m app.provision owner \
  --email sam@example.org --name "Sam Kapoor" \
  --restaurant "Slice House" --address "10 Green Line, Block A" \
  --fee-cents 200
# (without --password you are prompted, or a local one is generated and shown once)

# Delivery partner:
python -m app.provision partner --email dana@example.org --name "Dana Kim"
```

The CLI prints a generated password **once** — store it in a git-ignored
local file; it is never committed, logged, or echoed by the app.

## Local development (no Docker)

Backend (Python 3.12):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set a real JWT_SECRET (app refuses placeholders)
python -m app.seed            # optional: sample users/restaurants/menus/orders
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Migrations apply automatically on startup. Seed accounts use
documented example.org placeholder credentials (`app/seed.py`) — fine for
local browsing, never a grader path.

Frontend:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

The frontend calls `http://localhost:8000/api/v1` by default
(`VITE_API_BASE_URL` can override it — a non-secret; `http://localhost:5173`
is in the backend CORS allowlist, keep them in sync).

## Running the tests

```bash
cd backend  && .venv/bin/python -m pytest   # 183 tests; the 3 Docker tests skip without a docker CLI
cd frontend && npx vitest run               # 101 passed
cd frontend && npm run build                # production build
```

## OpenAI order insights (optional feature)

Set `OPENAI_API_KEY=...` in `.env` — **backend only, never in the frontend**
(D9). Without a key the whole app works; the Insights page shows a clear
"not configured" notice plus the exact figures the app computes. Provider
failures map to clean 429/502/504 responses; per-user rate limiting is
in-memory (resets on restart — single-worker deployment, documented).
Tunable via `OPENAI_MODEL`, `AI_RATE_LIMIT`, `AI_RATE_WINDOW_MINUTES`,
`AI_MAX_QUESTION_CHARS`, `AI_HISTORY_WINDOW` (see `.env.example`).

Automated tests run against a **mocked** client only. A real paid
OpenAI call was **not** made during development — live verification is a
user action.

## Documentation

- `docs/api-contract.md` — every endpoint: shapes, roles, ownership rules, status codes.
- `AGENTS.md` — development rules for AI assistants working on this repo.
- `docs/` — requirements, decisions, assumptions, database design, authorization
  matrix, test plan, architecture, milestone plan, progress.

## Known limitations (deliberate, documented)

- **SQLite + one worker** (D1): the in-memory AI rate limiter resets on
  restart and the reminder scanner is a single managed task. Migrating to
  PostgreSQL is real work (driver, migrations, verification) — not a
  one-line `DATABASE_URL` change.
- **JWT in localStorage** is required by the assignment brief; it is
  convenient but exposed to XSS, and is documented as a trade-off, not a
  production best practice (D15).
- Menu dishes are soft-deleted (deactivated), never hard-deleted, so order
  history snapshots stay meaningful (D31).
- Optional extras not implemented: public per-dish review listing (REV-04),
  compose preview service for the frontend (FE-15).
- Image uploads for menus are out of scope; an optional URL field is used.
