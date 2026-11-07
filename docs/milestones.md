# CampusBite — Milestone Plan

> 14 milestones, smallest-reviewable-first. Each has **scope** (what gets
> built), **acceptance criteria** (the bar for "done"), and **tests** (IDs
> from [test-plan.md](test-plan.md); requirement IDs from
> [requirements.md](requirements.md)).
>
> **Gate rule:** a milestone is done when *all* its mandatory (M) tests
> pass. Optional (O) items are built only after the milestone's M items are
> green. Nothing moves to the next milestone on red tests.

---

## M1 — Planning & source-of-truth documents ✅ CLOSED (2026-11-07)

- **Scope:** the ten docs in `docs/` (assignment-brief, decisions,
  requirements, authorization-matrix, test-plan, architecture, milestones,
  excluded-features, assumptions, progress).
- **Acceptance:** every brief requirement has an ID + milestone + test; all
  10 user decisions recorded verbatim in intent; AGENTS.md gap flagged; no
  application code exists yet.
- **Tests:** peer review by the user (this document).

## M2 — Backend scaffold & infrastructure

- **Scope:** `backend/` skeleton: FastAPI app, env-driven config
  (`pydantic-settings`), CORS allowlist (D10), error format (D14), health
  endpoint, `/api/v1` base (D14), middleware stubs wired (logging + timing,
  MW-01/02), pytest harness with per-test temp SQLite DB, **Dockerfile**,
  **docker-compose.yml** (backend + named volume), `.env.example`,
  `.gitignore` (D22), `git init` (with your approval — not done in M1).
- **Acceptance:** `docker compose up` → healthy app on :8000 with OpenAPI
  docs; data survives `down`/`up`; no secrets in image/repo; git status clean
  of data files.
- **Tests:** T-M2-01…07.

## M3 — Data model, migrations, seed

- **Scope:** the 8 SQLAlchemy models + relationships (architecture §5);
  FK-pragma event listener (D1); integer-cents money columns (D3); unique
  constraints (review/order, refund request/order); `status_updated_at`;
  Alembic baseline + auto-apply at boot (D11); seed script (D21);
  `data/` volume path.
- **Acceptance:** schema creates cleanly from zero via migrations; all
  integrity rules provable at the DB layer; seed produces a browsable dev
  world.
- **Tests:** T-M3-01…12 (incl. FK enforcement, persistence, concurrent
  transitions, snapshot immutability).

## M4 — Authentication & authorization core

- **Scope:** register (customer-only, D2), login, `/auth/me`; bcrypt (pinned,
  D4); PyJWT issue/verify (HS256-only, exp, sub; D4); startup secret guard;
  `core/deps.py` — `current_user` + role + ownership dependency primitives
  (D8); **CLI provisioning** for owners (+restaurant, one transaction) and
  delivery partners (D2); the full negative-authorization suite (matrix).
- **Acceptance:** all three roles can log in; every protected endpoint
  returns 401/403/404 per the matrix; privileged accounts exist only via CLI;
  logs contain no tokens/passwords.
- **Tests:** T-M4-01…19.

## M5 — Restaurants & menus

- **Scope:** public catalog (list/detail, pagination, search by name, price
  filter — D16); owner menu CRUD + availability toggle (soft delete, RST-03);
  money validation (cents, non-negative, D3).
- **Acceptance:** a stranger can browse; an owner can manage only their menu;
  filters behave at the boundaries.
- **Tests:** T-M5-01…10 (+ AUTHZ cases T-M4-16 reused).

## M6 — Checkout & order placement

- **Scope:** `POST /orders` checkout service (D3): DB-priced snapshot
  computation, availability + same-restaurant validation, integer-cent
  totals with documented delivery fee (D19), payment ledger `mock_paid`;
  customer order history (filters, pagination) + detail shape.
- **Acceptance:** an order exists with provably-correct totals and a payment
  record; tampered client totals are ignored; history shows only own orders.
- **Tests:** T-M6-01…09.

## M7 — Order lifecycle & delivery

- **Scope:** the **central state machine** (D7 map + `transition_order()`
  + `status_updated_at`); customer cancel (PLACED only); owner accept/prep/
  assign (READY only; active-DP validation, D5); partner transitions
  (assigned-only); partner endpoints: assigned list, detail (with delivery
  details), history; protected partner listing for owners (id+name, D5).
- **Acceptance:** every valid edge works for the right actor; every invalid
  edge → 409; the two-lock isolation (role vs assignment) holds for partners.
- **Tests:** T-M7-01…16 (+ T-M4-17).

