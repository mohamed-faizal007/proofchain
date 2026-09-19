# PROGRESS — session log

> Claude: read the **last entry** at the start of every session. Append a new entry at the end of every task.
> Keep entries short. Older entries may be condensed into the "History summary" once this file exceeds ~300 lines.

## Current status
- Phase: P1 (in progress)
- Next task: P1-08
- Blockers: none
- Deployed contract (localhost): —
- Deployed contract (sepolia): —

## Known issues / tech debt
- P0 review (2026-09-19), no HIGH findings. MEDIUM:
  - /health returns only {status}; spec shows mongo/s3/chain/nlp/canon_version (planned P2-04).
  - config.py default jwt_secret / empty anchor_private_key not rejected when app_env=prod (add validator, P3-01).
  - Other deps still use >= with no lockfile (only PyMuPDF is pinned).
- P0 review LOW: structlog unused; ci.yml lacks `permissions: contents: read` (pytest exit-5 tolerance removed after P1-02);
  X-Request-ID accepted unvalidated; 422 handler echoes pydantic `input` (strip before auth exists); http handler maps only 401/403/404/405 (no 413 FILE_TOO_LARGE);
  `app = create_app()` at import time; app-shell tests thin (error-code mapping, request-id, env-independent settings);
  hardhat.config.ts does not validate DEPLOYER_PRIVATE_KEY; compose hardhat service npm install clobbers host node_modules;
  dev.ps1 lacks exit-code checks; .env.example inline comments + VITE_EXPLORER_TX_URL not synced; 07 spec route rows added in P0-05 without ADR note; frontend API base URL hard-coded fallback.
- PyMuPDF has no type stubs, so extract.py's dict-key access (blocks/lines/spans/bbox/size/flags/text) is unchecked by mypy and relies entirely on the fixture tests to catch drift if the library's output shape changes in a future version.

- Section heading rule (c) (02 §8) misclassifies numbered prose with no trailing period (e.g. "5 apples were sold") as a heading. Spec-compliant, reporting-only (sections are outside `text_root`); pinned by `test_numbered_prose_is_misclassified_as_heading_known_limitation` and listed in 02 §13. Changing the rule needs an ADR.

## Follow-ups (ideas deliberately deferred — do not implement without a task)
- CI records the PyMuPDF version; consider a CI check that it matches the pin.
- Canonicalization quirk (found in P1-02): ″ (U+2033) canonicalizes to `''` (two apostrophes), not `"`, because NFKC (§3 step 1) expands it to two ′ (U+2032) before the quote mapping (step 3) runs, so ″ in step 3's list never matches. This is spec-compliant per the stated order in 02_ALGORITHMS.md §3 and is pinned by the test `double-prime-nfkc-first` in test_canonical.py. Fixing it would require reordering steps 1 and 3 (or dropping ″ from the list): a deliberate spec change needing an ADR in 09_DECISIONS.md and a `CANON_VERSION` bump. Do not change silently.

- Chunking hard-split risk (found in P1-05): a sentence over 600 chars with no space is cut at exactly 600 code points (`_hard_split` in chunking.py, 02 §4 "hard split if no space"), which could separate a combining mark from its base character. NFKC (§3 step 1) composes most base+mark pairs into single code points, which minimizes this, but it is not ruled out for v1 (e.g. marks with no precomposed form). The split is deterministic, so hashes stay stable; the cost is a chunk boundary in an odd place. Avoiding it would change §4, needing an ADR in 09_DECISIONS.md and a `CANON_VERSION` bump. Do not change silently.

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

### 2026-09-19 — P1-02 Canonicalization
- Done: proofchain_core/canonical.py (`CANON_VERSION = 1`, `normalize_text` per 02 §3 steps 1-5), exported from proofchain_core/__init__.py.
- Tests: tests/unit/core/test_canonical.py (33 table cases + hypothesis idempotence and output-shape + version). pytest 71 passed; ruff, format, mypy clean.
- Decisions: implemented literally in spec order; no ADR needed.
- Issues: ″ (U+2033) canonicalizes to `''`, not `"` (NFKC runs before quote mapping); spec-compliant, logged under Follow-ups. Fixing needs ADR + CANON_VERSION bump.
- Next: P1-03

