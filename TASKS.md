# TASKS — ordered backlog

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (explain in PROGRESS.md).
Rule: take the first `[ ]` task whose **Deps** are all `[x]`. One task = one Claude Code session = one commit.
Every task's implicit acceptance: tests/lint/types for the touched area pass, PROGRESS.md updated.

---
## P0 — Scaffold & tooling
### [x] P0-01 Repo skeleton
Deps: — · Refs: CLAUDE.md, 01 §2
Do: create folder structure from 01 §2 (empty `__init__.py`s), `.vscode/extensions.json` (python, ruff, eslint, prettier, solidity), `scripts/dev.ps1` (starts infra).
Accept: tree matches 01 §2; `git status` clean after commit.

### [x] P0-02 Backend project config
Deps: P0-01 · Refs: 01 §2, 08 A
Do: `backend/pyproject.toml` (setuptools, packages `app`, `proofchain_core`; deps: fastapi, uvicorn[standard], pydantic>=2, pydantic-settings, motor, boto3, web3>=6, pymupdf, python-multipart, passlib[bcrypt] or bcrypt, pyjwt, structlog; extras `dev`: pytest, pytest-asyncio, pytest-cov, hypothesis, httpx, moto[s3], mongomock-motor, reportlab, ruff, mypy; extras `nlp`: spacy, sentence-transformers, dateparser). Ruff + mypy + pytest config (markers, asyncio mode auto).
Accept: `pip install -e ".[dev]"` works in a fresh venv on Windows; `python -m pytest` runs (0 tests OK); ruff & mypy pass.

### [x] P0-03 FastAPI app shell
Deps: P0-02 · Refs: 01 §5-6, 04 System
Do: `app/main.py` (app factory, CORS, request-id middleware, error envelope handlers), `app/config.py` (Settings from `.env.example`), `app/errors.py`, `app/logging.py`, `/api/v1/health` returning static ok for now.
Accept: `uvicorn app.main:app` serves `/api/v1/health` and `/docs`; test for health + error envelope.

### [x] P0-04 Contracts project init
Deps: P0-01 · Refs: 05
Do: `contracts/` Hardhat TS project, toolbox, OpenZeppelin v5, `hardhat.config.ts` (solidity 0.8.24 optimizer on, networks localhost/sepolia from env, gasReporter), empty test passes.
Accept: `npx hardhat compile` and `npx hardhat test` succeed.

### [x] P0-05 Frontend init
Deps: P0-01 · Refs: 07
Do: Vite React TS, Tailwind, router, TanStack Query, axios, eslint+prettier, vitest; placeholder routes from 07; package.json scripts `dev, build, lint, typecheck (tsc --noEmit), test`.
Accept: `npm run dev`, `npm run build`, `npm run lint`, `npm run typecheck`, `npm run test` pass.

### [x] P0-06 Infra + CI
Deps: P0-02, P0-04, P0-05 · Refs: 08 B, infra/docker-compose.yml
Do: verify compose works (mongo, minio, bucket init); `.github/workflows/ci.yml` with 3 jobs (+ windows core job placeholder).
Accept: `docker compose -f infra/docker-compose.yml up -d` healthy; CI YAML valid (actionlint if available).

---
## P1 — Integrity core (`proofchain_core`) — THE HEART, TEST-FIRST
### [x] P1-01 Types & fixtures generator
Deps: P0-02 · Refs: 02 §7-9, 08 A
Do: `types.py` dataclasses (frozen, `to_dict/from_dict`); `tests/fixtures/make_fixtures.py` with reportlab producing fixture PDFs listed in 08 A; commit generated PDFs.
Accept: fixtures script is deterministic (same bytes twice) or documented if reportlab embeds timestamps (use `invariant=1`).

### [x] P1-02 Canonicalization
Deps: P1-01 · Refs: 02 §3
Do: `normalize_text` + table-driven tests for every rule (ligatures, NBSP, soft hyphen, quotes, dashes, whitespace, case preserved, ₹ preserved).
Accept: ≥ 20 test cases; hypothesis: idempotent (`f(f(x)) == f(x)`).

