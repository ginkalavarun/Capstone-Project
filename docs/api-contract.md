# CampusBite — API Contract

> **Status: implemented through batch 7** (health, auth, restaurants, menu,
> orders/checkout, order lifecycle & role dashboards, refunds, reviews,
> owner statistics, owner reminders).
> This document is the human-readable contract for the backend API. It must
> stay synchronized with the code (DOC-06): every endpoint batch updates the
> matching section *and* the changelog. The machine-generated OpenAPI
> (`/api/v1/docs`) is always current by construction; this file adds what
> OpenAPI cannot express — authorization policy, ownership rules, and
> conventions.

## 1. Conventions

### Base path & docs
- All endpoints live under **`/api/v1`** (D14). Version bumps mean a new
  prefix (`/api/v2`), never breaking changes under the same prefix.
- Interactive docs: `GET /api/v1/docs` (Swagger UI), `/api/v1/redoc`,
  `/api/v1/openapi.json` (API-02).

### Authentication (D4, D8)
- Bearer JWT: `Authorization: Bearer <token>`.
- HS256 only; `sub` = user id (stringified integer); `exp` required.
- Access tokens only (no refresh tokens in v1). The token grants
  *authentication*; the **database** is the source of truth for role and
  active state (a deactivated user's token stops working on the next
  request).
- Endpoints marked **public** (the catalog, D16) need no token.

### Authorization check order (every protected endpoint, AUTHZ-01)
1. **Auth** — missing/malformed/invalid/expired token, or deactivated user
   → `401`.
2. **Role** — DB role not allowed for the action → `403`.
3. **Ownership / assignment** — the resource does not belong to the caller
   (or the caller is not the assigned partner) → `404` (we hide existence;
   a `403` would leak that the resource exists — AUTHZ-06).
4. **State-machine edge** (lifecycle endpoints, batch 5) — the requested
   transition does not match the order's current status → `409
   INVALID_TRANSITION`. Nothing is written and `status_updated_at` is
   untouched (ORDER-11).

A valid role alone never grants access to another user's resources (D8).

### Errors (D14)
Every non-2xx body is exactly:

```json
{"detail": "Human-readable sentence.", "code": "MACHINE_CODE"}
```

`code` is a stable token the frontend branches on. Implemented codes:

| Code | Meaning |
|---|---|
| `TOKEN_MISSING` | No/empty bearer token |
| `TOKEN_MALFORMED` | Header present but empty token |
| `TOKEN_INVALID` | Bad signature/algorithm/claims/subject |
| `TOKEN_EXPIRED` | `exp` in the past |
| `USER_INACTIVE` | Account deactivated |
| `INVALID_CREDENTIALS` | Login failure (uniform — no enumeration) |
| `EMAIL_TAKEN` | Registration: email already registered |
| `PASSWORD_POLICY` | Password fails the 8–72 byte policy |
| `VALIDATION_ERROR` | Request body/params failed validation |
| `ROLE_FORBIDDEN` | Authenticated, but role not allowed |
| `NOT_FOUND` | Resource missing, **or** ownership failure (by design) |
| `IDEMPOTENCY_MISMATCH` | Same checkout key, different payload (batch 4, D34) |
| `INVALID_TRANSITION` | Requested order transition does not match the current status (batch 5) |
| `REFUND_REQUEST_EXISTS` | The order already has a refund request — one per order, permanently (batch 6, D28) |
| `ORDER_INELIGIBLE` | The action is impossible in the order's state (refund request before delivery, review before `delivered_at`) (batch 6) |
| `REFUND_ALREADY_DECIDED` | The refund request was already approved or rejected (batch 6) |
| `REVIEW_EXISTS` | The order already has a review (batch 6, REV-02/03) |
| `INTERNAL` | Unhandled error (details logged server-side only) |

Planned codes (later batches): `RATE_LIMITED`, …

### Money (D3, D26)
- One currency: **EUR**. All money fields are **integer cents** and use the
  suffix `_cents` (`price_cents`, `total_cents`, …). No floats, ever.
- Prices/fees are non-negative (`>= 0`); a sanity cap of `10_000_000`
  (€100,000) rejects obvious decimal-point bugs with 422.
- **The server computes all totals.** Clients send item ids + quantities;
  any client-submitted price/total is ignored or rejected.

### Timestamps (D33)
- Aware UTC, serialized as ISO-8601 with explicit offset, e.g.
  `2026-11-07T18:03:12.123456+00:00`. The app generates all timestamps
  (`utcnow()`); clients never supply them.

### Pagination (API-03)
- Every list endpoint accepts `limit` (default **20**, min 1, max **100**)
  and `offset` (min 0).
- List responses use the envelope:

```json
{"items": [ … ], "total": 42, "limit": 20, "offset": 0}
```

`total` counts **all rows matching the filters** (not just the page), so a
client can render pages and "showing X of Y".

### CORS (D10)
- Explicit allowlist (`CORS_ORIGINS`, comma-separated origins); development
  default `http://localhost:5173`. Never a wildcard. CORS is a browser
  convenience, not a security boundary — every rule above still applies.

