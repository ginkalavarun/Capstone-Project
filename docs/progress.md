# CampusBite — Progress Log

> Living record: what is done, what is next, and the running task board.
> Updated at the end of every task. Milestone definitions:
> [milestones.md](milestones.md).

## Status snapshot (2026-11-08, post-batch 10)

- **Workspace:** git repo on `main`; local HEAD `45f2361` **= `origin/main`**
  (in sync — the user pushes; this session made **no** commits). All
  reconciliation + all implementation work so far is currently
  uncommitted (modified docs + untracked `backend/` + new root files).
- **Current milestone:** **batches 1–10 ✅ COMPLETE** — the entire backend
  (M2+M3, M4, M5, M6, M7, M9 + M8-stats, M8 remainder) **and** the
  functional React frontend (batch 8, M11–M13) **and** the OpenAI order
  insights (batch 10, M10). The full order→delivery→review→refund saga plus
  the cancellation saga were exercised in a real headless browser against
  the running backend (see the batch 8 entry). The only deferred items are
  explicit optionals (FE-15 compose preview, REV-04 public review listing)
  and user-side verification actions (Docker, live OpenAI call).
- **State:** application code exists in `backend/` + `frontend/` (untracked
  in git until the user commits). 183 backend tests pass, 3 Docker tests
  skip (no docker CLI on this machine — exact commands in the batch 1 entry);
  101 frontend tests pass; `npm run build` succeeds. README created with
  exact run/provision/test commands.
- **Docs:** all planning docs present, incl. `docs/api-contract.md`
  (DOC-06 — synced through batch 10: every implemented endpoint fully
  documented, roadmap now empty); `README.md` created (2026-11-08, per the
  finish directive). `docs/learning-log.md` deferred — the 2026-11-08 finish
  directive asked for concise docs only, no learning guides.
## Task log

### 2026-11-07 — M1: planning documents

**Done**
- Read the full assignment brief (12-page PDF, extracted).
- Verified `AGENTS.md` is **unavailable** in the workspace; reported to user;
  did **not** guess its contents (tracked as assumption A1, blocked).
- Captured the user's 10 approved decisions verbatim-in-intent → `decisions.md`
  (D1–D10) plus tutor proposals (D11–D22).
- Authored all ten planning docs: assignment-brief, decisions, requirements
  (every requirement ID-linked to milestone + tests), authorization-matrix,
  test-plan (every test defined), architecture (golden-path trace),
  milestones (M1–M14 with acceptance criteria + tests), excluded-features,
  assumptions, progress.

**Gates to clear before M2**
- [x] User review of this document set (done 2026-11-07; A2 resolved via
      D16 approval; D11–D22 approved).
- [x] Repo on GitHub + `git init` + initial commit + push (done by user;
      tutor verified via MCP: same SHA, all ten docs present, in sync).
- [ ] A3–A13 config-default confirmation (non-blocking: M2's `.env.example`
      needs only DATABASE_URL / JWT_SECRET / CORS_ORIGINS / OPENAI_API_KEY).
- [x] User provides `AGENTS.md` (done 2026-11-07 — file created from
      user-provided content; A1 resolved, DOC-04 satisfied).

**Next (M2 — awaiting go-ahead):** backend scaffold — FastAPI app, env config,
CORS allowlist, error format, health, middleware stubs, pytest harness,
Dockerfile, docker-compose.yml, `.env.example` (`git init` + `.gitignore`
already done). Tests T-M2-01…07 must be green to close M2.

### 2026-11-07 — user review, D11–D22 approval, repo on GitHub

- User reviewed the doc set; **approved D11–D22** (recorded in decisions.md);
  A2 resolved via D16. A3–A13 remain open (config defaults, non-blocking).
- Verified on GitHub via MCP: commit `26d7a30` “Initial commit” on `main`
  contains all ten docs (byte-identical to local); local/remote in sync.
- Committed the approval record + `.gitignore` (D22) locally as one commit on
  `main` (on top of `26d7a30`; five files). The session has **no push route**:
  git HTTPS has no cached credentials (keychain empty, no SSH key, `gh`
  unauthenticated) and the GitHub MCP token is **read-only** (an API
  `push_files` attempt was denied with 403 on the git trees API). The push is
  therefore pending on the user. **User step (terminal with working git
  auth):** `git push origin main` — one commit, five files. The tutor will
  then verify the remote via the read-only MCP.

