# 09 — Architecture Decision Records

Format: **ADR-NNN — Title** · Status · Context → Decision → Consequences. Append new ADRs; never rewrite old ones
(mark them *Superseded by ADR-XXX*).

**ADR-001 — Monorepo.** Accepted. One repo with backend/, contracts/, frontend/, eval/ so Claude Code sees all
contracts (ABI, API types) at once. → Deploy script copies ABI into backend.

**ADR-002 — MinIO locally, AWS S3 in production.** Accepted. Same boto3 code with optional `S3_ENDPOINT_URL`.
→ No AWS account needed for development; bucket versioning enabled in both.

**ADR-003 — Two fingerprints: file hash + canonical text root.** Accepted. Byte hash gives exact integrity; the
text root enables localization and robustness to re-saves. → Localization is text-level; visual changes only
surface via file hash.

**ADR-004 — CONTENT_EQUIVALENT is not AUTHENTIC.** Accepted. Text-identical files may still differ in images,
signatures or annotations. → Separate verdict with warning.

**ADR-005 — Domain-separated SHA-256 Merkle tree, odd node promoted.** Accepted. Prevents leaf/node confusion and
the duplicate-last-node mutation weakness. → Custom implementation (no third-party Merkle library), fully tested.

**ADR-006 — Merkle fast path + sequence alignment fallback.** Accepted. Positional comparison cascades after an
insertion; alignment over leaf hashes yields true insert/delete/modify. → Report both methods and their costs.

**ADR-007 — Only approved versions are anchored.** Accepted. Keeps gas cost proportional to meaningful events and
makes "on-chain" ⇔ "authorized". Pending/rejected live in Mongo with provenance events. Revocations are on-chain.

**ADR-008 — AI never affects verdicts.** Accepted (report §1.4). NLP runs after localization; failures degrade to rules.

**ADR-009 — Motor + Pydantic v2 repositories (no ODM).** Accepted. Explicit queries, easy fakes in tests.

**ADR-010 — Store chunk text in MongoDB.** Accepted. Faster diff/NLP, no S3 round-trip at verify time. Trade-off:
duplicates document content in DB (acceptable for v1; access-controlled). Revisit for privacy-sensitive deployments.

**ADR-011 — Hardhat local chain for dev, Sepolia for demo.** Accepted. Free, fast iteration; public explorer links
for the demo. Single backend anchor wallet with ANCHOR_ROLE.

**ADR-012 — Background anchoring with reconciliation.** Accepted. Approve returns 202; FastAPI BackgroundTasks sends
the tx; startup reconciler + admin retry handle FAILED/stuck states idempotently.