## M8 — Owner dashboard, stats, reminders, middleware

- **Scope:** owner orders (filters + pagination); **basic stats** (D19) from
  snapshot data; **reminder system** (D6: lifespan scanner, 60 s, fresh
  session, 15-min rule, episode dedupe, resolve-on-progress, owner-only
  visibility, error-safe); request-logging + response-time middleware
  finalized (MW-01/02).
- **Acceptance:** a stale order surfaces a reminder to its owner and only its
  owner within ~2 minutes of the 15-min threshold (fake clock); scanner
  survives its own errors; logs show method/path/duration and no secrets.
- **Tests:** T-M8-01…09.

## M9 — Refunds & reviews

- **Scope:** refund request (DELIVERED-only, reason, one-per-order);
  owner approve/reject (**idempotent** approve; ledger `refunded` row);
  review (DELIVERED-only, one-per-order, DB constraint); customer-facing
  status display fields.
- **Acceptance:** the full refund saga works exactly once; double-approval is
  a no-op with one ledger row; reviews unique per delivered order.
- **Tests:** T-M9-01…11.

## M10 — AI order insights

- **Scope:** `POST /insights` (customer-only): context builder (SQL by caller
  id, bounded, de-PII'd, app-computed aggregates — D9); OpenAI client
  (env key, SDK); error/timeout/rate-limit mapping; configurable per-user
  in-memory limiter (single-worker caveat documented); full mock-based suite.
- **Acceptance:** the four example questions from the brief answer correctly
  against seeded history; another customer's data can never appear; a key
  outage degrades gracefully; the frontend never sees the key.
- **Tests:** T-M10-01…10.

## M11 — Frontend foundation

- **Scope:** Vite + React scaffold; React Router with all role routes;
  `AuthContext` (token in localStorage per brief, trade-off documented);
  protected-route + role-nav wrappers; `api/` fetch client (bearer header,
  uniform error unwrap, 401 handling); reusable primitives (Spinner,
  ErrorState, FilterBar, Pagination); responsive shell.
- **Acceptance:** login/logout flow works against the real backend; an
  unauthenticated user can't reach role pages; nav adapts to role.
- **Tests:** T-M11-01…06.

## M12 — Customer frontend

- **Scope:** restaurants page (search/filter), menu page (cents→$ formatting,
  add-to-cart), cart page (state + persistence, D15), checkout page (shows
  **server** total, handles 422/409); customer dashboard: orders with
  filters + pagination, status tracking (polling), cancel (PLACED only),
  review form, refund form, **AI insights page** (question, loading, errors).
- **Acceptance:** the golden path (architecture §3) is completable in the
  browser end-to-end by a customer.
- **Tests:** T-M12-01…11 (T-M12-11 responsive is a manual checklist).

## M13 — Owner + delivery frontends

- **Scope:** owner dashboard: incoming orders (filters), accept/prep actions,
  assign picker (from protected partner listing), refund approve/reject,
  reminders list, stats cards, menu management; delivery dashboard: assigned
  list + filters, detail with delivery address, OFD/Delivered actions,
  history.
- **Acceptance:** all three dashboards drive the entire lifecycle together in
  the browser (manual E2E, two terminals) and error paths show friendly UI.
- **Tests:** T-M13-01…08 + the manual E2E script.

## M14 — Packaging, docs, final verification

- **Scope:** final `docker-compose.yml` (backend + optional frontend preview,
  FE-15); README (all BR §13 sections + CLI provisioning + single-worker &
  rate-limiter caveats + localStorage trade-off); `.env.example` finalized;
  clean-repo secret/data scan; full test-suite green run documented in
  `progress.md`; prep for the **public** GitHub push (you push; I never do).
- **Acceptance:** a grader following the README from an empty machine reaches
  a running demo with all three roles + AI insights; repo scan is clean.
- **Tests:** T-M14-01…04.

---

## Suggested ordering logic (why this sequence)

1. **Docs first (M1):** every later decision is already settled.
2. **Infra before features (M2–M3):** Docker + DB + tests exist before any
   feature, so every feature is born testable.
3. **Auth before anything protected (M4):** the matrix is enforced from day
   one — no feature ships with a "temporary" auth gap.
4. **Read paths, then writes, then lifecycle (M5→M7):** browse → order →
   manage, matching how the app is used.
5. **Money-adjacent features early (M6, M9):** checkout and refunds are the
   highest-risk business logic; they land while context is fresh.
6. **Frontend in three role-sized slices (M11–M13):** each slice is demoable
   against the real backend immediately.
7. **Packaging last (M14):** README reflects what actually exists.