### 2026-11-07 — AGENTS.md + database design (M3 prep, docs only)

- User pushed `9229de9` from their terminal; MCP verified remote in sync.
- **AGENTS.md created** at repo root from user-provided content (A1
  resolved). Referenced-doc audit: all present except `docs/api-contract.md`
  (expected — comes with the API milestones); `docs/database.md` now exists.
- **Recovered decision D23 (SECRETS AND CONFIGURATION)** — the user's
  original 7th approved decision, which the M1 decision log had folded into
  D4/D9/requirements instead of recording standalone; appended as D23 (no
  renumbering, to protect the verified cross-references).
- **Wrote `docs/database.md`** — full M3 schema design (9 tables, three
  state machines, transactions, concurrency, worked example, design tests).
  **No ORM code, no migrations** — per instruction, awaiting user approval.

### 2026-11-07 — reconciliation (docs; user-approved batch policies)

- User approved the 2026-11-07 implementation batch with inline policies;
  recorded as **D24–D35** in `decisions.md` (one owner ≤ 1 restaurant;
  one restaurant per order; **EUR**; full refunds incl. fee; one refund
  request permanently; cancellation = mock reversal, no request row;
  post-delivery refund saga; review eligibility via `delivered_at`; menu
  items never hard-deleted; app-generated UTC timestamps; checkout
  idempotency key + request hash; D35 stats metric set).
- **A3–A13 confirmed as conservative defaults** (`assumptions.md`); A10
  currency → EUR per D26.
- `database.md` fully reconciled (9-table count box; `orders.delivered_at` /
  `idempotency_key` / `request_hash`; all state & transaction sections;
  worked example in €). `requirements.md` / `test-plan.md` gained the new
  IDs; `milestones.md` records the batch→milestone mapping; one secrets
  bullet added to `AGENTS.md` (user-authorized).

### 2026-11-07 — batch 1: foundation, configuration, database ✅

**Delivered** (all in `backend/`, plus root compose/env files):
- `app/main.py` (app factory: config guard, CORS allowlist, `detail`+`code`
  error format, request-logging middleware, lifespan migrations, docs under
  `/api/v1`), `app/core/*` (config+D4 guard, constants, errors, bcrypt/JWT
  security, canonical hash), `app/db/*` (engine with per-connection FK
  pragma, **`types.UTCDateTime`** (D33 storage contract), 9-table ORM models,
  session factory, migration runner), `alembic/` baseline `0001`,
  `seed.py` (D21 dev world, idempotent), health endpoints.
- `tests/conftest.py`, `tests/test_scaffold.py` (T-M2-01…07),
  `tests/test_db.py` (T-M3-01…25) — see results below.
- `Dockerfile` (no build-arg secrets, non-root, single worker),
  `.dockerignore`, `backend/.env.example`, root `.env.example`, root
  `docker-compose.yml` (env interpolation + safe defaults; named volume
  `campusbite-data`; healthcheck; non-destructive `down` documented).

**Bugs found & fixed while testing** (the "written but untested" code had
three): wrong relative-import depth in `app/main.py` (`..` vs `.`) and in
`app/api/v1/__init__.py`; SQLAlchemy 2.0 SQLite `DATETIME` silently drops
the timezone (verified empirically) → `UTCDateTime` now implements the
approved `+00:00` D33 contract; alembic `fileConfig` would have silenced
pytest loggers → `disable_existing_loggers=False`.

**Actual results (executed 2026-11-07, `backend/.venv`, Python 3.12.14):**
- `pytest`: **49 passed, 3 skipped** (T-M2-04/05/06-image — docker CLI not
  installed on this machine; the repo-scan half of T-M2-06 and everything
  else ran). Suite time ≈ 4 s.
- Manual smoke (fresh DB in /tmp): `alembic upgrade head` ✓; `python -m
  app.seed` → 6 users / 5 orders ✓; `uvicorn app.main:app` →
  `/api/v1/health` 200, `/api/v1/health/db` reports
  `foreign_keys_enabled: true`, `/api/v1/docs` + `/openapi.json` 200 ✓.
- `docker-compose.yml` validated as YAML (pyyaml, installed into the venv
  for validation only — not a runtime dependency).
- T-M2-07: `git check-ignore` confirms `.env`/`*.db`/`data/`/`.venv`/
  `node_modules`/`dist`/`__pycache__` ignored; `.env.example` *not* ignored.

