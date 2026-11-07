# CampusBite — Authorization Matrix

> Per decision D8 and contract rule: **role checks and resource-ownership
> checks are separate**. Every protected endpoint lists both. A valid role
> alone never grants access to another user's resources.
>
> **Check order (server-side, every request):**
> 1. **Auth** — JWT present, signed with our secret, `alg=HS256`, unexpired →
>    load user from DB; if missing/deactivated → `401`.
> 2. **Role** — DB role ∈ endpoint's allowed roles, else `403`.
> 3. **Ownership / assignment** — resource belongs to the caller
>    (customer→own order; owner→own restaurant's resources; partner→assigned
>    order). Not the owner → `404` (we return 404 rather than 403 for
>    ownership failures so we don't leak that a resource exists to the wrong
>    party).
>
> Roles: `C` = customer, `O` = restaurant owner, `DP` = delivery partner.
> "Owner(restaurant)" = the owner whose restaurant owns the resource.
> "Assigned partner" = the partner recorded on the order.
> Test IDs resolve in [test-plan.md](test-plan.md).

## Authentication

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| POST | `/api/v1/auth/register` | none (public) | n/a — payload may only create `customer`; any other role → 422 | n/a | AUTH-01 | T-M4-01, T-M4-02 |
| POST | `/api/v1/auth/login` | none (public) | n/a | n/a | AUTH-02 | T-M4-03 |
| GET | `/api/v1/auth/me` | yes | C, O, DP | self (identity from DB) | AUTH-09 | T-M4-11 |

## Restaurants & menu — public catalog (D16)

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| GET | `/api/v1/restaurants` | none | public | n/a (public catalog) | RST-01 | T-M5-01 |
| GET | `/api/v1/restaurants/{id}` | none | public | n/a | RST-02 | T-M5-02 |
| GET | `/api/v1/restaurants/{id}/menu` | none | public | n/a | MENU-01, MENU-02 | T-M5-03…05 |

## Restaurants & menu — owner management

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| POST | `/api/v1/restaurants/{id}/menu` | yes | O | owner of restaurant `{id}` | MENU-03 | T-M5-06, T-M4-16 |
| PUT | `/api/v1/menu-items/{id}` | yes | O | owner of the item's restaurant | MENU-04, MENU-05 | T-M5-07, T-M5-08, T-M4-16 |
| DELETE | `/api/v1/menu-items/{id}` | yes | O | owner of the item's restaurant (soft-remove per RST-03) | MENU-04, RST-03 | T-M5-09, T-M5-10 |
| GET | `/api/v1/delivery-partners` | yes | O | n/a — lists **active** partners, id + display name only (D5) | DELV-04 | T-M7-16, T-M4-16 |

## Orders — customer

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| POST | `/api/v1/orders` | yes | C | n/a — creates caller's order; items must exist/be available/same restaurant (CK-04) | CK-01…06, PAY-01 | T-M6-01…07 |
| GET | `/api/v1/orders` (own, filtered) | yes | C | **own orders only** (`customer_id = caller`) | ORDR-01 | T-M6-08, T-M4-15 |
| GET | `/api/v1/orders/{id}` | yes | C, O, DP | caller is the order's customer **or** owner of its restaurant **or** assigned partner | ORDR-02, DELV-02 | T-M6-09, T-M7-10, T-M4-15…17 |
| POST | `/api/v1/orders/{id}/cancel` | yes | C | own order **and** status = PLACED | ORDER-02 | T-M7-02, T-M7-03 |

## Orders — restaurant owner

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| GET | `/api/v1/owner/orders` (filtered, paginated) | yes | O | restaurant = caller's restaurant | DASH-01 | T-M8-01, T-M4-16 |
| GET | `/api/v1/orders/{id}` | yes | O | owner of the order's restaurant | ORDR-02 | T-M6-09, T-M4-16 |
| POST | `/api/v1/orders/{id}/accept` | yes | O | owner of order's restaurant **and** status = PLACED | ORDER-04 | T-M7-05, T-M4-16 |
| POST | `/api/v1/orders/{id}/status` (prep) | yes | O | owner of order's restaurant **and** valid prep edge (D7) | ORDER-05 | T-M7-06, T-M4-16 |
| POST | `/api/v1/orders/{id}/assign` | yes | O | owner of order's restaurant **and** status = READY **and** target partner role=DP + active | ORDER-06 | T-M7-07, T-M7-08 |

## Orders — delivery partner

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| GET | `/api/v1/delivery/orders` (assigned, filtered) | yes | DP | **assigned to caller only** | DELV-01 | T-M7-13, T-M4-17 |
| GET | `/api/v1/delivery/history` | yes | DP | previously assigned to caller | DELV-03 | T-M7-15, T-M4-17 |
| GET | `/api/v1/delivery/orders/{id}` | yes | DP | **this order assigned to caller** | DELV-02 | T-M7-14, T-M4-17 |
| POST | `/api/v1/orders/{id}/delivery-status` | yes | DP | **this order assigned to caller** **and** valid delivery edge (D7) | ORDER-07 | T-M7-09, T-M7-10 |

## Refunds & reviews

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| POST | `/api/v1/orders/{id}/refund-request` | yes | C | own order **and** status = DELIVERED **and** no existing request (REF-02) | REF-01, REF-02 | T-M9-01…03 |
| POST | `/api/v1/orders/{id}/refund/approve` | yes | O | owner of order's restaurant **and** an open request exists **and** not already refunded (idempotent) | REF-03, REF-04 | T-M9-04, T-M4-16 |
| POST | `/api/v1/orders/{id}/refund/reject` | yes | O | owner of order's restaurant **and** an open request exists | REF-03, REF-05 | T-M9-06, T-M4-16 |
| POST | `/api/v1/orders/{id}/review` | yes | C | own order **and** status = DELIVERED **and** no existing review (REV-02/03) | REV-01, REV-02 | T-M9-08, T-M9-09 |
| GET | `/api/v1/menu-items/{id}/reviews` | none | public (read-only, optional REV-04) | n/a | REV-04 | T-M9-11 |

## AI insights

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| POST | `/api/v1/insights` | yes | **C only** | context built exclusively from **caller's** orders; no target id accepted; rate-limited per user | AI-01…09 | T-M10-01…08 |

## Owner self-service stats & reminders

| Method | Path | Auth | Role | Ownership / assignment | Req | Test |
|---|---|---|---|---|---|---|
| GET | `/api/v1/owner/stats` | yes | O | own restaurant only | DASH-02 | T-M8-02, T-M4-16 |
| GET | `/api/v1/owner/reminders` | yes | O | reminders for own restaurant's orders only | BG-04 | T-M8-06, T-M4-16 |

## Cross-cutting negative-test matrix (D8)

These scenarios are generated for **every** protected endpoint above via a
parametrized test (T-M4-14), plus the dedicated cases:

| Scenario | Actors | Assertion |
|---|---|---|
| Two customers | cust-A, cust-B | A can never read/modify/cancel/refund/review B's order (401/404) |
| Two owners, different restaurants | owner-A (rest A), owner-B (rest B) | B cannot view/manage/accept/assign/stats/remind/refund on A's restaurant resources |
| Two delivery partners | dp-1, dp-2 | dp-2 cannot view/update any order assigned to dp-1 |
| Wrong role | customer on owner endpoints; partner on checkout, etc. | 403 |
| Valid role, other's resource | any | 404 (never 200, never 403 with resource data) |
| Unauthenticated | no/invalid/expired/tampered token | 401 |
| Deactivated user | valid old token, DB row deactivated | 401 (DB is source of truth — D4) |
