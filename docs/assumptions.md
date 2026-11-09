# CampusBite — Assumptions & Open Items

> **Unresolved assumptions** that need your confirmation, and **blocked
> items**. Confirmed decisions live in [decisions.md](decisions.md); this
> file holds only what is *not yet settled*. Each item shows my proposed
> default so you can just say "defaults are fine."

## ⚠️ Blocked / needs you

| ID | Item | Status |
|---|---|---|
| A1 | ~~`AGENTS.md` unavailable~~ — **RESOLVED 2026-11-07.** The user provided the file's content; it was created at the repo root. It codifies the development contract's workflow/boundaries (it matches the contract; no conflicts found). Requirement DOC-04 ("AGENTS.md present in repo") is **satisfied** by the file's presence. | ✅ resolved |

## Potential conflict with the brief — needs your call

| ID | Item | My read | Proposed default |
|---|---|---|---|
| A2 | ~~Public browsing vs "protect backend APIs"~~ — **RESOLVED 2026-11-07.** | The user approved D11–D22, which includes D16. Reading (a) is final: catalog reads are public; every account/order/money/owner/partner/AI endpoint is fully protected per D8. | ✅ Closed — no further action. |

## Confirmed conservative defaults (2026-11-07 implementation batch)

The batch prompt: *"Choose conservative defaults only when they do not change
business behavior, permissions, money rules, required features, or
architecture. Record each selected default and its reason."* All items below
are **confirmed as selected** — each is a configuration default, not a
business rule, and each is env-overridable. **A10 changed to EUR** per the
batch's currency instruction (see D26).

| ID | Item | Selected default (reason) |
|---|---|---|
| A3 | Password policy | Min **8**, max **72 bytes** (bcrypt's hard input limit — D4 fails loudly at the edge instead of truncating; 8 is a conservative floor) |
| A4 | JWT lifetime | **60 minutes** access token, configurable via env (`JWT_EXPIRE_MINUTES`) — access tokens only, D4 |
| A5 | Delivery fee | **Flat, per-restaurant, in cents**, default `200` (€2.00, D26) — snapshotted per order at checkout (D3/D32) |
| A6 | AI rate limit | **10 requests per rolling 10 minutes per user**, configurable via env; in-memory (single-worker caveat documented, D9) |
| A7 | AI history window | Most recent **50 orders** in context; question ≤ **500 chars** (D9) |
| A8 | Pagination | `limit` default **20**, max **100**; `offset`-based, with `total` in response |
| A9 | Reminder poll interval / threshold | Scanner every **60 s**; threshold **15 min** on `status_updated_at` (both env-configurable; batch M7 fixed these) |
| A10 | Currency | **EUR** (batch 2026-11-07 instruction, recorded as **D26**; supersedes the earlier USD proposal — the user never confirmed the USD proposal) |
| A11 | "Basic statistics" scope | The **D35 metric set** (orders by status, gross mock-paid, refunded, net retained, delivered count, items sold, avg order value, date range — own restaurant); D35 refines D19 per the batch |
| A12 | Frontend framework | **Vite** (official React scaffolder; standard, fast, no opinionated extra) |
| A13 | API client | **Fetch** (brief allows Fetch or Axios; fewer deps, and it's what we'd teach first) |

## Explicitly NOT assumptions (for the record)

- The 10 decisions (D1–D10) are **approved and final** per your 2026-11-07
  message — they are recorded in decisions.md and are not open.
- Tutor proposals D11–D22 were **approved by the user on 2026-11-07** and are
  binding decisions (recorded in decisions.md); the reading-sensitive D16 is
  thereby settled (A2 resolved).
- D24–D35 (2026-11-07 implementation batch) are **approved implementation
  decisions** recorded in decisions.md; they resolve database.md open items
  N1–N8 (N6/N7 accepted as documented design details — non-unique menu names
  and zero-price items are catalog conveniences, not business rules; WAL-off
  is a config default).

## Backlog (not scheduled — excluded by default, see excluded-features.md)

- Multi-restaurant owners, menu categories/images, promo codes, address
  books, multi-currency, i18n, hosted deployment, CI pipelines, WebSockets.