**Documented execution blocker (for the user's machine):**
`docker compose up -d --wait --timeout 180 backend` then
`curl http://localhost:8000/api/v1/health` (T-M2-04); the volume-persistence
flow is T-M2-05; image secret-scan is T-M2-06. Requires: `cp .env.example
.env` with a real `JWT_SECRET`.

**Small reconciliation doc fixes (flagged):** `test-plan.md`/`database.md`
T-M3-13 "7 FKs" → "13 FK columns" (reconciled schema); `database.md` §7
added the dynamic-typing honesty note + `UTCDateTime` implementation note;
removed one duplicated fragment line. **No requirement semantics changed.**

**Next:** batch 2 — authentication (register/login/me, bcrypt, PyJWT,
current-user dependency, role/ownership helpers) + local provisioning CLI
(T-M4-01…19).

### 2026-11-07 — batch 2: authentication + local provisioning ✅

**Delivered** (all in `backend/`):
- `app/core/deps.py` — `build_get_current_user` (bearer parse → `jwt.decode`
  with explicit HS256 allowlist, required `exp`+`sub`, integer `sub` → DB
  load → active check; controlled 401 codes TOKEN_MISSING/MALFORMED/INVALID/
  EXPIRED + USER_INACTIVE) and `build_require_roles` (403 ROLE_FORBIDDEN).
  The DB is the source of truth for role/active state — the token carries no
  trusted claims (D4).
- `app/schemas/auth.py` — `RegisterIn` (`extra="forbid"` so a payload
  containing `role` → 422, T-M4-02), `LoginIn`, `UserOut` (never the
  password hash), `RegisterOut`, `TokenOut`.
- `app/api/v1/auth.py` — `POST /auth/register` (201 customer-only / 409
  EMAIL_TAKEN / 422 PASSWORD_POLICY), `POST /auth/login` (uniform 401
  INVALID_CREDENTIALS — no user enumeration; USER_INACTIVE distinct),
  `GET /auth/me`.
- `app/provision.py` — CLI `python -m app.provision owner|partner`:
  owner+restaurant in ONE commit (D2); idempotent re-run honors the 1:1 rule
  (D24); missing `--password` → getpass on a TTY else a random password
  printed once (never a shared default, never logged).
- `tests/test_auth.py` — 19 tests covering T-M4-01…13, 15 (batch-2 half:
  token binding via `/me`), 18, 19. The full cross-resource halves of
  T-M4-14/16/17 land with the owned endpoints in batches 3–6 (test-plan M4
  note added).

**Bugs found & fixed while testing** (three, all root-caused):
1. `conftest.make_test_settings` raised on per-test overrides (`dict() got
   multiple values…`) → overrides now `update()` an explicit values dict
   (fixed in the prior session; the six T-M4-08 tests verified green this
   session).
2. **pydantic `EmailStr` rejects the reserved `.test` TLD** (email-validator
   2.2.0: “special-use or reserved name”) — every `@example.test` email 422'd
   at the HTTP boundary. Fixed per the handoff's preferred option 1: all 66
   occurrences across `tests/test_auth.py`, `tests/test_db.py`, `app/seed.py`
   moved to the RFC-2606 documentation domain `@example.org` (probe-verified
   accepted by the validator; `.local` is *also* rejected, so it was not
   chosen). This fixed a real functional bug, not just the tests: **seeded
   users previously could not log in** because `LoginIn.email` is an
   `EmailStr`. `test_db.py` is ORM-direct (never pydantic) and was passing —
   it was changed for repo-wide consistency so no future HTTP-level test
   inherits the trap.
3. T-M4-18's stub `FastAPI()` app lacked the `ApiError` → JSON handler, so
   the 401 `ApiError` propagated as a raw exception. Fixed by registering
   the same `register_error_handlers(app)` the production factory uses — the
   test now exercises the exact production error contract.

**Actual results (executed 2026-11-07, `backend/.venv`, Python 3.12.14):**
- `pytest`: **78 passed, 3 skipped** (the same 3 Docker tests; docker CLI
  still absent — user commands unchanged, see batch 1 entry). ≈ 11 s.
- Provisioning smoke (fresh /tmp DB, non-TTY): owner created with a generated
  password printed once; partner created with an explicit password; owner
  re-run → “already has restaurant … nothing to do” (1 user, 1 restaurant,
  fee 250 — no duplicates). ✓
- Seed→login round trip (fresh /tmp DB): `python -m app.seed` (6 users / 5
  orders) then API logins for one customer, one owner, one partner → all 200
  with correct roles; `/api/v1/health` 200. ✓

**Documented execution blocker (unchanged from batch 1):** Docker tests
T-M2-04/05 + image half of T-M2-06 require the user's machine: `cp
.env.example .env` (real `JWT_SECRET`) → `docker compose up -d --wait
--timeout 180 backend` → `curl http://localhost:8000/api/v1/health`.

**Next:** batch 3 — `docs/api-contract.md` + restaurants & menus endpoints
(public catalog with search/price filters/pagination; owner menu CRUD with
availability toggles and soft-deactivation; T-M5-01…10; the first
materialized halves of T-M4-14/16).

### 2026-11-07 — batch 3: API contract + restaurants & menus ✅

**Delivered:**
- `docs/api-contract.md` (DOC-06) — conventions (error format + machine
  codes, money, timestamps, pagination envelope, auth check order, CORS) and
  full endpoint documentation for everything implemented so far (health,
  auth, restaurants, menu) plus the synced roadmap table for batches 4–7 +
  stretch.
- `app/schemas/pagination.py` — `Page[T]` envelope + `PaginationParams`
  (limit 1–100 default 20; offset ≥ 0) — the single pagination contract for
  all list endpoints (API-03).
- `app/schemas/restaurants.py` — `RestaurantOut`, `MenuItemOut`,
  `CreateMenuItemIn`, `UpdateMenuItemIn` (partial update; whitespace-only
  names rejected via validator; price sanity cap €100,000).
- `app/api/v1/restaurants.py` — public catalog (D16, no auth): `GET
  /restaurants`, `GET /restaurants/{id}`, `GET /restaurants/{id}/menu`
  (case-insensitive name search with LIKE-wildcard escaping, inclusive price
  bounds); owner management: `POST /restaurants/{id}/menu`, `PUT/DELETE
  /menu-items/{id}` (DELETE = soft-remove, RST-03/D32).
- `app/core/deps.py` — `require_menu_item_owner` (role → 403, ownership →
  404; the separate checks of D8, reusable by later batches).
- `tests/test_restaurants.py` — 13 tests: T-M5-01…10 plus the first
  materialized halves of T-M4-14 (parametrized sweep: 3 owner endpoints ×
  401/403/404) and T-M4-16 (owner-B isolation, data-untouched read-back).

**Bugs found & fixed while testing** (four, all root-caused):
1. `Annotated[Session, Depends(...)]` placed *after* defaulted query params
   → Python `SyntaxError` (required-after-defaulted); reordered.
2. `Query(default=…)` inside `Annotated` → assertion at route registration;
   FastAPI requires the default on the `=` side.
3. FastAPI semantics trap: a bare pydantic model parameter is a request
   **body**, not query parameters — pagination is wired via
   `Annotated[PaginationParams, Depends()]`; a bare model would have made
   every list GET expect a JSON body. Caught during implementation (route
   construction + framework semantics), not by the tests.
4. **Whitespace-only dish names passed `min_length=1`** (e.g. `"   "` → 201,
   then stripped to `""` on save). Real bug, caught by a new test; fixed in
   both schemas with a strip-and-reject `field_validator`.
   (Test-side fixes, for the record: my own wrong price-filter math in
   T-M5-05, a missing `/api/v1` prefix in the sweep URLs, and
   `TestClient.delete()` not accepting `json=None`.)

**Actual results (executed 2026-11-07, `backend/.venv`, Python 3.12.14):**
- `pytest` (full suite): **91 passed, 3 skipped** (same 3 Docker tests).
  ≈ 34 s.
- Suite time note: the `world` fixture logs in 4 accounts per test; the
  M5 file adds ~20 s of bcrypt/verify cost. Acceptable for a capstone;
  revisit if the suite grows past a couple of minutes.

**Documented execution blocker (unchanged):** Docker tests still need the
user's machine (see batch 1 entry).

**Next:** batch 4 — checkout service (central order creation: item
validation, single-restaurant rule, integer-cent totals, snapshots, mock
payment ledger event, idempotency per D34; T-M6-01…14).

### 2026-11-07 — batch 4: checkout & mock payment ✅

**Delivered:**
- `app/schemas/orders.py` — `CheckoutIn` (unknown fields **ignored** per
  T-M6-02; qty 1…100; address 1–255; key 1–64), `OrderItemOut` (snapshot
  fields), `OrderOut` (explicit `from_order` construction — the derived
  `restaurant_name` has no column).
- `app/services/checkout.py` — `place_order`: the single place an order comes
  into existence. Role check → item validation (exists / available /
  one-restaurant D25) → server-side integer-cent money (D3/D26: snapshots +
  current fee) → idempotency (D34: customer-scoped key + canonical request
  hash; retry→original, mismatch→409, IntegrityError→re-read winner).
  Order + items + `mock_paid` ledger row in one commit.
- `app/api/v1/orders.py` — `POST /orders` (201 created / 200 idempotent
  retry), `GET /orders` (own history: status + date filters, paginated),
  `GET /orders/{id}` (customer / owning owner / assigned partner, else 404).
- `tests/test_checkout.py` — 14 tests: T-M6-01…14 incl. the tampered-money
  case, snapshot-persistence, threaded 3-way race (one order, one ledger
  row, zero errors), and cross-customer key isolation.

**Bugs found & fixed while testing** (three, all root-caused):
1. `OrderOut.restaurant_name` (derived from the relationship) is not a
   column — `model_validate(order)` failed with `Field required`. Fixed by
   explicit field-by-field construction in `from_order`.
2. **Idempotency race handler was on the wrong statement**: the explicit
   `db.flush()` (which INSERTs the order row) sat *outside* the
   try/except, so the `UNIQUE(customer_id, idempotency_key)` IntegrityError
   in a true race escaped to a 500. The threaded test (T-M6-13) caught it:
   2 of 3 threads raised. Moved the flush inside the try. This is exactly
   the class of bug the race test exists to find — it worked.
3. (Test-side) nothing else — the file was correct modulo the two above.

**Actual results (executed 2026-11-07, `backend/.venv`, Python 3.12.14):**
- `pytest` (full suite): **105 passed, 3 skipped** (same 3 Docker tests).
  ≈ 56 s.

**Documented execution blocker (unchanged):** Docker tests still need the
user's machine (see batch 1 entry).

**Next:** batch 5 — complete order & delivery lifecycle (central transition
machine, cancellation + D29 mock reversal, delivery assignment, partner
lists/detail, the deferred T-M4-15/16/17 endpoint sweeps; T-M7-01…20).

### 2026-11-08 — batch 5: order & delivery lifecycle (canonical M7) ✅

**Delivered:**
- `app/services/transitions.py` — the central state machine (D7): an
  explicit edge map (PLACED→ACCEPTED→PREPARING→READY→ASSIGNED→
  OUT_FOR_DELIVERY→DELIVERED, plus PLACED→CANCELLED and the batch-6
  DELIVERED→REFUNDED edge) and five named actions. Every action = role
  (403) → ownership/assignment (404) → compare-and-swap edge (409
  `INVALID_TRANSITION`). The CAS is a Core `UPDATE … WHERE id = :id AND
  status = :from`: under concurrency the database arbitrates — a loser
  touches 0 rows, writes nothing, and re-stamps nothing (ORDER-11:
  `status_updated_at` is the reminder clock, D6/D33). `deliver` stamps
  `delivered_at` in the same UPDATE (D31). Cancellation performs the D29
  mock reversal in the same transaction: CANCELLED + payment `refunded` +
  exactly one `refunded` ledger row (D27 full amount), **no**
  `refund_requests` row.
- `app/api/v1/lifecycle.py` — 10 endpoints: cancel / accept / status (prep)
  / assign / delivery-status, the owner dashboard (`GET /owner/orders` with
  status + date filters — DASH-01, delivered early per the batch contract),
  `GET /delivery-partners` (active partners, `id` + `full_name` only — D5),
  partner active list / history (split at DELIVERED/REFUNDED) / detail
  (assigned partner only).
- `app/schemas/orders.py` — `StatusIn` + `AssignIn` (single-field bodies,
  `extra="forbid"`); `customer_name` added to `OrderOut` (DELV-02: the
  partner needs a recipient to contact).
- `tests/test_lifecycle.py` — 19 tests (25 collected: T-M7-03+04 is one
  parametrized test): T-M7-01 = 63-case sweep of every action × every
  from-status; T-M7-11/12 timestamps + customer tracking; T-M7-13/14/15
  partner views; T-M7-16 partner listing; T-M7-17 no-op re-POST;
  T-M7-18/19 the D29 reversal + duplicate cancellation; T-M7-20 threaded
  cancel-vs-accept race; `test_m4_16` the final deferred M4 half (owner
  axis on orders + dashboards); the partner half of T-M4-17 in T-M7-10.

**Bugs found & fixed while testing** (three, all root-caused):
1. `lifecycle.py` had `Annotated[Optional[datetime]] = None` — one argument
   in `Annotated[...]` is a `TypeError` **at import time**, so the whole
   test suite failed to collect (batch 5 had been written but never
   executed). Fixed to `Annotated[Optional[datetime], Query()]`.
2. `update_preparation` returned **422** for a *known* status that is not
   its target (e.g. re-POSTing `ACCEPTED` on an ACCEPTED order), but
   canonical T-M7-17 requires **409** for that family and 422 only for
   unknown status strings (T-M7-06 "TELEPORTED"). The range check
   conflated "bad input" with "state-machine violation". Split into: not a
   known status → 422; known but non-target → 409; edge mismatch → 409.
   The same semantics now apply to `update_delivery_status`; the role
   check precedes input checks (the documented authorization order).
3. (Test-side) the threaded race test (T-M7-20) recorded **every**
   exception from the losing thread as a failure — but the loser *should*
   receive the 409 rejection (the service-level form of the 409 response).
   The test now treats exactly `ApiError(409, INVALID_TRANSITION)` as the
   expected losing outcome and re-reads the final state; any other
   exception still fails, and the ledger/state assertions are unchanged.
Also removed a leftover parametrized `_unused` placeholder from the test
file (collected as a 0-case test — harmless, sloppy).

**Actual results (executed 2026-11-08, `backend/.venv`, Python 3.12.14):**
- `pytest tests/test_lifecycle.py`: **25 passed** in 72.6 s (exit 0).
- `pytest` (full suite): **130 passed, 3 skipped** (the same 3 Docker
  tests — no docker CLI on this machine) in 128.7 s. No regressions in
  batches 1–4.

**Documented execution blocker (unchanged):** Docker tests still need the
user's machine (see batch 1 entry).

**Next:** batch 6 — refunds, reviews, owner statistics (canonical M9 +
M8-stats): one refund request per order permanently (D28), the atomic
approval transaction (D30), review eligibility via `delivered_at` (D31),
the D35 metric set.

### 2026-11-08 — batch 6: refunds, reviews, owner statistics (canonical M9 + M8-stats) ✅

**Delivered:**
- `app/services/refunds.py` — the refund-request lifecycle. `request_refund`
  (customer; DELIVERED only; **one request per order permanently, D28** —
  the existing-request check comes first, so a rejected request still
  answers 409). `approve_refund` applies D30 atomically: the central
  machine's `refund` edge (CAS) + payment `refunded` + request `approved`
  + exactly one `refunded` ledger row in one transaction; a double
  approval is a 200 no-op (REF-04). `reject_refund` stamps the request
  rejected and touches nothing on the order (REF-05). Both decisions use a
  *conditional* request update (`WHERE status = 'pending'`), so an
  approve/reject race resolves consistently (single-writer SQLite
  serialization; the loser re-evaluates and rolls back, never leaving a
  REFUNDED order with a non-approved request).
- `app/services/reviews.py` — `create_review`: customer, eligibility =
  **`delivered_at` set** (D31 — survives a later refund), one review per
  order (service check + `uq_reviews_order` backstop).
- `app/services/stats.py` — `GET /owner/stats` per the D35 metric set:
  SQL aggregates over the caller's own restaurant (no restaurant parameter
  exists to probe with); exact integer-cent arithmetic; date range bounds
  `created_at` / ledger-event time / `delivered_at` per the D35
  definitions; `delivered_count` includes later-refunded orders (D31).
