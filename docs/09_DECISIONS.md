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
