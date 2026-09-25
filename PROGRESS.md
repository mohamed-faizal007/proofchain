# PROGRESS — session log

> Claude: read the **last entry** at the start of every session. Append a new entry at the end of every task.
> Keep entries short. Older entries may be condensed into the "History summary" once this file exceeds ~300 lines.

## Current status
- Phase: P5 in progress (P5-01, P5-02 done)
- Next task: P5-03 Approve/reject + provenance events
- Blockers: none
- Deployed contract (localhost): —
- Deployed contract (sepolia): —

## Known issues / tech debt
- P0 review (2026-09-19), no HIGH findings. MEDIUM:
  - config.py prod validation was one finding with two halves, now split:
    - DONE (P3-01): default or <32-char `jwt_secret` rejected when app_env=prod.
    - DONE (P4-03): empty `anchor_private_key` (and `registry_address`) rejected when app_env=prod.
  - Other deps still use >= with no lockfile (only PyMuPDF is pinned).
- P0 review LOW: structlog unused; ci.yml lacks `permissions: contents: read` (pytest exit-5 tolerance removed after P1-02);
  X-Request-ID accepted unvalidated; 422 handler echoes pydantic `input` (FIXED in P3-02); http handler maps only 401/403/404/405 (no 413 FILE_TOO_LARGE);
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

- P3 phase review (2026-09-25), no HIGH findings, no spec drift (04 + ADR-014 match). Suites: backend 484 passed (coverage 97%), ruff/mypy clean, contracts 1 passed, frontend 15 passed + lint clean. Real-Mongo seed checked by hand. FIXED in P3-review: seed script echoed a too-short `SEED_PASSWORD` via pydantic's traceback (now a `SeedConfigError` without the value; pinned by `test_invalid_seed_password_is_rejected_without_leaking_it`). MEDIUM:
  - **Prod config fails open:** `app_env` defaults to `dev`, so a deploy that forgets `APP_ENV=prod` keeps the public default `JWT_SECRET` (forgeable ADMIN tokens, open `/auth/register`). The prod secret check is length-only (`"a"*32` passes). MITIGATED in P3-review: startup logs a WARNING when `app_env != prod` and the secret is the default (silent for `app_env=test`; `test_default_jwt_secret_*` in test_app_lifespan.py), but it fails open still. Full fix deferred to P10: remove `app_env`'s default so it must be set explicitly (touches ~20 Settings() calls in tests, `get_settings()` in main/seed, CI, dev script and compose), then refuse the default secret unless `app_env` is explicitly dev/test. Also tighten the length-only prod check.
  - **No login throttling** and each attempt costs a bcrypt verify on the anyio thread pool: online guessing and CPU exhaustion. Add per-IP/per-email backoff and a bcrypt concurrency cap (P10 hardening at latest, before public deploy).
  - **No audit trail for role changes** (`AuthService.set_roles` writes no event/log, no actor passed in): conflicts with the every-state-change-is-recorded rule. Decide an `admin_audit` collection or log entry before ISSUER/APPROVER flows (P5).
  - **Seed repair in prod** silently re-enables/re-roles the predictable demo accounts on any rerun (deliberate, for lockout recovery). Consider `--repair` opt-in and a log line per repair when APP_ENV=prod.
