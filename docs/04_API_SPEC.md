# 04 — REST API (FastAPI, prefix `/api/v1`)

Auth: `Authorization: Bearer <JWT>` (HS256, claims `sub`, `roles`, `exp`). OpenAPI auto-served at `/docs`.
Error envelope for all 4xx/5xx:
```json
{ "error": { "code": "REVISION_NOT_PENDING", "message": "Revision is not pending", "details": {} } }
```
Pagination: `?page=1&page_size=20` → `{ "items": [...], "page": 1, "page_size": 20, "total": 57 }`.

## Auth
| Method | Path | Role | Body / Notes | Response |
|---|---|---|---|---|
| POST | /auth/register | public (dev) / ADMIN (prod) | `{email, password, full_name}` → role VERIFIER | 201 User |
| POST | /auth/login | public | `{email, password}` | 200 `{access_token, token_type, user}` |
| GET | /auth/me | any | — | User |
| PATCH | /users/{id}/roles | ADMIN | `{roles: [...]}` | User |

A seed script (`python -m app.scripts.seed`) creates `admin@`, `issuer@`, `approver@` demo users.

## Documents & revisions
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | /documents | ISSUER | multipart: `file`, `title`, `doc_type`, `change_note?` → creates document + revision 1 (PENDING). 201 `{document, revision}` |
| GET | /documents | any | filter `q`, `doc_type`, `status`; paginated |
| GET | /documents/{id} | any | `{document, latest_approved_revision}` (revision or `null`) |
| POST | /documents/{id}/revisions | ISSUER | multipart `file`, `change_note`; parent = latest approved; 409 if one PENDING exists; 422 if text_root equals parent (no change) |
| GET | /documents/{id}/revisions | any | all revisions ordered by `revision_no` |
| GET | /revisions/{id} | any | revision detail |
| GET | /revisions/{id}/tree | any | integrity tree (roots + chunks) |
| GET | /revisions/{id}/file | any | `{url, expires_in}` presigned GET |
| GET | /revisions/{id}/diff?against={revId} | any | LocalizationResult + analysis between two revisions (default against parent) |
| POST | /revisions/{id}/approve | APPROVER | `{comment?}`; 403 if approver == submitter; 202 → anchoring in background. Returns the revision (`status=APPROVED`, `anchor.status=ANCHORING`); 409 `REVISION_NOT_PENDING` if not PENDING (incl. losing a concurrent review) |
| POST | /revisions/{id}/reject | APPROVER | `{comment}` required (blank = 422); 200 with the revision; 403 `SELF_APPROVAL_FORBIDDEN` if rejecter == submitter (maker ≠ checker applies to both decisions); 409 `REVISION_NOT_PENDING` if not PENDING |
| POST | /revisions/{id}/revoke | APPROVER | `{reason}` required (blank = 422, max 500 chars, stored on-chain so public); only APPROVED **and** anchored. Synchronous: 200 with the revision (`status=REVOKED`, `revocation`) after the on-chain revoke. 409 `REVISION_NOT_APPROVED` + `details.status` if not APPROVED (incl. already REVOKED); 409 `CONFLICT` + `details.anchor_status` if APPROVED but not ANCHORED yet; 503 `CHAIN_UNAVAILABLE` (chain down or not configured), 502 `ANCHOR_FAILED` (rejected on-chain); nothing is written on any of these. Any APPROVER may revoke (maker ≠ checker does not apply) |
| POST | /revisions/{id}/retry-anchor | ADMIN | idempotent: checks chain before sending. `anchor.status=FAILED` → 202, revision returned queued (`ANCHORING`), new attempt in background; `ANCHORED` → 200 no-op; queued/in flight → 409 `CONFLICT`; not APPROVED → 409 `REVISION_NOT_APPROVED` |
| GET | /documents/{id}/provenance | any | ordered events + `chain_valid` (hash-chain check) |

Read routes (P5-05). "any" = any authenticated user (401 without a token); unknown ids are 404 `NOT_FOUND`.
- `GET /documents`: `page` ≥ 1 (default 1), `page_size` 1–100 (default 20), newest `updated_at` first.
  `q` is a case-insensitive **literal** substring of `title` (max 200 chars; never a regex). `doc_type` is one
  of the DocType values. `status` (a revision status) matches documents that have **at least one** revision
  in that status, so a document with an APPROVED and a PENDING revision is listed under both filters (never
  twice in one list). Items are Document objects. Invalid parameters are 422 `VALIDATION_ERROR`.
- `GET /documents/{id}/revisions`: plain array of revisions (not paginated), ascending `revision_no`.
- `GET /revisions/{id}/tree`: `{revision_id, document_id, canon_version, file_hash, text_root, page_count,
  pages: [{index, root, chunks: [{id, index, text, leaf_hash, bbox, section_id}]}], sections}`; 404 if the
  revision or its tree is missing.
- `GET /revisions/{id}/file`: `{url, expires_in}`; the URL pins the stored S3 object version. Known limit: it
  is signed for the backend's S3 endpoint (see PROGRESS.md "Presigned URL host", owned by P8-03/P10-03).
