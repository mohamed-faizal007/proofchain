# PROGRESS — session log

> Claude: read the **last entry** at the start of every session. Append a new entry at the end of every task.
> Keep entries short. Older entries may be condensed into the "History summary" once this file exceeds ~300 lines.

## Current status
- Phase: P3 (P2 complete; phase review pending)
- Next task: P3-01
- Blockers: none
- Deployed contract (localhost): —
- Deployed contract (sepolia): —

## Known issues / tech debt
- P0 review (2026-09-19), no HIGH findings. MEDIUM:
  - config.py default jwt_secret / empty anchor_private_key not rejected when app_env=prod (add validator, P3-01).
  - Other deps still use >= with no lockfile (only PyMuPDF is pinned).
- P0 review LOW: structlog unused; ci.yml lacks `permissions: contents: read` (pytest exit-5 tolerance removed after P1-02);
  X-Request-ID accepted unvalidated; 422 handler echoes pydantic `input` (strip before auth exists); http handler maps only 401/403/404/405 (no 413 FILE_TOO_LARGE);
  `app = create_app()` at import time; app-shell tests thin (error-code mapping, request-id, env-independent settings);
  hardhat.config.ts does not validate DEPLOYER_PRIVATE_KEY; compose hardhat service npm install clobbers host node_modules;
  dev.ps1 lacks exit-code checks; .env.example inline comments + VITE_EXPLORER_TX_URL not synced; 07 spec route rows added in P0-05 without ADR note; frontend API base URL hard-coded fallback.
- PyMuPDF has no type stubs, so extract.py's dict-key access (blocks/lines/spans/bbox/size/flags/text) is unchecked by mypy and relies entirely on the fixture tests to catch drift if the library's output shape changes in a future version.

- Section heading rule (c) (02 §8) misclassifies numbered prose with no trailing period (e.g. "5 apples were sold") as a heading. Spec-compliant, reporting-only (sections are outside `text_root`); pinned by `test_numbered_prose_is_misclassified_as_heading_known_limitation` and listed in 02 §13. Changing the rule needs an ADR.
- Datetimes (P2-01, RESOLVED): the client is built with `tz_aware=True`, so stored datetimes come back as aware UTC on real Mongo (verified on mongo:7) and mongomock; BSON truncates to milliseconds, so round-trip equality tests must zero microseconds. Repositories/services compare against `datetime.now(UTC)`; never naive datetimes.
- Unique-index nulls (P2-01 check, mongomock 4.3 vs mongo:7): both treat a missing field and an explicit null as the same key, so two documents without `chain_doc_id` (or `email`) raise DuplicateKeyError in the fast suite too; pinned by `test_unique_index_treats_missing_field_as_null` in test_db.py, so no blind spot for this class of bug. Sparse/partial unique indexes were not compared.
- P2 phase review (2026-09-20), no HIGH findings. Suites: backend 392 passed (total coverage 95%; `app/deps.py` 0% until P3+ uses it), ruff/mypy clean, contracts 1 passed, frontend 15 passed + lint clean. `-m mongo`/`-m minio` integration tests were not run in this review. MEDIUM:
  - **S3 timeouts vs public /health (FIXED in P2-review: S3 client timeouts):** connect 1s, read 5s, 2 total attempts on the boto client, so an unreachable S3 holds a worker thread ~12s at most instead of 60s x 3; pinned by `test_hanging_s3_call_is_bounded_by_botocore_timeout`. Remaining: `/health` can still fan out one thread per request for that window; consider a short TTL cache for the S3 probe.
  - `EventRepository.append` retries once (ADR-019, deliberate: sized for maker/checker). A third concurrent writer gets a 409; `_tip` walks all of a document's events per append (O(n)). Consider 5-10 retries with jitter and a tip pointer / latest-only fetch.
  - State change and event are two separate Mongo writes (e.g. `set_review` then `append(REVISION_APPROVED)`), not atomic: a crash between them leaves an APPROVED revision with no event. The P5 services must fix the write order or use a transaction, plus a reconcile check and a test.
  - `RevisionRepository` still inherits unguarded `update_one`/`delete` from `BaseRepository`, bypassing the PENDING guard; protect or remove them on revisions/trees. (`set_anchor` now filters on `status == "APPROVED"` as a backstop, FIXED in P2-review; the primary check is the P5-04 service invariant, now in its Accept line.)
