# CampusBite

CampusBite is a full-stack restaurant ordering and delivery platform (student capstone project). Customers browse restaurants, order dishes with a dummy payment, track orders, review them, and request refunds. Restaurant owners manage menus and orders, assign delivery partners, and decide refund requests. Delivery partners complete the orders assigned to them. Customers can also ask AI questions about their own order history.

## Technologies used

| Layer | Technology |
|---|---|
| Frontend (`frontend/`) | React (JavaScript, ES6+), React Hooks, React Router DOM, Vite. State via contexts (auth, cart). |
| Backend (`backend/`) | Python, FastAPI, Pydantic v2, SQLAlchemy 2 ORM, Alembic migrations, PyJWT (HS256), bcrypt. |
| Database | SQLite (a SQL relational database), stored on a persistent Docker volume, with foreign-key enforcement on every connection. All money is stored as integer cents (EUR). |
| AI | OpenAI API (`openai` SDK), called from the backend only. |
| Packaging | Docker and Docker Compose (one backend service, one worker). |
| Version control | Git and GitHub. |
| Tests | `pytest` (backend), Vitest + Testing Library (frontend). |

## Features implemented

### Customer
- Register and log in.
- Browse restaurants and view menus and dish details.
- Search dishes by name and filter by price.
- Add dishes to a cart, update quantities, and remove items (one restaurant per cart).
- Place orders with a dummy payment (payment status becomes `mock_paid`; no real gateway).
- View order history, filter by status and date, and track order status.
- Cancel an order while it is still `PLACED`.
- Submit a rating and review after delivery.
- Request a return/refund after delivery, with a reason (one request per order).
- Ask the AI about previous orders (Insights page).

### Restaurant owner
- Log in (accounts are provisioned locally, see below).
- Add, update, and manage dishes, and mark them available or unavailable.
- View incoming orders, filter by status and date, accept orders, and update preparation status.
- Assign a delivery partner when an order is `READY`.
- View basic restaurant statistics.
- Approve or reject return/refund requests.
- View reminders for orders left in `PLACED` or `ACCEPTED` for more than 15 minutes.

### Delivery partner
- Log in (accounts are provisioned locally).
- View only the orders assigned to them, including customer delivery details.
- Mark an order `OUT_FOR_DELIVERY`, then `DELIVERED`.
- View delivery history.

### Platform
- Password hashing with bcrypt, JWT authentication, and role-based access control enforced in the backend (not only hidden in the frontend). Users can only access data they are authorized to see or change.
- Order lifecycle: `PLACED` -> `ACCEPTED` -> `PREPARING` -> `READY` -> `ASSIGNED` -> `OUT_FOR_DELIVERY` -> `DELIVERED`, plus `CANCELLED` and `REFUNDED`. The backend rejects invalid transitions.
- Separate dashboards for the three roles, with filters and pagination.
- Request logging and response-time middleware.
- Background scanner that creates reminder records for stale orders.
- Reusable React components, protected routes, loading and error states, and a responsive layout.

## Quick start (backend with Docker Compose)

Prerequisites: Git, and Docker Desktop (or Docker Engine) with the Docker daemon running.

```bash
git clone https://github.com/ginkalavarun/Capstone-Project.git
cd Capstone-Project
cp .env.example .env
# Generate a secret and paste it into .env as JWT_SECRET (the app refuses the placeholder).
# On macOS/Linux use python3 (or: openssl rand -base64 48):
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build
```

- Backend: <http://localhost:8000>. Interactive API docs: <http://localhost:8000/api/v1/docs>.
- Alembic migrations run automatically before the app serves traffic.
- The database file is `/data/campusbite.db` inside the named volume `campusbite-data`. It survives container recreation.

**Non-destructive shutdown:** `docker compose down` (keeps the volume). Never use `docker compose down -v` unless you want to delete the database.

A fresh clone has an empty database. Add data as described in the next section.

**Demo logins:** once the backend is running, load the sample data with `docker compose exec -T backend python -m app.seed`. Then start the frontend (see "Running the frontend locally") and log in at <http://localhost:5173> with the accounts listed below. For example: `priya@example.org` / `Customer-Pass-1` (customer), `sam@example.org` / `Owner-Pass-1` (restaurant owner), and `dana@example.org` / `Partner-Pass-1` (delivery partner).

## Creating accounts and demo data

In the browser, only **customers** can register: open the frontend, click Register, and use a new email and password (each account needs its own email). **Restaurant owners (with their restaurant) and delivery partners cannot register in the browser.** They are created with a local command, because privileged roles must not be publicly self-registered. Once they exist, they log in on the same Login page as everyone else.

### Option A: sample data in one command

With the backend running:

```bash
docker compose exec -T backend python -m app.seed
```

This creates two restaurants with menus (Slice House, Bagel Bros), sample orders in several statuses, a pending refund request, a stale-order reminder, and these development-only accounts (safe example.org placeholders, not real credentials):

| Role | Email | Password |
|---|---|---|
| Customer | priya@example.org | Customer-Pass-1 |
| Customer | dev@example.org | Customer-Pass-2 |
| Owner | sam@example.org | Owner-Pass-1 |
| Owner | lena@example.org | Owner-Pass-2 |
| Delivery partner | dana@example.org | Partner-Pass-1 |
| Delivery partner | marco@example.org | Partner-Pass-2 |

The seed command is safe to run again; it skips records that already exist.

### Option B: create your own owner and partner

