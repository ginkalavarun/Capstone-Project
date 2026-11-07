# CampusBite — Progress Log

> Living record: what is done, what is next, and the running task board.
> Updated at the end of every task. Milestone definitions:
> [milestones.md](milestones.md).

## Status snapshot (2026-11-07)

- **Workspace:** fresh (no code, no `.git` yet).
- **Current milestone:** **M1 — Planning & source-of-truth documents.**
- **State:** docs drafted, **awaiting user review** (user instructed: stop
  after documentation/planning; no application code yet).

## Task log

### 2026-11-07 — M1: planning documents

**Done**
- Read the full assignment brief (12-page PDF, extracted).
- Verified `AGENTS.md` is **unavailable** in the workspace; reported to user;
  did **not** guess its contents (tracked as assumption A1, blocked).
- Captured the user's 10 approved decisions verbatim-in-intent → `decisions.md`
  (D1–D10) plus tutor proposals (D11–D22).
- Authored all nine planning docs: assignment-brief, decisions, requirements
  (every requirement ID-linked to milestone + tests), authorization-matrix,
  test-plan (every test defined), architecture (golden-path trace),
  milestones (M1–M14 with acceptance criteria + tests), excluded-features,
  assumptions, progress.

**Gates to clear before M2**
- [ ] User review of this document set (especially: A2 public-browse reading,
      A3–A13 proposed defaults, D16).
- [ ] User provides `AGENTS.md` (or confirms it doesn't exist) → unblock A1.
- [ ] User approves `git init` for the repo (M2 scope; we never init/commit
      without approval).

**Next (M2 — after approval):** backend scaffold — FastAPI app, env config,
CORS allowlist, error format, health, middleware stubs, pytest harness,
Dockerfile, docker-compose.yml, `.env.example`, `.gitignore`, `git init`.
Tests T-M2-01…07 must be green to close M2.

## Standing rules of engagement (from the development contract)

- Small tasks, approval before edits, real test results only, no invented
  runs.
- Never: implement the whole project at once, rewrite unrelated files, add
  deps without explaining, change requirements to pass tests, weaken tests
  or authorization, read/print real `.env`/credentials, or commit/push/delete
  without approval.
- OpenAI key: backend only. localStorage: per brief, trade-off documented.
