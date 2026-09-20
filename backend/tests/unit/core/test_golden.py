"""Golden vectors: literal expected hashes, never recomputed with the code under test.

These pin the byte-level definition of every hash in 02_ALGORITHMS.md §5-§7 (prefix bytes,
pairing order, odd-node promotion, page-level prefix) and the extraction + canonicalization +
chunking pipeline for a committed fixture. If one fails, an anchored `text_root` would change:
that is a spec change, so add an ADR and bump CANON_VERSION (docs/09_DECISIONS.md) and only
then regenerate the literals. The values were cross-checked against an independent
hashlib-only implementation (P1 phase review follow-up).
"""

from pathlib import Path

from proofchain_core import (
    CANON_VERSION,
    EMPTY_PAGE_ROOT,
    build_integrity_tree,
    file_hash,
    leaf_hash,
    merkle_root,
    node_hash,
    page_merkle_root,
    page_node_hash,
    sha256_hex,
)

CONTRACT = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs" / "contract_3page.pdf"

LEAF_EMPTY = "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
LEAF_A = "022a6979e6dab7aa5ae4c3e5e45f7e977112a7e63593820dbec1ec738a24f93c"
LEAF_B = "57eb35615d47f34ec714cacdf5fd74608a5e8e102724e80b24b287c0c27b6a31"
NODE_AB = "b137985ff484fb600db93107c77b0365c80d78f5b429ded0fd97361d077999eb"
PAGE_NODE_AB = "ea6b667f6870eea04dcee10fe7ef6dd4254d3f51a574c54d4971086947421aa9"
EMPTY_ROOT = "7e431fee8c00b7bc023605bbab928d03b353bb23b3302b0cf548e326dc56e194"
MERKLE_ABC = "36642e73c2540ab121e3a6bf9545b0a24982cd830eb13d3cd19de3ce6c021ec1"

CONTRACT_FILE_HASH = "6da7adb97d1ff583918b343aae3c196d4e36e4554078ee941d01eb2706f0a3a2"
CONTRACT_FIRST_LEAF = "2db33807bcd95840a6da273b6a7ae5e60e9da114b39a7461026235f95338b1f0"
CONTRACT_PAGE_ROOTS = [
    "918bbff8f4db3ad7b202a038f1f933111460abbf080e273c611be45f709e3185",
    "1fa6834fe7cf27b241aac5978a8e1eafe6461ed3e72482ce1de34733085c5eba",
    "e16a582f97a194724e22f8ccd9f70fb71cab19525e388bcfc24cf94a8c4aed5f",
]
CONTRACT_TEXT_ROOT = "ed46066f96a601e0552c541833042434d95f677b3d956d7ea329254e9428d80d"
CONTRACT_SECTION_HASHES = [
    "1d54b08e9aff56ccd02f8f13c941e6cea5aa9cf74cf6d3be4501097755aaf551",
    "e8459fa7de034cca8244d72be41f95c3b8f0c3c1ea0b3908b81a65a250bbd4fb",
    "3903f864d9a40676c66343ad58a20ee5215ba85f15189cd614385c016d5ba07d",
]


def test_canon_version_is_pinned() -> None:
    assert CANON_VERSION == 2


def test_primitive_golden_vectors() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert leaf_hash("") == LEAF_EMPTY
    assert leaf_hash("a") == LEAF_A
    assert leaf_hash("b") == LEAF_B
    assert node_hash(LEAF_A, LEAF_B) == NODE_AB
    assert page_node_hash(LEAF_A, LEAF_B) == PAGE_NODE_AB
    assert NODE_AB != PAGE_NODE_AB
    assert EMPTY_PAGE_ROOT == EMPTY_ROOT


def test_merkle_golden_vectors() -> None:
    leaves = [leaf_hash(x) for x in "abc"]
    assert merkle_root(leaves[:2]) == NODE_AB
    assert merkle_root(leaves) == MERKLE_ABC  # odd node promoted, not duplicated
    assert page_merkle_root([LEAF_A]) == LEAF_A
    assert page_merkle_root([LEAF_A, LEAF_B]) == PAGE_NODE_AB


def test_contract_fixture_golden_roots() -> None:
    data = CONTRACT.read_bytes()
    assert file_hash(data) == CONTRACT_FILE_HASH
    tree = build_integrity_tree(data)
    assert tree.canon_version == 2
    assert tree.file_hash == CONTRACT_FILE_HASH
    assert [len(p.chunks) for p in tree.pages] == [5, 4, 3]
    assert tree.pages[0].chunks[0].text == "1. Definitions"
    assert tree.pages[0].chunks[0].leaf_hash == CONTRACT_FIRST_LEAF
    assert [p.root for p in tree.pages] == CONTRACT_PAGE_ROOTS
    assert tree.text_root == CONTRACT_TEXT_ROOT
    assert [s.hash for s in tree.sections] == CONTRACT_SECTION_HASHES
