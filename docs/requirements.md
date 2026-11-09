# CampusBite — Requirements Checklist

> Every requirement has a **unique ID**, a **M/O** flag
> (**M** = mandatory from the assignment brief; **O** = optional enhancement
> beyond the brief's floor), a **milestone**, and **acceptance tests**
> (IDs resolve in [test-plan.md](test-plan.md)). Decisions referenced as
> (D#) resolve in [decisions.md](decisions.md).
>
> **Legend for source:** BR = assignment brief section; CT = development
> contract business rule; D# = decision log.

---

## 1. Authentication (milestone M4 — ✅ complete in batch 2, 2026-11-07)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| AUTH-01 | Public `POST /auth/register` creates a **customer** account; privileged roles cannot be self-assigned | BR §3, D2 | M | T-M4-01, T-M4-02 |
| AUTH-02 | Login `POST /auth/login` returns a JWT on valid credentials | BR §3 | M | T-M4-03 |
| AUTH-03 | Passwords hashed with **bcrypt** (direct library, pinned version) | BR §3, D4 | M | T-M4-04 |
| AUTH-04 | JWT: **PyJWT, HS256 only**, `exp` required and validated, `sub` = stable user id | BR §3, D4 | M | T-M4-05, T-M4-06 |
| AUTH-05 | Current user **loaded from DB** per request; deleted/deactivated users rejected | CT, D4 | M | T-M4-07 |
| AUTH-06 | Startup refuses to boot on missing/placeholder `JWT_SECRET` | D4 | M | T-M4-08 |
| AUTH-07 | Password input validated against bcrypt's 72-byte effective limit (fail, never truncate) + minimum length | D4 | M | T-M4-09 |
| AUTH-08 | Tokens and passwords never appear in logs | D4 | M | T-M4-10 |
| AUTH-09 | `GET /auth/me` returns the authenticated user's profile (any role) | BR §3 | M | T-M4-11 |
| AUTH-10 | CLI provisioning command creates owners (+ restaurant, one transaction) and delivery partners; no privileged defaults committed | D2 | M | T-M4-12, T-M4-13 |

## 2. Authorization / RBAC (milestone M4, enforced everywhere)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| AUTHZ-01 | Every protected endpoint: auth → role → ownership/assignment (three checks, all server-side) | BR §3, CT, D8 | M | T-M4-14…19 (matrix) |
| AUTHZ-02 | A valid role alone never grants access to another user's resources | CT, D8 | M | T-M4-15 (two customers) |
| AUTHZ-03 | Two owners of different restaurants are isolated | CT, D8 | M | T-M4-16 |
| AUTHZ-04 | Two delivery partners are isolated; only the assigned partner acts | BR §2C, CT, D5 | M | T-M4-17 |
| AUTHZ-05 | Full endpoint coverage in [authorization-matrix.md](authorization-matrix.md) | CT | M | T-M4-14 (parametrized sweep) |
| AUTHZ-06 | Unauthorized access returns 401 (unauthenticated) / 403 (role) / 404 (not owner — hides existence) | CT | M | T-M4-18 |

## 3. Restaurants & menus (milestone M5 — ✅ complete in batch 3, 2026-11-07; MENU-07 enforced at checkout, batch 4)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| RST-01 | List restaurants (paginated) | BR §6, §10 | M | T-M5-01 |
| RST-02 | Restaurant detail | BR §2A3 | M | T-M5-02 |
| MENU-01 | View a restaurant's menu and dish details | BR §2A3 | M | T-M5-03 |
| MENU-02 | Search dishes by **name** and filter by **price** (query params, paginated) | BR §2A4 | M | T-M5-04, T-M5-05 |
| MENU-03 | Owner adds dishes to **their** menu | BR §2B2 | M | T-M5-06, T-M4-16 |
| MENU-04 | Owner views/updates **their** dishes | BR §2B3 | M | T-M5-07 |
| MENU-05 | Owner marks dishes available/unavailable | BR §2B4 | M | T-M5-08 |
| MENU-06 | Non-owner (incl. other owner) cannot modify a menu | BR §3, D8 | M | T-M4-16, T-M5-09 |
| MENU-07 | Unavailable dishes are excluded from checkout (M6) | CT | M | T-M6-04 |
| RST-03 | Dish deletion is a *soft* remove (unavailable) so historical order snapshots stay coherent | D3 | O | T-M5-10 |

## 4. Cart, checkout & order placement (milestone M6 — ✅ complete in batch 4, 2026-11-07)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| CART-01 | Cart managed in React state (+ localStorage persistence) — frontend only, no cart table | BR §9, D15 | M | T-M12-01 |
| CK-01 | `POST /orders` (customer) with item ids + quantities places an order in status `PLACED` | BR §2A7, §4 | M | T-M6-01 |
| CK-02 | **Checkout total computed on the server** from current DB prices; client total never authoritative | CT, D3 | M | T-M6-02 |
| CK-03 | `order_items` snapshots **item name + unit price cents** at order time | CT, D3 | M | T-M6-03 |
| CK-04 | Validate: positive quantities, non-negative prices, items exist, available, same restaurant | D3 | M | T-M6-04, T-M6-05 |
| CK-05 | On placement: payment status `mock_paid` + a **payment ledger record** created | BR §5 | M | T-M6-06 |
| CK-06 | Order totals: `total_cents` = Σ(unit_price_cents × qty) + documented delivery fee (integer cents, EUR — D26) | D3, D26 | M | T-M6-07 |
| CK-07 | Checkout requires a bounded client idempotency key (1–64 chars), stored on the order | batch 2026-11-07, D34 | M | T-M6-10 |
| CK-08 | Identical retry (same customer + key + payload) returns the **original** order; no second order/ledger row | D34 | M | T-M6-11 |
| CK-09 | Same key with a different payload → `409 IDEMPOTENCY_MISMATCH` | D34 | M | T-M6-12 |
| CK-10 | Competing identical checkouts create exactly one order (DB unique backstop) | D34 | M | T-M6-13 |
| PAY-01 | Payment ledger keeps one row per payment event (mock_paid, later refunded) | BR §5, §10 | M | T-M6-06, T-M9-04 |
| ORDR-01 | View **own** order history (paginated, filter by status + date) | BR §2A8, §6 | M | T-M6-08, T-M4-15 |
| ORDR-02 | Order detail includes items (snapshots), status timeline, payment + refund state | BR §2A9 | M | T-M6-09 |

## 5. Order lifecycle (milestone M7 — ✅ complete in batch 5, 2026-11-08)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| ORDER-01 | Central state machine (D7 map) is the only path to change status | CT, D7 | M | T-M7-01 (map sweep) |
| ORDER-02 | Customer cancels **only from PLACED** | BR §4, CT | M | T-M7-02, T-M7-03 |
| ORDER-03 | Delivered orders cannot be cancelled | BR §4 | M | T-M7-04 |
| ORDER-04 | Owner accepts order (PLACED→ACCEPTED) | BR §4 | M | T-M7-05 |
| ORDER-05 | Owner updates prep: ACCEPTED→PREPARING→READY | BR §4 | M | T-M7-06 |
| ORDER-06 | Owner assigns an **active delivery partner** only when READY (READY→ASSIGNED); partner role+active validated | BR §4, D5 | M | T-M7-07, T-M7-08 |
| ORDER-07 | Assigned partner: ASSIGNED→OUT_FOR_DELIVERY→DELIVERED; non-assigned partner rejected | BR §4, D5 | M | T-M7-09, T-M7-10 |
| ORDER-08 | Invalid transitions rejected with 409 + machine-readable code | BR §4, D14 | M | T-M7-01 |
| ORDER-09 | Every transition stamps `status_updated_at` | D6 | M | T-M7-11 |
| ORDER-10 | Customer tracks order status (polling detail endpoint) | BR §2A9 | M | T-M7-12 |
| ORDER-11 | A no-op re-POST of the current state must **not** re-stamp `status_updated_at` (it would reset the reminder clock) | D33, D6 | M | T-M7-17 |

## 6. Delivery partners (milestone M7 — ✅ complete in batch 5, 2026-11-08)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| DELV-01 | Partner sees **only orders assigned to them** (paginated, filter by status) | BR §2C2, §6 | M | T-M7-13, T-M4-17 |
| DELV-02 | Partner sees customer delivery details for assigned orders | BR §2C3 | M | T-M7-14 |
| DELV-03 | Partner delivery history (past completed assignments) | BR §2C6 | M | T-M7-15 |
| DELV-04 | Partner listing for owners: id + display name only, owner-protected, active only | D5 | M | T-M7-16 |
| DELV-05 | Partner cannot cancel, modify, or refund anything | BR §3, D8 | M | T-M4-17 |

## 7. Owner dashboard, stats, reminders (milestone M8 — ✅ complete in batches 5–7, 2026-11-08)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| DASH-01 | Owner views incoming orders for **their** restaurant, filter by status + date (paginated) | BR §2B5, §6 | M | T-M8-01, T-M4-16 |
| DASH-02 | Basic restaurant statistics, the **D35 metric set** (orders by status, gross mock-paid, refunded, net retained, delivered count, items sold, avg order value, date range) — own restaurant only; no metric is blindly called "revenue" | BR §2B9, D19, D35 | M | T-M8-02 |
| BG-01 | Lifespan-managed scanner every 60 s (single worker); fresh session per scan | BR §8, D1, D6 | M | T-M8-03 (fake clock) |
| BG-02 | Finds PLACED/ACCEPTED orders with `status_updated_at` > 15 min | BR §8, D6 | M | T-M8-04 |
| BG-03 | Dedupe per (order, status) episode; resolve when order progresses | D6, D20 | M | T-M8-05 |
| BG-04 | Reminders visible to the restaurant owner only | BR §8, D6 | M | T-M8-06, T-M4-16 |
| BG-05 | Scan errors logged, never crash the app; clean shutdown | D6 | M | T-M8-07 |
| MW-01 | Middleware logs request method + path (no tokens/passwords) | BR §8, D4 | M | T-M8-08 |
| MW-02 | Middleware measures + records API response time | BR §8 | M | T-M8-09 |
| MW-03 | Middleware attaches/propagates an `X-Request-Id`; logs never contain auth headers, tokens, passwords, keys, or full delivery addresses | batch 2026-11-07 | M | T-M8-10 |

## 8. Refunds & reviews (milestone M9 — ✅ complete in batch 6, 2026-11-08; optional REV-04 public listing deferred)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| REF-01 | Customer requests refund **only after DELIVERED**, with a required reason | BR §5 | M | T-M9-01, T-M9-02 |
| REF-02 | **One refund request per order, permanently** — including after rejection; no second-request flow (D28) | BR §5, CT, D28 | M | T-M9-03, T-M9-13 |
| REF-03 | Owner (of the order's restaurant) approves or rejects | BR §5 | M | T-M9-05, T-M4-16 |
| REF-04 | Approved → payment status `refunded` + refund ledger record; **idempotent** (double-approval never creates a second refund) | BR §5, CT, D7 | M | T-M9-04 |
| REF-05 | Rejected → return status `rejected`; order status unchanged (stays DELIVERED) | BR §5 | M | T-M9-06 |
| REF-06 | Customer sees payment + refund status on their order | BR §6 | M | T-M9-07 |
| REV-01 | Customer submits a rating + review **only for delivered orders** | BR §2A11 | M | T-M9-08 |
| REV-02 | **One review per order** (second rejected; update optional) | CT | M | T-M9-09 |
| REV-03 | One review per delivered order enforced in DB (unique constraint) | BR §10 | M | T-M9-10 |
| REV-04 | Reviews visible to other customers on the dish/restaurant (read-only) | BR §2A11 | O | T-M9-11 |
| REV-05 | Review eligibility = order **actually delivered** (`delivered_at` set), including orders later refunded; no review edit/delete in this batch | D31 | M | T-M9-12 |

## 9. AI order insights (milestone M10 — ✅ complete in batch 10, 2026-11-08; live provider call is a user action)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| AI-01 | Customer asks questions about **their own** order history; answer rendered in React | BR §7 | M | T-M10-01 (mock) |
| AI-02 | Context built from DB rows filtered by **authenticated user id** only; no target-customer param accepted | BR §7, D9 | M | T-M10-02 |
| AI-03 | **Cross-customer isolation**: a question cannot surface another customer's data | BR §7, D9 | M | T-M10-03 |
| AI-04 | No model-generated SQL / no DB tool access; bounded pre-serialized context | D9 | M | T-M10-04 |
| AI-05 | Exact monetary aggregates computed in app code and provided as context | D9 | M | T-M10-05 |
| AI-06 | Bounds: question length (≤500 ch) + history window (≤50 orders) enforced | D9 | M | T-M10-06 |
| AI-07 | Error handling: upstream error, timeout, **rate limit** → clean 5xx/429, no stack traces | BR §7, D9 | M | T-M10-07 |
| AI-08 | Configurable per-user rate limit (in-memory; single-worker caveat documented) | BR §7, D9 | M | T-M10-08 |
| AI-09 | OpenAI key backend-env only; never in frontend code/bundle | BR §7, contract | M | T-M10-09 (bundle scan) |
| AI-10 | OpenAI **mocked** in automated tests; real client wiring retained | D9 | M | T-M10-01…10 |
| AI-11 | Non-customers (owner/partner) cannot use the insights endpoint | D8 | M | T-M4-14 |

## 10. Database (milestone M3)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| DB-01 | Tables: Users, Restaurants, MenuItems, Orders, OrderItems, Reviews, PaymentLedger, ReminderLogs **+ RefundRequests** (the 9th, justified by BR §5 return mechanics; count reconciled 2026-11-07) | BR §10/§5, database.md | M | T-M3-01 |
| DB-02 | Relationships per brief (customer→orders; restaurant→items/orders; order→items; delivered order→1 review; order→payment entries; partner→orders) | BR §10 | M | T-M3-02 |
| DB-03 | FKs enforced on every connection (SQLite pragma) | D1 | M | T-M3-03 |
| DB-04 | `order_items` snapshot columns (item_name, unit_price_cents) immutable after order | D3 | M | T-M3-04 |
| DB-05 | Reviews: unique per order (DB constraint) | BR §10, REV-03 | M | T-M3-05 |
| DB-06 | Refund request: unique per order (DB constraint) | REF-02 | M | T-M3-06 |
| DB-07 | `status_updated_at` maintained on orders; reminder dedupe key columns | D6 | M | T-M3-07 |
| DB-08 | Integer-cents money columns everywhere | D3 | M | T-M3-08 |
| DB-09 | Versioned migrations (Alembic), auto-applied + documented manual step | D1, D11 | M | T-M3-09 |
| DB-10 | Persistence across container restart (volume) | D1 | M | T-M3-10 |
| DB-11 | Concurrency: overlapping order updates behave correctly (no lost writes/exceptions) | D1 | M | T-M3-11 |
| DB-12 | Seed script: dev-only sample data, documented, no real credentials | D2, D21 | M | T-M3-12 |
| DB-13 | `orders.delivered_at` set once on DELIVERED, never cleared (survives REFUNDED); review eligibility uses it (D31) | D31 | M | T-M3-24, T-M9-12 |
| DB-14 | Idempotency columns on orders + UNIQUE(customer_id, idempotency_key) + request_hash (D34) | D34 | M | T-M3-25 |

## 11. Frontend (milestones M11–M13 — ✅ complete in batch 8, 2026-11-08; browser E2E verified, FE-15 optional-compose deferred)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| FE-01 | React + JS (ES6+) + Hooks + React Router DOM | BR §1, §9 | M | T-M11-01 |
| FE-02 | Login + registration pages | BR §9 | M | T-M11-02 |
| FE-03 | Auth context (user, role, token) via `useContext`; token in **localStorage** (brief requirement; trade-off documented) | BR §3, §9, D4 | M | T-M11-03 |
| FE-04 | Protected routes + role-based navigation; hiding is UX only (backend enforces) | BR §3, §9 | M | T-M11-04 |
| FE-05 | API client attaches `Authorization: Bearer` to protected calls; uniform error/loading states | BR §9 | M | T-M11-05 |
| FE-06 | Restaurant listing page (search/filter from MENU-02) | BR §9 | M | T-M12-02 |
| FE-07 | Restaurant menu page + dish detail | BR §9 | M | T-M12-03 |
| FE-08 | Cart page: add/update/remove/quantities (frontend state, persisted) | BR §2A5-6, §9 | M | T-M12-04 |
| FE-09 | Checkout page → places order, handles server-computed total display + errors | BR §9 | M | T-M12-05 |
| FE-10 | Customer dashboard: orders (filter status/date), track status (polling), cancel eligible, refund request, review submit, AI insights page | BR §6, §9 | M | T-M12-06…10 |
| FE-11 | Owner dashboard: incoming orders (filters), accept/prep/assign, refund approve/reject, reminders list, stats, menu management | BR §6, §9 | M | T-M13-01…05 |
| FE-12 | Delivery dashboard: assigned deliveries (filter), delivery details, status updates, history | BR §6, §9 | M | T-M13-06…08 |
| FE-13 | Responsive layout (desktop + mobile) | BR §9 | M | T-M12-11 (manual) |
| FE-14 | Loading states + error boundaries on all async views | BR §9 | M | T-M11-06 |
| FE-15 | Vite dev server + build; preview mode via compose (optional service) | D12, D13 | O | T-M14-02 |
| FE-16 | Accessible labels + keyboard-usable controls on all forms/actions (batch M8) | batch 2026-11-07 | M | T-M11-08 |
| FE-17 | 401/token-expiry handling redirects to login **once** — no endless redirect loop; cart is cleared/isolated on account change | batch 2026-11-07, D4, D15 | M | T-M11-07, T-M12-12 |

## 12. API, Docker, deployment (milestones M2, M14)

| ID | Requirement | Src | M/O | Test |
|---|---|---|---|---|
| API-01 | RESTful API with proper validation, status codes, error format (`detail` + machine `code`) | BR §12, D14 | M | T-M2-01, all |
| API-02 | OpenAPI/Swagger docs available | BR §13 | M | T-M2-02 |
| API-03 | Pagination (limit/offset or cursor) on all list endpoints | BR §6 | M | T-M5-01, T-M6-08, T-M7-13, T-M8-01 |
| API-04 | CORS explicit allowlist, configurable, no wildcard | D10 | M | T-M2-03 |
| DOCKER-01 | Backend Dockerfile; starts correctly in container | BR §11 | M | T-M2-04 |
| DOCKER-02 | `docker-compose.yml` runs the backend; DB in a persistent volume; port exposed | BR §11, D1 | M | T-M2-05 |
| DOCKER-03 | Secrets out of image and repo; `.env.example` with placeholders + docs | BR §11, D23, D22 | M | T-M2-06 |
| DOC-01 | README: overview, tech, features, run frontend, run backend via compose, env vars, DB setup, API docs, CLI provisioning, single-worker + rate-limiter caveats | BR §13 | M | T-M14-01 |
| DOC-02 | `.gitignore` excludes `*.sqlite3`, `data/`, `.env`, `node_modules`, `dist`, `__pycache__`, `.venv` | D1, D22 | M | T-M2-07, T-M14-03 |
| DOC-03 | Public GitHub repo ready (user pushes; never auto-pushed by us) | BR §submission | M | T-M14-04 (manual) |
| DOC-04 | `AGENTS.md` present in repo (content pending user-provided file) | user | M | ✅ present (A1 resolved) |
| DOC-05 | `docs/learning-log.md` explaining the ten contract topics with actual implemented filenames/function names | batch 2026-11-07 (M9) | M | T-M14-05 |
| DOC-06 | `docs/api-contract.md` exists and stays synchronized with the implemented API (endpoint, shapes, roles/ownership, status codes, pagination, money/timestamp conventions) | batch 2026-11-07 (M3) | M | T-M14-06 |

---

## Mandatory vs optional — how to read this

- **Mandatory (M):** appears in the assignment brief (or is a direct
  consequence of a brief requirement + approved decision). The grade depends
  on these.
- **Optional (O):** enhancements beyond the brief's floor — e.g. soft delete
  (RST-03), public review display (REV-04), compose preview service (FE-15).
  We build them **only after** every M for that milestone is green, and any
  of them can be cut without violating the brief.
- The brief's word **"basic"** (basic statistics, basic error/rate-limit
  handling) marks the *floor*: D19 and D9 define exactly what "basic" means
  for this project; going beyond it (real analytics dashboard, Redis-based
  limiting) is optional scope, not required.
