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