- P3 phase review LOW: `get_optional_user` returns 401 for a stale bearer token on public routes (pin the behavior in a test); `normalize_email` uses `.lower()` (no casefold/NFKC) and uniqueness relies on every insert path using it; register 409 leaks account existence (ADMIN-only in prod); JWT has no iat/jti/iss/aud (fine while single service). Test gaps: prod seed repair, concurrent duplicate register, inactive-user login 401, caplog check that passwords/tokens/hashes never reach logs, prod register with invalid token or deactivated admin, whitespace/low-entropy JWT secret, JWT `sub` non-string/empty.
- P4 review (2026-09-25, `code-reviewer` on the chain client; no HIGH; reviewer did not run tests). MEDIUM, all in `Web3RegistryClient` / config unless noted:
  - Unmapped web3 errors become 500s: `TimeExhausted` (receipt wait; tx may still be pending), `Web3RPCError` (insufficient funds, nonce too low), `ContractLogicError` from view calls in `_rpc`, and ABI-encoding errors (e.g. canon_version > uint16). Map connection/timeouts to `ChainUnavailableError`, RPC/encoding errors to `AnchorFailedError`. Fix in P5-04.
  - FIXED (P4-review): `_send` put raw exception text into `AnchorFailedError`. Checked what can leak: never the private key (signing is local, malformed-key errors do not echo it); the response text was only node revert text plus your own doc ids; but aiohttp `ClientResponseError` (HTTP 401/403/429 from a provider) embeds the full RPC URL, so an API key in the URL survived in `__cause__`, and web3 itself logs the URI at DEBUG. Now: fixed messages, cause dropped for connectivity errors (`from None`, class name logged only), `web3` logger pinned to WARNING. Tests: `test_web3_error_mapping.py`. Rule for P5-04: never log or persist `str(exc)` / `exc_info` of chain errors beyond the class name.
  - Duplicate anchor after a receipt timeout: idempotency sees only mined state, so a retry while the first tx is still in the mempool sends a second tx. The asyncio lock also covers one process only (multiple workers collide on nonces). P5-04 must re-check the chain before resending and either run a single worker or record that in an ADR.
  - Prod guard does not check `chain_rpc_url` / `chain_id` (defaults 127.0.0.1:8545 / 31337 pass), and `anchor_private_key` is a plain `str` (visible in `repr(settings)` / validation errors). Consider `SecretStr` and rejecting chain 31337 / localhost RPC in prod (P10-02).
  - CORRECTED (measured, not read from file names; the reviewer never opened `tests/unit/chain/`): the claim "no node-free unit tests" was wrong. Node-free suite covers `web3_client.py` at 61% (65 of 106 lines): constructor (ABI load, key and address validation), `_rpc`/`_send` connectivity mapping (HTTP 401, dead port), `ContractLogicError` mapping, secret-leak checks, `version_count`, `aclose`, and `health()` failure path, via `test_web3_error_mapping.py` and `test_health.py`; the shared idempotency rule, hex conversion and Fake client are at 100%. Still NOT covered node-free (only by `-m chain`, which the default run skips): `anchor_version` orchestration (idempotent-skip wiring, `VersionAnchored` parsing and the missing-event error), `get_version` bounds, `_read_version` struct decoding, the `_send` happy path and `status != 1`, `_wait_confirmations`, health success and wrong `chain_id`, and `from_settings`. Add stubbed-AsyncWeb3 tests for those in P5-04 (`tests/unit/chain/`).
- P4 review LOW: `request_kwargs={"timeout": float}` may not be enforced by aiohttp (use `ClientTimeout`; verify); no gas buffer and `baseFeePerGas` defaults to 0 on non-1559 chains; idempotency ignores `canon_version` (state in 05 if intended); Fake vs real diverge (canon_version range, `anchored_at` is a block counter, never raises `ChainUnavailableError`); `main.py` lifespan: if `registry_client.aclose()` raises, the Mongo client is not closed (use nested try/finally), and a half-set REGISTRY_ADDRESS/ANCHOR_PRIVATE_KEY only logs a generic warning; health does not check ANCHOR_ROLE or balance, and `/chain/status` (04) is not implemented (confirm scope); confirmations wait does not re-verify the receipt after a reorg (fine locally, note for sepolia).

- P5-01 known limits (registration rollback, `DocumentService.register`):
  - Events are append-only, so if `REVISION_SUBMITTED` fails after `DOCUMENT_CREATED` was written, the rows and S3 object are rolled back but the first event stays, pointing at a deleted document. Logged (ids only); pinned by `test_event_2_failure_leaves_a_logged_orphan_event`. The real fix is the atomic write / reconcile check the P2 review asks for in the P5 services.
  - A `DOCUMENT_CREATED` append that commits and then raises is not counted as written (no orphan-event log line). Rolled-back rows are still removed.
  - Rollback is `except Exception`, so a cancelled request (client disconnect, `CancelledError`) can leave orphans; and a rollback step that itself fails leaves orphans that are only logged (`registration rollback incomplete, orphaned resources: ...`). A reconciler for orphaned S3 keys / rows does not exist yet.
  - The 12 MB tree-size guard with S3 fallback (03 line 50) is still not implemented; a very large PDF could exceed Mongo's 16 MB document limit and would then fail at the tree upsert (rolled back, 500). Decide before P6 or drop from 03.
  - `logger.exception("unhandled exception")` in the request-id middleware logs `str(exc)` via the traceback, so any raw web3/aiohttp exception that escapes a service would log an RPC URL / API key. Chain errors are mapped in P5-04; consider redacting in the log formatter in P10-01.