**ADR-013 — Versioned canonicalization (`CANON_VERSION`).** Accepted. Stored with every revision and on-chain so old
anchors remain verifiable after algorithm changes (verify with the stored version's rules).

**ADR-014 — JWT (HS256) with role claims.** Accepted. Simple for a single-org academic system. Refresh tokens out of scope.

**ADR-015 — PyMuPDF for extraction.** Accepted. Fast, gives bboxes and font info needed for sections and highlights.
Note AGPL licence — acceptable for academic use; mention in report.

**ADR-016 — version_no is 1-based end-to-end.** Accepted. Mongo `version_no`, API responses, and the on-chain `versionNo` (contract array index 0 = version 1) all use the same 1-based value; the backend never adds or subtracts 1 when moving between layers.

**ADR-017 — Page-level Merkle prefix (0x03); `CANON_VERSION` 1 → 2.** Accepted (P1-09 audit, finding 1).
*Problem:* in v1, `text_root` combined page roots with the same `node()` (prefix 0x01) used inside a page, so a
tree over pages was indistinguishable from a tree over chunks. Verified: pages `[a,b],[c,d]` and one page
`[a,b,c,d]` gave the same `text_root`; `[a,b],[c]` equalled `[a,b,c]`; and
`verify_proof(node_hash(a,b), proof[1:], root)` returned True, i.e. an internal node was accepted as a leaf.
A re-paginated document with the same chunk sequence therefore reported CONTENT_EQUIVALENT although `page_count`
(not stored on-chain) differed. No content forgery was possible without a SHA-256 collision, but it contradicted
ADR-005's aim of preventing leaf/node confusion.
*Decision:* page roots are combined with `page_node(l, r) = H(0x03 || l || r)` (0x00 leaf, 0x01 chunk node,
0x02 empty page are taken). `merkle_*` functions take a `node` keyword; `page_merkle_root` is the page-level entry
point; chunk-level trees and section hashes are unchanged. `CANON_VERSION` = 2.
*Consequences:* every multi-page `text_root` changes; single-page roots, page roots, leaf hashes and `file_hash` do
not. Committed fixture PDFs and their hashes are unaffected; only tests recomputing `text_root` were updated.
*Pre-launch exception, not a precedent:* this is a pre-launch version bump. No v1 anchors or stored revisions
exist (nothing is persisted before P2), so v1 is deliberately not kept as a verifiable version and no
backward-compatibility path is built. This carries no obligation and sets no precedent for later bumps. Once real
anchors exist, ADR-013 governs: `CANON_VERSION` is stored with every revision and on-chain, and a bump must keep
older anchors verifiable under their stored version's rules. From `CANON_VERSION = 2` onward, everything anchored
is covered by that mechanism.

**ADR-018 — Spec clarifications from the P1-09 audit, findings 2 and 7 (documentation and explicit defaults only; no hash or output change; `CANON_VERSION` stays 2 as set by ADR-017).** Accepted.
Code behaviour that the spec left ambiguous is now normative, and pinned by tests:
(1) §4 a sentence > 600 chars is cut at the last space at index ≤ 600 (piece length ≤ 600), else hard-cut at 600;
(2) §8 `body_size` ties take the smaller size; (3) §9 `hash_comparisons` = page-root comparisons (`page_count`, when
page counts are equal) + leaf hashes fed to the alignment of the scope diffed; (4) §9.4 the replace-pair text ratio
uses `SequenceMatcher(..., autojunk=True)`, passed explicitly. (4) has a known cost: on long chunks made of
frequent characters the ratio can collapse (590 chars, first 20 rewritten: 0.0 vs 0.99 with `autojunk=False`), so a
MODIFIED can surface as DELETED + INSERTED. Switching to `autojunk=False` would change localization output and
requires a new ADR; verdicts are unaffected either way. Related deferrals (P6 service-layer guards for quadratic
replace pairing and canon_version mismatch) are recorded in PROGRESS Follow-ups.

**ADR-019 — Canonical JSON and hash chain for `provenance_events` (P2-02; off-chain only, `CANON_VERSION` unchanged).** Accepted.
*Problem:* 03 says `event_hash = sha256(canonical JSON of the event without event_hash)` but never defines "canonical JSON". Left implicit, a change of JSON library, key order, escaping or timestamp format would silently invalidate every stored audit chain.
*Decision:* the hashed object has exactly these keys, sorted by code point: `_id`, `actor_id`, `at`, `data`, `document_id`, `prev_event_hash`, `revision_id`, `type` (`event_hash` excluded; null values are kept as `null`). Serialization is `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` encoded as UTF-8, then SHA-256, lowercase hex. `at` is a UTC string with exactly millisecond precision, `YYYY-MM-DDTHH:MM:SS.mmmZ` (BSON stores milliseconds; `append` truncates to ms before hashing so a stored event re-hashes identically). `data` may contain only `null`, bool, int, str, lists and dicts with str keys; floats, NaN/Infinity, datetimes and other types are rejected (`ValueError`) so the hash never depends on float formatting. Naive datetimes are rejected.
*Chaining:* `prev_event_hash` is `null` for a document's first event, else the previous event's `event_hash`. A unique index on `(document_id, prev_event_hash)` makes forks impossible (a document has one genesis event and each event has at most one successor); `append` retries once on a conflict.
*Pinned by:* `tests/unit/app/test_event_hash.py` asserts the literal serialized string and its SHA-256 for one concrete event (independently computed with hashlib). If it fails, stored `event_hash`es would no longer verify: change the format only with a new ADR and a migration, never by editing the literals.
*Limits:* the chain is cheap off-chain tamper evidence, not a security boundary. Deleting the newest event(s) of a document is undetectable from the chain alone (a truncation leaves a valid shorter chain); anchored state on-chain remains the source of truth. `verify_chain` detects mutation, mid-chain removal and reordering.

**ADR-020 � Chain cross-check compares `revoked` and `canon_version`, and an outage is never a mismatch (P6-03; verification only, `CANON_VERSION` unchanged).** Accepted.
*Problem:* 02 �11 compared only `(fileHash, textRoot)` on-chain vs Mongo. The Follow-up "P6 verification: compare on-chain `revoked` in the RECORD_MISMATCH check" (found in the P4-01 design discussion) noted that a revocation divergence is invisible to it: the P5-05 revoke is chain-first and non-atomic, so a failed Mongo write leaves the chain revoked and Mongo APPROVED (and a direct Mongo edit can do the reverse). The spec also did not say what an unreachable node means.
*Decision:* the cross-check of the matched (or, for TAMPERED, the chosen reference) revision reads `getVersion(chain_doc_id, version_no)` and yields `RECORD_MISMATCH` if any of `file_hash`, `text_root`, `canon_version` differs, if on-chain `revoked != (Mongo status == REVOKED)`, or if the version does not exist on-chain. The lookup key is `Document.chain_doc_id`. The check runs only for `ANCHORED` revisions with a `version_no`. Otherwise, and when no registry is configured or the node is unreachable (`ChainUnavailableError`), it is *not performed*: `chain_check.performed=false`, `ok=null` with a reason code, and the Mongo-based verdict stands.
*Availability over guarantee:* an outage must not block verification and must not be reported as tampering (a false `RECORD_MISMATCH` would be worse than an unchecked one). The cost is that during an outage database tampering is not detected by that verification; the report says so through `performed=false`.
*Consequences:* mismatches list field names only, never values. `RECORD_MISMATCH` still overrides every other verdict (PRD); assembling the verdict is P6-04. The chain is not walked via `prevTextRoot`.


**ADR-021 - Anonymous `/verify` reports are redacted; unknown `document_id` is not an oracle for anonymous callers (P6 phase review; API behaviour only, `CANON_VERSION` unchanged).** Accepted.
*Problem:* with `PUBLIC_VERIFY=true` an unauthenticated caller could upload any parsable PDF with a known `document_id` and receive the localization of the approved reference: `ref_text` (the stored chunk text; for an unrelated upload, every reference chunk), bounding boxes, chunk ids and section titles. A report for a revoked file also carried the revocation `reason`, the revoker's user id and the tx hash (the reason is also embedded in the AUTHORIZATION step detail and the summary), and an unknown `document_id` gave 404 while a known one gave a report. 04 described the public response shape but never decided that stored content and revocation notes are public.
*Decision:* for an anonymous caller (`user is None`) the report is built redacted, so the stored record equals the response. Each localization region keeps `id`, `type`, `ref_page`, `cand_page`, `cand_chunk_id`, `section_id` (the `stats` and page lists are unchanged) and drops `ref_text`, `cand_text`, `ref_bbox`, `cand_bbox`, `ref_chunk_id`, `section_title`. A revocation keeps only `at`, and the AUTHORIZATION detail and summary say "revoked on <date>" without the reason. An unknown `document_id` is treated as no `document_id` (the same report as omitting it, HTTP 200). Authenticated callers are unchanged, including the 404 for an unknown id (they can already read every document through the read routes). `PUBLIC_VERIFY` keeps its default.
*Verdicts unaffected:* redaction runs after the verdict is fixed; it changes wording and disclosed fields only.
*Residual, accepted:* a known `document_id` with a non-matching upload still yields `TAMPERED` while an unknown one yields `UNKNOWN_DOCUMENT`, so existence is still inferable from the verdict. Closing it fully would mean ignoring `document_id` for anonymous callers and losing anonymous tamper localization; not done. Mitigated by `document_id` being a `uuid4` (122 random bits from `os.urandom`, not enumerable), which the caller must already hold. Pinned by `test_known_limit_existence_is_still_inferable_from_the_verdict`. `chain_doc_id = sha256(document_id)` is public on-chain and does not reveal the id.
*Not addressed here (logged in PROGRESS Known issues):* no rate limit or size cap beyond `max_upload_mb` on the anonymous route.
