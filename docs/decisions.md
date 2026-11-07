# CampusBite — Decision Log (ADR-lite)

> Source of truth for *how* we build CampusBite. Each entry: **Decision**,
> **Rationale**, **Consequences / constraints we must honor in code**.
> Decisions D1–D10 are **user-approved (2026-11-07)** and must not be
> re-litigated without the user. D11+ are planning decisions proposed by the
> tutor, pending explicit approval where noted.

---

## D1 — Database: SQLite for the capstone

**Decision:** Use SQLite via SQLAlchemy, configured by `DATABASE_URL`.

**Rationale:** The brief requires a "SQL-based relational database." SQLite
satisfies that with zero external services, the fewest failure points for a
grader running `docker compose up`, and no credentials to manage.

**Constraints we must honor:**
- The database file lives in a **persistent Docker volume** (survives
  container recreation).
- **Enable foreign-key enforcement on every connection** (SQLite does not
  enforce FKs by default) — via a SQLAlchemy event listener
  (`PRAGMA foreign_keys = ON`) per connection.
- **Separate database sessions for web requests and background scans**
  (the reminder scanner opens its own session; it must not share a session
  with a live request).
- **Keep write transactions short** (commit promptly; no long-held locks).
- **Document a single-backend-worker configuration** (one uvicorn worker;
  in-memory state such as the AI rate limiter is only valid under this — see D9).
- **Tests required:** FK enforcement (orphan insert rejected), persistence
  across container restart, overlapping order updates (concurrency), and
  reminder scans running alongside request activity.
- **Database files and local data directories are excluded from Git**
  (`.gitignore`).
- **Versioned migrations** applied automatically or via an explicitly
  documented startup/setup step (we choose Alembic — see D11).

**Honesty note (user instruction, recorded verbatim):** Do **not** claim
PostgreSQL migration is a one-line change. `DATABASE_URL` makes *configuration*
flexible; real PostgreSQL support requires its own migrations, driver setup
(`psycopg2`/`asyncpg`), dialect-specific verification, and re-testing of the
SQLite-specific behaviors above (e.g., FK pragma, concurrency semantics).
SQLite is a *capstone* choice, not a production database.

---

## D2 — Registration and role provisioning

**Decision:**
- The **public** `POST /auth/register` creates **CUSTOMER accounts only**.
  Attempts to self-assign a privileged role are **rejected** (the role is not
  even accepted from the client payload, or is validated against an allowlist
  of `{customer}`).
- A **documented local CLI/provisioning command** creates privileged accounts:
  restaurant **owners** (with their restaurant, in **one database
  transaction**), and **delivery partners**.
- No public owner/delivery registration flow. No admin UI.
- **No real credentials or shared privileged default passwords** in code,
  seed files, docs, or the repo. The CLI reads values from `.env`/arguments
  or prompts; `.env.example` shows placeholder names only.

**Rationale:** Privileged roles must not be self-assignable — that would make
RBAC meaningless (see Q1 from onboarding: never trust the client). Provisioning
is a trusted, local, out-of-band operation for a capstone.

**Constraints:**
- Owner user + restaurant row commit atomically (rollback together on failure).
- CLI usage documented in README and `progress.md` (exact command + example
  using *placeholder* credentials only).
- Provisioned users must be usable by all three dashboards for manual testing.

---

## D3 — Money: integer minor units

**Decision:** All prices, totals, payments, and refunds use **integer minor
units** (cents). The application uses **one documented currency: USD**
(field names are currency-agnostic but values are USD cents, e.g.
`price_cents = 1299` means $12.99).

**Constraints:**
- Explicit field names: `price_cents`, `unit_price_cents`, `total_cents`,
  `refund_cents`, etc. (never bare floats, never client-authoritative).
- **All checkout math happens on the backend** from current DB prices.
- `order_items` stores **item-name and unit-price snapshots** at order time
  (the "policy and proof for all parties" rule): order history, refunds,
  stats, and AI context read snapshots, never live menu data.
- Validate: **positive quantities**, **non-negative prices**; reject items
  that are unavailable, belong to a different restaurant, or don't exist.
- A **client-supplied total is never trusted** — if the client sends one,
  it is ignored (or the request is rejected; we choose: ignore and recompute,
  documented in the API contract).
- Checkout verifies menu items still exist, are available, and belong to the
  ordering restaurant before computing the total.

**Rationale:** Binary floats cannot represent decimal currency exactly;
integer cents make sums exact and portable.

---

## D4 — Authentication: PyJWT + direct bcrypt

**Decision:** **PyJWT** with **HS256** and the **bcrypt library directly**
(not passlib). Access tokens only; **no refresh tokens in v1**.

**Constraints:**
- **Explicitly allow only the intended algorithm** when verifying
  (`algorithms=["HS256"]`); reject `alg: none` and algorithm-confusion input.
- **Require and validate token expiration** (`exp` claim mandatory; expired
  tokens rejected).