Run these inside the container so the accounts go into the same database the app uses:

```bash
docker compose exec backend python -m app.provision owner \
  --email sam@example.org --name "Sam Kapoor" \
  --restaurant "Slice House" --address "10 Green Line, Block A" \
  --fee-cents 200
docker compose exec backend python -m app.provision partner \
  --email dana@example.org --name "Dana Kim"
```

- Without `--password`, you are prompted for one (8 to 72 characters). With `-T` or no terminal, a random password is generated and printed once, so save it.
- The owner and restaurant are created in one transaction. Each owner has at most one restaurant.
- Provisioning does not create dishes. Log in as the owner and add them on the menu management page.

## Running the frontend locally

Prerequisites: Node.js and npm. The backend must be running.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The frontend calls `http://localhost:8000/api/v1` by default. `VITE_API_BASE_URL` can override this (it is not a secret). The frontend origin `http://localhost:5173` must be in the backend `CORS_ORIGINS` setting (it is by default).

## Environment variables

Copy `.env.example` to `.env` (repository root, used by Docker Compose). Never commit `.env`; only `.env.example` with placeholders is tracked. The OpenAI key is read by the backend only and must never appear in frontend code.

| Variable | Purpose |
|---|---|
| `JWT_SECRET` | Required. Long random secret used to sign tokens. The app refuses to start with the placeholder. |
| `DATABASE_URL` | Database connection string. Default in Docker: `sqlite:////data/campusbite.db`. |
| `JWT_EXPIRE_MINUTES` | Access-token lifetime in minutes. |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins (no wildcards). |
| `BACKEND_HOST_PORT` | Host port the backend is published on (default 8000). |
| `REMINDER_SCANNER_ENABLED` | Turns the stale-order reminder scanner on or off. |
| `REMINDER_INTERVAL_SECONDS` | How often the scanner runs. |
| `REMINDER_STALE_MINUTES` | Age after which a `PLACED` or `ACCEPTED` order gets a reminder (15). |
| `OPENAI_API_KEY` | Optional. Enables the AI Insights feature. |
| `OPENAI_MODEL` | OpenAI model name used for insights. |
| `AI_RATE_LIMIT`, `AI_RATE_WINDOW_MINUTES`, `AI_MAX_QUESTION_CHARS`, `AI_HISTORY_WINDOW` | Optional tuning for the insights feature (see `.env.example`). |
| `VITE_API_BASE_URL` | Optional, frontend only. Overrides the backend API URL. |

After changing `.env`, recreate the backend: `docker compose up -d --force-recreate`.

## Database setup

- The database is SQLite, accessed through the SQLAlchemy ORM.
- Alembic migrations in `backend/alembic/` run automatically at backend startup, so no manual setup is needed.
- Tables: users, restaurants, menu items, orders, order items, payment ledger, refund requests, reviews, and reminder logs. Orders store snapshots of item names, prices, and the delivery address so later menu edits do not change order history.
- Relationships follow the assignment: a customer has many orders, a restaurant has many menu items and orders, an order has many items and many payment ledger entries, a delivered order has at most one review, and a delivery partner can be assigned to many orders.
- For local development without Docker, see the next section.

## Local development (backend without Docker)

Python 3.12 is required.

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set a real JWT_SECRET
python -m app.seed            # optional sample data
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## API documentation

- Interactive Swagger UI (while the backend runs): <http://localhost:8000/api/v1/docs>.
- `docs/api-contract.md` lists every endpoint with request and response shapes, allowed roles, ownership rules, and status codes.
- All protected endpoints expect the header `Authorization: Bearer <token>`, obtained from the login endpoint.

## Running the tests

```bash
cd backend  && .venv/bin/python -m pytest   # Docker tests skip without a docker CLI
cd frontend && npx vitest run
cd frontend && npm run build                # production build
```

The two Docker tests reuse the local compose project and run `app.seed`. If your local database holds data you care about, run them from a throwaway copy of the repository.

## OpenAI order insights

Customers can request summaries and ask questions about their own orders. The backend loads only the authenticated customer's orders, computes totals itself, and sends a bounded, minimal prompt to the OpenAI API. It handles timeouts, upstream errors, and rate limits with clear error responses and applies a per-user rate limit.

Set `OPENAI_API_KEY` in `.env` to enable it. Without a key the rest of the app works, and the Insights page shows a "not configured" notice with the figures the app computes itself. Automated tests use a mocked client; a live OpenAI call must be verified by the user with their own key.

## Additional documentation

- `docs/api-contract.md`: API reference.
- `docs/manual-testing-guide.md`: step-by-step manual walkthrough of every role.
- `docs/`: requirements, decisions, database design, authorization matrix, test plan, and progress notes.
- `AGENTS.md`: development rules used for AI assistants working on this repository.

## Known limitations

- SQLite with one backend worker: the in-memory AI rate limiter resets on restart and the reminder scanner is a single managed task. Moving to PostgreSQL would need a new driver, migrations, and verification.
- The JWT is stored in `localStorage`, as the assignment requires. This is convenient but exposed to XSS, and is not a production best practice.
- Dishes that appear in past orders are deactivated, never hard-deleted, so order history stays correct.
- Payments are simulated only; there is no real payment gateway, WebSocket notification, or image upload.
- Optional extras not implemented: public per-dish review listing and a frontend service in Docker Compose.
- Seed data is for local demonstration only; the seed passwords are public placeholders and must not be reused anywhere real.
