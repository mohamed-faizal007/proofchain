"""Tests for 02_ALGORITHMS.md §2 extraction. Reads committed fixture PDFs, never regenerates."""

import io
from pathlib import Path

import pymupdf
import pytest
from reportlab.pdfgen.canvas import Canvas

from proofchain_core import (
    EncryptedPdfError,
    InvalidPdfError,
    NoExtractableTextError,
    extract_pages,
)

PDFS = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs"


def _read(name: str) -> bytes:
    return (PDFS / name).read_bytes()


def _all_text(name: str) -> str:
    return " ".join(b.text for p in extract_pages(_read(name)) for b in p.blocks)


def test_one_page_structure() -> None:
    pages = extract_pages(_read("one_page.pdf"))
    assert [p.index for p in pages] == [0]
    assert pages[0].blocks
    for block in pages[0].blocks:
        assert block.text
        assert block.bbox.x0 < block.bbox.x1
        assert block.bbox.y0 < block.bbox.y1
        assert block.spans


def test_contract_has_three_pages_with_zero_based_indices() -> None:
    pages = extract_pages(_read("contract_3page.pdf"))
    assert [p.index for p in pages] == [0, 1, 2]
    assert all(p.blocks for p in pages)


def test_bbox_is_top_left_origin_in_points() -> None:
    pages = extract_pages(_read("one_page.pdf"))
    blocks = pages[0].blocks
    # Content starts at a 72pt margin from the top; reading order runs top to bottom.
    assert blocks[0].bbox.y0 < 120
    assert [b.bbox.y0 for b in blocks] == sorted(b.bbox.y0 for b in blocks)
    assert all(b.bbox.y1 <= 842 for b in blocks)  # A4 height


def test_heading_is_bold_and_larger_than_body() -> None:
    blocks = extract_pages(_read("one_page.pdf"))[0].blocks
    heading, body = blocks[0].spans[0], blocks[-1].spans[0]
    assert heading.flags & 16
    assert not body.flags & 16
    assert heading.size == pytest.approx(16)
    assert body.size == pytest.approx(11)


def test_multi_line_block_joined_with_single_space() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 200, 200), "alpha beta gamma delta epsilon zeta " * 3)
    blocks = extract_pages(doc.tobytes())[0].blocks
    assert len(blocks) == 1
    assert "\n" not in blocks[0].text
    assert "  " not in blocks[0].text


def test_unicode_variants_returned_raw() -> None:
    text = _all_text("unicode_variants.pdf")
    assert "ﬁ" in text  # fi ligature is not normalized at extraction
    assert "“" in text  # smart quote is not normalized either


def test_deterministic() -> None:
    data = _read("contract_3page.pdf")
    assert extract_pages(data) == extract_pages(data)


def test_image_only_rejected() -> None:
    with pytest.raises(NoExtractableTextError):
        extract_pages(_read("image_only.pdf"))


def test_too_little_text_rejected() -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "tiny")
    with pytest.raises(NoExtractableTextError):
        extract_pages(doc.tobytes())


def test_threshold_counts_canonical_characters() -> None:
    # Runs of spaces are 40 raw characters but collapse to almost nothing canonically.
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "a" + " " * 40 + "b c", fontname="helv")
    assert len(doc[0].get_text().strip()) >= 20
    with pytest.raises(NoExtractableTextError):
        extract_pages(doc.tobytes())


def test_encrypted_fixture_rejected() -> None:
    with pytest.raises(EncryptedPdfError):
        extract_pages(_read("encrypted.pdf"))


def test_owner_only_encryption_rejected() -> None:
    # Owner password set, empty user password: PyMuPDF opens this without a password,
    # but 02 §2 says reject encrypted PDFs, so it is still refused.
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "This text is readable without any password.")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="")
    assert not pymupdf.open(stream=data, filetype="pdf").needs_pass
    with pytest.raises(EncryptedPdfError):
        extract_pages(data)


def test_not_a_pdf_rejected() -> None:
    with pytest.raises(InvalidPdfError):
        extract_pages(_read("not_a_pdf.pdf"))


@pytest.mark.parametrize("data", [b"", b"%PDF-1.7\n", b"\x00" * 64])
def test_garbage_rejected(data: bytes) -> None:
    with pytest.raises(InvalidPdfError):
        extract_pages(data)


def _bold_heading_with_trailing_space_pdf() -> bytes:
    """Bold "Payment Terms" plus a non-bold trailing space, as Word-style producers emit."""
    buf = io.BytesIO()
    c = Canvas(buf)
    c.setFont("Helvetica", 11)
    c.drawString(72, 780, "Ordinary body text of the agreement goes here for length.")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, 700, "Payment Terms")
    c.setFont("Helvetica", 11)
    c.drawString(72 + c.stringWidth("Payment Terms", "Helvetica-Bold", 11), 700, " ")
    c.save()
    return buf.getvalue()


def test_blank_flag_marks_whitespace_only_spans() -> None:
    blocks = extract_pages(_bold_heading_with_trailing_space_pdf())[0].blocks
    body, heading = blocks
    assert [s.blank for s in body.spans] == [False]
    assert [(s.bold, s.blank) for s in heading.spans] == [(True, False), (False, True)]
