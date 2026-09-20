"""Tests for 02_ALGORITHMS.md §7 integrity tree."""

import json
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from proofchain_core import (
    CANON_VERSION,
    EMPTY_PAGE_ROOT,
    EncryptedPdfError,
    InvalidPdfError,
    NoExtractableTextError,
    build_integrity_tree,
    file_hash,
    merkle_root,
    node_hash,
    page_merkle_root,
    page_node_hash,
)
from proofchain_core.tree import main
from proofchain_core.types import IntegrityTree

PDFS = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs"
TEXT = "Content that is long enough to pass the extraction threshold."


def _pdf(pages: list[str | None]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    return bytes(doc.tobytes())


def _pdf_blocks(pages: list[list[str]]) -> bytes:
    """One PDF page per entry; each string is a separate, well-spaced text block."""
    doc = pymupdf.open()
    for blocks in pages:
        page = doc.new_page()
        for i, text in enumerate(blocks):
            page.insert_text((72, 72 + 120 * i), text)
    return bytes(doc.tobytes())


def _read(name: str) -> bytes:
    return (PDFS / name).read_bytes()


def _expected_roots(tree: IntegrityTree) -> tuple[list[str], str]:
    """Recompute §7 from the chunks, independently of the builder."""
    roots = [
        merkle_root([c.leaf_hash for c in p.chunks]) if p.chunks else EMPTY_PAGE_ROOT
        for p in tree.pages
    ]
    return roots, page_merkle_root(roots)


def test_deterministic_twice() -> None:
    data = _read("contract_3page.pdf")
    assert build_integrity_tree(data).to_dict() == build_integrity_tree(data).to_dict()


def test_json_roundtrip() -> None:
    tree = build_integrity_tree(_read("contract_3page.pdf"))
    loaded = IntegrityTree.from_dict(json.loads(json.dumps(tree.to_dict())))
    assert loaded == tree
    assert loaded.to_dict() == tree.to_dict()


def test_roots_match_spec() -> None:
    tree = build_integrity_tree(_read("contract_3page.pdf"))
    roots, text_root = _expected_roots(tree)
    assert [p.root for p in tree.pages] == roots
    assert tree.text_root == text_root
    assert tree.page_count == len(tree.pages) == 3
    assert [p.index for p in tree.pages] == [0, 1, 2]
    assert all(c.page == p.index for p in tree.pages for c in p.chunks)


def test_file_hash_and_canon_version() -> None:
    data = _read("one_page.pdf")
    tree = build_integrity_tree(data)
    assert tree.file_hash == file_hash(data)
    assert tree.canon_version == CANON_VERSION == 2


def test_single_page_root_is_text_root() -> None:
    tree = build_integrity_tree(_read("one_page.pdf"))
    assert tree.page_count == 1
    assert tree.text_root == tree.pages[0].root


def test_sections_cover_all_chunks_in_order() -> None:
    tree = build_integrity_tree(_read("contract_3page.pdf"))
    assert tree.sections
    listed = [cid for s in tree.sections for cid in s.chunk_ids]
    assert listed == [c.id for p in tree.pages for c in p.chunks]


@pytest.mark.parametrize(
    "layout",
    [
        [TEXT, None, TEXT + " B"],
        [None, TEXT, TEXT + " B"],
        [TEXT, TEXT + " B", None],
    ],
    ids=["blank-middle", "blank-first", "blank-last"],
)
def test_empty_page_uses_empty_root(layout: list[str | None]) -> None:
    tree = build_integrity_tree(_pdf(layout))
    blank = layout.index(None)
    assert tree.page_count == 3
    assert [p.index for p in tree.pages] == [0, 1, 2]
    assert tree.pages[blank].chunks == ()
    assert tree.pages[blank].root == EMPTY_PAGE_ROOT
    # Independent §7 computation: the blank page still occupies its slot.
    roots = [
        EMPTY_PAGE_ROOT if t is None else merkle_root([c.leaf_hash for c in p.chunks])
        for t, p in zip(layout, tree.pages, strict=True)
    ]
    assert tree.text_root == page_merkle_root(roots)


def test_blank_page_position_changes_text_root() -> None:
    a = build_integrity_tree(_pdf([TEXT, None, TEXT]))
    b = build_integrity_tree(_pdf([TEXT, TEXT, None]))
    assert a.text_root != b.text_root


def test_content_equivalent_same_text_root() -> None:
    data = _read("contract_3page.pdf")
    doc = pymupdf.open(stream=data, filetype="pdf")
    doc.set_metadata({"title": "changed"})
    changed = bytes(doc.tobytes())
    a, b = build_integrity_tree(data), build_integrity_tree(changed)
    assert a.file_hash != b.file_hash
    assert a.text_root == b.text_root


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("encrypted.pdf", EncryptedPdfError),
        ("image_only.pdf", NoExtractableTextError),
        ("not_a_pdf.pdf", InvalidPdfError),
    ],
)
def test_error_fixtures_propagate(name: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        build_integrity_tree(_read(name))


def test_cli_prints_roots(capsys: pytest.CaptureFixture[str]) -> None:
    path = PDFS / "contract_3page.pdf"
    assert main([str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    tree = build_integrity_tree(path.read_bytes())
    assert out["file_hash"] == tree.file_hash
    assert out["text_root"] == tree.text_root
    assert out["page_count"] == 3
    assert out["page_roots"] == [p.root for p in tree.pages]
    assert out["canon_version"] == CANON_VERSION


def test_package_entry_point_runs_clean() -> None:
    path = PDFS / "contract_3page.pdf"
    result = subprocess.run(
        [sys.executable, "-m", "proofchain_core", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert (
        json.loads(result.stdout)["text_root"] == build_integrity_tree(path.read_bytes()).text_root
    )


def test_cli_reports_bad_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(PDFS / "not_a_pdf.pdf")]) == 1
    assert capsys.readouterr().err


BLOCKS = [f"Paragraph number {i} is long enough to be one chunk on its own." for i in range(4)]


def test_pagination_changes_text_root_for_identical_chunk_sequence() -> None:
    # ADR-017 regression: pages [a,b],[c,d] vs one page [a,b,c,d].
    two_pages = build_integrity_tree(_pdf_blocks([BLOCKS[:2], BLOCKS[2:]]))
    one_page = build_integrity_tree(_pdf_blocks([BLOCKS]))
    chunks = lambda t: [c.text for p in t.pages for c in p.chunks]  # noqa: E731
    assert chunks(two_pages) == chunks(one_page) == BLOCKS
    assert two_pages.page_count == 2 and one_page.page_count == 1
    assert two_pages.text_root != one_page.text_root


def test_pagination_changes_text_root_odd_split() -> None:
    # pages [a,b],[c] vs [a,b,c]
    split = build_integrity_tree(_pdf_blocks([BLOCKS[:2], BLOCKS[2:3]]))
    flat = build_integrity_tree(_pdf_blocks([BLOCKS[:3]]))
    assert split.text_root != flat.text_root


def test_text_root_uses_page_domain_for_multi_page() -> None:
    tree = build_integrity_tree(_pdf_blocks([BLOCKS[:2], BLOCKS[2:]]))
    a, b = (p.root for p in tree.pages)
    assert tree.text_root == page_node_hash(a, b)
    assert tree.text_root != node_hash(a, b)