- **Stable user ID as the token subject** (`sub` = user PK, as string).
- **Load the current user and role from the database** on each request (the
  token's `sub` is a pointer; the DB is the source of truth for role and
  active status — this also gives us a revocation path: deactivated/deleted
  users stop working immediately).
- **Reject missing or unsafe JWT secrets at startup** (fail fast: no secret,
  or a known-weak/placeholder value → the app refuses to boot).
- **Never log tokens or passwords** (middleware logs method + path only).
- **Validate password input against the installed bcrypt version's limit**
  (bcrypt's effective input limit is 72 bytes; validate and *fail* rather than
  silently truncate), and enforce a reasonable minimum length (we propose
  8–72 bytes — see A3 in assumptions).
- **Pin and test dependency versions** (requirements pinned to the tested
  versions; a test asserts the bcrypt round-trip behavior of the pinned combo).

**localStorage trade-off (recorded honestly):** The brief *requires* storing
the token in `localStorage`. We comply, but the README documents that this is
an assignment requirement, **not** production best practice: `localStorage` is
readable by any JavaScript on the page (XSS exposure), and the security model
relies on the server verifying the signed token and enforcing authorization on
every request — the frontend can never be the security boundary.

---

## D5 — Delivery partners

**Decision:**
- Owners select from **active, provisioned** delivery-partner accounts.
- The partner **listing endpoint is owner-protected** and returns **only
  `id` + display name** — no emails or other personal details.
- During assignment, the backend **validates the partner's role AND active
  status** from the DB (a customer or deactivated account cannot be assigned).
- **Only the owner of the order's restaurant** may assign a partner.
- **Only READY orders** may be assigned (state machine, D7/milestone M7).
- **Only the assigned partner** may perform delivery transitions
  (`ASSIGNED → OUT_FOR_DELIVERY → DELIVERED`).

**Rationale:** Delivery is a two-lock operation: role check (is a delivery
partner?) **and** assignment check (is *this* order assigned to *them*?).
Both are enforced server-side; a valid delivery-partner role alone never
grants access to another partner's order.

---

## D6 — Reminders: managed periodic scanner

**Decision:** A **managed background scanner** started through the FastAPI
**application lifespan** runs **every 60 seconds** in the documented
single-worker configuration. We do **not** rely only on request-triggered
`BackgroundTasks` (those never run when no requests arrive — the exact
situation in which stale orders need reminding).

**Scanner behavior:**
- Finds orders in `PLACED` or `ACCEPTED` whose `status_updated_at` is
  **> 15 minutes** old.
- **Opens a fresh database session per scan** (D1).
- **Deduplicates** reminders per order/status-episode (one reminder per
  status episode, not one per scan tick — keyed on order + status).
- **Excludes/resolves** reminders once the order progresses (a reminder for
  an order now `READY` is hidden or marked resolved).
- **Reminder visibility is restricted to the restaurant owner** of that order.
- **Handles scan errors** (a failed scan logs and continues; it must not
  crash the app) and **shuts down cleanly** with the lifespan.
- **Tests use a controllable clock** (injectable "now" / fake time) — no real
  15-minute waits in automated tests.

---

## D7 — Order state machine: enforced centrally

**Decision:** All status transitions are enforced in **one central place**
(single source of truth: a transition map + a single `transition_order()`
service function). No endpoint performs ad-hoc status edits.

**Transition map (plus actor rules):**

| From | To | Who | Extra condition |
|---|---|---|---|
| PLACED | CANCELLED | Customer (owner of order) | — |
| PLACED | ACCEPTED | Owner of order's restaurant | — |
| ACCEPTED | PREPARING | Owner of order's restaurant | — |
| PREPARING | READY | Owner of order's restaurant | — |
| READY | ASSIGNED | Owner of order's restaurant | partner must be active + role=delivery_partner |
| ASSIGNED | OUT_FOR_DELIVERY | The **assigned** delivery partner | — |
| OUT_FOR_DELIVERY | DELIVERED | The **assigned** delivery partner | — |
| DELIVERED | REFUNDED | Owner of order's restaurant | only if a refund request exists and is approved |

- **Invalid transitions are rejected** with a clear error (409/422), and
  **delivered orders cannot be cancelled** (no DELIVERED→CANCELLED edge).
- Every transition updates `status_updated_at` (feeds the D6 reminder
  scanner) and is the only path by which `status` changes.

---

## D8 — Authorization: three checks on every protected endpoint

**Decision:** Every protected endpoint performs, in order:
1. **Authentication** — valid, non-expired, correctly signed JWT; user
   loaded from DB and active.
2. **Role** — the caller's DB role is in the endpoint's allowed roles.
3. **Resource ownership / delivery assignment** — the specific resource
   belongs to the caller (customer→own order; owner→own restaurant's
   resources; partner→orders assigned to them). A valid role **alone never
   grants access to another user's resources.**