- P5-02 interpretation choices and limits (revision submission, `DocumentService.submit_revision`):
  - **Owner-only submit is an interpretation, not spec.** 04 says only `ISSUER` for `POST /documents/{id}/revisions`; the code also requires `submitter == document.owner_id` (403 otherwise). Revisit if a shared-team workflow is ever needed (e.g. a per-document ISSUER allow-list).
  - `change_note` is required on submit (04 lists it without `?`, unlike registration); blank is 422 VALIDATION_ERROR.
  - The PENDING check is scoped to `(document_id, status=PENDING)`; pinned by `test_pending_revision_on_another_document_never_blocks` and the other-owner variant. The parent is the latest APPROVED revision (not the latest revision); NO_CONTENT_CHANGE compares `text_root` only when `canon_version` matches, and is skipped when no revision is approved yet.
  - Races: two submits that both pass the pending check compute the same `revision_no`; the unique `(document_id, revision_no)` index rejects the loser, mapped to 409 PENDING_REVISION_EXISTS and rolled back (`test_racing_submit_loses_...`).
  - Counter: `bump_revision_count` is one atomic `$inc` (100 concurrent bumps verified on mongo:7). Its compensating -1 is registered only after the `$inc` returned, so an increment that commits but loses its ack leaves `revision_count` one too high (logged nowhere, pinned by `test_write_that_commits_then_raises_is_rolled_back[counter]`). Same append-only-event orphan limit as P5-01 if the event append commits then raises.
  - The 12 MB tree-size guard (see P5-01 limits) is still undecided.

## Follow-ups (ideas deliberately deferred — do not implement without a task)
- CI records the PyMuPDF version; consider a CI check that it matches the pin.
- **Presigned URL host (P2-03):** `S3Storage.presign_get` signs against the internal `S3_ENDPOINT_URL`. That host is only browser-reachable when the backend runs on the host next to MinIO (`http://localhost:9000`). Once the backend runs in Docker (`app` compose profile, P10-03) the endpoint is `http://minio:9000`, which a browser cannot resolve. The host is part of the SigV4 signature, so it cannot be rewritten after signing. **Must be resolved by P8-03 (revision file download in the frontend) together with the compose networking in P10-03, before either is called done.** Options: a separate `S3_PUBLIC_ENDPOINT_URL` used only for presigning (needs an `.env.example` entry and a second boto client), or a backend proxy download route. No P2-03 test covers this: moto and the host-local MinIO check use one hostname.
- **/health degraded status code (P2-04):** `/health` returns HTTP 200 with `status: "degraded"` in the body when mongo or S3 is down. Whether it should return 503 instead is undecided; decide in P10 when real deployment/orchestration is set up (Docker healthchecks, any future load balancer), since that is when it matters operationally. Do not change before then.
- Event append concurrency (P2-02, ADR-019): `EventRepository.append` retries once on a lost race. That is enough for the maker/checker pattern (at most 2 concurrent writers per document; pinned by `test_two_concurrent_appends_both_succeed_and_chain_stays_linear`), and higher contention fails safely with `ConflictError` (409) and never forks (`test_many_concurrent_appends_never_fork`, both in `tests/integration/test_events_real_mongo.py`). If a future usage pattern needs more concurrent writers per document, the retry count in `events.py` (or adding backoff/jitter) is the tuning knob.
- **Auth roles read fresh from DB (P3-02, deliberate):** `get_current_user` / `require_roles` load the user from Mongo on every authenticated request and check `is_active` and `roles` from that document, NOT from the JWT `roles` claim. The claim is still issued (04 requires it) but is not trusted for authorization. Tradeoff: performance vs immediate revocation. Costs one indexed `_id` lookup per request; in return, role changes (`PATCH /users/{id}/roles`) and deactivation take effect at once instead of waiting up to `jwt_expire_minutes` for the token to expire (there are no refresh tokens or revocation list, ADR-014). If request volume ever makes that lookup a bottleneck, options are a short-TTL in-process user cache (bounds revocation delay to the TTL) or trusting the claim with a short expiry; either weakens immediate revocation, so decide deliberately and record an ADR.
- **Last-admin guard (P3-02):** `AuthService.set_roles` refuses (409 CONFLICT) to remove ADMIN from an active user when no other *active* ADMIN exists. Known limits:
  - **Race window:** it is check-then-write, not atomic. Two admins demoting each other at the same instant can both pass the check and leave zero active admins. Narrow for a small system; closing it needs a Mongo transaction or a post-write recount with rollback.
  - **Future deactivate-user endpoint:** the same guard MUST apply there (deactivating the last active ADMIN is the same lockout). No such endpoint exists yet; whoever adds one must reuse `count_active_with_role` and add the matching test.
  - Direct DB edits bypass it. Lockout recovery: rerun `python -m app.scripts.seed` (P3-03; restores `admin@proofchain.local` to ADMIN + active, or recreates it), or `db.users.updateOne({email: "..."}, {$set: {roles: ["ADMIN"], is_active: true}})` in mongosh.
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

