# 02 — Algorithms (NORMATIVE)

> This file is the contract for `proofchain_core`. Any change requires an ADR in `09_DECISIONS.md`
> and, if hashes could change, a bump of `CANON_VERSION`. Current: **`CANON_VERSION = 1`**.

## 1. Pipeline overview
```
pdf bytes ──► file_hash = SHA256(bytes)
          └─► extract blocks per page ─► canonicalize ─► chunk ─► leaf hashes
                                                             ├─► page roots ─► TEXT ROOT
                                                             └─► sections (overlay) ─► section hashes
```

## 2. Extraction (`extract.py`)
- Library: **PyMuPDF** (`import pymupdf`), pinned version in `pyproject.toml`.
- For each page (0-based index `p`): `page.get_text("dict", sort=True)`; keep blocks with `type == 0`.
- For each block: for each line, concatenate span texts in order; join lines with a single space.
  Record `bbox` (block bbox, PDF points, top-left origin), and per-span `size` and `flags` (bold = `flags & 16`).
- Reject document with `NoExtractableTextError` if total canonical characters across all pages < 20
  (likely scanned). Reject encrypted PDFs (`EncryptedPdfError`) and non-PDF bytes (`InvalidPdfError`).

## 3. Canonicalization (`canonical.py`) — `normalize_text(s) -> str`
Applied to every block text, in this exact order:
1. Unicode **NFKC** (also expands ligatures ﬁ → fi).
2. Remove soft hyphen `U+00AD` and zero-width chars `U+200B U+200C U+200D U+FEFF`.
3. Map quotes `‘ ’ ‚ ‛ ′` → `'` and `“ ” „ ‟ ″` → `"`; dashes `‐ ‑ ‒ – — ―` → `-`.
4. Replace every run of Unicode whitespace (incl. NBSP, tabs, newlines) with one ASCII space.
5. Strip leading/trailing spaces.
**Case, punctuation, digits and currency symbols are preserved** (they carry meaning: amounts, dates).
Blocks whose canonical text is empty are dropped. No header/footer removal in v1.

## 4. Chunking (`chunking.py`)
- `MAX_CHUNK_CHARS = 600`.
- Each surviving block is one paragraph. If `len(text) <= 600` → one chunk.
- Otherwise split into sentences with regex `(?<=[.!?;:])\s+(?=[A-Z0-9("'\[])` and greedily pack
  consecutive sentences while the packed length (joined by single spaces) ≤ 600. A single sentence > 600
  is split at the last space before position 600 (hard split if no space).
- Chunk id: `p{page}-c{index}` where `index` is 0-based within the page, in reading order.
- Chunk fields: `id, page, index, text, bbox, leaf_hash`. Split chunks inherit the block bbox.

## 5. Hashing (`hashing.py`) — domain-separated SHA-256
```
H(x)            = SHA-256(x)                               (lowercase hex in Python)
leaf(chunk)     = H(0x00 || utf8(chunk.text))
node(l, r)      = H(0x01 || bytes(l) || bytes(r))
EMPTY_PAGE_ROOT = H(0x02 || b"PROOFCHAIN_EMPTY_PAGE")
file_hash       = H(raw pdf bytes)
```
Domain separation prevents leaf/node confusion (second-preimage) attacks.

## 6. Merkle tree (`merkle.py`)
- `merkle_root(hashes: list[str]) -> str`: build levels bottom-up; pair adjacent nodes left→right with `node(l, r)`;
  if a level has an odd count, the **last node is promoted unchanged** to the next level (never duplicated —
  duplication enables the CVE-2012-2459 mutation). Root of a single-element list is that element.
  Empty list is an error (callers use `EMPTY_PAGE_ROOT`).
- `merkle_levels(hashes) -> list[list[str]]` (level 0 = leaves) for storage and proofs.
- `merkle_proof(hashes, i) -> list[ProofStep(sibling, side)]` and `verify_proof(leaf, proof, root) -> bool`.
  Promoted nodes contribute no step at that level.

## 7. Integrity tree (`tree.py`) — `build_integrity_tree(pdf_bytes) -> IntegrityTree`
```
page_root[p] = merkle_root([c.leaf_hash for c in chunks of page p])  or EMPTY_PAGE_ROOT
text_root    = merkle_root(page_root[0..n-1])
```
`IntegrityTree = { canon_version, file_hash, text_root, page_count, pages[{index, root, chunks[]}], sections[] }`.
Determinism test: building twice, and after JSON round-trip, yields identical dicts.

## 8. Sections overlay (`sections.py`)
Sections are for *reporting* ("Section 4 – Payment Terms changed"); they are **not** part of `text_root`.
- `body_size` = most frequent span size (rounded to 0.5pt) across the document.
- A block is a **heading** if canonical text length ≤ 120, it does not end with `.`, and any of:
  (a) max span size ≥ `body_size × 1.15`; (b) all spans bold; (c) matches
  `^(ARTICLE|SECTION|CLAUSE|SCHEDULE|ANNEXURE)\b|^(\d+(\.\d+)*[.)]?|[IVXLC]+[.)])\s+\S` (case-insensitive for words).
