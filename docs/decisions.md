# CampusBite — Decision Log (ADR-lite)

> Source of truth for *how* we build CampusBite. Each entry: **Decision**,
> **Rationale**, **Consequences / constraints we must honor in code**.
> The user's ten approved decisions (2026-11-07) are **D1–D6, D8–D10, and
> D23**; D7 (central state machine) is the development contract's rule,
> recorded between them. None may be re-litigated without the user.
> D11–D22 were proposed by the tutor and **approved by the user
> (2026-11-07)**; they are binding as well. (D23 was appended late on
> 2026-11-07 to record the user's 7th decision — SECRETS — which M1 had
> folded into D4/D9/requirements instead of logging standalone; D7 keeps its
> number to protect the verified cross-references.)

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

## D11–D22 — Planning decisions (approved by the user, 2026-11-07)

These were proposed by the tutor to make the plan concrete. The user
approved the full range **D11–D22** on 2026-11-07; they are binding like
D1–D10. Approval of D16 also resolves assumption A2 (public catalog browsing
is final). A3–A13 in [assumptions.md](assumptions.md) (config defaults)
remain open and are non-blocking for M2.

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

## D23 — Secrets and configuration (user decision 7, recorded late)

**Decision:** Actual secrets stay out of source code, Git history, Docker
images, build args, logs, and frontend bundles. Local `.env` files drive
development; runtime uses environment injection. `.env.example` contains
safe placeholders with documentation. **Frontend environment variables never
contain secrets** (the frontend may only hold non-secret config such as the
API base URL).

**Rationale:** The user's 7th approved decision (2026-11-07). It is the
umbrella over the security constraints scattered through D4 (JWT secret
startup guard; no token/password logging), D9 (OpenAI key backend-only),
DOCKER-03, and DOC-02. It is recorded here so the complete set of the user's
ten decisions — D1–D6, D8–D10, D23 — lives in one place. Appended as D23
rather than renumbering D7, to protect existing cross-references.

**Note for AGENTS.md:** its "Approved Direction" list now contains the
secrets bullet — **added 2026-11-07** with the implementation batch
(approved by the user; nothing else in that file was touched).

---

## D24–D35 — Batch decisions (user-approved, 2026-11-07 implementation batch)

These are **implementation decisions explicitly approved in the user's
2026-11-07 batch prompt**: *"Use the following policies where they answer the
actual open question … Do not claim these policies were explicitly required
by the assignment. Record them as approved implementation decisions from this
prompt."* They resolve the open items **N1–N8** of
[database.md](database.md) §10.2.

### D24 — One owner has at most one restaurant (resolves N4)

**Decision:** one owner account owns **at most one** restaurant.
`restaurants.owner_id` is UNIQUE and NOT NULL.

**Consequences:** provisioning (D2) creates owner + restaurant as one atomic
pair; there is no multi-restaurant UI/API; an owner's restaurant is found by
`owner_id = caller` (the D8 ownership anchor).

### D25 — One restaurant per order

**Decision:** an order contains dishes from **exactly one** restaurant. The
checkout payload names the restaurant; every item must belong to it (CK-04).
Mixed-restaurant carts are rejected 422.

### D26 — Application currency: EUR (resolves the D3/A10 currency pick)

**Decision:** the single documented application currency is **EUR**; all
`*_cents` fields hold euro cents (1 cent = €0.01).

**Provenance (recorded honestly):** D3 (user-approved) required *choosing and
documenting one currency* but named none. The recorded draft of D3 and
assumption A10 proposed USD; the user never confirmed A3–A13. The batch
instruction: *"Retain an already approved currency; otherwise use EUR and
document it consistently."* Since no specific currency was ever user-approved,
**EUR applies**. Field names stay currency-agnostic (`*_cents`); a later
switch to USD would be a label/documentation change only — no schema or
arithmetic change.

### D27 — Refunds are always the full order total (resolves N1)

**Decision:** an approved refund covers the order's **full `total_cents`,
including the delivery fee**. No partial refunds in v1.

### D28 — One refund request per order, permanently (incl. after rejection)

**Decision:** exactly **one** refund request per order, **including after a
rejection** — there is no "second request" flow in v1. The UNIQUE
`order_id` on `refund_requests` is the DB backstop (database.md §6).

### D29 — Cancellation performs a full mock reversal (resolves N2)

**Decision:** when a customer cancels a `PLACED` order, **one transaction**:
`status → CANCELLED`, `payment_status → refunded`, and **one `refunded`
payment-ledger event** (amount = `total_cents`). Cancellation is **not** a
refund request: it creates **no `refund_requests` row**.

**Consequences:** the earlier open policy (database.md §5.3) is closed. No
`void` payment status is needed — the `refunded` payment value is reached two
ways, disambiguated by the order status (CANCELLED = pre-delivery reversal,
no request row; REFUNDED = post-delivery refund, request row exists). The
ledger `UNIQUE(order_id, type)` backstop prevents a double reversal.

### D30 — Post-delivery refund saga (confirms database.md §5.5)

**Decision:** owner-approved refund on a `DELIVERED` order, **one
transaction**: request → `approved` (+`decided_by`/`decided_at`), order
`status → REFUNDED`, `payment_status → refunded`, exactly **one** `refunded`
ledger event (amount = `total_cents` per D27). Rejection leaves the order
`DELIVERED` and payment `mock_paid`; the one-request rule (D28) still holds.

### D31 — Review eligibility = actually delivered, including after refund (resolves N3)

