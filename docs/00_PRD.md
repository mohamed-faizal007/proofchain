# 00 — Product Requirements (PRD)

## 1. Problem
Whole-document hashing tells you *whether* a PDF changed, never *where*, *what*, *whether it was
authorized*, or *how it evolved*. ProofChain answers all five by combining hierarchical SHA-256
hashing, Merkle trees, blockchain anchoring, maker–checker versioning, and NLP change classification.

## 2. Scope
**In scope (v1):** text-based (digitally generated) PDFs; English text; single organization deployment;
local chain (Hardhat) for development and Sepolia testnet for demo.
**Out of scope (v1):** scanned/image PDFs (OCR), images/signatures inside PDFs, non-English NLP,
multi-tenant orgs, mainnet deployment, digital-signature (PAdES) validation. Scanned PDFs must be
*rejected with a clear error*, not silently mis-hashed.

## 3. Users & roles
| Role | Can |
|---|---|
| ISSUER (maker) | Register documents, submit new revisions |
| APPROVER (checker) | Approve / reject revisions submitted by *someone else*; revoke approved versions |
| VERIFIER | Verify any PDF, view reports |
| ADMIN | Manage users/roles; everything above |
| Public (no login) | Verify a PDF and see the verdict (configurable) |

## 4. Functional requirements
| ID | Requirement | Objective (report §1.6) |
|---|---|---|
| FR-1 | Compute SHA-256 of raw file bytes for every uploaded PDF | O1 |
| FR-2 | Extract text per page, canonicalize, split into chunks, detect sections | O2 |
| FR-3 | Build hierarchical hashes: chunk → page → document text root; section hashes as an overlay | O2, O3 |
| FR-4 | Store PDFs in S3, metadata/trees/provenance in MongoDB | O5 |
| FR-5 | Revisions follow a maker–checker workflow: PENDING → APPROVED / REJECTED; APPROVED may be REVOKED | O5, O6 |
| FR-6 | On approval, anchor (docId, fileHash, textRoot, prevTextRoot, canonVersion) on-chain; record tx hash | O4 |
| FR-7 | Every state change writes an append-only provenance event | O5 |
| FR-8 | Verify a candidate PDF: exact match → content-equivalent → Merkle/alignment localization | O1, O3 |
| FR-9 | Decide authorization: matches approved version / known-but-unapproved / unknown modification | O6 |
| FR-10 | Cross-check Mongo records against on-chain records during verification | O4 |
| FR-11 | Classify each changed region (amount, date, party, clause add/remove/modify, obligation/negation, minor) with severity and explanation | O7 |
| FR-12 | Dashboard: verdict, pipeline steps, highlighted regions on the PDF, change list, version timeline, chain proof links | all |
| FR-13 | Evaluation harness producing metrics/plots for the report | research |

## 5. Verification verdicts (user-facing)
| Verdict | Meaning |
|---|---|
| `AUTHENTIC_LATEST` | Byte-identical to the latest approved version |
| `AUTHENTIC_SUPERSEDED` | Matches an older approved version; a newer one exists |
| `CONTENT_EQUIVALENT` | Canonical text identical to an approved version but bytes differ (re-save, metadata, or non-text change such as an image/signature). Shown with a warning; never called authentic |
| `UNAUTHORIZED_VERSION` | Matches a revision that was submitted but never approved (pending/rejected) or was revoked |
| `TAMPERED` | Matches nothing approved; changes localized against the closest approved version |
| `RECORD_MISMATCH` | Off-chain record disagrees with on-chain anchor (database tampering) — overrides all others |
| `UNKNOWN_DOCUMENT` | No document could be associated with the upload |

## 6. Non-functional requirements
- NFR-1 Determinism: same input → same hashes across Windows/Linux, runs, Python versions ≥3.11.
- NFR-2 Performance (local, no NLP): 20-page PDF register < 3 s, verify < 3 s. NLP adds < 5 s for ≤ 20 changes on CPU.
- NFR-3 Security: JWT auth, bcrypt passwords, role checks server-side, upload size/type validation, no secrets in repo, contract access-controlled.
- NFR-4 Privacy: no document content on-chain; presigned, short-lived S3 URLs.
- NFR-5 Testability: `proofchain_core` ≥ 90 % line coverage; contract 100 % function coverage.
- NFR-6 Reproducibility: eval results regenerate from a seed and a config file.

## 7. Success criteria (for the report)
- 100 % detection of any text change (by construction; verified empirically).
- Chunk-level localization F1 ≥ 0.95 on the synthetic tamper corpus; page-level ≥ 0.98.
- Zero false "TAMPERED" on benign re-saves (metadata-only changes).
- Change-type classification macro-F1 reported with confusion matrix (target ≥ 0.85).
- Gas cost per anchor and latency-vs-pages curves reported.

## 8. Glossary
- **Canonical text** — extracted text after the deterministic normalization in `02_ALGORITHMS.md`.
- **Chunk** — smallest hashed unit (a paragraph or part of one), ≤ 600 chars.
- **Text root** — Merkle root over page roots; the document's content fingerprint.
- **Revision** — any uploaded version of a document; **approved version** — a revision that passed checker approval and was anchored.
