# 03 — Data Model (MongoDB)

Driver: **Motor** (async) + Pydantic v2 models; repositories in `app/repositories/` own all queries.
All `_id`s are UUID4 strings (not ObjectId) so they are portable into URLs and on-chain derivations.
Timestamps: UTC `datetime`. Hashes: 64-char lowercase hex.

## users
```jsonc
{ "_id": "uuid", "email": "a@b.com", "full_name": "…", "password_hash": "bcrypt…",
  "roles": ["ISSUER"|"APPROVER"|"VERIFIER"|"ADMIN"], "is_active": true, "created_at": "…" }
```
Indexes: `email` unique.

## documents
```jsonc
{ "_id": "uuid", "title": "Lease Agreement – Flat 4B", "doc_type": "CONTRACT|CERTIFICATE|INVOICE|LEGAL|OTHER",
  "owner_id": "user uuid", "chain_doc_id": "hex(sha256(_id))",
  "latest_approved_revision_id": "uuid|null", "latest_approved_version_no": 3,
  "revision_count": 5, "created_at": "…", "updated_at": "…" }
```
Indexes: `owner_id`, `chain_doc_id` unique, text index on `title`.

## revisions  (every uploaded version)
```jsonc
{ "_id": "uuid", "document_id": "uuid", "revision_no": 4,          // sequential per document, all revisions
  "parent_revision_id": "uuid|null", "change_note": "Updated rent clause",
  "status": "PENDING|APPROVED|REJECTED|REVOKED",
  "version_no": 3,                                                 // set only when APPROVED+anchored (= the on-chain versionNo returned by anchorVersion / the VersionAnchored event, used directly (no +1))
  "submitted_by": "uuid", "submitted_at": "…",
  "reviewed_by": "uuid|null", "reviewed_at": "…|null", "review_comment": "…|null",
  "file": { "s3_key": "documents/{doc}/revisions/{rev}.pdf", "s3_version_id": "…", "size_bytes": 123,
            "original_filename": "lease.pdf", "content_type": "application/pdf" },
  "file_hash": "hex", "text_root": "hex", "canon_version": 2, "page_count": 7, "chunk_count": 88,
  "anchor": { "status": "NOT_REQUESTED|ANCHORING|ANCHORED|FAILED", "tx_hash": "0x…", "block_number": 123,
              "chain_id": 31337, "contract": "0x…", "anchored_at": "…", "error": "…|null", "attempts": 1 } }
```
Indexes: `(document_id, revision_no)` unique, `file_hash`, `text_root`, `(document_id, status)`, `anchor.status`.

## integrity_trees  (one per revision; kept separate to keep revisions small)
```jsonc
{ "_id": "revision uuid", "document_id": "uuid", "canon_version": 2, "file_hash": "hex", "text_root": "hex",
  "page_count": 7,
  "pages": [ { "index": 0, "root": "hex",
               "chunks": [ { "id": "p0-c0", "index": 0, "text": "…", "leaf_hash": "hex",
                              "bbox": [x0, y0, x1, y1], "section_id": "S1" } ] } ],
  "sections": [ { "id": "S1", "title": "1. Definitions", "chunk_ids": ["p0-c1", "…"], "hash": "hex" } ],
  "page_levels": [["hex", "…"], ["hex"]] }
```
Chunk text is stored (ADR-010) so NLP can compare without re-downloading PDFs. Size guard: if a tree
document would exceed 12 MB, store it as JSON in S3 (`trees/{rev}.json`) and keep only roots here.

## provenance_events  (append-only; never update or delete)
```jsonc
{ "_id": "uuid", "document_id": "uuid", "revision_id": "uuid|null", "type":
  "DOCUMENT_CREATED|REVISION_SUBMITTED|REVISION_APPROVED|REVISION_REJECTED|VERSION_ANCHORED|ANCHOR_FAILED|VERSION_REVOKED|VERIFIED",
  "actor_id": "uuid|null", "at": "…", "data": { /* type-specific: tx_hash, verdict, comment… */ },
  "prev_event_hash": "hex|null", "event_hash": "hex" }
```
`event_hash = sha256(canonical JSON of the event without event_hash)`; `prev_event_hash` chains events
per document — a cheap off-chain tamper-evidence for the audit log. Index: `(document_id, at)`.

## verifications
```jsonc
{ "_id": "uuid", "requested_by": "uuid|null", "at": "…", "document_id": "uuid|null",
  "candidate": { "filename": "x.pdf", "file_hash": "hex", "text_root": "hex", "page_count": 7 },
  "verdict": "…", "matched_revision_id": "uuid|null", "reference_revision_id": "uuid|null",
  "chain_check": { "performed": true, "ok": true, "onchain_file_hash": "hex", "onchain_text_root": "hex", "tx_hash": "0x…" },
  "localization": { /* LocalizationResult */ }, "analysis": [ /* ChangeAnalysis per region */ ],
  "timings_ms": { "hash": 0, "match": 0, "localize": 0, "nlp": 0, "chain": 0, "total": 0 } }
```
Index: `(document_id, at)`, `requested_by`.

## State machine (revisions)
```
PENDING --approve--> APPROVED (anchor: ANCHORING -> ANCHORED | FAILED -> retry)
PENDING --reject---> REJECTED   (terminal)
APPROVED --revoke--> REVOKED    (on-chain VersionRevoked event)
```
Only one PENDING revision per document at a time (409 otherwise).