- P2 phase review LOW:
  - (`set_anchor` return value FIXED: now `matched_count`.) Document counters (`revision_count`, `latest_approved_*`, `updated_at`) have no atomic helper yet (P5).
  - Models do not enforce 64-char lowercase hex for `file_hash`/`text_root`/`event_hash`/`prev_event_hash`; user emails are not normalised and the unique index is case-sensitive; `User.roles` may be empty.
  - `_check_json_native` accepts ints beyond int64 (BSON `OverflowError` is not mapped to a domain error). `S3Storage.get` has no size cap; `presign_get` `expires_seconds` has no upper bound.
  - `/health` is public and exposes `canon_version` and dependency status (accepted; 503 vs liveness/readiness split is a P10 decision, see Follow-ups).
  - Test gaps: 3+ concurrent appenders, out-of-range int in event data, `set_anchor` on non-APPROVED, thread starvation in health; the mongo/minio markers are not run by default (consider running them in CI).
- P2 phase review doc drift (no code change): 03_DATA_MODEL does not mention the unique `(document_id, prev_event_hash)` index or ADR-019's canonical-JSON definition (line ~59-60); the 12 MB tree-size guard with S3 fallback (`trees/{rev}.json`, 03 line 50) is not implemented in `TreeRepository` (decide in P5-01 or drop from 03); `chain_doc_id = hex(sha256(_id))` and bbox shape are not validated by the models; 04 error-code list omits `CONFLICT` (409) and `STORAGE_ERROR` (502) that `errors.py` adds.

## Follow-ups (ideas deliberately deferred — do not implement without a task)
- CI records the PyMuPDF version; consider a CI check that it matches the pin.
- **Presigned URL host (P2-03):** `S3Storage.presign_get` signs against the internal `S3_ENDPOINT_URL`. That host is only browser-reachable when the backend runs on the host next to MinIO (`http://localhost:9000`). Once the backend runs in Docker (`app` compose profile, P10-03) the endpoint is `http://minio:9000`, which a browser cannot resolve. The host is part of the SigV4 signature, so it cannot be rewritten after signing. **Must be resolved by P8-03 (revision file download in the frontend) together with the compose networking in P10-03, before either is called done.** Options: a separate `S3_PUBLIC_ENDPOINT_URL` used only for presigning (needs an `.env.example` entry and a second boto client), or a backend proxy download route. No P2-03 test covers this: moto and the host-local MinIO check use one hostname.
- **/health degraded status code (P2-04):** `/health` returns HTTP 200 with `status: "degraded"` in the body when mongo or S3 is down. Whether it should return 503 instead is undecided; decide in P10 when real deployment/orchestration is set up (Docker healthchecks, any future load balancer), since that is when it matters operationally. Do not change before then.
- Event append concurrency (P2-02, ADR-019): `EventRepository.append` retries once on a lost race. That is enough for the maker/checker pattern (at most 2 concurrent writers per document; pinned by `test_two_concurrent_appends_both_succeed_and_chain_stays_linear`), and higher contention fails safely with `ConflictError` (409) and never forks (`test_many_concurrent_appends_never_fork`, both in `tests/integration/test_events_real_mongo.py`). If a future usage pattern needs more concurrent writers per document, the retry count in `events.py` (or adding backoff/jitter) is the tuning knob.
- Canonicalization quirk (found in P1-02): ″ (U+2033) canonicalizes to `''` (two apostrophes), not `"`, because NFKC (§3 step 1) expands it to two ′ (U+2032) before the quote mapping (step 3) runs, so ″ in step 3's list never matches. This is spec-compliant per the stated order in 02_ALGORITHMS.md §3 and is pinned by the test `double-prime-nfkc-first` in test_canonical.py. Fixing it would require reordering steps 1 and 3 (or dropping ″ from the list): a deliberate spec change needing an ADR in 09_DECISIONS.md and a `CANON_VERSION` bump. Do not change silently.

- Chunking hard-split risk (found in P1-05): a sentence over 600 chars with no space is cut at exactly 600 code points (`_hard_split` in chunking.py, 02 §4 "hard split if no space"), which could separate a combining mark from its base character. NFKC (§3 step 1) composes most base+mark pairs into single code points, which minimizes this, but it is not ruled out for v1 (e.g. marks with no precomposed form). The split is deterministic, so hashes stay stable; the cost is a chunk boundary in an odd place. Avoiding it would change §4, needing an ADR in 09_DECISIONS.md and a `CANON_VERSION` bump. Do not change silently.

- Localization (P1-08): a chunk moved across a page boundary with unchanged text gives CHANGED with zero regions (§9 diffs chunk text only). Pinned by `test_moved_chunk_without_text_change_has_no_regions`; listed in 02 §13. Fixing needs an ADR.