### [x] P1-03 Hashing & Merkle
Deps: P1-01 · Refs: 02 §5-6
Do: `hashing.py`, `merkle.py` (root, levels, proof, verify, changed_leaves_by_descent).
Accept: known-answer tests for n=1,2,3,4,5 computed by hand in test; property tests from 08 A; leaf vs node domain separation test.

### [x] P1-04 Extraction
Deps: P1-02 · Refs: 02 §2
Do: `extract.py` → list of pages of blocks (text, bbox, spans size/flags). Errors: InvalidPdf, EncryptedPdf, NoExtractableText.
Accept: tests on all fixtures incl. error fixtures.

### [x] P1-05 Chunking
Deps: P1-04 · Refs: 02 §4
Do: `chunking.py`. Accept: boundary tests (599/600/601 chars, long sentence hard split, ids stable).

### [x] P1-06 Sections overlay
Deps: P1-05 · Refs: 02 §8
Do: `sections.py`. Accept: 3-page contract fixture yields the expected section titles; preamble section; cross-page section.

### [x] P1-07 build_integrity_tree
Deps: P1-03, P1-05, P1-06 · Refs: 02 §7
Do: `tree.py`, public API in `__init__.py` (`CANON_VERSION`, `build_integrity_tree`, `localize`).
Accept: determinism test (twice + JSON round-trip); empty page handled; CLI `python -m proofchain_core.tree file.pdf` prints roots.

### [x] P1-08 Localization
Deps: P1-07 · Refs: 02 §9
Do: `localize.py` fast path + alignment + replace pairing.
Accept: tests: identical, content-equivalent (metadata change via PyMuPDF), single modify, insert at start (no cascade), delete, multi-page edits, page-count change, spill-over to next page; hypothesis random single mutation → exactly one region.

### [x] P1-09 Core hardening review
Deps: P1-08 · Refs: 02 all
Do: run `spec-guardian` subagent; fix findings; coverage ≥ 90 %; mypy strict on core.
Accept: coverage report attached to PROGRESS entry; tag `v0.1-core`.

---
## P2 — Persistence & storage
### [x] P2-01 Mongo connection & repositories base
Deps: P0-03 · Refs: 03
Do: Motor client lifecycle in app lifespan, index creation at startup, generic repo helpers, test setup with mongomock-motor.
### [x] P2-02 Repositories
Deps: P2-01 · Refs: 03 · Do: users, documents, revisions, trees, events (hash-chained append), verifications.
Accept: unit tests per repo incl. unique indexes and event hash chain validation.
### [ ] P2-03 S3 storage client
Deps: P0-03 · Refs: 01 §4, ADR-002 · Do: put/get/presign/head with version id; moto tests; MinIO manual check.
### [ ] P2-04 Health endpoint real checks
Deps: P2-01, P2-03 · Do: mongo ping, S3 head bucket, chain placeholder.

---
## P3 — Auth & users
### [ ] P3-01 Passwords & JWT
Deps: P0-03 · Refs: 04 Auth, ADR-014
### [ ] P3-02 Auth routes, dependencies, role guard
Deps: P3-01, P2-02 · Accept: tests for login, me, role 403s.
### [ ] P3-03 Seed script
Deps: P3-02 · Do: `python -m app.scripts.seed` creates demo users (idempotent).

---
## P4 — Smart contract & chain client
### [ ] P4-01 ProofChainRegistry.sol + tests
Deps: P0-04 · Refs: 05 · Accept: all tests in 05 pass; gas report printed; run `code-reviewer` subagent on contract.
### [ ] P4-02 Deploy script + ABI export
Deps: P4-01 · Refs: 05 Deployment · Accept: local deploy writes deployments/localhost.json and backend ABI.
### [ ] P4-03 RegistryClient (Fake + Web3)
Deps: P4-02, P0-03 · Refs: 05 Backend client · Accept: fake unit-tested; `@pytest.mark.chain` test anchors & reads on local node.