### 2026-09-19 — P1-03 Hashing & Merkle
- Done: proofchain_core/hashing.py (sha256_hex, leaf_hash, node_hash, file_hash, EMPTY_PAGE_ROOT) and merkle.py (merkle_levels/root/proof, verify_proof, changed_leaves_by_descent, frozen ProofStep with to_dict/from_dict); exported from __init__.py.
- Tests: test_hashing.py (known answers, leaf/node/plain domain separation, forged-leaf test, hex64 validation) and test_merkle.py (hand-built roots n=1..5, CVE-2012-2459 promotion, proofs n=1..33, tamper cases, hypothesis properties, descent vs naive). pytest 154 passed; ruff, format, mypy clean.
- Decisions: `changed_leaves_by_descent(ref_levels, cand_levels)` takes stored levels and returns sorted leaf indices; raises ValueError on differing leaf counts (page-count changes are P1-08's job). `side` is where the sibling sits ("left"/"right"). node_hash rejects anything but 64 lowercase hex chars. No ADR needed.
- Issues: none.
- Next: P1-04

### 2026-09-19 — P1-04 Extraction
- Done: proofchain_core/extract.py (`extract_pages` -> `ExtractedPage`/`ExtractedBlock`/`SpanInfo`; raw block text, block bbox, per-span size/flags) and proofchain_core/errors.py (`InvalidPdfError`, `EncryptedPdfError`, `NoExtractableTextError`, base `ProofChainCoreError`); exported from __init__.py.
- Tests: tests/unit/core/test_extract.py (16 tests: fixtures one_page/contract_3page/unicode_variants, all three error fixtures, owner-only encryption, canonical-char threshold, garbage bytes, determinism). pytest 170 passed; ruff, format, mypy clean.
- Decisions: core exceptions live in proofchain_core (core cannot import `app`); the P2 service layer maps them to the `app/errors.py` DomainError subclasses. The 20-char minimum is counted on `normalize_text(...).strip()` per block. Empty blocks are kept for chunking (P1-05) to drop.
- Issues: **Encryption check is stricter than 02 §2 text.** Any PDF carrying an /Encrypt dictionary is rejected, not only ones that need a password. Example that is rejected: a PDF saved with an owner password and an *empty* user password (e.g. `doc.tobytes(encryption=PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="")`, the common "anyone can open it, but printing/copying is restricted" report). It opens and extracts fine without any password, so the spec's "reject encrypted" could be read as allowing it; we reject it anyway because the file bytes (and hash) are of an encrypted container and permission-restricted PDFs are a routine output of Word/Acrobat "restrict editing", which users would otherwise submit expecting it to work. If that use case matters, relaxing it needs a spec edit/ADR. Detection note: PyMuPDF auto-authenticates the empty user password and then reports `is_encrypted=False`, so we also check `doc.metadata["encryption"]` (None when unencrypted).
- Next: P1-05

### 2026-09-19 — P1-05 Chunking
- Done: proofchain_core/chunking.py (`MAX_CHUNK_CHARS`, `split_paragraph`, `chunk_pages`); exported from __init__.py. Blocks are canonicalized, empties dropped, split per §4, ids `p{page}-c{index}`, leaf_hash via `leaf_hash`.
- Tests: tests/unit/core/test_chunking.py (19 tests: 599/600/601 boundaries, greedy packing, lowercase non-split, space and hard splits, tail packing within a block and not across blocks, stable ids, bbox inheritance, post-NFKC length, contract fixture determinism). pytest 189 passed; ruff, format, mypy clean.
- Decisions: length measured on canonical text in code points; a long sentence's tail can pack with following sentences of the same block only (packing state is per `split_paragraph` call); a split cuts at the last space at index <= 600. No ADR needed.
- Issues: hard split with no space may separate a combining mark from its base (see Follow-ups).
- Next: P1-06

### 2026-09-19 — P1-06 Sections overlay
- Done: proofchain_core/sections.py (`build_sections`, `body_size`); chunking.py gains `ChunkOrigin(chunk, block)` and `chunk_blocks`, with `chunk_pages` now a thin wrapper (output unchanged). Exported `build_sections`, `chunk_blocks`, `ChunkOrigin`. `Chunk`/types.py untouched (origin is never serialized). One additive bullet in 02 §13 (known limitation); §8 normative rules unchanged.
- Tests: test_sections.py (fixture titles S1-S3, cross-page section, S0 preamble, each heading rule alone, exclusions, body_size rounding/tie/split-block, hash = merkle_root, determinism, known-limitation pair) and 3 additions to test_chunking.py. pytest 234 passed; ruff, format, mypy clean.
- Decisions: rule (c) keywords are case-insensitive via a scoped `(?i:...)`, so roman numerals stay case-sensitive as §8 says "for words". Half-up rounding to 0.5pt (not banker's). body_size ties take the smaller size. Blocks with empty canonical text are dropped before chunking, so their spans do not count toward body_size. Heading length/period/regex tests use the block's canonical text. Headings numbered S1.. (S0 reserved for Preamble). No ADR needed.
- Issues: Follow-up commit added `SpanInfo.blank` (set at extraction: span's canonical text is empty) and made `_is_heading` and `body_size` skip blank spans; without it a bold heading with a non-bold trailing space was missed by rule (b). Ignoring blank spans is a judgment reading, not stated in §8. Tests were written alongside the code in one pass, not strictly red-first. Numbered-prose heading limitation logged under Known issues.
- Next: P1-07

### 2026-09-19 — P1-07 build_integrity_tree
- Done: proofchain_core/tree.py (`build_integrity_tree` per 02 §7, `main()` CLI printing roots as JSON), `__main__.py` (`python -m proofchain_core file.pdf`); `build_integrity_tree` exported from __init__.py.
- Tests: tests/unit/core/test_tree.py (determinism, JSON round-trip, roots recomputed independently, blank page first/middle/last uses EMPTY_PAGE_ROOT, metadata-only change keeps text_root, error fixtures, CLI incl. subprocess entry point). pytest 258 passed; ruff, format, mypy clean.
- Decisions: `extract_pages` keeps blank pages (zero blocks, indices unshifted), so they get `EMPTY_PAGE_ROOT` in place. `localize` export deferred to P1-08 (not implemented yet). Added `__main__.py` as a warning-free CLI entry; no ADR needed.
- Issues: `python -m proofchain_core.tree` (the command named in the task) prints a cosmetic runpy RuntimeWarning because the package imports `tree` eagerly; use `python -m proofchain_core` to avoid it.
- Next: P1-08
