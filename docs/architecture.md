# CampusBite — Minimal Architecture

> Beginner-oriented. One question answers the whole shape: *when a customer
> taps "Place order", what happens, in what order, through what?*

## 1. The shape of the system

```
┌────────────────────┐        ┌─────────────────────────────┐       ┌──────────┐
│  React frontend    │  HTTP  │        FastAPI backend       │  SQL  │  SQLite  │
│  (Vite dev server) │───────▶│  containers (Docker Compose) │──────▶│  (volume)│
│                    │        │                             │       │          │
│  • pages per role  │◀───────│  • JWT auth (PyJWT/HS256)   │◀──────│  8 tables│
│  • React Router    │ JSON   │  • RBAC + ownership checks  │       │          │
│  • cart (state)    │        │  • central order state mach.│       │          │
│  • token in        │        │  • OpenAI client (env key)  │       │          │
│    localStorage    │        │  • background reminder scan │       │          │
└────────────────────┘        └─────────────────────────────┘       └──────────┘
        5173                              8000
```

Three processes, three jobs:

1. **React** — what you *see*. UI state only (cart, forms, routes). It never
   computes money, never enforces rules. It stores the JWT in `localStorage`
   (brief requirement) and sends it as `Authorization: Bearer <token>`.
2. **FastAPI** — what you *get*. Every request is verified (auth → role →
   ownership, D8), business rules applied (D3 money, D7 state machine), and
   results serialized as JSON. Secrets live only here (D4/D7/D9).
3. **SQLite** — what *happened*. Relational tables (D1). One file in a Docker
   volume; FK enforcement per connection; short write transactions.

Supporting pieces inside the backend: **Alembic** (versioned migrations),
**bcrypt** (passwords), **PyJWT** (tokens), **OpenAI SDK** (insights,
backend-only), a **lifespan-managed scanner** (reminders, D6), and
**middleware** (request logging + response timing, MW-01/02).

## 2. Repo layout (D12)

```
campusbite/
├── docs/                    # this source-of-truth set
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, lifespan (scanner), middleware, routers
│   │   ├── core/            # config (env), security (bcrypt, JWT), deps (auth/role/ownership)
│   │   ├── db/              # engine, session, base, models.py, init/migrations
│   │   ├── models/          # SQLAlchemy ORM models (8 tables)
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── services/        # checkout, state machine, reminders, insights, stats
│   │   ├── api/v1/          # routers: auth, restaurants, menu, orders, owner, delivery, refunds, reviews, insights
│   │   └── seed.py          # dev-only fixtures (D21)
│   ├── alembic/             # versioned migrations (D11)
│   ├── tests/               # pytest (test-plan.md)
│   ├── requirements.txt     # pinned (D4)
│   ├── Dockerfile
│   ├── .env.example
│   └── (docker-compose.yml at repo root)
├── frontend/
│   ├── src/
│   │   ├── api/             # fetch client: base URL, bearer header, error unwrap
│   │   ├── context/         # AuthContext (user, role, token)
│   │   ├── components/      # reusable: OrderCard, StatusBadge, FilterBar, …
│   │   ├── pages/           # Login, Register, Restaurants, Menu, Cart, Checkout,
│   │   │                    # CustomerDashboard, OwnerDashboard, DeliveryDashboard, AIInsights
│   │   └── App/             # router + protected-route wrappers
│   └── package.json
├── docker-compose.yml       # backend (+ optional frontend preview, FE-15)
├── .env.example
└── README.md
```

## 3. The golden path, request by request

**Scenario:** Priya (customer) places an order for 2× Margherita ($12.99 each)
at Slice House.

### ① Cart is client-side only (D15)
Tapping "Add to cart" mutates React state (+ `localStorage`). No API call, no
server table. The cart is a *draft* — it has no authority.

### ② `POST /api/v1/orders` — the only call that matters
```json
{ "restaurant_id": 3, "items": [{ "menu_item_id": 41, "quantity": 2 }] }
```
Server, in order:
1. **Middleware** logs `POST /api/v1/orders` + measures the clock (MW-01/02).
2. **Auth dependency** verifies the JWT (HS256 signature, `exp`), loads user
   #17 from the DB, confirms active. `401` if anything is off.