- `app/schemas/refunds.py` + `app/schemas/stats.py` — single-purpose
  `extra="forbid"` request bodies and the `OwnerStatsOut` metric shape.
- `app/api/v1/refunds.py`, `reviews.py`, `owner.py` + router registration
  (batch-6 placeholder in `__init__.py` replaced); `refund_status`
  (REF-06) added to `OrderOut`.
- `tests/test_refunds.py` (T-M9-01…07, 13, 14 + threaded double-approval
  race), `tests/test_reviews.py` (T-M9-08, 09, 10, 12 + authz/eligibility
  edges), `tests/test_stats.py` (T-M8-02, T-M8-11 + date range + the
  owner-scoping half of T-M4-16 on stats) — 24 tests, reusing the
  lifecycle file's seed helpers.
- Optional REV-04 (public per-dish review listing) deliberately **not**
  implemented — it is an optional enhancement (M/O = O), not an
  assignment requirement; recorded as deferred-optional.

**Bugs found & fixed while testing** (three, all test-data side — the
service code passed as written):
1. The rest2 seed order inherited `make_order`'s default fee (250) instead
   of rest2's real fee (350) → the scoping assertion expected the wrong
   total. Seeded with `fee=350` explicitly.
2. My `net_retained` expectation was wrong arithmetic (5800 − 2900 = 2900,
   not 1450 — there are *two* refund events, not one).
