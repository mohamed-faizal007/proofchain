"""Known-answer and domain-separation tests for 02_ALGORITHMS.md §5 hashing."""

import hashlib
import re

import pytest

from proofchain_core.hashing import EMPTY_PAGE_ROOT, file_hash, leaf_hash, node_hash, sha256_hex

HEX64 = re.compile(r"[0-9a-f]{64}")


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_sha256_hex_known_answer() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_hex(b"abc") == _h(b"abc")


@pytest.mark.parametrize("text", ["", "abc", "héllo wörld", "日本語", "a\nb"])
def test_leaf_hash_is_prefixed_utf8(text: str) -> None:
    assert leaf_hash(text) == _h(b"\x00" + text.encode("utf-8"))


def test_node_hash_is_prefixed_concat_of_bytes() -> None:
    left, right = leaf_hash("a"), leaf_hash("b")
    assert node_hash(left, right) == _h(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))


def test_node_hash_is_order_sensitive() -> None:
    left, right = leaf_hash("a"), leaf_hash("b")
    assert node_hash(left, right) != node_hash(right, left)


def test_empty_page_root_constant() -> None:
    assert _h(b"\x02" + b"PROOFCHAIN_EMPTY_PAGE") == EMPTY_PAGE_ROOT


def test_file_hash_has_no_prefix() -> None:
    assert file_hash(b"%PDF-1.4 x") == _h(b"%PDF-1.4 x")


def test_outputs_are_lowercase_hex64() -> None:
    a, b = leaf_hash("a"), leaf_hash("b")
    for value in (a, node_hash(a, b), EMPTY_PAGE_ROOT, file_hash(b"x"), sha256_hex(b"")):
        assert HEX64.fullmatch(value)


def test_domain_separation_leaf_vs_plain_hash() -> None:
    assert leaf_hash("abc") != sha256_hex(b"abc")


def test_domain_separation_leaf_cannot_forge_node() -> None:
    # Second-preimage attack: a "leaf" whose text is the two child digests
    # concatenated must not collide with the internal node over those children.
    left, right = leaf_hash("a"), leaf_hash("b")
    forged = bytes.fromhex(left) + bytes.fromhex(right)
    assert sha256_hex(b"\x00" + forged) != node_hash(left, right)
    assert sha256_hex(forged) != node_hash(left, right)


def test_empty_page_root_differs_from_empty_leaf() -> None:
    assert leaf_hash("") != EMPTY_PAGE_ROOT


@pytest.mark.parametrize("bad", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_node_hash_rejects_non_hex64(bad: str) -> None:
    good = leaf_hash("a")
    with pytest.raises(ValueError):
        node_hash(bad, good)
    with pytest.raises(ValueError):
        node_hash(good, bad)
