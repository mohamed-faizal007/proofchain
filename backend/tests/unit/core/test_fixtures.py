"""P1-01: fixture PDFs are deterministic and have the properties 08 §A requires.

Byte-identity is verified on the machine running the tests only. Cross-OS identity
of regenerated files is unverified (see PROGRESS.md); tests that need exact hashes
must read the committed PDFs, never regenerate.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pymupdf
import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
PDFS = FIXTURES / "pdfs"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_fixtures", FIXTURES / "make_fixtures.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _load_generator()


def _read_all(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir()) if p.is_file()}


def test_fixtures_deterministic(gen: ModuleType, tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    gen.generate(a)
    gen.generate(b)
    assert _read_all(a) == _read_all(b)


def test_fixtures_committed_match(gen: ModuleType, tmp_path: Path) -> None:
    # Guards accidental drift on the machine that generated the files. A failure on a
    # different OS/reportlab build means regeneration is not byte-stable there; the
    # committed bytes remain the source of truth.
    gen.generate(tmp_path)
    assert _read_all(tmp_path) == _read_all(PDFS)


def test_fixture_set_is_complete() -> None:
    assert set(_read_all(PDFS)) == {
        "one_page.pdf",
        "contract_3page.pdf",
        "unicode_variants.pdf",
        "image_only.pdf",
        "encrypted.pdf",
        "not_a_pdf.pdf",
    }


def _text(path: Path) -> list[str]:
    with pymupdf.open(path) as doc:
        return [page.get_text() for page in doc]


def test_one_page() -> None:
    pages = _text(PDFS / "one_page.pdf")
    assert len(pages) == 1
    assert len(pages[0].strip()) > 20


def test_contract_has_three_pages_and_numbered_headings() -> None:
    pages = _text(PDFS / "contract_3page.pdf")
    assert len(pages) == 3
    joined = "\n".join(pages)
    for heading in ("1. Definitions", "2. Payment Terms", "3. Termination"):
        assert heading in joined


def test_unicode_variants_contain_the_awkward_characters() -> None:
    text = "".join(_text(PDFS / "unicode_variants.pdf"))
    # NBSP is written into the PDF but MuPDF extraction normalises it to a plain space,
    # so it is not asserted here; canonicalization (P1-02) still maps it.
    assert any(ch in text for ch in "‘’“”")  # smart quotes
    assert any(ch in text for ch in "ﬁﬂ")  # ligatures


def test_image_only_has_no_text_but_has_an_image() -> None:
    with pymupdf.open(PDFS / "image_only.pdf") as doc:
        assert len(doc) == 1
        assert doc[0].get_text().strip() == ""
        assert doc[0].get_image_info()  # inline image: not listed by get_images()


def test_encrypted_needs_password() -> None:
    with pymupdf.open(PDFS / "encrypted.pdf") as doc:
        assert doc.needs_pass


def test_not_a_pdf() -> None:
    assert not (PDFS / "not_a_pdf.pdf").read_bytes().startswith(b"%PDF")