- **P6 verification: compare on-chain `revoked` in the RECORD_MISMATCH check (found in P4-01 design discussion, MEDIUM):**
  02 §11 decides authorization from Mongo only (`status == APPROVED and not revoked`), and its chain cross-check compares only `(fileHash, textRoot)`. If Mongo and chain disagree on revocation (chain revoked but Mongo still APPROVED, or the reverse, e.g. after the non-atomic P5-05 revoke write fails halfway), verification cannot detect it. Fix in P6: extend the cross-check to compare the on-chain `revoked` flag (`OnChainVersion` must expose it) against Mongo `status == REVOKED`, yielding `RECORD_MISMATCH` on divergence. Needs a 02 §11 spec edit (ADR) plus a test in each direction. Related context, deliberate in P4-01: revocation is audit-preserving. A revoked version stays readable on-chain, and a later version's `prevTextRoot` still points at the revoked version's `textRoot` (test "keeps the hash chain intact when anchoring after a revoke"). Nothing in verification or localization walks `prevTextRoot` (it is an audit field), and revoked versions are excluded as reference baselines (02 §10) and as authentic matches (02 §11), so a revoked version's data is not trusted going forward.

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

### 2026-09-20 — P3-01 Passwords & JWT
- Done: `app/security/passwords.py` (bcrypt hash/verify, sync), `app/security/jwt.py` (HS256 create/decode, `TokenClaims`, injectable clock), `UnauthorizedError` (401), prod validator in `config.py` for `jwt_secret`.
- Tests: `test_passwords.py`, `test_jwt.py` (round trip, expiry, wrong secret, tampered payload, alg none / HS512, missing and invalid claims, garbage), `test_config.py`. 431 passed, ruff/mypy clean.
- Decisions: passwords over 72 bytes are rejected (bcrypt would truncate); `verify_password` returns False for them and for malformed hashes. No iss/aud claims (04 lists only sub, roles, exp). No ADR.
- Issues: the P0 prod-config finding is only HALF closed: `jwt_secret` done; `anchor_private_key` re-assigned to P4-03 (see Known issues and TASKS.md P4-03).
- Next: P3-02

### 2026-09-20 — P3-02 Auth routes, dependencies, role guard
- Done: `POST /auth/register|login`, `GET /auth/me`, `PATCH /users/{id}/roles` (ADMIN); `AuthService` (services/auth.py), DTOs (schemas/auth.py), `get_current_user` / `require_roles` / `require_register_access` in deps.py; settings on `app.state`.
- Tests: `test_auth.py` (register, login, me, bad tokens, role 403s, roles-from-DB, prod register, last-admin guard). 461 passed, ruff/mypy clean.
- Decisions: roles read from DB per request, not the JWT claim; login always does one real bcrypt verify (dummy hash for unknown email); register is ADMIN-only in prod; emails normalised; 422 handler strips `input`; ruff treats `Depends` as immutable; last-admin guard (409). No ADR.
- Issues: last-admin guard is check-then-write (race), and must be reused by any future deactivate endpoint (see Follow-ups); `anchor_private_key` prod check still P4-03.
- Next: P3-03

