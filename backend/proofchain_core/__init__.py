"""Pure, deterministic integrity library. See docs/02_ALGORITHMS.md."""

from proofchain_core.canonical import CANON_VERSION, normalize_text
from proofchain_core.chunking import MAX_CHUNK_CHARS, ChunkOrigin, chunk_blocks, chunk_pages
from proofchain_core.errors import (
    EncryptedPdfError,
    InvalidPdfError,
    NoExtractableTextError,
    ProofChainCoreError,
)
from proofchain_core.extract import ExtractedBlock, ExtractedPage, SpanInfo, extract_pages
from proofchain_core.hashing import EMPTY_PAGE_ROOT, file_hash, leaf_hash, node_hash, sha256_hex
from proofchain_core.localize import localize
from proofchain_core.merkle import (
    ProofStep,
    changed_leaves_by_descent,
    merkle_levels,
    merkle_proof,
    merkle_root,
    verify_proof,
)
from proofchain_core.sections import build_sections
from proofchain_core.tree import build_integrity_tree

__all__ = [
    "CANON_VERSION",
    "ChunkOrigin",
    "EMPTY_PAGE_ROOT",
    "EncryptedPdfError",
    "ExtractedBlock",
    "ExtractedPage",
    "InvalidPdfError",
    "MAX_CHUNK_CHARS",
    "NoExtractableTextError",
    "ProofChainCoreError",
    "ProofStep",
    "SpanInfo",
    "build_integrity_tree",
    "build_sections",
    "changed_leaves_by_descent",
    "chunk_blocks",
    "chunk_pages",
    "extract_pages",
    "file_hash",
    "leaf_hash",
    "localize",
    "merkle_levels",
    "merkle_proof",
    "merkle_root",
    "node_hash",
    "normalize_text",
    "sha256_hex",
    "verify_proof",
]
