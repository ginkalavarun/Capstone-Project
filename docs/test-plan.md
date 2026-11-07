# CampusBite — Test Plan

> Test IDs are referenced from [requirements.md](requirements.md) and
> [authorization-matrix.md](authorization-matrix.md). Backend tests:
> **pytest + httpx/TestClient**, each in an isolated temporary SQLite DB.
> Frontend tests: **Vitest + React Testing Library** (where marked FE).
> All privileged fixtures are **placeholder credentials** (D2).
>
> Conventions:
> - "actor X calls endpoint E with resource R of actor Y" = the standard
>   negative-authorization pattern (auth ✓, role ✓ or ✗, ownership ✗).
> - Money assertions use integer cents.
> - Time-dependent tests (reminders, expiries) use an **injectable clock**
>   (D6) — no real sleeps of minutes.

## M2 — Scaffold & infrastructure

| ID | Test | Asserts |
|---|---|---|
| T-M2-01 | API error-format smoke | Malformed body → 422 with `{"detail", "code"}` shape (D14) |
| T-M2-02 | OpenAPI docs | `GET /api/v1/docs` and `/api/v1/openapi.json` reachable |
| T-M2-03 | CORS allowlist | Request from a non-allowlisted origin gets no CORS headers; allowlisted origin does (D10) |
| T-M2-04 | Container boot | `docker compose up` → `/api/v1/health` 200 inside the container |
| T-M2-05 | Volume persistence | Write a row, `docker compose down && up` → row survives (D1) |
| T-M2-06 | No secrets in image/repo | Scan built image layers + repo tree for `.env`, known placeholder sentinel → absent (D7) |
| T-M2-07 | `.gitignore` effective | `git status` after local run shows no `*.sqlite3`, `data/`, `.env`, `node_modules`, `dist`, `__pycache__` (D22) |

## M3 — Data model & seed

| ID | Test | Asserts |
|---|---|---|
| T-M3-01 | Schema | All 8 tables exist with expected columns/constraints (DB-01) |
| T-M3-02 | Relationships | ORM navigations work both directions for every brief-listed relationship (DB-02) |
| T-M3-03 | FK enforcement | Inserting an order referencing a missing restaurant raises IntegrityError (SQLite pragma active, D1) |
| T-M3-04 | Snapshot immutability | Changing a menu item's name/price does not change existing order_items rows (D3) |
| T-M3-05 | One review per order (DB) | Second review row for the same order → IntegrityError (unique constraint) |
| T-M3-06 | One refund request per order (DB) | Duplicate request row → IntegrityError |
| T-M3-07 | status_updated_at | Transition service updates the timestamp; reminder dedupe columns present |
| T-M3-08 | Cents columns | All money columns are INTEGER and reject floats/negatives at validation |
| T-M3-09 | Migrations | Fresh DB → `alembic upgrade head` (or auto-apply at boot) yields working schema; a versioned second migration adds a column and upgrades cleanly (D1, D11) |
| T-M3-10 | Persistence | Data written via one session is visible from a new session/process (DB volume semantics) |
| T-M3-11 | Concurrency | Two sessions transition the same order simultaneously → exactly one wins with a valid edge, the other gets INVALID_TRANSITION (no exception 500, no lost/corrupt state) (D1) |
| T-M3-12 | Seed | `python -m app.seed` creates documented dev fixtures; re-running is idempotent; no real credentials appear |

## M4 — Authentication & authorization