- A section = a heading chunk + all following chunks until the next heading (may span pages).
  Chunks before the first heading form section `S0` titled "Preamble".
- `section_hash = merkle_root(leaf hashes of its chunks)`. Fields: `id (S{n}), title, chunk_ids, hash`.

## 9. Localization (`localize.py`) — `localize(ref: IntegrityTree, cand: IntegrityTree) -> LocalizationResult`
Order of checks:
1. `file_hash` equal → `IDENTICAL`, no regions.
2. `text_root` equal → `CONTENT_EQUIVALENT`, no regions.
3. **Merkle fast path** (only when `page_count` equal): compare `page_root[p]` pairwise; collect mismatched pages
   `M`. Record `hash_comparisons` performed (for evaluation). If every mismatch stays within its page
   (the chunk counts of the neighbouring pages are unchanged) localize inside each page in `M` with step 4
   restricted to that page.
4. **Alignment** (always used when page counts differ, or when step 3 detects spill-over between pages):
   flatten chunks of both trees in reading order; run
   `difflib.SequenceMatcher(None, ref_leaves, cand_leaves, autojunk=False).get_opcodes()`.
   - `equal` → unchanged.
   - `delete` → one `DELETED` region per ref chunk.
   - `insert` → one `INSERTED` region per cand chunk.
   - `replace` (i1:i2 vs j1:j2): pair chunks greedily by highest `SequenceMatcher(None, a.text, b.text).ratio()`
     (ties → lower index); pairs with ratio ≥ 0.30 become `MODIFIED`; leftovers become `DELETED` / `INSERTED`.
   This handles insertions that shift every later chunk (a pure positional comparison would flag the rest
   of the document) — this is a key point for the report.
5. Group adjacent regions of the same type on the same page into one region only for UI display;
   the result keeps chunk-level regions.

`ChangeRegion = { id, type: MODIFIED|INSERTED|DELETED, ref_chunk_id?, cand_chunk_id?, ref_page?, cand_page?,
ref_text?, cand_text?, cand_bbox?, ref_bbox?, section_id?, section_title? }`
`LocalizationResult = { status: IDENTICAL|CONTENT_EQUIVALENT|CHANGED, regions[], changed_pages_ref[],
changed_pages_cand[], method: MERKLE_FAST_PATH|ALIGNMENT, hash_comparisons, stats{modified,inserted,deleted} }`

## 10. Choosing the reference version (service layer, not core)
When the candidate matches no revision, compare it against **every approved version** of the document
and choose the one with the most `equal` chunks (ties → latest). Report which version was used.

## 11. Authorization decision (service layer)
```
match = revision where file_hash == cand.file_hash, else where text_root == cand.text_root
if match and match.status == APPROVED and not revoked:
    if match.file_hash == cand.file_hash:
        verdict = AUTHENTIC_LATEST if match is latest approved else AUTHENTIC_SUPERSEDED
    else:
        verdict = CONTENT_EQUIVALENT   # text identical, bytes differ (see ADR-004)
elif match (PENDING | REJECTED | REVOKED):  verdict = UNAUTHORIZED_VERSION
elif document known:                        verdict = TAMPERED (+ localization + NLP)
else:                                       verdict = UNKNOWN_DOCUMENT
then: chain cross-check of the matched/reference version:
    on-chain (fileHash, textRoot) must equal Mongo; else verdict = RECORD_MISMATCH
```
Document association when `document_id` is not supplied: lookup by `file_hash`, then by `text_root`; otherwise
`UNKNOWN_DOCUMENT` (the UI then asks the user to pick the document).

## 12. Complexity (for the report)
- Build: O(C) hashing for C chunks, O(C) Merkle nodes.
- Fast path with k changed pages out of n: O(n) page-root comparisons, then O(chunks in k pages).
  (Descending a stored page-level Merkle tree gives O(k log n); implement `changed_leaves_by_descent()`
  over `merkle_levels` and report both counts.)
- Alignment fallback: SequenceMatcher on hashes, worst case O(C²), typically near-linear.

## 13. Known limitations (state honestly in the report)
- Re-generated PDFs where the producer reflows text into different blocks cause extra MODIFIED regions
  even when wording is equivalent; normalization cannot fix layout-driven block splits.
- Visual-only tampering (images, signatures, colours without text change) is invisible to the text root
  but caught by `file_hash`; that is why CONTENT_EQUIVALENT is a separate verdict with a warning and is
  never reported as AUTHENTIC (ADR-004).
- Scanned PDFs out of scope.
- Section headings (§8) are a heuristic used only for reporting. Rule (c) can misclassify ordinary numbered
  prose that has no trailing period (e.g. "5 apples were sold") as a heading, which splits a section in the
  report. `text_root`, localization and every verdict are unaffected, because sections are not hashed into it.
- Localization (§9) diffs chunk text only. A chunk whose text is unchanged but that moves across a page
  boundary changes the page roots and `text_root` (status CHANGED) yet yields no regions, so the UI has
  nothing to highlight. The verdict is unaffected.