3. The 30-min-boundary order was seeded exactly 30 min old *before* the
   cutoff was computed, so it fell just outside the range. Seeded at
   20 min instead.

**Actual results (executed 2026-11-08, `backend/.venv`, Python 3.12.14):**
- `pytest tests/test_refunds.py tests/test_reviews.py tests/test_stats.py`:
  **24 passed** in 50.1 s (exit 0).
- `pytest` (full suite): **154 passed, 3 skipped** (the same 3 Docker
  tests — no docker CLI on this machine) in 177 s. No regressions in
  batches 1–5 (the `OrderOut.refund_status` addition was compatible).

**Documented execution blocker (unchanged):** Docker tests still need the
user's machine (see batch 1 entry).

**Next:** batch 7 — the lifespan-managed reminder scanner (D6: 60 s
interval, 15 min stale, PLACED/ACCEPTED, fresh session per tick,
episode-deduped, owner-only retrieval, error-tolerant, clean shutdown;
T-M8-03…07 with a controlled clock) + request-logging middleware
(T-M8-08…10: no secrets in logs, duration, `X-Request-Id`).

### 2026-11-08 — batch 7: reminder scanner + middleware tests (canonical M8 remainder) ✅

**Delivered:**
- `app/services/reminders.py` — `scan_once` (one short transaction:
  detect stale `PLACED`/`ACCEPTED` orders > 15 min → one row per
  (order, status-episode); resolve rows whose order left that status) and
  the `ReminderScanner` managed thread: fresh session per scan (D1),
  injectable clock (D6 — tests use a fake "now", no 15-minute waits),
  a failing scan logs + continues (BG-05), `stop()` joins the thread for
  clean lifespan shutdown. The episode key is `(order_id,
  status_at_reminder)` (D20): the approved machine has no state
  recurrence, so no separate episode counter is needed — the model's
  `uq_reminders_episode` constraint is the dedupe mechanism.
