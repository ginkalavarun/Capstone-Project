# CampusBite — Assumptions & Open Items

> **Unresolved assumptions** that need your confirmation, and **blocked
> items**. Confirmed decisions live in [decisions.md](decisions.md); this
> file holds only what is *not yet settled*. Each item shows my proposed
> default so you can just say "defaults are fine."

## ⚠️ Blocked / needs you

| ID | Item | Status |
|---|---|---|
| A1 | **`AGENTS.md` is not available.** No such file exists anywhere I can see (verified across the workspace/repo, 2026-11-07). You asked me to read it and, if unavailable, to tell you — **I am telling you, and I have not guessed its contents.** Any requirement I have written comes only from the assignment PDF, your 10 decisions, and the development contract. If AGENTS.md imposes extra constraints (style, tooling, repo conventions), send it and I'll reconcile every doc against it. Requirement DOC-04 ("AGENTS.md present in repo") is **parked** until you provide the file. | ⛔ blocked on you |

## Potential conflict with the brief — needs your call

| ID | Item | My read | Proposed default |
|---|---|---|---|
| A2 | ~~Public browsing vs "protect backend APIs"~~ — **RESOLVED 2026-11-07.** | The user approved D11–D22, which includes D16. Reading (a) is final: catalog reads are public; every account/order/money/owner/partner/AI endpoint is fully protected per D8. | ✅ Closed — no further action. |

## Proposed defaults — confirm or override (all small, all in M2/M10 config)

| ID | Item | Proposed default |
|---|---|---|
| A3 | Password policy | Min **8**, max **72 bytes** (bcrypt's hard limit — D4 fails loudly at the edge instead of truncating) |
| A4 | JWT lifetime | **60 minutes** access token, configurable via env (`JWT_EXPIRE_MINUTES`) |
| A5 | Delivery fee | **Flat, per-restaurant, in cents**, default `200` ($2.00) — part of the server-computed checkout total (D3) |
| A6 | AI rate limit | **10 requests per rolling 10 minutes per user**, configurable via env; in-memory (single-worker caveat documented, D9) |
| A7 | AI history window | Most recent **50 orders** in context; question ≤ **500 chars** (D9) |
| A8 | Pagination | `limit` default **20**, max **100**; `offset`-based, with `total` in response |
| A9 | Reminder poll interval / threshold | Scanner every **60 s**; threshold **15 min** on `status_updated_at` (both env-configurable) |
| A10 | Currency | **USD**, documented in README + `.env.example` comment (D3 asked us to choose and document one) |
| A11 | "Basic statistics" scope | Orders by status, revenue (snapshot cents), items sold, avg order value, date range — own restaurant (D19) |
| A12 | Frontend framework | **Vite** (official React scaffolder; standard, fast, no opinionated extra) |
| A13 | API client | **Fetch** (brief allows Fetch or Axios; fewer deps, and it's what we'd teach first) |

## Explicitly NOT assumptions (for the record)

- The 10 decisions (D1–D10) are **approved and final** per your 2026-11-07
  message — they are recorded in decisions.md and are not open.
- Tutor proposals D11–D22 were **approved by the user on 2026-11-07** and are
  binding decisions (recorded in decisions.md); the reading-sensitive D16 is
  thereby settled (A2 resolved).

## Backlog (not scheduled — excluded by default, see excluded-features.md)

- Multi-restaurant owners, menu categories/images, promo codes, address
  books, multi-currency, i18n, hosted deployment, CI pipelines, WebSockets.
