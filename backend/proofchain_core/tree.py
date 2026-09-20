"""Integrity tree (02_ALGORITHMS.md §7)."""

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from proofchain_core.canonical import CANON_VERSION
from proofchain_core.chunking import chunk_blocks
from proofchain_core.errors import ProofChainCoreError
from proofchain_core.extract import extract_pages
from proofchain_core.hashing import EMPTY_PAGE_ROOT, file_hash
from proofchain_core.merkle import merkle_root, page_merkle_root
from proofchain_core.sections import build_sections
from proofchain_core.types import Chunk, IntegrityTree, Page


def build_integrity_tree(pdf_bytes: bytes) -> IntegrityTree:
    """Build the text Merkle tree of a PDF (§7).

    page_root[p] = merkle_root(leaf hashes of page p) or EMPTY_PAGE_ROOT;
    text_root    = page_merkle_root(page roots), page prefix 0x03 (ADR-017).
    Sections are reporting-only (§8).
    Raises InvalidPdfError, EncryptedPdfError, NoExtractableTextError.
    """
    extracted = extract_pages(pdf_bytes)
    origins = chunk_blocks(extracted)

    by_page: dict[int, list[Chunk]] = {p.index: [] for p in extracted}
    for origin in origins:
        by_page[origin.chunk.page].append(origin.chunk)

    pages = tuple(
        Page(
            index=p.index,
            root=(
                merkle_root([c.leaf_hash for c in by_page[p.index]])
                if by_page[p.index]
                else EMPTY_PAGE_ROOT
            ),
            chunks=tuple(by_page[p.index]),
        )
        for p in extracted
    )
    return IntegrityTree(
        canon_version=CANON_VERSION,
        file_hash=file_hash(pdf_bytes),
        text_root=page_merkle_root([p.root for p in pages]),
        page_count=len(pages),
        pages=pages,
        sections=build_sections(origins),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: `python -m proofchain_core.tree file.pdf` prints the roots as JSON."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m proofchain_core.tree file.pdf", file=sys.stderr)
        return 2
    try:
        tree = build_integrity_tree(Path(args[0]).read_bytes())
    except (OSError, ProofChainCoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = {
        "canon_version": tree.canon_version,
        "file_hash": tree.file_hash,
        "text_root": tree.text_root,
        "page_count": tree.page_count,
        "page_roots": [p.root for p in tree.pages],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