**Decision:** a review may be submitted once the order has **actually been
delivered**, including orders that were later refunded. Eligibility is the
new non-null `orders.delivered_at` timestamp (set **once** when the order
becomes `DELIVERED`, never cleared) — **not** the current order status.
`delivered_at` is preserved through `REFUNDED`. No review
editing/deletion in this batch.

### D32 — Menu items referenced by orders are deactivated, never hard-deleted

**Decision:** `DELETE /menu-items/{id}` sets `available = 0` (soft remove,
RST-03). Hard delete never happens: `menu_item_id` provenance FKs on
`order_items` (RESTRICT) would orphan receipt lines.

### D33 — Timestamps: UTC everywhere; ISO-8601 text in SQLite

**Decision:** all persisted timestamps are **UTC**. The application generates
every timestamp (aware UTC); the database never generates time. On SQLite,
SQLAlchemy `DateTime` stores **ISO-8601 text**
(`YYYY-MM-DD HH:MM:SS.ffffff +00:00`); with a fixed offset, lexicographic
order = chronological order, and the scanner's
`status_updated_at < now − 15 min` comparison is plain text comparison.
`status_updated_at` is stamped **only when status actually changes** (a no-op
re-POST must not refresh it — that would reset the reminder clock).

### D34 — Checkout idempotency keys (resolves N5 with the right mechanism)

**Decision:** `POST /orders` **requires** a client-generated **idempotency
key** (1–64 chars, e.g. `crypto.randomUUID()`), stored on the order, scoped to
the **authenticated customer**: UNIQUE(`customer_id`, `idempotency_key`). The
order also stores `request_hash` (SHA-256 of the canonicalized payload:
restaurant id + sorted menu-item/quantity pairs).

- Identical retry (same key, same hash) → returns the **original** order; no second order or payment row.
- Same key, different payload (hash mismatch) → `409 IDEMPOTENCY_MISMATCH`.
- Competing identical requests → the DB unique lets exactly one insert win; the loser re-reads and returns the winner's order.
- The frontend generates one key per checkout intent and reuses it only on retry.

This **supersedes** the earlier N5 idea of a 60-second near-duplicate 409,
which would have false-positived on a legitimate re-order of the same dish.

### D35 — Owner statistics metric set (refines D19)

**Decision:** `GET /owner/stats?from&to` (own restaurant only) returns:

| Metric | Definition (documented; never blindly called "revenue") |
|---|---|
| `orders_by_status` | counts of the restaurant's orders in the date range by current status |
| `gross_mock_paid_cents` | Σ `total_cents` over the range's placed orders (every placed order has a `mock_paid` event) |
| `refunded_cents` | Σ `refunded` ledger events in the range (cancellation reversals **and** approved refunds, D29/D30) |
| `net_retained_cents` | `gross_mock_paid_cents − refunded_cents` |
| `delivered_count` | orders actually delivered in the range (`delivered_at` in range) — **including** later-refunded ones (D31) |
| `items_sold` | Σ order-item quantities (D19) |
| `avg_order_value_cents` | `gross_mock_paid_cents` ÷ placed-order count (D19) |

All integer cents, EUR (D26). The same definitions live in
`docs/api-contract.md` and the README.

### D36 — AI insights implementation shape (batch 10, refines D9)

**Decision:** `POST /api/v1/insights/question` (customer role only) is
implemented in `app/services/insights.py` + `app/api/v1/insights.py`:

- **Degradation contract:** no `OPENAI_API_KEY` → `200` with
  `provider: "unconfigured"`, `answer: null`, plus the exact app-computed
  `stats` (a clear configuration signal; **no** fake AI output, and no
  503 — the feature is "available but unconfigured"). Empty order history →
  `provider: "deterministic"` with a plain sentence and no provider call.
- **Provider seam:** `create_app(settings, openai_client_factory=None)` —
  production builds the real `openai` client lazily from the env key; tests
  inject fakes, so the suite never touches the network. A live paid call
  was **not** made during development (user action).
- **Rate limiting:** `InMemoryRateLimiter` (sliding window, per user id,
  `AI_RATE_LIMIT`/`AI_RATE_WINDOW_MINUTES`). In-memory state resets on
  restart and is correct only for the documented single-worker deployment
  (D9 limitation, documented in README + api-contract).
- **Prompt hygiene (AI-02/03/06):** context = the caller's own orders
  (window-bounded), PII-light (no addresses/e-mails/names of other people),
  amounts in integer cents with the currency stated. Question length-bounded
  by `AI_MAX_QUESTION_CHARS`.
- **Upstream failure mapping:** provider 429 → `429 AI_UPSTREAM_RATE_LIMITED`,
  timeout → `504 AI_TIMEOUT`, other API errors → `502 AI_UPSTREAM_ERROR`;
  provider error text is never forwarded.

### D37 — Batch 8 frontend compliance fixes (applied 2026-11-08; verify)

Three small source changes made while bringing the frontend suite to green
and during the browser E2E. They implement contract behavior, not cosmetic
changes; the user is asked to review/confirm them (they were flagged in the
previous session's handoff):

1. `OrderCard` renders `customer_name` + `delivery_address` when present —
   required for the partner list view (DELV-01: partners must see who/where
   to deliver). Verified in the real browser during the E2E.
2. `ConfirmButton`'s armed-state `aria-label` is the confirm label itself
   (a "(confirm action)" suffix had broken accessibility-name consumers).
3. `Menu.jsx` filter submission maps the inputs to the reader's key names
   (`search`/`min`/`max`) — the old shorthand silently dropped both price
   filters (genuine bug, found via instrumentation).