| ID | Test | Asserts |
|---|---|---|
| T-M4-01 | Register → customer | Valid payload creates a `customer`; login works (AUTH-01) |
| T-M4-02 | No self-privilege | Payload with `role: owner`/`delivery_partner` → 422, no user created (AUTH-01) |
| T-M4-03 | Login happy + sad | Correct creds → JWT; wrong password → 401; unknown email → 401 (uniform) (AUTH-02) |
| T-M4-04 | bcrypt | Stored hash is bcrypt (`$2b$` prefix); pinned bcrypt round-trips (D4) |
| T-M4-05 | JWT shape | Token verifies with HS256; contains `sub` (user id) + `exp`; tampered signature → 401 (AUTH-04) |
| T-M4-06 | alg=none / wrong alg | `alg: none` or RS256-labeled tokens rejected (D4) |
| T-M4-07 | DB is source of truth | Deactivate the user row → a previously valid token now 401 (D4, AUTH-05) |
| T-M4-08 | Startup guard | Missing or placeholder `JWT_SECRET` → app fails to start (test asserts the config guard) (D4) |
| T-M4-09 | Password limits | <8 or >72-byte passwords → 422 with clear message; 72-byte accepted (D4) |
| T-M4-10 | No secrets in logs | Log capture during register/login/protected call contains no token or password (D4) |
| T-M4-11 | /auth/me | Each role gets own profile; no token without 401 (AUTH-09) |
| T-M4-12 | CLI owner provisioning | Command creates owner + restaurant atomically; failing restaurant data → neither row exists (D2) |
| T-M4-13 | CLI partner provisioning | Creates active delivery partners; no default shared passwords in repo (D2) |
| T-M4-14 | Endpoint sweep (parametrized) | For every protected endpoint: no token → 401; valid role, foreign resource → 404; wrong role → 403 (AUTHZ-01/05) |
| T-M4-15 | Two customers | cust-A cannot GET/POST anything on cust-B's orders (AUTHZ-02) |
| T-M4-16 | Two owners, different restaurants | owner-B cannot manage menu/orders/stats/reminders/refunds of restaurant A (AUTHZ-03) |
| T-M4-17 | Two delivery partners | dp-2 cannot list/view/update orders assigned to dp-1 (AUTHZ-04) |
| T-M4-18 | Status-code policy | Ownership failure → 404 (not 403/200); role failure → 403 (AUTHZ-06) |
| T-M4-19 | Expired token | Backdated `exp` → 401 (D4) |

## M5 — Restaurants & menus

| ID | Test | Asserts |
|---|---|---|
| T-M5-01 | List paginated | `limit/offset` math correct; total reported (RST-01, API-03) |
| T-M5-02 | Detail | Unknown id → 404 (RST-02) |
| T-M5-03 | Menu + dish detail | Dish fields incl. `price_cents` (MENU-01) |
| T-M5-04 | Search by name | Case-insensitive substring; multiple matches; none → empty page (MENU-02) |
| T-M5-05 | Filter by price | `min_price_cents`/`max_price_cents` boundaries inclusive (MENU-02) |
| T-M5-06 | Owner adds dish | Valid → 201; validation errors (missing name, negative price) → 422 (MENU-03) |
| T-M5-07 | Owner updates dish | Name/price/description update persists (MENU-04) |
| T-M5-08 | Toggle availability | `available=false` reflected in reads (MENU-05) |
| T-M5-09 | Non-owner cannot modify | Other owner / customer / partner → 404 on another's menu item (MENU-06) |
| T-M5-10 | Soft delete | DELETE sets unavailable; item stays readable in public catalog as unavailable; historical orders unaffected (RST-03) |

## M6 — Checkout & order placement

| ID | Test | Asserts |
|---|---|---|
| T-M6-01 | Place order | 201; status PLACED; items + `total_cents` returned (CK-01) |
| T-M6-02 | Server-side total | Client sends tampered `total_cents` → ignored; stored total = Σ(snapshot × qty) + fee (CK-02) |
| T-M6-03 | Snapshot | order_items store name + `unit_price_cents` as of placement; later menu changes don't alter them (CK-03) |
| T-M6-04 | Unavailable / foreign items | Any unavailable, missing, or cross-restaurant item → 422, no order created (CK-04, MENU-07) |
| T-M6-05 | Quantity/price validation | qty 0, negative, or non-integer → 422 (CK-04) |
| T-M6-06 | Payment record | Payment ledger row `mock_paid` with `total_cents` + timestamp; payment status on order = mock_paid (CK-05, PAY-01) |
| T-M6-07 | Total math | Mixed items: exact integer-cent sum incl. documented delivery fee (CK-06) |
| T-M6-08 | Own history | Caller sees only own orders; status + date filters work; paginated (ORDR-01) |
| T-M6-09 | Detail shape | Items (snapshots), status, `status_updated_at`, payment state, refund state present (ORDR-02) |

## M7 — Lifecycle & delivery