**Mandatory negative tests** (full list in test-plan.md): two customers,
two owners of different restaurants, two delivery partners, plus
wrong-role and cross-resource cases on every protected endpoint. See
`authorization-matrix.md` for the endpoint-by-endpoint map.

---

## D9 — AI insights: OpenAI, backend-only, isolated, bounded

**Decision:**
- Order data for the prompt is **filtered by the authenticated user's ID on
  the backend**. The endpoint **does not accept a target customer ID** from
  the request or from the question text.
- **No model-generated SQL** and no arbitrary database/tool access. The
  model receives a *serialized, pre-fetched, bounded* data blob plus the
  user's question, and answers in text.
- **Only necessary fields** are sent (id, status, dates, item names, item
  counts, `total_cents`, delivery address presence) — no passwords, no
  partner emails, minimized PII.
- **Exact monetary aggregates are computed in application code** (SQL/Python
  over the user's orders) and included as context, so the model doesn't do
  the arithmetic.
- **Bounds:** question length capped (we propose 500 chars) and history size
  capped (we propose most recent 50 orders); overflow is truncated
  deterministically with a note in the context.
- **Error handling:** upstream OpenAI errors, timeouts, and **rate limits**
  are caught and mapped to clean API errors (503 with a friendly message;
  never a raw stack trace).
- **Rate limiting:** a **configurable per-user** limit (e.g. N requests per
  rolling window). If the limiter is in-memory (our choice for the capstone),
  the README documents that **it resets on restart and only supports the
  documented single-worker setup** (D1/D6) — consistent with the brief's
  "basic … rate-limit handling."
- **Tests mock OpenAI** (no real API calls in CI) while the real integration
  code path (client wiring, env key, error mapping) is retained and
  exercised via the mock. **Cross-customer isolation tests** assert a
  customer's question can never surface another customer's data.
- The **OpenAI key lives only in backend env vars** (never in frontend code,
  bundles, or the repo); `OPENAI_API_KEY` placeholder in `.env.example`.

---

## D10 — CORS: explicit allowlist

**Decision:** CORS uses an **explicit, configurable frontend-origin
allowlist** (env-driven, e.g. `CORS_ORIGINS=https://a,https://b` parsed into
a list). Document development (`http://localhost:5173`) and preview origins.
**No wildcard origins** as a workaround.
**CORS is not a replacement for authentication or authorization** — it only
controls which browser origins may call us; all enforcement remains
server-side per D8.

---

## D11+ — Planning decisions proposed by the tutor (pending your approval)

These are needed to make the plan concrete. None of them contradict the
assignment; flag any you don't like.

- **D11 Migrations = Alembic**, auto-applied at startup in the documented
  single-worker setup (plus a manual `alembic upgrade head` command for
  docs). Rationale: versioned, reviewable schema history satisfies D1.
- **D12 Project layout:** `backend/` (app, tests, Dockerfile,
  `docker-compose.yml`, `.env.example`) and `frontend/` (Vite + React);
  `docs/` at repo root. Compose lives at repo root and starts the backend
  (frontend via the Vite dev server in dev; a second compose service for
  preview is optional).
- **D13 Backend port 8000**, frontend dev server 5173, CORS allowlist
  defaults match.
- **D14 API base path** `/api/v1` with OpenAPI docs at `/api/v1/docs`.
  Error format: `{"detail": "...", "code": "..."}` — machine-readable
  `code` for the frontend to branch on (e.g. `INVALID_TRANSITION`).
- **D15 Cart is frontend-only state** (React state + `localStorage`), per the
  brief's "basic React state management"; **no cart table** (the brief's
  table list has none). Checkout is `POST /orders` with item ids +
  quantities; the backend recomputes everything (D3).
- **D16 Browse endpoints (restaurant list/detail/menu list+search) are
  public** (a public catalog is authorized for everyone); **all mutations and
  "me"/owner/partner data require auth + role + ownership** (D8). This is a
  design choice the brief doesn't pin down — documented, reversible.
- **D17 Testing = pytest + httpx TestClient** for the backend; Vitest +
  React Testing Library for the frontend (basic component tests) — optional
  depth per milestone.
- **D18 Order status values are stored as strings** matching the brief
  (`"PLACED"`, …) for readability in the DB, reviews, and AI context.
- **D19 "Basic statistics" = orders by status, revenue (from `total_cents`
  snapshots), items sold, average order value, over a date range** — the
  owner's own restaurant only.
- **D20 Reminder "episode" key = (order_id, status)**; a new status starts a
  new episode. Resolved when the order leaves that status.
- **D21 Seed script** (`python -m app.seed` or CLI): sample restaurants,
  menus, a few orders across statuses, demo customers/owners/partners —
  **all placeholder data, documented as dev-only, excluded from prod use.**
- **D22 `.gitignore` from day one** of code (M2): `*.sqlite3`, `data/`,
  `.env`, `__pycache__`, `node_modules`, `dist`, `.venv`.