- P1 phase review (2026-09-20), no HIGH findings. Suites: backend 299 passed (core coverage 98%), ruff/mypy clean, contracts 1 passed, frontend 15 passed + lint clean. MEDIUM (golden vectors and the `_open` leak were fixed afterwards, see the P1-review entry in the Log):
  - `text_root` depends on the Python Unicode database (NFKC, `\s`) and PyMuPDF; only PyMuPDF is pinned. CI pins Python 3.11; the runtime does not (`requires-python>=3.11`). Pin the runtime minor (Docker image) and consider recording `unicodedata.unidata_version` with each tree/ADR-013 canon version.
  - No resource limits on untrusted PDFs (page count, total chars, chunk count; all pages' `get_text("dict")` held in memory). Add `MAX_PAGES`/`MAX_TOTAL_CHARS` (raise `InvalidPdfError`) with a size limit at upload; pairs with the P6 replace-pairing guard.
- P1 phase review LOW:
  - `ProofStep.from_dict` does not type-check `sibling`; `verify_proof` catches only ValueError, so untrusted JSON with a null/int sibling can raise TypeError (500 instead of False). Validate in from_dict, catch (ValueError, TypeError).
  - `chunking._hard_split` re-slices the remaining string each iteration (O(N^2/600) copying on one huge unspaced paragraph); use an offset. `merkle_proof` rebuilds all levels per call (O(C^2) for all leaves); accept precomputed levels.
  - `types.from_dict` methods do no validation (bbox length/finite, hash format, `page_count == len(pages)`, root consistency), and `localize` trusts stored `file_hash`/`text_root` for IDENTICAL/CONTENT_EQUIVALENT. Contract: the service must recompute the candidate tree from bytes and verify stored trees (consider a core `verify_tree`) before use.
  - Determinism note: `\s` in `normalize_text` also matches U+001C-U+001F and U+0085 (not Unicode White_Space); deterministic in Python but an independent re-implementation could differ. Note in 02 §3.
- P1 phase review doc drift (no code change): 02 §8 does not state that blank spans are excluded from `body_size` and heading rules (a)/(b) (P1-06 judgment; add to §8/ADR); 03_DATA_MODEL shows chunk `section_id`, `chunk_count`, `page_levels` that `Chunk`/`IntegrityTree` do not carry (derive in the P2 service; `page_levels` via `merkle_levels(..., node=page_node_hash)`), and omits chunk `page`; 02 §9.3 wording vs the looser spill-over rule (finding 6); `LocalizationResult.method` is None for IDENTICAL/CONTENT_EQUIVALENT (spec should say nullable). Also note: the code-reviewer subagent ran under system Python 3.13 without pytest (line numbers in its report were unreliable); rely on the .venv (3.11) for test runs.
- P1-09 follow-ups (deferred, none needs code in P1):
  - **P6 service-layer guard (audit finding 3, MEDIUM, DoS):** replace pairing (`_pair_replace`, localize.py) is quadratic in the size of a `replace` opcode (measured 0.17s at 20x20, 0.75s at 40x40 chunks; a ~1000-chunk full rewrite would take minutes on /verify). A cap inside core would change output (needs ADR); add a size/time guard in the /verify service (reject or degrade to DELETED+INSERTED beyond N x M) in P6.
  - **P6 service-layer guard (finding 9, INFO):** `localize` does not check `ref.canon_version == cand.canon_version`. The service must compare trees built under the same version (or rebuild the reference under the candidate's rules) before calling it.
  - `verify_proof` (merkle.py) still accepts an internal node presented as a leaf with a truncated proof inside one chunk-level tree (`verify_proof(node_hash(a,b), proof[1:], root)` is True). Not exploitable today (proofs are built from stored leaves); if proofs are ever exposed to third parties, verify from chunk text and check proof length against the leaf count. 02 §5 / ADR-005 slightly overstate the protection.
  - Not re-audited in P1-09 (only spot-checked by spec-guardian): 02 §9 steps 3 and 5, and §2, §4, §8 in full. Schedule a future review pass.

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

### 2026-09-19 — P1-08 Localization
- Done: proofchain_core/localize.py (`localize`, `PAIR_THRESHOLD`); exported from __init__.py. Merkle page-root fast path with per-page alignment; whole-document alignment on page-count change or spill-over. One additive bullet in 02 §13.
- Tests: tests/unit/core/test_localize.py (18: identical, metadata-only, modify, insert middle/start, spill-over, moved chunk, delete, multi-page, page-count change, replace pairing/tie, repeated chunks, sections, round-trip, real PDF, Hypothesis single mutation). pytest 276 passed; ruff, format, mypy clean; localize.py coverage 100%.
- Decisions: spill-over = mismatched page with changed chunk count and a mismatched neighbour. `hash_comparisons` = page-root comparisons (if counts equal) + leaves aligned. Region ids `r1..` in opcode order (replace: MODIFIED, DELETED, INSERTED). Section fields from cand, or ref for DELETED. Leaf-level matcher uses autojunk=False; ratio pairing keeps the default (literal §9.4). No ADR needed.
- Issues: code was written before the tests (not red-first). Page-move-only case has no regions (see Known issues).
- Next: P1-09

### 2026-09-20 — P1-09 Core hardening review
- Done: audit (spec-guardian + review), 9 findings. Fixes: page-level Merkle prefix 0x03 (`page_node_hash`, `page_merkle_root`; `merkle_*` take a `node` keyword), `CANON_VERSION` 1 -> 2 (ADR-017); replace-pair ratio passes `autojunk=True` explicitly (ADR-018); stale `canon_version=1` fixture in test_types.py -> 2; 02 §4/§8/§9/§12 clarified, §13 extended. Tagged `v0.1-core` locally (not pushed).
- Tests: pytest 299 passed (was 276 at P1-08); ruff, format clean; mypy clean and `mypy --strict proofchain_core` clean. Core coverage 98% (target >= 90%):
  __init__ 100, __main__ 0 (CLI shim, covered only by a subprocess test), canonical 100, chunking 100, errors 100, extract 95, hashing 100, localize 100, merkle 94, sections 100, tree 91, types 100.
- Findings coverage:
  | # | Sev | Finding | Disposition | Pinned by |
  |---|-----|---------|-------------|-----------|
  | 1 | HIGH | text_root did not bind page boundaries | FIXED (ADR-017, canon v2); residual noted in 02 §13 | test_hashing/test_merkle/test_tree page-node tests |
  | 2 | MED | replace-pair autojunk default collapses ratio on long chunks | autojunk=True explicit + ADR-018; §13 limitation | test_replace_pairing_uses_autojunk_default_known_limitation |
  | 3 | MED | replace pairing quadratic (DoS on /verify) | DEFERRED: P6 service-layer guard (Follow-ups) | none (no core change) |
  | 4 | LOW | normalize_text not idempotent (e+ZWJ+U+0301) | documented in §13 | test_not_idempotent_zwj_between_base_and_mark_known_limitation |
  | 5 | LOW | lone surrogate -> raw UnicodeEncodeError in leaf_hash | pinned; service must map it | test_lone_surrogate_raises_unicode_encode_error_known_limitation |
  | 6 | LOW | spill-over rule vs §9.3 wording (equal-count swaps stay on fast path) | pinned; wording-only | test_equal_count_swap_between_adjacent_pages_stays_on_fast_path |
  | 7 | LOW | three silent spec ambiguities (hard-split index, body_size ties, hash_comparisons) | now in spec text + ADR-018; noted in §13 | existing chunking/sections/localize tests |
  | 8 | LOW | extraction ignores off-page text, annotations, form fields, hidden layers | documented in §13 (file_hash still catches) | n/a |
  | 9 | INFO | localize does not check canon_version match | DEFERRED: P6 service-layer guard (Follow-ups) | none |
  Also from the spec-guardian re-run: stale test_types fixture fixed; §12 page-node note added; `verify_proof` internal-node-as-leaf overstatement and the unaudited §9/§2/§4/§8 sections logged as Follow-ups (no re-audit done).
- Spec-guardian on §5-§7 after ADR-017: MATCH (hashing prefixes, page-level root, tree, CANON_VERSION 2 across code/docs/tests).
- Decisions: ADR-017, ADR-018. v1 is not kept verifiable (pre-launch exception, no anchors exist).
- Issues: __main__.py shows 0% because pytest-cov does not see the subprocess run; behaviour is tested. Tests for finding 2 pin a limitation, they do not fix it.
- Next: P2-01

### 2026-09-20 — P1-review follow-up fixes
- Done: `tests/unit/core/test_golden.py` pins literal hashes (leaf, node, page node, EMPTY_PAGE_ROOT, merkle roots incl. odd promotion, and `file_hash`/page roots/`text_root`/section hashes of contract_3page.pdf), cross-checked against an independent hashlib-only implementation. `extract._open` now closes the PyMuPDF document on every rejection path (try/except BaseException, close, re-raise).
- Tests: `test_document_is_closed_on_every_exit_path` (encrypted, owner-only, image-only, success; fails on the old code for encrypted and owner-only). pytest 307 passed; ruff, format, mypy clean; core coverage 98%.
- Decisions: garbage bytes are not covered by the leak test because `pymupdf.open` raises before a handle exists. Golden fixture roots also pin extraction, so a PyMuPDF change will fail them by design.
- Issues: none new. Remaining P1 review items stay under Known issues.
- Next: P2-01

### 2026-09-20 — P2-01 Mongo connection & repositories base
- Done: `app/db.py` (Motor client `tz_aware=True`, idempotent `ensure_indexes` per 03, Mongo type aliases), `app/repositories/base.py` (generic `BaseRepository`, duplicate key -> `ConflictError`), `app/deps.py` `get_db`, lifespan in `create_app(settings, db=None)`, `ConflictError` (409 CONFLICT) in errors.py, `mongo` pytest marker (excluded by default).
- Tests: unit (index set/idempotency, unique + null-collision, `$text` limitation, tz-aware round trip, repo, lifespan) + `tests/integration/test_indexes_real_mongo.py`. Fast suite 328 passed; `-m mongo` 4 passed against Docker mongo:7; ruff/format/mypy clean.
- Decisions: `tz_aware=True` on the client (stored datetimes come back aware UTC; BSON truncates to ms, so round-trip equality tests zero microseconds). `CONFLICT` code is not in 04; added without an ADR.
- Issues: mongomock lacks `$text` queries (index creation works); title search in P5-05 needs a real-Mongo test or regex fallback. Text-index behavior verified on real Mongo only.
- Next: P2-02

### 2026-09-20 — P2-02 Repositories
- Done: Pydantic models (`app/models/`) and repositories for users, documents, revisions (PENDING-guarded `set_review`, `set_anchor`), trees (upsert), verifications, and append-only hash-chained events (`events.py`, `event_hash.py`); repo getters in `deps.py`; unique index `(document_id, prev_event_hash)` in `db.py`.
- Tests: unit per repo, golden vector for the event hash (`test_event_hash.py`), chain-verify mutation cases; real-Mongo `test_events_real_mongo.py` (index, retry-on-conflict, concurrency). Fast 375 passed, `-m mongo` 12 passed; ruff/format/mypy clean.
- Decisions: ADR-019 (canonical JSON + chain format, off-chain, `CANON_VERSION` unchanged). Append retries once; higher contention gives ConflictError, never a fork (see Follow-ups).
- Issues: tail truncation of the event chain is undetectable off-chain (documented in ADR-019 and pinned by a test). `_tip` walks all of a document's events per append (O(n)).
- Next: P2-03

### 2026-09-20 — P2-03 S3 storage client
- Done: `app/storage/s3.py` (`S3Storage`: put/get/head/presign_get/head_bucket, sync boto3 via `anyio.to_thread`, path-style + SigV4, `StoredObject` with version id), `keys.py` (`revision_key`), `StorageError` (502 STORAGE_ERROR) in errors.py, `get_storage` dep, storage built in the lifespan (`create_app(..., storage=None)` injects a double), `minio` pytest marker (excluded by default).
- Tests: `tests/unit/app/test_storage.py` on moto (versioning, old version readable, missing -> None/StorageError, presign pins versionId + expiry, head_bucket). `tests/integration/test_storage_real_minio.py` passes against Docker MinIO incl. a real presigned GET. Fast suite 385 passed; `-m minio` 1 passed; ruff/format/mypy clean.
- Decisions: client never creates the bucket (compose `minio-init` / infra does). `STORAGE_ERROR` code is not in 04; added without an ADR, like `CONFLICT`.
- Issues: presigned URL host limitation, see Follow-ups ("Presigned URL host"), owned by P8-03 / P10-03.
- Next: P2-04

### 2026-09-20 — P2-04 Health endpoint real checks
- Done: `app/services/health.py` (`check_health`: mongo ping + S3 head_bucket concurrently, 2s timeout each, no exception text leaked), thin `api/v1/health.py`, 04 §System note (values, integer `canon_version`).
- Tests: `tests/unit/app/test_health.py` (ok, mongo down, bucket missing, S3 raising, no leak, hung dep timeout, no-lifespan); shell test updated. 392 passed, ruff/mypy clean.
- Decisions: degraded is HTTP 200 with `status: "degraded"`; 503 question deferred to P10 (Follow-ups). `chain`/`nlp` report `not_configured` until P4/P7. No ADR.
- Issues: none.
- Next: P3-01