---
## P5 — Documents, revisions, maker–checker, anchoring
### [ ] P5-01 Document registration service + route
Deps: P1-07, P2-02, P2-03, P3-02 · Refs: 01 §3.1, 04
### [ ] P5-02 Submit revision
Deps: P5-01 · Accept: 409 when pending exists; 422 NO_CONTENT_CHANGE.
### [ ] P5-03 Approve/reject + provenance events
Deps: P5-02 · Accept: self-approval 403; state machine tests.
### [ ] P5-04 Anchoring service (background + reconcile + retry)
Deps: P5-03, P4-03 · Refs: 01 §3.2, ADR-012 · Accept: FAILED → retry → ANCHORED with fake client; idempotency test.
### [ ] P5-05 Revoke, list/detail, tree, presigned file, provenance endpoints
Deps: P5-04 · Refs: 04
### [ ] P5-06 Revision diff endpoint
Deps: P5-05, P1-08 · Refs: 04 (`/revisions/{id}/diff`)

---
## P6 — Verification pipeline
### [ ] P6-01 Candidate matching & document association
Deps: P5-05 · Refs: 02 §10-11
### [ ] P6-02 Closest approved version + localization
Deps: P6-01, P1-08
### [ ] P6-03 Chain cross-check + RECORD_MISMATCH
Deps: P6-02, P4-03 · Accept: test that edits Mongo text_root directly → RECORD_MISMATCH.
### [ ] P6-04 /verify route, report assembly, persistence, timings
Deps: P6-03 · Refs: 04 VerificationReport · Accept: integration test for every verdict in PRD §5.

---
## P7 — NLP semantic analysis
### [ ] P7-01 Token diff + regex entities (money ₹/Rs/INR/$, dates, %, numbers)
Deps: P0-02 · Refs: 06
### [ ] P7-02 Obligation/negation detection + rule classifier + templates
Deps: P7-01
### [ ] P7-03 spaCy NER + embeddings (lazy singletons) + graceful fallback
Deps: P7-02
### [ ] P7-04 Integrate into verification & diff; optional LLM explanation behind flag
Deps: P7-03, P6-04 · Accept: NLP failure does not change verdict (test).

---
## P8 — Frontend
### [ ] P8-01 API client, types, auth context, login/register, protected routes
Deps: P0-05, P3-02 · Refs: 07
### [ ] P8-02 Dashboard + document list + new document upload
Deps: P8-01, P5-01
### [ ] P8-03 Document detail: version timeline, provenance timeline, submit revision
Deps: P8-02, P5-05
### [ ] P8-04 Approvals queue
Deps: P8-03
### [ ] P8-05 PdfViewerWithHighlights (+ bbox tests)
Deps: P8-01 · Refs: 07 Highlight overlay
### [ ] P8-06 Verify page + VerificationDetail (banner, steps, side-by-side, change list, chain proof)
Deps: P8-05, P6-04, P7-04
### [ ] P8-07 Verification history + revision diff view + polish (empty/error states, dark mode)
Deps: P8-06

---
## P9 — Evaluation (paper results)
### [ ] P9-01 Corpus generator (templates, Faker en_IN, reportlab, JSON specs)
Deps: P1-07 · Refs: 08 C.1
### [ ] P9-02 Tamper operations + ground truth
Deps: P9-01 · Refs: 08 C.2
### [ ] P9-03 Evaluation runner: detection, localization, efficiency, latency, baselines
Deps: P9-02, P1-08 · Refs: 08 C.3
### [ ] P9-04 Classification evaluation + ablation
Deps: P9-03, P7-03
### [ ] P9-05 Gas & Sepolia latency measurement; figures + auto REPORT.md
Deps: P9-03, P10-02

---
## P10 — Hardening, deploy, docs, demo
### [ ] P10-01 Security pass (upload validation, rate limit on /verify & /auth/login, headers, secret scan) with code-reviewer subagent
Deps: P6-04, P8-06
### [ ] P10-02 Sepolia deployment + verified contract + backend config
Deps: P4-02
### [ ] P10-03 Dockerfiles for backend/frontend, full compose profile `app`
Deps: P8-07
### [ ] P10-04 End-to-end demo script (`scripts/demo.ps1`) + seeded demo data (original, approved v2, tampered copies)
Deps: P10-03
### [ ] P10-05 Final docs: README, architecture diagrams export, API examples, user guide; tag v1.0
Deps: all