- `GET /documents/{id}/provenance`: `{document_id, chain_valid, events: [{id, document_id, revision_id, type,
  actor_id, at, data, prev_event_hash, event_hash}]}` in hash-chain order; events that are off the chain
  (tampered/forked) are still listed after it, and `chain_valid` is then `false`.
- `GET /revisions/{id}/diff?against={revId}` (P5-06): `{revision_id, against_revision_id, localization,
  analysis}`. `{id}` is the candidate and `against` the reference (default: `{id}`'s `parent_revision_id`);
  `localization` is the LocalizationResult of 02 §9 computed from the two stored trees. `analysis` is `null`
  until NLP is integrated (P7-04). Any revision status may be diffed (approvers review PENDING ones here).
  Errors: 404 `NOT_FOUND` (either revision or either tree missing); 422 `VALIDATION_ERROR` +
  `details.field="against"` when `{id}` has no parent and no `against` is given, or `against` belongs to
  another document; 409 `CONFLICT` + `details {canon_version, against_canon_version}` when the two trees were
  built under different `CANON_VERSION`s (hashes not comparable; nothing is localized).
- Revisions in every response carry `revocation` (`null` unless REVOKED) and never expose the S3 key.

## Verification
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | /verify | public or any (config `PUBLIC_VERIFY=true`) | multipart `file`, `document_id?`, `include_nlp=true` → VerificationReport |
| GET | /verifications | any | own history, paginated |
| GET | /verifications/{id} | owner/ADMIN | full report |

### VerificationReport (response shape)
```jsonc
{ "id": "uuid", "verdict": "TAMPERED", "summary": "3 changes on pages 2 and 5 vs approved v3",
  "document": { "id": "…", "title": "…" },
  "matched_revision": null,
  "reference_revision": { "id": "…", "version_no": 3, "revision_no": 5, "anchored_tx": "0x…" },
  "steps": [ { "name": "FILE_HASH", "status": "FAIL", "detail": "…" },
             { "name": "TEXT_ROOT", "status": "FAIL" },
             { "name": "LOCALIZATION", "status": "DONE", "detail": "MERKLE_FAST_PATH, 12 comparisons" },
             { "name": "AUTHORIZATION", "status": "FAIL", "detail": "No approved or pending revision matches" },
             { "name": "CHAIN_CHECK", "status": "PASS" },
             { "name": "SEMANTIC_ANALYSIS", "status": "DONE" } ],
  "candidate": { "file_hash": "…", "text_root": "…", "page_count": 7 },
  "localization": { /* LocalizationResult, see 02_ALGORITHMS §9 */ },
  "analysis": [ { "region_id": "r1", "primary_category": "AMOUNT_CHANGE", "categories": ["AMOUNT_CHANGE"],
                  "severity": "HIGH", "similarity": 0.94,
                  "entity_changes": [ { "type": "MONEY", "before": "₹50,000", "after": "₹80,000" } ],
                  "explanation": "The amount changed from ₹50,000 to ₹80,000 in Section 4 (Payment Terms)." } ],
  "chain_check": { "performed": true, "ok": true, "tx_hash": "0x…", "explorer_url": "…" },
  "timings_ms": { "total": 812 } }
```

## System
| GET | /health | public | `{status, mongo, s3, chain, nlp, canon_version}` |
|---|---|---|---|
| GET | /chain/status | any | `{chain_id, contract, latest_block, anchor_account, balance_eth}` |

`/health`: `canon_version` is an integer (the `CANON_VERSION` constant of `proofchain_core`). `mongo`/`s3` are `"ok"` or `"down"`; `chain` is `"ok"`/`"down"` from the registry client's `health()` (checked concurrently with a per-probe timeout, no exception text) or `"not_configured"` when no registry client is configured, which does not degrade `status`; `nlp` is `"not_configured"` until implemented; `status` is `"ok"` or `"degraded"` and the HTTP status stays 200.

## Error codes (non-exhaustive)
`INVALID_PDF, ENCRYPTED_PDF, NO_EXTRACTABLE_TEXT, FILE_TOO_LARGE, NOT_FOUND, FORBIDDEN, SELF_APPROVAL_FORBIDDEN,
REVISION_NOT_PENDING, REVISION_NOT_APPROVED, PENDING_REVISION_EXISTS, NO_CONTENT_CHANGE, ANCHOR_FAILED, CHAIN_UNAVAILABLE, VALIDATION_ERROR`.

`REVISION_NOT_APPROVED` (409): anchoring was requested for a revision whose `status` is not `APPROVED`. Raised by
every anchoring entry point (retry endpoint, startup reconciler, direct service call); only APPROVED revisions
are ever anchored.

Anchoring (P5-04): approve returns 202 and anchoring runs after the response. The outcome is only visible on the
revision (`anchor.*`) and in provenance events (`VERSION_ANCHORED` / `ANCHOR_FAILED`); an unconfigured chain
does not fail the approval, it records `anchor.status=FAILED`, `anchor.error=CHAIN_NOT_CONFIGURED`. On an
ANCHORED revision `anchor.tx_hash` may be `null` when the version was recovered as already on-chain.