- `app/main.py` — the scanner is now started/stopped in the application
  **lifespan** (gated by `REMINDER_SCANNER_ENABLED`, 60 s interval, 15 min
  threshold from config; stored on `app.state` for observability).
- `app/api/v1/owner.py` — `GET /owner/reminders` (BG-04): owner-only
  (403 otherwise), open reminders of the caller's own restaurant with
  order context, paginated, oldest first; `ReminderOut` added to
  `app/schemas/stats.py`.
- `tests/test_scanner.py` — T-M8-03 (fresh-session-per-scan counted via a
  wrapper factory + real 1 s-interval lifespan wiring with a backdated
  stale order; clean start/stop), T-M8-04 (just-below / exactly-15 /
  just-above the threshold with a fake clock; both eligible states;
  ineligibles ignored), T-M8-05 (dedupe per episode, resolve on progress,
  new episode reminded), T-M8-06 (owner visibility: own rows only,
  resolved hidden, foreign owner sees empty, non-owners 403 — the
  T-M4-16 half), T-M8-07 (a failing scan is logged and the loop
  continues).
- `tests/test_middleware.py` — T-M8-08/09/10 against the batch-1
  `RequestLoggingMiddleware` (caplog-captured `campusbite.request`):
  method+path logged, duration measured, `X-Request-Id`
  propagated/generated/echoed, and **no** bearer tokens / `Bearer` text /
  passwords in any log line.

