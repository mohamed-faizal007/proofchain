"""Tests for 02_ALGORITHMS.md §8 sections overlay."""

import io
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from proofchain_core import (
    ExtractedBlock,
    ExtractedPage,
    SpanInfo,
    build_sections,
    chunk_blocks,
    extract_pages,
    merkle_root,
)
from proofchain_core.chunking import ChunkOrigin
from proofchain_core.sections import body_size
from proofchain_core.types import BBox, Section

PDFS = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs"
BOX = BBox(72.0, 100.0, 500.0, 140.0)
BOLD = 16


def _block(text: str, size: float = 11.0, flags: int = 0) -> ExtractedBlock:
    return ExtractedBlock(text=text, bbox=BOX, spans=(SpanInfo(size=size, flags=flags),))


def _sections(*pages: list[ExtractedBlock]) -> tuple[Section, ...]:
    extracted = [ExtractedPage(index=i, blocks=tuple(p)) for i, p in enumerate(pages)]
    return build_sections(chunk_blocks(extracted))


def _titles(*pages: list[ExtractedBlock]) -> list[str]:
    return [s.title for s in _sections(*pages)]


def _body(n: int = 1) -> list[ExtractedBlock]:
    return [_block(f"Ordinary body sentence number {i} of the agreement.") for i in range(n)]


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


# --- fixture ---------------------------------------------------------------------------------


def test_contract_fixture_yields_expected_sections() -> None:
    pages = extract_pages((PDFS / "contract_3page.pdf").read_bytes())
    sections = build_sections(chunk_blocks(pages))
    assert [s.id for s in sections] == ["S1", "S2", "S3"]
    assert [s.title for s in sections] == ["1. Definitions", "2. Payment Terms", "3. Termination"]


def test_contract_fixture_section_spans_pages() -> None:
    pages = extract_pages((PDFS / "contract_3page.pdf").read_bytes())
    s2, s3 = build_sections(chunk_blocks(pages))[1:]
    assert s2.chunk_ids[0].startswith("p0-") and s2.chunk_ids[-1].startswith("p1-")
    assert s3.chunk_ids[-1].startswith("p2-")


# --- structure -------------------------------------------------------------------------------


def test_preamble_is_s0_and_headings_number_from_one() -> None:
    sections = _sections([*_body(2), _block("ARTICLE 1"), *_body(1), _block("ARTICLE 2")])
    assert [(s.id, s.title) for s in sections] == [
        ("S0", "Preamble"),
        ("S1", "ARTICLE 1"),
        ("S2", "ARTICLE 2"),
    ]
    assert [len(s.chunk_ids) for s in sections] == [2, 2, 1]


def test_no_preamble_when_document_starts_with_heading() -> None:
    assert [s.id for s in _sections([_block("SECTION 1"), *_body(1)])] == ["S1"]


def test_heading_without_body_is_a_section_of_its_own_chunk() -> None:
    sections = _sections([_block("CLAUSE 9")])
    assert [(s.title, s.chunk_ids) for s in sections] == [("CLAUSE 9", ("p0-c0",))]


def test_section_spans_pages() -> None:
    sections = _sections([_block("ARTICLE 1"), *_body(1)], [*_body(1)], [_block("ARTICLE 2")])
    assert sections[0].chunk_ids == ("p0-c0", "p0-c1", "p1-c0")
    assert sections[1].chunk_ids == ("p2-c0",)


def test_no_headings_gives_only_preamble() -> None:
    assert [s.id for s in _sections([*_body(3)])] == ["S0"]


def test_no_chunks_gives_no_sections() -> None:
    assert build_sections([]) == ()
    assert _sections([_block("   ")]) == ()


def test_split_block_body_stays_in_its_section() -> None:
    sections = _sections([_block("ARTICLE 1"), _block("A" * 1300)])
    assert len(sections) == 1
    assert len(sections[0].chunk_ids) == 4


def test_every_chunk_is_in_exactly_one_section_in_order() -> None:
    pages = extract_pages((PDFS / "contract_3page.pdf").read_bytes())
    origins = chunk_blocks(pages)
    ids = [i for s in build_sections(origins) for i in s.chunk_ids]
    assert ids == [o.chunk.id for o in origins]


