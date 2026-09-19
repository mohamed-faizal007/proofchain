# PROGRESS — session log

> Claude: read the **last entry** at the start of every session. Append a new entry at the end of every task.
> Keep entries short. Older entries may be condensed into the "History summary" once this file exceeds ~300 lines.

## Current status
- Phase: P0 (complete)
- Next task: P1-02
- Blockers: none
- Deployed contract (localhost): —
- Deployed contract (sepolia): —

## Known issues / tech debt
- P0 review (2026-09-19), no HIGH findings. MEDIUM:
  - /health returns only {status}; spec shows mongo/s3/chain/nlp/canon_version (planned P2-04).
  - config.py default jwt_secret / empty anchor_private_key not rejected when app_env=prod (add validator, P3-01).
  - Other deps still use >= with no lockfile (only PyMuPDF is pinned).
- P0 review LOW: structlog unused; ci.yml lacks `permissions: contents: read` and tolerates pytest exit 5 (remove at P1 start);
  X-Request-ID accepted unvalidated; 422 handler echoes pydantic `input` (strip before auth exists); http handler maps only 401/403/404/405 (no 413 FILE_TOO_LARGE);
  `app = create_app()` at import time; app-shell tests thin (error-code mapping, request-id, env-independent settings);
  hardhat.config.ts does not validate DEPLOYER_PRIVATE_KEY; compose hardhat service npm install clobbers host node_modules;
  dev.ps1 lacks exit-code checks; .env.example inline comments + VITE_EXPLORER_TX_URL not synced; 07 spec route rows added in P0-05 without ADR note; frontend API base URL hard-coded fallback.

## Follow-ups (ideas deliberately deferred — do not implement without a task)
- CI records the PyMuPDF version; consider a CI check that it matches the pin.

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

### 2026-09-19 — P0-05 Frontend init
- Done: frontend/ Vite 6 + React 18 + TS strict, Tailwind v3 (darkMode class), Router v6, TanStack Query v5, axios, eslint 9 + prettier, vitest. Placeholder routes (src/pages/placeholders.tsx, src/App.tsx), src/api/{client,types}.ts (ApiError from error envelope, request id from X-Request-ID, getToken hook stub), src/routerFuture.ts (v7 flags opted in).
- Tests: App.test.tsx (10 routes + NotFound), api/client.test.ts (envelope parsing, fallback, bearer header). lint, typecheck, test (15), build green; dev server serves 200.
- Decisions: added routes /documents/:id/revisions/new and /verifications (now in 07 route table). No react-hook-form/zod/react-pdf/lucide yet (added when first used). Extra deps beyond the task list: eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals, eslint-config-prettier, @testing-library/{dom,jest-dom,user-event}, jsdom, @types/node.
- Issues: npm audit reports warnings (not addressed). Auth (AuthContext/ProtectedRoute) deferred to a later task.
- Next: P0-06

### 2026-09-19 — P0-06 Infra + CI
- Done: infra/docker-compose.yml (minio healthcheck, minio-init waits on healthy, images pinned), .github/workflows/ci.yml (backend, core-windows placeholder, contracts, frontend), scripts/dev.ps1 (--wait, -Chain switch).
- Tests: none (config). compose config valid; up --wait -> mongo+minio healthy; minio-init created proofchain-docs with versioning (verified via mc); actionlint clean; dev.ps1 parses. CI not yet run on GitHub.
- Decisions: MinIO images moved to quay.io (minio/minio and minio/mc are gone from Docker Hub) with pinned release tags. pytest steps tolerate exit 5 until P1 adds core tests.
- Issues: hardhat compose service (chain profile) not exercised; deferred to P4.
- Next: P1-01

### 2026-09-19 — P0-review MEDIUM fixes
- Done: NoContentChangeError 409 -> 422 (matches 04 spec; test_no_content_change_is_422 added). Compose ports for mongo/minio/hardhat bound to 127.0.0.1. PyMuPDF pinned `==1.28.2` in backend/pyproject.toml.
- Tests: pytest 11 passed; ruff, format, mypy clean; compose config valid.
- Decisions: PyMuPDF is pinned exactly because text extraction feeds canonicalization and hashing; an upgrade can change extracted text and therefore hashes, so bumping it needs a deliberate change (re-run fixtures, consider CANON_VERSION/ADR). Other deps stay lower-bound only.
- Next: P1-01

### 2026-09-19 — P1-01 Types & fixtures generator
- Done: proofchain_core/types.py (frozen dataclasses BBox, Chunk, Page, Section, IntegrityTree, ChangeRegion, LocalizationResult + StrEnums; to_dict/from_dict, tuples for sequences, BBox as [x0,y0,x1,y1]). tests/fixtures/make_fixtures.py + committed tests/fixtures/pdfs/ (one_page, contract_3page, unicode_variants, image_only, encrypted, not_a_pdf). reportlab pinned `==5.0.1`.
- Tests: test_types.py (round trip incl. JSON, frozen, key order, optionals, tuples) and test_fixtures.py (determinism, committed-match, per-file properties). pytest 35 passed; ruff, format, mypy clean.
- Decisions: base-14 fonts only, no font embedded in any fixture. Ligatures (fi/fl) come from Helvetica registered with StandardEncoding (WinAnsi, reportlab's default, lacks them); NBSP and smart quotes use default WinAnsi Helvetica. An earlier draft embedded Vera TTF, which broke the base-14-only rule; that was unnecessary and was reverted. Fixtures use invariant=1; encrypted.pdf was also byte-stable across two runs.
- Issues: CI update (run 35430923152, commit b211498, push to main): all four jobs green, including `backend` (ubuntu-latest) and `core-windows`. Regeneration of all six fixtures matched the committed bytes on Linux as well as Windows, for this reportlab pin (5.0.1) and PyMuPDF pin. Caveat on evidence: per-test output is not visible without authentication (logs API returned 403, gh not installed), so this is inferred from the backend job's pytest step succeeding; that step tolerates exit code 5 (no tests collected), which cannot apply since 35 tests exist. Still only one Linux run; a reportlab/zlib change could break byte-identity, in which case fall back to the property tests. Tests needing exact hashes must read the committed PDFs, never regenerate. Observation: MuPDF extraction normalises NBSP (U+00A0) to a plain space, so NBSP never reaches canonicalization via extract; P1-02 still maps it per spec. The fixture has only fi/fl ligatures (no ffi/ffl). Verified on Windows and on the GitHub ubuntu-latest runner (one run) for all fixtures including the StandardEncoding line.
- Next: P1-02