**Bugs found & fixed while testing:** none in application code — both
new test files passed on their first run (10/10). Two sloppiness items
fixed in the new code before the run (a dead import in `owner.py`; a
naive-datetime fallback in `ReminderOut` construction).

**Actual results (executed 2026-11-08, `backend/.venv`, Python 3.12.14):**
- `pytest tests/test_scanner.py tests/test_middleware.py`: **10 passed**
  in 16.1 s (exit 0).
- `pytest` (full suite): **164 passed, 3 skipped** (the same 3 Docker
  tests — no docker CLI on this machine) in 193.8 s. No regressions —
  the lifespan change (scanner start/stop) is inert for the existing
  suite because `make_test_settings` keeps the scanner disabled.

**Documented execution blocker (unchanged):** Docker tests still need the
user's machine (see batch 1 entry).

### 2026-11-08 — Batch 8: functional React frontend (M11–M13) ✅

**Done** (see the 2026-11-08 handoff for the full per-file detail; this
session finished the work and verified it):

- All 12 pages + auth/cart contexts + api client + routing are in place
  (batch-8 source per the handoff). Final fixes this session: `OrderCard`
  customer+address rows, `ConfirmButton` aria-label, `Menu` filter key
  mapping (D37), plus the mock/harness test-infra fixes (R1–R5) that took
  the suite from 41 failed → **101/101 passing, stable across 3 runs**.