def test_section_hash_is_merkle_root_of_its_leaf_hashes() -> None:
    pages = extract_pages((PDFS / "contract_3page.pdf").read_bytes())
    origins = chunk_blocks(pages)
    leaf = {o.chunk.id: o.chunk.leaf_hash for o in origins}
    for s in build_sections(origins):
        assert s.hash == merkle_root([leaf[i] for i in s.chunk_ids])


def test_build_sections_is_deterministic_and_round_trips() -> None:
    pages = extract_pages((PDFS / "contract_3page.pdf").read_bytes())
    first = build_sections(chunk_blocks(pages))
    assert first == build_sections(chunk_blocks(pages))
    assert tuple(Section.from_dict(s.to_dict()) for s in first) == first


# --- heading rules (each alone) --------------------------------------------------------------


def test_rule_a_larger_font_is_heading() -> None:
    # Body 11pt; 11 * 1.15 = 12.65.
    assert _titles([*_body(3), _block("Payment terms", size=12.7)]) == ["Preamble", "Payment terms"]
    assert _titles([*_body(3), _block("Payment terms", size=12.6)]) == ["Preamble"]


def test_rule_a_uses_max_span_size_of_block() -> None:
    mixed = ExtractedBlock(
        text="Payment terms",
        bbox=BOX,
        spans=(SpanInfo(11.0, 0), SpanInfo(14.0, 0)),
    )
    assert _titles([*_body(3), mixed]) == ["Preamble", "Payment terms"]


def test_rule_b_all_bold_is_heading() -> None:
    assert _titles([*_body(3), _block("Payment terms", flags=BOLD)]) == [
        "Preamble",
        "Payment terms",
    ]


def test_rule_b_mixed_bold_is_not_heading() -> None:
    mixed = ExtractedBlock(
        text="Payment terms",
        bbox=BOX,
        spans=(SpanInfo(11.0, BOLD), SpanInfo(11.0, 0)),
    )
    assert _titles([*_body(3), mixed]) == ["Preamble"]


@pytest.mark.parametrize(
    "text",
    [
        "ARTICLE 4",
        "Section 2 Scope",
        "clause 7",
        "SCHEDULE A",
        "Annexure B",
        "1 Definitions",
        "1. Definitions",
        "2.1 Payment",
        "2.1.3) Sub-clause",
        "IV. Miscellaneous",
        "C) Notices",
    ],
)
def test_rule_c_pattern_is_heading(text: str) -> None:
    assert _titles([*_body(2), _block(text)]) == ["Preamble", text]


@pytest.mark.parametrize(
    "text",
    [
        "Articles of association apply",  # word boundary: "Articles" is not "ARTICLE"
        "iv. miscellaneous",  # roman numerals are not case-insensitive
        "1.Definitions",  # no whitespace after the number
        "Payment terms",
    ],
)
def test_rule_c_pattern_non_matches_are_not_headings(text: str) -> None:
    assert _titles([*_body(2), _block(text)]) == ["Preamble"]


# --- heading exclusions ----------------------------------------------------------------------


def test_long_block_is_not_heading_even_if_larger_and_bold() -> None:
    text = "ARTICLE 1 " + "x" * 111  # 121 chars
    assert len(text) == 121
    assert _titles([*_body(2), _block(text, size=20.0, flags=BOLD)]) == ["Preamble"]
    assert "ARTICLE 1 " + "x" * 110 in _titles([*_body(2), _block(text[:-1], flags=BOLD)])


def test_block_ending_with_period_is_not_heading() -> None:
    assert _titles([*_body(2), _block("ARTICLE 1.", size=20.0, flags=BOLD)]) == ["Preamble"]


def test_heading_length_is_measured_on_canonical_text() -> None:
    # Whitespace runs collapse: 130 raw chars, 9 canonical.
    assert _titles([*_body(2), _block("ARTICLE" + " " * 120 + "1")]) == ["Preamble", "ARTICLE 1"]


# --- body_size -------------------------------------------------------------------------------


def _origins(*blocks: ExtractedBlock) -> list[ChunkOrigin]:
    return chunk_blocks([ExtractedPage(index=0, blocks=tuple(blocks))])


def test_body_size_is_most_frequent_span_size() -> None:
    assert body_size(_origins(_block("a1", 14.0), _block("b1", 11.0), _block("c1", 11.0))) == 11.0


