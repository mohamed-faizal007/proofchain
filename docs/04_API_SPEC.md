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
| GET | /documents/{id} | any | document + latest approved revision summary |
| POST | /documents/{id}/revisions | ISSUER | multipart `file`, `change_note`; parent = latest approved; 409 if one PENDING exists; 422 if text_root equals parent (no change) |
| GET | /documents/{id}/revisions | any | all revisions ordered by `revision_no` |
| GET | /revisions/{id} | any | revision detail |
| GET | /revisions/{id}/tree | any | integrity tree (roots + chunks) |
| GET | /revisions/{id}/file | any | `{url, expires_in}` presigned GET |
| GET | /revisions/{id}/diff?against={revId} | any | LocalizationResult + analysis between two revisions (default against parent) |
| POST | /revisions/{id}/approve | APPROVER | `{comment?}`; 403 if approver == submitter; 202 → anchoring in background |
| POST | /revisions/{id}/reject | APPROVER | `{comment}` required |
| POST | /revisions/{id}/revoke | APPROVER | `{reason}`; only APPROVED; writes on-chain revocation |
| POST | /revisions/{id}/retry-anchor | ADMIN | idempotent: checks chain before sending |
| GET | /documents/{id}/provenance | any | ordered events + `chain_valid` (hash-chain check) |

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

## Error codes (non-exhaustive)
`INVALID_PDF, ENCRYPTED_PDF, NO_EXTRACTABLE_TEXT, FILE_TOO_LARGE, NOT_FOUND, FORBIDDEN, SELF_APPROVAL_FORBIDDEN,
REVISION_NOT_PENDING, PENDING_REVISION_EXISTS, NO_CONTENT_CHANGE, ANCHOR_FAILED, CHAIN_UNAVAILABLE, VALIDATION_ERROR`.