---

## 2. Health

| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/api/v1/health` | none | `{"status": "ok"}` — liveness |
| GET | `/api/v1/health/db` | none | `{"status": "ok"|"degraded", "database": "reachable", "foreign_keys_enabled": bool}` — DB reachable + FK pragma enabled (D1). Never exposes configuration or credentials. |

## 3. Authentication (batch 2)

### POST /api/v1/auth/register — *public* (D2: creates customers only)
Request: `{"email": "user@example.com", "password": "…", "full_name": "…", "role"?: …}`
- `email` — valid address; normalized to lowercase.
- `password` — 8–72 **bytes** (bcrypt's effective limit; never truncated —
  a violation is a 422, not silent data loss).
- `full_name` — 1–120 chars.
- **`extra` fields are rejected (422)** — in particular any attempt to set
  `role` (D2: privileged roles are provisioned locally, never self-assigned).

| Status | Meaning |
|---|---|
| `201` | Created. Body: `{"user": {"id","email","full_name","role","is_active"}}` — **no token** (log in to get one), never the password hash. |
| `409` | `EMAIL_TAKEN` |
| `422` | `VALIDATION_ERROR` (bad email/fields) or `PASSWORD_POLICY` |

### POST /api/v1/auth/login — *public*
Request: `{"email", "password"}`.
| Status | Meaning |
|---|---|
| `200` | `{"access_token", "token_type": "bearer", "user": {…UserOut}}`. Token: HS256, `sub`=user id, `type="access"`, `exp` = now + `JWT_EXPIRE_MINUTES`. |
| `401` | `INVALID_CREDENTIALS` (wrong password **or** unknown email — deliberately uniform, prevents enumeration) or `USER_INACTIVE`. |

### GET /api/v1/auth/me — *authenticated* (any role)
Returns the caller's `UserOut` (id, email, full_name, role, is_active).
Re-loads the user from the DB per request (AUTH-05).

## 4. Restaurants — public catalog (batch 3, D16)

### GET /api/v1/restaurants
Query: `limit`, `offset` (conventions §pagination).
Response: `Page<RestaurantOut>` ordered by name.
`RestaurantOut` = `{id, name, description, address, delivery_fee_cents, created_at, updated_at}`.

### GET /api/v1/restaurants/{id}
`200` → `RestaurantOut`; `404 NOT_FOUND` for unknown ids.

### GET /api/v1/restaurants/{id}/menu
Query: `limit`, `offset`, plus:
| Param | Type | Bounds | Effect |
|---|---|---|---|
| `search` | string | ≤120 chars | Case-insensitive **substring** on dish name; `%`/`_` are treated as literals (LIKE-escaped). No match → empty page (200). |
| `min_price_cents` | int | 0…10,000,000 | `price_cents >=` value (**inclusive**) |
| `max_price_cents` | int | 0…10,000,000 | `price_cents <=` value (**inclusive**) |

Response: `Page<MenuItemOut>` ordered by name.
`MenuItemOut` = `{id, restaurant_id, name, description, price_cents, available, created_at, updated_at}`.
Soft-removed dishes remain listed with `available: false` (RST-03); **checkout
excludes them** (MENU-07, batch 4). `404 NOT_FOUND` for unknown restaurant.

## 5. Menu management — owner only (batch 3, D8)

All three require: valid token → role `restaurant_owner` (else `403
ROLE_FORBIDDEN`) → ownership of the restaurant (else `404 NOT_FOUND`).

### POST /api/v1/restaurants/{restaurant_id}/menu
Owner adds a dish to **their** restaurant. Body `CreateMenuItemIn`:
`{name: 1–120 (whitespace-only rejected), description?: ≤1000, price_cents: 0…10M, available: bool = true}`; extra fields → 422.
`201` → `MenuItemOut`. `404` if the restaurant is not the caller's.

### PUT /api/v1/menu-items/{menu_item_id}
Owner updates a dish (name / description / price_cents / available).
**Partial update**: only fields present in the body change; for
`description`, `null` = keep, `""` = clear. Empty body → `422`; extra
fields → `422`; negative price → `422`.
`200` → updated `MenuItemOut`. Historical order snapshots are unaffected (D3).

### DELETE /api/v1/menu-items/{menu_item_id}
**Soft remove** (RST-03/D32): sets `available=false`. The row is never
hard-deleted — it stays readable in the public catalog and past orders keep
their snapshots. `204` no body.

---

## 6. Orders (batch 4 — checkout & views)

### POST /api/v1/orders — customer only
Body (`CheckoutIn`; **unknown fields ignored** — CK-02/T-M6-02):

| Field | Type | Bounds | Notes |
|---|---|---|---|
| `items` | array (≥1) | line: `{menu_item_id: >0, quantity: 1…100}` | Duplicate lines for the same dish merge into one receipt line. |
| `delivery_address` | string | 1–255, not blank | Snapshotted on the order. |
| `idempotency_key` | string | 1–64 chars (D34) | Client-generated; scoped to the authenticated customer. Used as-is. |

Server behavior (all recomputed from the DB — D3): every item must exist,
be **available**, and belong to **one** restaurant (else 422); totals are
`Σ snapshot_price × qty` + the restaurant's current delivery fee (integer
cents, EUR). Placement writes the order (PLACED / mock_paid), the snapshot
terms, and one `mock_paid` ledger row in a **single transaction**.

| Status | Meaning |
|---|---|
| `201` | New order created. Body: `OrderOut` (below). |
| `200` | Idempotent retry: identical key + identical payload → the **original** order (D34). |
| `409` | `IDEMPOTENCY_MISMATCH` — same key, different payload. |
| `403` | Not a customer. |
| `422` | Validation (bad items/quantities/address/key bounds). |

`OrderOut` = `{id, status, payment_status, refund_status, status_updated_at,
delivered_at, restaurant_id, restaurant_name, customer_id, customer_name,
delivery_partner_id, delivery_address, items_subtotal_cents,
delivery_fee_cents, total_cents, items: [{id, menu_item_id, item_name,
unit_price_cents, quantity, line_total_cents}], created_at}`
(`restaurant_name`/`customer_name` are resolved from the users/restaurant
tables at response time; `customer_name` was added in batch 5 — the
assigned partner must know who to contact, DELV-02. `refund_status` —
`null` / `pending` / `approved` / `rejected` — was added in batch 6 so the
purchasing customer sees the refund state, REF-06).

### GET /api/v1/orders — customer only (ORDR-01)
Query: `limit`, `offset`, `status` (one of the order statuses),
`date_from`/`date_to` (ISO-8601 bounds on `created_at`).
Response: `Page<OrderOut>`, newest first. Only the caller's own orders are
ever visible (AUTHZ-02).

### GET /api/v1/orders/{id} (ORDR-02, D8)
Allowed: the order's customer, the owner of its restaurant, or its assigned
delivery partner. Anyone else (including another customer/owner/partner) →
`404` (existence hidden). Response: `OrderOut` (batch 8 adds
`refund_reason` — the customer's request text when a refund request exists,
so the owner can decide without a second round-trip).

## 7. Order lifecycle & role dashboards (batch 5)

All mutations go through the **central state machine**
(`app/services/transitions.py`, D7) — there is no generic "set status"
endpoint; every route maps to one named action with one explicit edge.
Check order: role (`403`) → ownership/assignment (`404`, existence hidden,
AUTHZ-06) → state-machine edge (`409 INVALID_TRANSITION`, a
compare-and-swap `UPDATE … WHERE status = <from>` — under concurrent
requests the database arbitrates: exactly one winner commits, losers
receive `409` and change nothing, including `status_updated_at`,
ORDER-11).

Status values: `PLACED ACCEPTED PREPARING READY ASSIGNED OUT_FOR_DELIVERY
DELIVERED CANCELLED REFUNDED`. Payment values: `mock_paid`, `refunded`.
All mutation endpoints return the updated `OrderOut`.

### POST /api/v1/orders/{id}/cancel — *customer*
| Check | Failure |
|---|---|
| role ≠ customer | `403` |
| not the order's customer | `404` |
| status ≠ PLACED (incl. a second cancel) | `409 INVALID_TRANSITION` |

Cancellation is a **mock payment reversal (D29)**, not a refund request:
one transaction sets status `CANCELLED` + payment `refunded` and appends
one `refunded` ledger row for the full `total_cents` (delivery fee
included, D27). **No `refund_requests` row** — that table is the
post-delivery path (batch 6). `delivered_at` stays `null`.

### POST /api/v1/orders/{id}/accept — *owner of the restaurant*
`403` wrong role; `404` not the owner; edge **PLACED → ACCEPTED** (else
`409`).

### POST /api/v1/orders/{id}/status — *owner of the restaurant* (prep chain)
Body `{"status": …}` — exactly one field, extras → `422` (`extra="forbid"`).
Target semantics (T-M7-06/T-M7-17):

| Target | Result |
|---|---|
| not a known order status (e.g. `TELEPORTED`) | `422 VALIDATION_ERROR` |
| a known status that is not PREPARING/READY — incl. re-POSTing the order's current state | `409 INVALID_TRANSITION` |
| `PREPARING` while ACCEPTED, or `READY` while PREPARING | `200` → `OrderOut` |
| any other edge mismatch | `409 INVALID_TRANSITION` |

Rejections write nothing, so `status_updated_at` is never re-stamped
(it is the reminder clock — D6/D33).

### POST /api/v1/orders/{id}/assign — *owner of the restaurant*
Body `{"delivery_partner_id": n}` — exactly one field, extras → `422`.
The partner must exist, have role `delivery_partner`, and be **active**
else `422`. Edge **READY → ASSIGNED** (else `409`); the partner id is
stored on the order in the same transaction.

### POST /api/v1/orders/{id}/delivery-status — *assigned partner only*
Body as the prep endpoint. Targets `OUT_FOR_DELIVERY` (from ASSIGNED) or
`DELIVERED` (from OUT_FOR_DELIVERY); unknown / non-target targets →
`422` / `409` as above. Completing delivery stamps `delivered_at` (D31 —
review eligibility survives a later refund). A partner who is not the
order's assigned partner → `404` (they cannot even see it).

### GET /api/v1/owner/orders — *owner* (DASH-01)
Incoming orders for **the caller's own restaurant** only (one restaurant
per owner, D24) — `Page<OrderOut>`, newest first.
Query: `limit`, `offset`, `status` (known status, else `422`),
`date_from`/`date_to` (ISO-8601 bounds on `created_at`).

### GET /api/v1/delivery-partners — *owner* (DELV-04, D5)
`[{id, full_name}]` — **active** delivery partners only, and **only those
two fields** (no emails or other personal data — the minimum an owner
needs to pick a deliverer). Non-owners → `403`.

### GET /api/v1/delivery/orders — *partner* (DELV-01)
Orders **assigned to the caller** whose status is not DELIVERED/REFUNDED
(the active workload). Query: `limit`, `offset`, `status`. Ordered by
`status_updated_at` desc.

### GET /api/v1/delivery/history — *partner* (DELV-03)
The caller's past completed assignments (DELIVERED, incl. later-REFUNDED).
Same query params. Ordered by `delivered_at` desc, nulls last.

### GET /api/v1/delivery/orders/{id} — *assigned partner* (DELV-02)
Full `OrderOut`, including `customer_name` + `delivery_address`. Any
partner who is not the order's assigned partner (and every other role) →
`404`.

---

## 8. Refunds, reviews & owner statistics (batch 6)

### POST /api/v1/orders/{id}/refund-request — *customer*
Body `{"reason": 1–1000 chars, not blank}` — exactly one field, extras →
`422`.

| Check | Failure |
|---|---|
| role ≠ customer | `403` |
| not the order's customer | `404` |
| a request already exists — pending, approved, **or rejected** (D28: one request per order, **permanently**) | `409 REFUND_REQUEST_EXISTS` |
| order not DELIVERED | `409 ORDER_INELIGIBLE` |

`201` → `RefundRequestOut` = `{id, order_id, status, reason,
requested_at, decided_at}` (`decided_by` omitted — the decider is the
restaurant's owner by construction).

### POST /api/v1/orders/{id}/refund/approve — *owner of the restaurant*
`403` wrong role; `404` not the owner **or no request exists** (existence
hidden, AUTHZ-06).

- request **pending** → **one transaction** (D30): order `REFUNDED`
  (the central machine's `refund` edge, compare-and-swap) + payment
  `refunded` + request `approved` (decided at/by stamped) + **exactly one**
  `refunded` ledger row for the full `total_cents` (D27 incl. fee).
  `200` → `OrderOut`.
- request already **approved** → `200` **no-op** (REF-04: a double
  approval — even under a race — never creates a second refund ledger row).
- request **rejected** → `409 REFUND_ALREADY_DECIDED`.

### POST /api/v1/orders/{id}/refund/reject — *owner of the restaurant*
Same `403`/`404` checks. The request becomes `rejected` (decision stamped);
the order and payment are **untouched** (REF-05: it stays DELIVERED /
mock_paid). Deciding twice → `409 REFUND_ALREADY_DECIDED`. The one-request
rule (D28) still blocks any new request afterwards.

### POST /api/v1/orders/{id}/review — *customer*
Body `{"rating": 1–5, "comment"?: ≤1000 chars}` — exactly those fields,
extras → `422`; rating outside 1–5 → `422`.

| Check | Failure |
|---|---|
| role ≠ customer / not the order's customer | `403` / `404` |
| order not actually delivered (`delivered_at` null — D31; a **later refund does not invalidate** eligibility) | `409 ORDER_INELIGIBLE` |
| a review already exists (REV-02/03; `uq_reviews_order` backstop) | `409 REVIEW_EXISTS` |

`201` → `ReviewOut` = `{id, order_id, rating, comment, created_at}`.
No edit/delete path exists in this batch (approved scope, D31). (The
optional public per-dish review listing, REV-04, is not implemented in
this batch — optional enhancement, not an assignment requirement.)

### GET /api/v1/owner/stats — *owner* (DASH-02, the D35 metric set)
Own restaurant only — **no restaurant parameter exists**, so there is no
way to probe another restaurant. Query: `date_from`/`date_to`
(ISO-8601; bounds `created_at` for the order-based metrics, the event
timestamp for `refunded_cents`, and `delivered_at` for `delivered_count`).

Response `OwnerStatsOut` (all money = integer cents, EUR):
`currency`, `date_from`, `date_to`, `placed_order_count`,
`orders_by_status` (all nine statuses, zero-filled),
`gross_mock_paid_cents` (Σ `total_cents` of the range's placed orders —
every placement produced one `mock_paid` event), `refunded_cents` (Σ
`refunded` ledger events in the range — cancellation reversals **and**
approved refunds), `net_retained_cents` (gross − refunded, exactly),
`delivered_count` (actually delivered in the range — **including**
later-refunded orders, D31), `items_sold` (Σ line quantities),
`avg_order_value_cents` (gross ÷ placed count, integer floor).
Definitions are documented, never blindly called "revenue" (D35).

### GET /api/v1/owner/restaurant — *owner* (batch 8, frontend enablement)
The caller's **own** restaurant (one owner = at most one restaurant, D24).
No restaurant parameter exists. Non-owners → `403`; an owner without a
restaurant → `404`. Response: `RestaurantOut`. The owner menu-management
UI uses it to learn its restaurant id.

---

## 9. Owner reminders (batch 7)

### GET /api/v1/owner/reminders — *owner* (BG-04, D6)
The **open** stale-order reminders for the caller's own restaurant (one
restaurant per owner, D24) — paginated (`limit`/`offset`), oldest detected
first. A different owner gets their own (empty) list — never another
restaurant's rows; non-owners → `403`.

`ReminderOut` = `{id, order_id, status_at_reminder, detected_at, resolved,
resolved_at, order_status, order_total_cents, order_created_at}`.

**How reminders work (D6):** a **managed periodic scanner** started through
the application lifespan runs every 60 s in the documented single-worker
configuration (it does *not* rely on request-triggered `BackgroundTasks`,
which would never fire for a silently-stale order). Each scan: creates one
row per (order, status-episode) for `PLACED`/`ACCEPTED` orders whose
`status_updated_at` is > 15 min old (dedupe via `uq_reminders_episode` —
one reminder per episode, not per tick), and resolves rows whose order has
left that status. Fresh session per scan; scan errors are logged and the
loop continues (BG-05); clean shutdown with the lifespan.

---

## 10. AI order insights (batch 10, D9)

### POST /api/v1/insights/question — *customer only*
Body `{"question": 1–1000 chars}` — exactly one field, extras → `422`.
There is **no target-customer parameter** (AI-02): the analysis is always
scoped to the authenticated user's own orders.

| Check | Failure |
|---|---|
| role ≠ customer | `403 ROLE_FORBIDDEN` |
| blank question | `422 QUESTION_EMPTY` |
| question > `ai_max_question_chars` (default 500) | `422 QUESTION_TOO_LONG` |
| per-user rate limit hit (default 10 / 10 min, in-memory) | `429 RATE_LIMITED` |
| OpenAI upstream 429 | `429 AI_UPSTREAM_RATE_LIMITED` |
| OpenAI timeout | `504 AI_TIMEOUT` |
| other OpenAI API failure | `502 AI_UPSTREAM_ERROR` |

`200` → `{answer, provider, stats}`:

- **No key configured** → `provider: "unconfigured"`, `answer: null` — a
  clear degradation signal (the client renders a configuration notice plus
  the stats). **No fake AI output is ever returned** (D9).
- **Customer has no orders** → `provider: "deterministic"`, `answer` = a
  plain "no orders yet" sentence (no provider call).
- **Configured** → `provider: "openai:<model>"`, `answer` = the model's
  text (≤300 tokens).

`stats` is **always computed in application code** (AI-05), integer cents,
definitions mirroring the owner statistics (D35): `order_count`,
`gross_cents` (every placed order was mock-paid), `refunded_cents`,
`net_retained_cents` (gross − refunded), `avg_order_cents` (integer floor),
`delivered_count` (delivered_at-based — includes later-refunded, D31),
`top_restaurants` / `top_dishes` (top 3).

**Model context (AI-02/03/04/06):** the prompt contains the caller's own
orders, most recent first, bounded to `ai_history_window` (default 50):
order id, restaurant name, status, payment status, placed date, total
(cents), item snapshots (name, quantity, unit price cents). **Excluded:**
delivery addresses, e-mails, partner/customer names, any other customer's
rows. No model-generated SQL, no DB/tool access — the model only sees the
serialized summary.

---

## 11. Roadmap — endpoints planned in later batches

Details are written here **as each batch lands** (sync rule above). Source:
[authorization-matrix.md](authorization-matrix.md) and
[requirements.md](requirements.md).

| Batch | Endpoint | Auth |
|---|---|---|
| — | (all planned endpoints are implemented) | — |

---

## Changelog
- **2026-11-07** — Created (batch 3). Documents health, auth (batch 2),
  restaurants & menu (batch 3).
- **2026-11-07** — Batch 4: §6 Orders (checkout semantics, idempotency
  contract, 201-vs-200 retry rule, detail authorization). Roadmap renumbered
  to §7 (batches 5–7 + stretch).
- **2026-11-08** — Batch 5: new §7 Order lifecycle & role dashboards (10
  endpoints: the five transition actions, owner dashboard, partner
  listing/active/history/detail) with transition semantics — the
  422-vs-409 target rule, the D29 cancellation reversal, the partner
  active/history split. `customer_name` added to `OrderOut` (DELV-02);
  `IDEMPOTENCY_MISMATCH` + `INVALID_TRANSITION` moved to the implemented
  code table; step 4 (state-machine edge) added to the authorization
  order. Roadmap renumbered to §8; its batch-5 rows removed, incl.
  `GET /owner/orders`, which was delivered in batch 5 (DASH-01).
- **2026-11-08** — Batch 8: `GET /owner/restaurant` (frontend enablement —
  own-restaurant lookup; 403 non-owner / 404 no-restaurant) and
  `OrderOut.refund_reason` (the customer's request text, for the owner
  decision UI). Read-only projections of existing authorized data — no new
  business rules.
- **2026-11-08** — Batch 6: new §8 Refunds, reviews & owner statistics
  (5 endpoints: refund request/approve/reject, review, `GET /owner/stats`)
  with the D28 one-request-permanently rule, the D30 atomic-approval
  semantics (200 no-op on double-approval, one `refunded` ledger row),
  the D31 `delivered_at` review gate, and the D35 metric set.
  `refund_status` added to `OrderOut` (REF-06); `REFUND_REQUEST_EXISTS`,
  `ORDER_INELIGIBLE`, `REFUND_ALREADY_DECIDED`, `REVIEW_EXISTS` added to
  the implemented code table. Roadmap renumbered to §9; its batch-6 rows
  removed. Optional REV-04 (public review listing) not implemented —
  recorded as deferred-optional.
- **2026-11-08** — Batch 7: new §9 Owner reminders
  (`GET /owner/reminders`) + the scanner semantics (D6: lifespan-managed
  periodic scan, 60 s / 15 min / PLACED+ACCEPTED, episode dedupe, resolve
  on progress, owner-only visibility, error-tolerant, clean shutdown).
  Roadmap renumbered to §10; its batch-7 row removed — only the stretch
  (M10 insights) row remains.
- **2026-11-08** — Batch 10: new §10 AI order insights
  (`POST /insights/question`) — the D9 security table (role-only authz, no
  target-customer param, PII-light bounded context, app-computed stats),
  the degradation contract (`provider: "unconfigured"` + `answer: null` +
  stats when no key; `"deterministic"` for empty history), and the
  429/502/504 upstream failure mapping. Roadmap renumbered to §11 and now
  empty — every planned endpoint is implemented.