3. **Role check**: must be `customer`.
4. **Checkout service** (D3):
   - loads menu items **from the DB** (never the client's prices), verifies
     each exists, is `available`, and belongs to restaurant 3;
   - snapshots `item_name` + `unit_price_cents` into `order_items`;
   - computes `total_cents = 1299×2 + delivery_fee` in integer cents;
   - **ignores any client-supplied total**.
5. **One transaction:** insert `orders` (status `PLACED`, `status_updated_at`
   = now) + `order_items` + a `payment_ledger` row (`mock_paid`). Commit.
   (`mock_paid` is the dummy payment — BR §5.)
6. **Response:** `201` with the full order (items with snapshots, total,
   payment state). React navigates to the dashboard.

### ③ Owner accepts: `POST /api/v1/orders/{id}/accept`
Auth → role `owner` → **ownership** (order's restaurant = caller's) →
**state machine** (D7): `PLACED → ACCEPTED` is a valid edge, so it applies and
stamps `status_updated_at`. Anything else → `409 INVALID_TRANSITION`.

### ④ Same for `PREPARING → READY` (owner), then **assign**
`POST /orders/{id}/assign { "delivery_partner_id": 9 }` — owner of that
restaurant, order must be `READY`, partner must be role `delivery_partner`
**and active** (D5) → `ASSIGNED`.

### ⑤ Partner delivers
Marco (the assigned DP) polls `GET /api/v1/delivery/orders/{id}` (his only —
the query filters on `delivery_partner_id = caller`). He posts
`OUT_FOR_DELIVERY`, later `DELIVERED`. A *different* partner gets `404` —
the role check passes but the **assignment** check fails (D8: two separate
locks).

### ⑥ Afterwards, customer-side
- **Track:** polls her order detail (status + `status_updated_at` timeline).
- **Review:** `POST /orders/{id}/review` — only when `DELIVERED`, one per
  order (DB unique constraint backs the service check).
- **Refund:** `POST /orders/{id}/refund-request` with a reason — only when
  `DELIVERED`, one per order. Owner approves → payment ledger gets a `refunded`
  row (idempotent: approving twice creates exactly one).

### ⑦ Meanwhile, in the background (D6)
The lifespan scanner ticks every 60 s on its **own DB session**. An order
sitting in `PLACED`/`ACCEPTED` with `status_updated_at` older than 15 minutes
gets a reminder row (deduped per order+status episode). The owner's dashboard
list shows them. If the order progresses, the reminder resolves.

### ⑧ AI insight: `POST /api/v1/insights { "question": "…" }`
Auth → role `customer` → **rate limit** (per user, configurable) → service
fetches **only caller's** orders (SQL `WHERE customer_id = :caller`), reduces
them to a bounded, de-PII'd context with app-computed money aggregates →
OpenAI (mock in tests) → text answer. No target-id parameter exists, so the
question can't point at another customer (D9).

## 4. Why each boundary sits where it does

| Boundary | Where | Why |
|---|---|---|
| Cart | frontend state | Brief says basic React state; no cart table in §10. A draft has no authority. |
| Money math | backend service | Integers, DB prices, server total (D3). Client numbers are display-only. |
| Status changes | one central transition function | One map, one code path (D7) — no endpoint improvises. |
| Who-can-do-what | per-endpoint dependencies (auth/role/ownership) | D8; 401/403/404 policy in the matrix. |
| Passwords / JWT secret / OpenAI key | backend env (`.env`, never in image/repo) | D4/D7. Frontend env vars: non-secrets only (e.g. API base URL). |
| AI data | SQL filtered by caller id | D9; the model is an untrusted text processor, never a data accessor. |
| Stale-order nagging | background scanner | Needs to run with zero traffic (D6). |
| Schema changes | Alembic migrations | Versioned, reviewable, auto-applied at boot (D1/D11). |

## 5. Data model (the 8 tables, one diagram)

```
users ─┬─< orders >─┬─< order_items >─ menu_items >─ restaurants
       │            │        (snapshot: name, unit_price_cents)
       │            ├─< payment_ledger        (mock_paid, refunded)
       │            ├─  refund_request (0..1)  (one per order)
       │            ├─  review (0..1)          (one per delivered order)
       │            └──> reminder_logs (0..n, deduped per status episode)
       │            └──> users(delivery_partner)  [assigned partner]
       └──────────────────────────────────────────────┘
restaurants ──> users(owner)   [one restaurant per owner, D2]
```

Key columns that make the rules work:
- `orders.status` (string, D18) + `orders.status_updated_at` (feeds D6).
- `orders.customer_id → users`, `orders.restaurant_id → restaurants`,
  `orders.delivery_partner_id → users` (nullable until assigned).
- `order_items.unit_price_cents` + `item_name` — the immutable receipt (D3).
- `payment_ledger`: one row per money event (`mock_paid` at placement,
  `refunded` on approval) — the "ledger" is the audit trail.
- `refund_request`: unique per order (DB constraint) with status
  `pending/approved/rejected` + reason.
- `reminder_logs`: (order_id, status) episode key + resolved flag.

## 6. Trust model in one paragraph

The browser is the only untrusted party. It may lie about cart contents,
totals, and even its own role — and it does, in tests, constantly. The
backend treats every request as untrusted input: verify the signed token,
re-load the user, re-check role and ownership **per resource**, re-compute
money, re-check the state machine — then and only then mutate data inside
one short transaction. The OpenAI model is a second untrusted party: it
receives a bounded, pre-filtered snapshot and returns text; it never queries
the database. Everything durable and provable lives in SQLite.