### 2026-09-25 — P3-03 Seed script
- Done: `app/scripts/seed.py` (`python -m app.scripts.seed`): creates `admin@` / `issuer@` / `approver@proofchain.local` (ADMIN / ISSUER / APPROVER). Rerun repairs roles + `is_active` only (never password or name), so it doubles as lockout recovery; it writes via the repository, bypassing the last-admin guard on purpose. `seed_password` setting + `.env.example` entry.
- Tests: `test_seed.py` (20): idempotency, seed emails validate through `RegisterIn`, total-lockout recovery (demoted / deactivated / both / row deleted, other admins inactive, precondition `count_active_with_role("ADMIN") == 0`, recovered admin can log in), prod without `SEED_PASSWORD` (None / "" / whitespace) raises before any write and existing users unchanged, `main()` exits 1 with a clear stderr message and never calls `create_client`. 481 passed, ruff/mypy clean.
- Decisions: `@proofchain.local` domain; password from `SEED_PASSWORD`, dev-only default, required in prod (checked before any connection). No ADR.
- Real Mongo (mongo:7) checked by hand: create path on a throwaway DB (3 "created", roles correct, admin login OK, DB dropped) and repair path on `proofchain` (idempotent, 3 users).
- Issues: `set_roles` does not itself block restoring ADMIN; in a real lockout the API path is unusable because no active ADMIN can authenticate, hence the seed.
- Next: P3 phase review, then P4-01

### 2026-09-25 — P4-01 ProofChainRegistry.sol + tests
- Done: `contracts/contracts/ProofChainRegistry.sol` per 05 (AccessControl, custom errors, event per state change); removed Placeholder.sol and the smoke test. docs/05 gained an "Implementation details" note.
- Tests: `ProofChainRegistry.test.ts` (25): v1/v2 linkage, event args and timestamps, role checks (incl. admin grant/revoke, anchorer cannot grant), zero-hash and zero-address reverts, out-of-range versions, revoke and double revoke, findByFileHash hit/miss/duplicate/revoked, and v1 -> v2 -> revoke v2 -> v3 keeping `prevTextRoot` = v2 root. tsc clean.
- Gas (final 25-test run, optimizer 200 runs): anchorVersion min 120,622 / max 125,813 / avg 122,409 (29 calls), revokeVersion 35,636-35,780 / avg 35,684 (6 calls), grantRole 51,450, revokeRole 29,486, deploy 869,000 (1.4% of block limit). findByFileHash is a linear scan (view, no tx gas).
- Decisions: `ZeroAddress` constructor error; `latestVersion` on empty doc reverts `VersionNotFound(docId, 0)`; findByFileHash returns the newest match; revocation is audit-preserving (revoked versions stay readable, later `prevTextRoot` still links to them); `revokedAt` is event-only. No ADR (05 is not the normative canon spec; no CANON_VERSION impact).
- Review: `code-reviewer` found no HIGH/MEDIUM. LOW items handled: 3 extra tests and a NatSpec note on `reason`. Left as is: duplicate hashes and `canonVersion == 0` are accepted.
- Issues: RECORD_MISMATCH should also compare on-chain `revoked` (see Follow-ups, for P6).
- Next: P4-02 (deploy script writes deployments JSON and the backend ABI)

### 2026-09-25 — P4-02 Deploy script + ABI export
- Done: `contracts/scripts/deploy.ts` (thin CLI) + `scripts/lib/deploy-lib.ts` (`deployRegistry`): admin = deployer, anchorer = `ANCHOR_ADDRESS` (default deployer); writes `contracts/deployments/<network>.json` and the bare ABI array to `backend/app/chain/abi/ProofChainRegistry.json` (committed); prints `REGISTRY_ADDRESS=`. `deploy:local` npm script, `ANCHOR_ADDRESS` in `.env.example`.
- Tests: `test/deploy.test.ts` (6): default and explicit anchorer roles, record fields + code at address, ABI equals artifact, byte-identical re-runs, malformed `ANCHOR_ADDRESS` rejected before any tx. Contracts 31 passed, tsc clean. Manual: real `hardhat node` + `deploy --network localhost` gave 0x5FbD...0aa3 (block 1); localhost.json and 26-entry ABI verified.
- Decisions: in-process `hardhat` network writes no files unless output paths are passed; `deployments/localhost.json` and `hardhat.json` are gitignored (sepolia.json will be committed in P10-02). No ADR.
- Issues: none. Backend untouched.
- Next: P4-03 (also must reject empty `anchor_private_key` in prod, see Known issues)