| ID | Test | Asserts |
|---|---|---|
| T-M7-01 | Full map sweep | Every (from, to) pair: valid edges succeed with correct actor; invalid edges → 409 `INVALID_TRANSITION` (ORDER-01/08) |
| T-M7-02 | Cancel from PLACED | Customer cancels own PLACED → CANCELLED (ORDER-02) |
| T-M7-03 | Cancel not from others | Cancel on ACCEPTED/…/DELIVERED → 409 (ORDER-02/03) |
| T-M7-04 | Delivered not cancellable | DELIVERED → cancel 409 (ORDER-03) |
| T-M7-05 | Accept | Owner PLACED→ACCEPTED; non-owner 404; wrong status 409 (ORDER-04) |
| T-M7-06 | Prep chain | ACCEPTED→PREPARING→READY by owner; skipping (PLACED→READY) 409 (ORDER-05) |
| T-M7-07 | Assign only from READY | Assign on PREPARING → 409; on READY → ASSIGNED (ORDER-06) |
| T-M7-08 | Partner validity | Assigning a customer / deactivated partner → 422 (ORDER-06, D5) |
| T-M7-09 | Partner transitions | Assigned partner OFD→DELIVERED succeeds (ORDER-07) |
| T-M7-10 | Non-assigned partner | Another DP → 404 (ORDER-07, DELV) |
| T-M7-11 | Timestamps | Each transition updates `status_updated_at` (ORDER-09) |
| T-M7-12 | Customer tracking | Customer GET detail reflects latest status + timestamps (ORDER-10) |
| T-M7-13 | Partner list | Only assigned orders; status filter; paginated (DELV-01) |
| T-M7-14 | Partner detail | Includes customer delivery details for assigned orders (DELV-02) |
| T-M7-15 | Partner history | Past completed deliveries listed (DELV-03) |
| T-M7-16 | Partner listing for owners | Owner gets id + display name of **active** partners only — no emails; non-owner → 403 (DELV-04, D5) |

## M8 — Owner dashboard, stats, reminders, middleware

| ID | Test | Asserts |
|---|---|---|
| T-M8-01 | Owner orders | Own-restaurant orders only; status + date filters; pagination (DASH-01) |
| T-M8-02 | Stats | Orders-by-status, revenue (snapshot cents), items sold, avg value, date range; own restaurant only (DASH-02) |
| T-M8-03 | Scanner lifecycle | Scanner starts with app (fake 60 s ticks) and stops on shutdown; fresh session per scan (BG-01) |
| T-M8-04 | Stale detection | Order PLACED with `status_updated_at` 16 min ago (fake clock) → reminder created (BG-02) |
| T-M8-05 | Dedupe + resolve | Second tick in same episode → no duplicate; owner progress to READY → reminder resolved/hidden; re-stale in ACCEPTED → new episode reminder (BG-03) |
| T-M8-06 | Visibility | Other owner / customer / partner cannot read the reminder (BG-04) |
| T-M8-07 | Error isolation | Scan raising (e.g. transient DB error) → logged, app + next tick survive (BG-05) |
| T-M8-08 | Request logging | Middleware logs method + path; never token/password (MW-01) |
| T-M8-09 | Response timing | Middleware records per-request duration observable in logs/monitoring (MW-02) |

## M9 — Refunds & reviews

| ID | Test | Asserts |
|---|---|---|
| T-M9-01 | Refund after delivered | DELIVERED + reason → request pending (REF-01) |
| T-M9-02 | Not before delivery | Request on PREPARING/… → 409 (REF-01) |
| T-M9-03 | One request only | Second request on same order → 409 (REF-02) |
| T-M9-04 | Approve | Owner approves → payment `refunded` + refund ledger row; double-approve → 200 no-op, **one** ledger row (REF-03/04) |
| T-M9-05 | Approve authorization | Other owner / customer / partner → 403/404 (REF-03) |
| T-M9-06 | Reject | Owner rejects → return status `rejected`; order stays DELIVERED; double-decide → 409 (REF-05) |
| T-M9-07 | Customer sees state | Order detail exposes payment + refund status (REF-06) |
| T-M9-08 | Review after delivered | DELIVERED + rating + text → created (REV-01) |
| T-M9-09 | One review | Second → 409 (REV-02) |
| T-M9-10 | DB constraint | Direct duplicate review insert → IntegrityError (REV-03) |
| T-M9-11 | Public reviews (O) | Read-only listing per dish/restaurant; no write path (REV-04) |

## M10 — AI insights (OpenAI mocked)