def test_body_size_rounds_to_half_points_half_up() -> None:
    assert body_size(_origins(_block("a1", 10.74))) == 10.5
    assert body_size(_origins(_block("a1", 10.75))) == 11.0
    assert body_size(_origins(_block("a1", 10.76))) == 11.0
    assert body_size(_origins(_block("a1", 10.25))) == 10.5


def test_body_size_tie_takes_the_smaller_size() -> None:
    assert body_size(_origins(_block("a1", 14.0), _block("b1", 11.0))) == 11.0


def test_body_size_counts_a_split_block_once() -> None:
    # One 1300-char block (3 chunks) at 9pt against two short blocks at 11pt: 11pt wins 2 to 1.
    origins = _origins(_block("A" * 1300, 9.0), _block("b1", 11.0), _block("c1", 11.0))
    assert body_size(origins) == 11.0


def test_body_size_none_without_spans() -> None:
    no_spans = ExtractedBlock(text="text", bbox=BOX, spans=())
    assert body_size(_origins(no_spans)) is None


def test_rule_a_skipped_without_any_spans_and_rule_c_still_applies() -> None:
    blocks = [
        ExtractedBlock(text="ARTICLE 1", bbox=BOX, spans=()),
        ExtractedBlock(text="plain text", bbox=BOX, spans=()),
    ]
    assert _titles(blocks) == ["ARTICLE 1"]


# --- known limitation (02 §13) ---------------------------------------------------------------


def test_numbered_prose_is_misclassified_as_heading_known_limitation() -> None:
    """KNOWN LIMITATION, pinned on purpose (02 §8 rule (c), listed in 02 §13).

    The pattern `\\d+...\\s+\\S` matches any block that starts with a number and a space, so
    ordinary prose such as "5 apples were sold" is reported as a section heading even at body
    size and without bold. The spec's only guard is the no-trailing-period exclusion, which this
    text deliberately avoids. Sections feed reporting only; text_root and verdicts are unaffected.

    If this test starts failing, the heading rule changed: that needs an ADR and a CANON_VERSION
    review, not a quiet edit of this assertion.
    """
    sections = _sections([*_body(2), _block("5 apples were sold"), *_body(1)])
    assert [s.title for s in sections] == ["Preamble", "5 apples were sold"]
    assert [len(s.chunk_ids) for s in sections] == [2, 2]


def test_numbered_prose_with_trailing_period_is_not_a_heading() -> None:
    """The edge of the limitation above: the same text ending in a period is excluded."""
    assert _titles([*_body(2), _block("5 apples were sold.")]) == ["Preamble"]


# --- blank spans (whitespace-only, e.g. a non-bold trailing space) ---------------------------


def _blank(size: float = 11.0, flags: int = 0) -> SpanInfo:
    return SpanInfo(size=size, flags=flags, blank=True)


def test_blank_span_does_not_defeat_all_bold_rule() -> None:
    heading = ExtractedBlock(
        text="Payment Terms ", bbox=BOX, spans=(SpanInfo(11.0, BOLD), _blank(11.0, 0))
    )
    assert _titles([*_body(3), heading]) == ["Preamble", "Payment Terms"]


def test_blank_span_does_not_defeat_all_bold_rule_on_extracted_pdf() -> None:
    pdf = _bold_heading_with_trailing_space_pdf()
    sections = build_sections(chunk_blocks(extract_pages(pdf)))
    assert [s.title for s in sections] == ["Preamble", "Payment Terms"]


def test_blank_span_does_not_trigger_size_rule() -> None:
    block = ExtractedBlock(
        text="Payment terms ", bbox=BOX, spans=(SpanInfo(11.0, 0), _blank(20.0, 0))
    )
    assert _titles([*_body(3), block]) == ["Preamble"]


def test_block_with_only_blank_spans_yields_no_section() -> None:
    block = ExtractedBlock(text="   ", bbox=BOX, spans=(_blank(),))
    assert _sections([block]) == ()
    assert _titles([*_body(1), block]) == ["Preamble"]


def test_body_size_ignores_blank_spans() -> None:
    padded = ExtractedBlock(
        text="Real text", bbox=BOX, spans=(SpanInfo(11.0, 0), _blank(9.0), _blank(9.0), _blank(9.0))
    )
    assert body_size(_origins(padded)) == 11.0


def test_body_size_none_when_every_span_is_blank() -> None:
    assert body_size(_origins(ExtractedBlock(text="text", bbox=BOX, spans=(_blank(),)))) is None
