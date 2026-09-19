# PROGRESS — session log

> Claude: read the **last entry** at the start of every session. Append a new entry at the end of every task.
> Keep entries short. Older entries may be condensed into the "History summary" once this file exceeds ~300 lines.

## Current status
- Phase: P0 (in progress)
- Next task: P0-06
- Blockers: none
- Deployed contract (localhost): —
- Deployed contract (sepolia): —

## Known issues / tech debt
- (none yet)

## Follow-ups (ideas deliberately deferred — do not implement without a task)
- Pin or record the PyMuPDF version in CI (extraction determinism depends on it).

## History summary
- (empty)

---

## Entry template
```
### <YYYY-MM-DD> — <TASK-ID> <title>
- Done: <what was built, key files>
- Tests: <what was added; result of the test/lint/type commands>
- Decisions: <any choice not already in docs; add ADR if significant>
- Issues: <anything left broken or surprising>
- Next: <next task ID>
```

## Log

### 2026-09-19 — P0-01 Repo skeleton
- Done: backend/app and backend/proofchain_core packages (docstring-only stubs), tests tree, .vscode/extensions.json, scripts/dev.ps1, .gitkeep in contracts/frontend/eval.
- Tests: none (scaffolding); extensions.json parses, dev.ps1 parses.
- Decisions: app/ has packages only (module files come in P0-03+); no CANON_VERSION yet (P1-02).
- Issues: none. info.md left untracked (out of scope).
- Next: P0-02

### 2026-09-19 — P0-02 Backend project config
- Done: backend/pyproject.toml (setuptools, deps, `dev`/`nlp` extras, pytest/ruff/mypy config; mypy strict on proofchain_core).
- Tests: none. Fresh py -3.11 venv + `pip install -e ".[dev]"` OK; pytest collects 0 tests (exit 5, expected); ruff, ruff format, mypy all clean.
- Decisions: plain `bcrypt` instead of passlib (unmaintained; breaks with bcrypt>=4.1). Lower-bound pins only, no lockfile. Ruff rules E,F,I,UP,B,SIM, line length 100.
- Issues: PyMuPDF resolved to 1.28.2; `import fitz` warns as deprecated, so use `import pymupdf` in core. `nlp` extra declared but not installed.
- Follow-ups added: pin/record PyMuPDF version in CI (determinism of extraction depends on it).
- Next: P0-03

### 2026-09-19 — P0-03 FastAPI app shell
- Done: backend/app/{config,errors,logging,main}.py, api/v1/health.py (+router in api/v1/__init__.py). App factory with CORS, request-id middleware, error-envelope handlers.
- Tests: tests/unit/app/test_app_shell.py (10 tests: health, docs, request id, domain/validation/unhandled/404 envelopes, CORS, settings). pytest, ruff, mypy green; live uvicorn served /api/v1/health and /docs (200).
- Decisions: health returns only {status: "ok"} (deps + canon_version added later). Added codes INTERNAL_ERROR, UNAUTHORIZED, METHOD_NOT_ALLOWED, HTTP_ERROR beyond the spec's list. 500s are caught inside the request-id middleware so the header is kept. CORS_ORIGINS is a comma-separated string with a cors_origin_list property.
- Issues: Starlette TestClient warns that httpx is deprecated in favour of httpx2 (plus an anyio alias warning); harmless for now.
- Next: P0-04

### 2026-09-19 — P0-04 Contracts project init
- Done: contracts/{package.json,hardhat.config.ts,tsconfig.json}, contracts/contracts/Placeholder.sol, test/smoke.test.ts. Hardhat 2 + toolbox, OZ v5, solc 0.8.24 optimizer 200, networks localhost + sepolia (only when env set), gasReporter via REPORT_GAS.
- Tests: smoke test (deploy + DEFAULT_ADMIN_ROLE) passes; compile, test, REPORT_GAS test, tsc --noEmit all clean.
- Decisions: placeholder contract + smoke test instead of an empty test, so OZ v5 wiring is exercised. dotenv reads env only.
- Issues: Placeholder.sol and smoke.test.ts are temporary; delete in P4-01. npm audit reports warnings (not addressed).
- Next: P0-05

### 2026-09-19 � P0-05 Frontend init
- Done: frontend/ Vite 6 + React 18 + TS strict, Tailwind v3 (darkMode class), Router v6, TanStack Query v5, axios, eslint 9 + prettier, vitest. Placeholder routes (src/pages/placeholders.tsx, src/App.tsx), src/api/{client,types}.ts (ApiError from error envelope, request id from X-Request-ID, getToken hook stub), src/routerFuture.ts (v7 flags opted in).
- Tests: App.test.tsx (10 routes + NotFound), api/client.test.ts (envelope parsing, fallback, bearer header). lint, typecheck, test (15), build green; dev server serves 200.
- Decisions: added routes /documents/:id/revisions/new and /verifications (now in 07 route table). No react-hook-form/zod/react-pdf/lucide yet (added when first used). Extra deps beyond the task list: eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals, eslint-config-prettier, @testing-library/{dom,jest-dom,user-event}, jsdom, @types/node.
- Issues: npm audit reports warnings (not addressed). Auth (AuthContext/ProtectedRoute) deferred to a later task.
- Next: P0-06