- `npm run build`: ✓ (317 kB JS / 6.7 kB CSS). `npm run lint`: 0 errors,
  5 benign fast-refresh warnings.
- **Browser E2E (now VERIFIED, no longer manual-only):** the installed
  browser-automation skill drove a real headless Chromium against a live
  seeded backend (throwaway `/tmp/campus-smoke` DB, 6 seed users):
  customer checkout (€18.98 = €16.98 + €2.00, exact) → owner
  accept→prepare→ready→assign → partner out-for-delivery→delivered →
  customer review (5★) + refund request → owner approve → REFUNDED +
  refunded payment → second order cancelled from PLACED (one `refunded`
  ledger row). Database verified afterwards: order 6 = REFUNDED/refunded
  with exactly one `refunded` ledger event + preserved review; order 7 =
  CANCELLED/refunded with one reversal; reminder scanner rows appeared for
  both stale seed orders (60 s lifespan scan confirmed live).
  **Zero console errors and zero failed requests across all six runs.**
  Smoke servers were killed and the throwaway DB removed afterwards.
- Docs synced: api-contract batch 8 (`GET /owner/restaurant`,
  `OrderOut.refund_reason`), requirements §11 markers, decisions D37.

**Remaining (not defects):** FE-15 compose preview service (optional,
O). Browser verification of the responsive layout (FE-13) was not
screen-checked — unit-test level only.

### 2026-11-08 — Batch 10: OpenAI order insights (M10) ✅

**Done**

- `backend/app/services/insights.py` — `InsightsService` +
  `InMemoryRateLimiter` (sliding window, per user; documented
  restart-reset/single-worker limitation), app-computed integer-cent stats
  (D35 definitions), PII-light bounded prompt, controlled upstream failure
  mapping (429/504/502), `provider: "unconfigured"` graceful degradation
  (no fake answers), `"deterministic"` for empty history. New:
  `schemas/insights.py`, `api/v1/insights.py` (`POST /insights/question`,
  customer role), router factory seam through `create_app`, test file
  `tests/test_insights.py` (14 tests: role, happy path + exact stats, PII
  exclusion from the prompt, cross-customer isolation, no target-customer
  param, unconfigured, length/empty bounds, rate limit + per-user isolation,
  empty history, upstream 429/timeout/502 mapping — all against a **mocked**
  client; no network, no paid calls).
- Frontend `Insights.jsx` wired to the endpoint: renders the answer, the
  app-computed stats block, the "not configured" notice when
  `provider: "unconfigured"`, and calm 429/503 messages.
- Docs: README (OpenAI section), api-contract §10 (+ changelog),
  requirements §9 marker, decisions D36.

**Actual results (executed 2026-11-08):**

- `backend: .venv/bin/python -m pytest` → **183 passed, 3 skipped** (the 3
  Docker tests; no docker CLI on this machine) in 222 s.
- `frontend: npx vitest run` → **101 passed** (13 files); `npm run build`
  → ✓.
- **Live OpenAI call: NOT made** — the provider integration is implemented
  and mocked-tested; a live paid request requires the user's key/approval.

## Standing rules of engagement (from the development contract)

- Small tasks, approval before edits, real test results only, no invented
  runs.
- Never: implement the whole project at once, rewrite unrelated files, add
  deps without explaining, change requirements to pass tests, weaken tests
  or authorization, read/print real `.env`/credentials, or commit/push/delete
  without approval.
- OpenAI key: backend only. localStorage: per brief, trade-off documented.