| ID | Test | Asserts |
|---|---|---|
| T-M10-01 | Happy path (mock) | Question → OpenAI called with bounded context → answer returned (AI-01, AI-10) |
| T-M10-02 | Context isolation | Context payload contains only caller's order ids (AI-02) |
| T-M10-03 | Cross-customer | Craft question mentioning another customer's order id/name → response context + DB query proven to exclude it; no other customer's data in prompt (AI-03) |
| T-M10-04 | No SQL/tool access | Client config exposes no DB/tools; prompt injection strings in question don't leak other users' data or system instructions (AI-04) |
| T-M10-05 | App-side aggregates | "How much did I spend this week?" → correct integer-cent total computed in app code and present in context (AI-05) |
| T-M10-06 | Bounds | 501-char question → 422; 51-order history → truncated to 50 with marker (AI-06) |
| T-M10-07 | Failure mapping | Upstream 500 / timeout / 429 from OpenAI → clean 503/429 with safe message, no stack trace (AI-07) |
| T-M10-08 | Per-user limit | N+1th request in window → 429; different user unaffected; config-driven limit (AI-08) |
| T-M10-09 | Key handling | `OPENAI_API_KEY` absent → feature returns clean 503 (feature degraded), app still serves everything else; key never in frontend bundle (AI-09) |
| T-M10-10 | Mock wiring | All the above run against the mock client; one integration-marked test asserts real-client wiring path (skipped in CI without a key) (AI-10) |

## M11 — Frontend foundation (FE)

| ID | Test | Asserts |
|---|---|---|
| T-M11-01 | Scaffold + router | All role routes render; unknown route → 404 page (FE-01) |
| T-M11-02 | Login/register UI | Form validation, API calls, token stored in localStorage, redirect by role (FE-02/03) |
| T-M11-03 | Auth context | User/role/token propagate via context; logout clears token (FE-03) |
| T-M11-04 | Protected routes | Unauthenticated → redirected to login; role mismatch → 403 page (FE-04) |
| T-M11-05 | API client | Bearer header attached; 401 mid-session → clear token + redirect (FE-05) |
| T-M11-06 | Loading/errors | Async views show loading then error state on failure (FE-14) |

## M12 — Customer frontend (FE)

| ID | Test | Asserts |
|---|---|---|
| T-M12-01 | Cart state | Add/update/remove/quantity in state + localStorage persistence (CART-01) |
| T-M12-02 | Restaurant list | Renders, search/filter inputs wired (FE-06) |
| T-M12-03 | Menu page | Dishes, prices formatted from cents, add-to-cart (FE-07) |
| T-M12-04 | Cart page | Edit quantities, remove, totals displayed (FE-08) |
| T-M12-05 | Checkout | Places order, shows server-computed total, handles 422/409 errors (FE-09) |
| T-M12-06 | Dashboard orders | List + status/date filters + pagination (FE-10) |
| T-M12-07 | Track status | Polls detail; renders current status + timeline (FE-10) |
| T-M12-08 | Cancel | Button only when PLACED; confirms; handles 409 (FE-10) |
| T-M12-09 | Refund request | Form with reason; only when DELIVERED; shows pending/refunded/rejected (FE-10) |
| T-M12-10 | AI insights page | Question box, loading, error states, answer render (FE-10) |
| T-M12-11 | Responsive (manual) | Desktop + mobile viewports: nav, dashboards, cart usable (FE-13) |

## M13 — Owner + delivery frontends (FE)

| ID | Test | Asserts |
|---|---|---|
| T-M13-01 | Owner orders | List + filters + pagination (FE-11) |
| T-M13-02 | Accept/prep/assign UI | Action buttons appear per status; assign picker from protected listing (FE-11) |
| T-M13-03 | Refund management | Pending requests; approve/reject with confirmation (FE-11) |
| T-M13-04 | Reminders | List + "acknowledge/dismiss" (visual) (FE-11) |
| T-M13-05 | Stats + menu mgmt | Stats cards; add/edit/toggle dishes (FE-11) |
| T-M13-06 | Partner assigned list | Assigned deliveries + status filter (FE-12) |
| T-M13-07 | Partner actions | OFD / Delivered buttons with confirmation; 409 handled (FE-12) |
| T-M13-08 | Partner history | Past deliveries list (FE-12) |

## M14 — Packaging & final

| ID | Test | Asserts |
|---|---|---|
| T-M14-01 | README completeness | Every required section present and accurate (run steps verified from a clean machine) (DOC-01) |
| T-M14-02 | Preview via compose (O) | `docker compose up` serves frontend + backend together (FE-15) |
| T-M14-03 | Clean-repo scan | No `.env`, `*.sqlite3`, `data/`, secrets, or node_modules in `git ls-files` (DOC-02) |
| T-M14-04 | E2E golden path (manual) | Register → browse → cart → order → owner accepts/preps/assigns → partner delivers → review + refund → AI question; all three dashboards; reminders fire on a stale order (manual script in README) |
