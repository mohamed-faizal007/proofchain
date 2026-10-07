"""P10-04: the demo documents are deterministic and shaped as the demo script promises."""

from typing import Any

import pytest

from tests.unit.deploy.script_loader import load_script

pytest.importorskip("faker")  # eval extra; the demo generator reuses eval/


@pytest.fixture(scope="module")
def demo() -> Any:
    return load_script("demo_data")


@pytest.fixture(scope="module")
def built(demo: Any) -> Any:
    return demo.build_demo_set()


def test_demo_corpus_deterministic(demo: Any, built: Any) -> None:
    again = demo.build_demo_set()
    assert again.v1 == built.v1 and again.v2 == built.v2
    assert [c.pdf for c in again.copies] == [c.pdf for c in built.copies]


def test_v2_differs_from_v1_and_every_copy_is_a_distinct_file(built: Any) -> None:
    pdfs = [c.pdf for c in built.copies]  # includes v1 and v2 themselves
    assert built.v1 != built.v2
    assert len(set(pdfs)) == len(pdfs)


def test_copies_cover_original_v2_tampers_and_a_resave(built: Any) -> None:
    by_key = {c.key: c for c in built.copies}
    assert by_key["original_v1"].pdf == built.v1
    assert by_key["approved_v2"].pdf == built.v2
    assert by_key["original_v1"].expected_verdict == "AUTHENTIC_SUPERSEDED"
    assert by_key["approved_v2"].expected_verdict == "AUTHENTIC_LATEST"
    tampered = [c for c in built.copies if c.key.startswith("tampered_")]
    assert len(tampered) >= 4
    assert all(c.expected_verdict == "TAMPERED" and c.expected_category for c in tampered)
    assert {c.expected_category for c in tampered} >= {
        "AMOUNT_CHANGE",
        "PARTY_CHANGE",
        "OBLIGATION_CHANGE",
    }
    assert by_key["resaved_v2"].expected_verdict == "CONTENT_EQUIVALENT"


def test_non_tampered_copies_expect_no_category(built: Any) -> None:
    for c in built.copies:
        if not c.key.startswith("tampered_"):
            assert c.expected_category is None


def test_demo_document_is_small_enough_to_read_in_a_demo(built: Any) -> None:
    import pymupdf

    with pymupdf.open(stream=built.v1, filetype="pdf") as doc:
        assert 1 <= doc.page_count <= 4


def test_write_pdfs_writes_every_file(demo: Any, built: Any, tmp_path: Any) -> None:
    written = demo.write_pdfs(built, tmp_path)
    names = {p.name for p in written}
    assert {f"{c.key}.pdf" for c in built.copies} <= names
    for p in written:
        assert p.read_bytes().startswith(b"%PDF")
