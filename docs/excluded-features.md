# CampusBite — Excluded Features (Scope Creep Guard)

> Anything on this list is **out of scope for the capstone** unless the user
> explicitly re-scopes it in writing. The brief's own "not required" notes
> (marked BR) plus additions that protect the delivery date.
>
> Rule of thumb for new ideas: *does the brief or a user decision require
> it?* No → it goes here, not into a milestone.

## Explicitly excluded by the brief (BR)

| Item | BR basis |
|---|---|
| Real payment gateway / real money | §5 "dummy payment … without integrating any real payment gateway" |
| Real-time notifications / WebSockets / push | §8 "not required" |
| Embeddings, vector databases, RAG for the AI feature | §7 "not required" |
| Redux / Zustand or any advanced state library | §9 "not mandatory" |
| Refresh tokens / OAuth / social login | not in brief; JWT access tokens only (D4) |
| Admin role / admin UI | brief has exactly three roles; privileged accounts are CLI-provisioned (D2) |
| Public registration for owners/delivery partners | D2 (customer-only public registration) |
| Restaurant creation via API/UI by end users | owner + restaurant is provisioned by CLI (D2) |
| Menu categories, dietary tags, image uploads, cuisine types | not in brief's menu requirements |
| Order-level customizations / notes / toppings | not in brief (items = menu items + quantity) |
| Multiple restaurants per owner | brief: one owner, their restaurant (D2 one-transaction provisioning) |
| Address book / multiple saved addresses / map integration | delivery details = one address field on the order |
| Promotions, coupons, loyalty, dynamic pricing | not in brief |
| In-app chat / customer–owner messaging | not in brief |
| Role self-change or elevation | D2/D8 — roles never change via API |
| Internationalization / multi-currency | D3 fixes USD; "basic" scope |
| Dark mode, theming beyond a clean baseline | FE polish, not brief |
| CI/CD pipelines, auto-deployment (Render/Fly/etc.) | brief requires local Docker Compose runnability + a GitHub repo, not hosted deployment |
| Load testing / performance engineering | not in brief |
| Database: PostgreSQL/Mongo etc. | D1: SQLite for the capstone (with the honest non-one-line caveat) |

## Excluded by decisions (D#)

| Item | Decision |
|---|---|
| Passlib for password hashing | D4 (direct bcrypt) |
| Refresh-token rotation flows | D4 (access tokens only in v1) |
| Long-lived / never-expiring JWTs | D4 (exp required) |
| Request-triggered reminders as the only mechanism | D6 (managed scanner) |
| Real-time reminder delivery to the UI (polling only) | D6 + BR §8 |
| Client-supplied checkout totals being trusted | D3 |
| Float money columns | D3 |
| Wildcard CORS | D10 |
| Model-generated SQL / tool-calling AI / multi-turn chat sessions | D9 (single bounded Q→A per request) |
| Persistent (DB/Redis) rate-limit storage | D9 (in-memory, single-worker documented) |
| Duplicate refund ledger rows on double-approval | D7/REF-04 (idempotent) |
| Order items ever mutating after placement | D3 (immutable snapshots) |

## Optional (O) items — allowed only after milestone M-tests green

These appear in requirements.md as **O** and may be built *late*: soft menu
delete (RST-03), public review display (REV-04), compose preview frontend
service (FE-15). They are **not** prerequisites for any other milestone.

## How to propose adding something

1. File it in [assumptions.md](assumptions.md) → "Backlog (not scheduled)".
2. User approves in writing.
3. It receives a requirement ID, milestone slot, and tests — only then does
   it enter the plan.
