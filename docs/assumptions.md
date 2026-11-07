# CampusBite — Assumptions & Open Items

> **Unresolved assumptions** that need your confirmation, and **blocked
> items**. Confirmed decisions live in [decisions.md](decisions.md); this
> file holds only what is *not yet settled*. Each item shows my proposed
> default so you can just say "defaults are fine."

## ⚠️ Blocked / needs you

| ID | Item | Status |
|---|---|---|
| A1 | **`AGENTS.md` is not available.** The workspace is empty; no such file exists anywhere I can see. You asked me to read it and, if unavailable, to tell you — **I am telling you, and I have not guessed its contents.** Any requirement I have written comes only from the assignment PDF, your 10 decisions, and the development contract. If AGENTS.md imposes extra constraints (style, tooling, repo conventions), send it and I'll reconcile every doc against it. Requirement DOC-04 ("AGENTS.md present in repo") is **parked** until you provide the file. | ⛔ blocked on you |

## Potential conflict with the brief — needs your call

| ID | Item | My read | Proposed default |
|---|---|---|---|
| A2 | **Public browsing vs "protect backend APIs"** (D16). The brief's auth section says protect backend APIs with auth; its customer list says customers *browse* restaurants/menus. These can conflict. | Two defensible readings: (a) catalog reads are public (standard for food apps; "protect" then applies to everything that touches accounts/orders/money), or (b) *all* endpoints require a logged-in user. | **Reading (a)** — catalog public; every account/order/money/owner/partner/AI endpoint fully protected. It's the industry norm and keeps the browse UX simple; the brief's protection mandate is still fully honored for all sensitive surfaces. **If your grader expects login-before-browsing, flip D16 — it's a one-milestone change (M5).** |

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
- Tutor proposals D11–D22 are pending your review of *this* doc set, but none
  contradict the brief; the only reading-sensitive one is D16 (tracked as A2).

## Backlog (not scheduled — excluded by default, see excluded-features.md)

- Multi-restaurant owners, menu categories/images, promo codes, address
  books, multi-currency, i18n, hosted deployment, CI pipelines, WebSockets.
