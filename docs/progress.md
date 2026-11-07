# CampusBite — Progress Log

> Living record: what is done, what is next, and the running task board.
> Updated at the end of every task. Milestone definitions:
> [milestones.md](milestones.md).

## Status snapshot (2026-11-07)

- **Workspace:** git repo, `main` in sync with `origin` =
  `github.com/ginkalavarun/Capstone-Project`; no application code yet.
- **Current milestone:** **M1 — Planning & source-of-truth documents. ✅ CLOSED**
- **State:** **Pushed** — `main` = `9229de9` = `origin/main` (user pushed;
  verified via read-only MCP: two commits on GitHub, all docs in sync).
  **AGENTS.md now exists** (created from user-provided content; A1 resolved).
  DB design `docs/database.md` written, **awaiting approval** (no ORM code,
  no migrations). Next: M2 scaffold (awaiting go-ahead) and/or schema
  approval.

## Task log

### 2026-11-07 — M1: planning documents

**Done**
- Read the full assignment brief (12-page PDF, extracted).
- Verified `AGENTS.md` is **unavailable** in the workspace; reported to user;
  did **not** guess its contents (tracked as assumption A1, blocked).
- Captured the user's 10 approved decisions verbatim-in-intent → `decisions.md`
  (D1–D10) plus tutor proposals (D11–D22).
- Authored all ten planning docs: assignment-brief, decisions, requirements
  (every requirement ID-linked to milestone + tests), authorization-matrix,
  test-plan (every test defined), architecture (golden-path trace),
  milestones (M1–M14 with acceptance criteria + tests), excluded-features,
  assumptions, progress.

**Gates to clear before M2**
- [x] User review of this document set (done 2026-11-07; A2 resolved via
      D16 approval; D11–D22 approved).
- [x] Repo on GitHub + `git init` + initial commit + push (done by user;
      tutor verified via MCP: same SHA, all ten docs present, in sync).
- [ ] A3–A13 config-default confirmation (non-blocking: M2's `.env.example`
      needs only DATABASE_URL / JWT_SECRET / CORS_ORIGINS / OPENAI_API_KEY).
- [x] User provides `AGENTS.md` (done 2026-11-07 — file created from
      user-provided content; A1 resolved, DOC-04 satisfied).

**Next (M2 — awaiting go-ahead):** backend scaffold — FastAPI app, env config,
CORS allowlist, error format, health, middleware stubs, pytest harness,
Dockerfile, docker-compose.yml, `.env.example` (`git init` + `.gitignore`
already done). Tests T-M2-01…07 must be green to close M2.

### 2026-11-07 — user review, D11–D22 approval, repo on GitHub

- User reviewed the doc set; **approved D11–D22** (recorded in decisions.md);
  A2 resolved via D16. A3–A13 remain open (config defaults, non-blocking).
- Verified on GitHub via MCP: commit `26d7a30` “Initial commit” on `main`
  contains all ten docs (byte-identical to local); local/remote in sync.
- Committed the approval record + `.gitignore` (D22) locally as one commit on
  `main` (on top of `26d7a30`; five files). The session has **no push route**:
  git HTTPS has no cached credentials (keychain empty, no SSH key, `gh`
  unauthenticated) and the GitHub MCP token is **read-only** (an API
  `push_files` attempt was denied with 403 on the git trees API). The push is
  therefore pending on the user. **User step (terminal with working git
  auth):** `git push origin main` — one commit, five files. The tutor will
  then verify the remote via the read-only MCP.

### 2026-11-07 — AGENTS.md + database design (M3 prep, docs only)

- User pushed `9229de9` from their terminal; MCP verified remote in sync.
- **AGENTS.md created** at repo root from user-provided content (A1
  resolved). Referenced-doc audit: all present except `docs/api-contract.md`
  (expected — comes with the API milestones); `docs/database.md` now exists.
- **Recovered decision D23 (SECRETS AND CONFIGURATION)** — the user's
  original 7th approved decision, which the M1 decision log had folded into
  D4/D9/requirements instead of recording standalone; appended as D23 (no
  renumbering, to protect the verified cross-references).
- **Wrote `docs/database.md`** — full M3 schema design (9 tables, three
  state machines, transactions, concurrency, worked example, design tests).
  **No ORM code, no migrations** — per instruction, awaiting user approval.

## Standing rules of engagement (from the development contract)

- Small tasks, approval before edits, real test results only, no invented
  runs.
- Never: implement the whole project at once, rewrite unrelated files, add
  deps without explaining, change requirements to pass tests, weaken tests
  or authorization, read/print real `.env`/credentials, or commit/push/delete
  without approval.
- OpenAI key: backend only. localStorage: per brief, trade-off documented.
