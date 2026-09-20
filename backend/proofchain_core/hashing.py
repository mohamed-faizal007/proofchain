"""Domain-separated SHA-256 hashing. Normative spec: docs/02_ALGORITHMS.md §5."""

import hashlib
import re

_HEX64 = re.compile(r"[0-9a-f]{64}")

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"
_EMPTY_PREFIX = b"\x02"
_PAGE_NODE_PREFIX = b"\x03"


def sha256_hex(data: bytes) -> str:
    """H(x) = SHA-256(x), lowercase hex (§5)."""
    return hashlib.sha256(data).hexdigest()


def leaf_hash(text: str) -> str:
    """leaf(chunk) = H(0x00 || utf8(chunk.text)) (§5)."""
    return sha256_hex(_LEAF_PREFIX + text.encode("utf-8"))


def _digest_bytes(h: str) -> bytes:
    if not _HEX64.fullmatch(h):
        raise ValueError("hash must be 64 lowercase hex characters")
    return bytes.fromhex(h)


def node_hash(left: str, right: str) -> str:
    """node(l, r) = H(0x01 || bytes(l) || bytes(r)) (§5)."""
    return sha256_hex(_NODE_PREFIX + _digest_bytes(left) + _digest_bytes(right))


def page_node_hash(left: str, right: str) -> str:
    """page_node(l, r) = H(0x03 || bytes(l) || bytes(r)) (§5, ADR-017).

    Combines page roots into text_root; distinct from `node_hash` so a page-level
    computation can never equal a chunk-level one at the same tree position.
    """
    return sha256_hex(_PAGE_NODE_PREFIX + _digest_bytes(left) + _digest_bytes(right))


def file_hash(pdf_bytes: bytes) -> str:
    """file_hash = H(raw pdf bytes), no domain prefix (§5)."""
    return sha256_hex(pdf_bytes)


# EMPTY_PAGE_ROOT = H(0x02 || b"PROOFCHAIN_EMPTY_PAGE") (§5)
EMPTY_PAGE_ROOT = sha256_hex(_EMPTY_PREFIX + b"PROOFCHAIN_EMPTY_PAGE")