### 2026-09-25 � P4-03 RegistryClient (Fake + Web3)
- Done: `app/chain/` (`RegistryClient` Protocol, `FakeRegistryClient`, `Web3RegistryClient` on AsyncWeb3 with EIP-1559, nonce lock, confirmations, `VersionAnchored` parsing, `hexutil`, `types`); `get_registry_client` dep (503 if unconfigured), lifespan builds and closes the client; `GET /health` now reports `chain` ok/down/not_configured (concurrent, timeout-bounded, no exception text); prod config rejects empty `ANCHOR_PRIVATE_KEY` and `REGISTRY_ADDRESS`.
- Tests: `tests/unit/chain/` (hex, fake client, shared idempotency rule, dep wiring), 6 new health tests, config tests; `-m chain` `test_chain_web3.py` (4) passed on a real Hardhat node. 529 passed, ruff/mypy clean.
- Decisions: idempotency skips the tx only if the latest version matches fileHash+textRoot AND is not revoked (else anchors fresh); skipped anchor returns `already_anchored=True, tx_hash=None`; provider retries disabled so a down node fails fast (retries belong to P5-04); `chain: not_configured` does not degrade `status`. Noted in docs/04 and 05. No ADR.
- Issues: none. `aclose()` added to the Protocol to avoid leaking the HTTP session.
- Next: P4 phase review, then P5-01

### 2026-09-25 — P5-01 Document registration service + route
- Done: `POST /api/v1/documents` (ISSUER only, multipart `file`, `title`, `doc_type`, `change_note?`) returning 201 `{document, revision}`. `DocumentService.register` validates title/note/size/PDF header, builds the tree in a worker thread (core errors mapped to `INVALID_PDF`/`ENCRYPTED_PDF`/`NO_EXTRACTABLE_TEXT`), then writes S3 -> document -> revision -> tree -> `DOCUMENT_CREATED` -> `REVISION_SUBMITTED`, with best-effort reverse rollback of S3/tree/revision/document on any failure. New: `S3Storage.delete`, `tree_mapping.tree_to_doc`, `schemas/documents.py` DTOs (S3 key not exposed), `get_document_service` dep.
- Tests: `test_documents_register.py` (16: happy path vs direct core call, S3/DB/events persisted and event chain valid, authz 401/403, all 422/413 cases, filename path stripped); `test_documents_register_faults.py` (failure at each of 6 steps; DB write that commits then raises; failure of the rollback itself for every step x every rollback step, and all rollback steps at once: original error is what the caller sees, every registered undo step still attempted, log has class names and ids only, no exception text in body or service log); storage delete test. Mutation check: disabling the rollback call fails 34 of 40 fault tests. 587 passed, ruff/mypy clean.
- Decisions: DB undo steps are registered before their write (a write that commits then raises is still cleaned up); S3 put is registered after success (needs the version id to delete that exact version). Uses the existing catch-all in the request-id middleware for 500s, no new handler. No ADR.
- Issues: see Known issues "P5-01 known limits".
- Next: P5-02 Submit revision

### 2026-09-25 — P5-02 Submit revision
- Done: `POST /api/v1/documents/{id}/revisions` (ISSUER and document owner, multipart `file` + required `change_note`) returning 201 `{document, revision}`. `DocumentService.submit_revision`: 404 / 403 / 409 `PENDING_REVISION_EXISTS` / 422 `NO_CONTENT_CHANGE` before any write, then S3 -> revision -> tree -> atomic `revision_count` `$inc` -> `REVISION_SUBMITTED`, with the P5-01 reverse rollback (generalized with an `op` label). Shared upload validation moved to `services/_intake.py`. New: `DocumentRepository.bump_revision_count`, `RevisionRepository.get_latest_approved`.
- Tests: `test_revisions_submit.py` (22: parent linkage, events, pending 409, pending on another document/owner never blocks, rejection then resubmit, same-text-new-bytes and identical-file 422, no-parent case, authz 401/403/403-non-owner/404, note rules, bad uploads, lost race on revision_no), `test_revisions_submit_faults.py` (failure at each of 5 steps, commit-then-raise, failing rollback: original error kept, no exception text in body or log), `test_document_counter.py` (4) and `-m mongo` `test_document_counter_real_mongo.py` (100 concurrent `$inc`, passed on mongo:7). 622 passed, ruff/mypy clean.
- Decisions: owner-only submit and required `change_note` (see Known issues, P5-02); no ADR (no spec/CANON change).
- Issues: see Known issues "P5-02 interpretation choices and limits".
- Next: P5-03 Approve/reject + provenance events (must also update `latest_approved_*` and fix the state+event write order, see P2 review).
