"""Tests for 02_ALGORITHMS.md §9 localization."""

from difflib import SequenceMatcher
from pathlib import Path

import pymupdf
from hypothesis import given
from hypothesis import strategies as st

from proofchain_core import (
    CANON_VERSION,
    EMPTY_PAGE_ROOT,
    build_integrity_tree,
    leaf_hash,
    localize,
    merkle_root,
    page_merkle_root,
    sha256_hex,
)
from proofchain_core.types import (
    BBox,
    Chunk,
    IntegrityTree,
    LocalizationMethod,
    LocalizationResult,
    LocalizationStatus,
    Page,
    RegionType,
    Section,
)

PDFS = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs"
TEXT = "Content that is long enough to pass the extraction threshold."


def _tree(pages: list[list[str]], sections: tuple[Section, ...] = ()) -> IntegrityTree:
    """Synthetic tree from chunk texts per page; file_hash derives from the text."""
    built = []
    for p, texts in enumerate(pages):
        chunks = tuple(
            Chunk(f"p{p}-c{i}", p, i, t, BBox(0, 10.0 * i, 100, 10.0 * i + 9), leaf_hash(t))
            for i, t in enumerate(texts)
        )
        root = merkle_root([c.leaf_hash for c in chunks]) if chunks else EMPTY_PAGE_ROOT
        built.append(Page(p, root, chunks))
    return IntegrityTree(
        canon_version=CANON_VERSION,
        file_hash=sha256_hex("|".join("/".join(t) for t in pages).encode()),
        text_root=page_merkle_root([p.root for p in built]),
        page_count=len(built),
        pages=tuple(built),
        sections=sections,
    )


def _para(uid: int) -> str:
    return f"paragraph {uid} lorem ipsum dolor sit amet consectetur"


def _kinds(result: LocalizationResult) -> list[tuple[RegionType, str | None, str | None]]:
    return [(r.type, r.ref_chunk_id, r.cand_chunk_id) for r in result.regions]


def _pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    return bytes(doc.tobytes())


def test_identical() -> None:
    tree = _tree([[_para(1)]])
    result = localize(tree, tree)
    assert result.status is LocalizationStatus.IDENTICAL
    assert result.regions == () and result.method is None and result.hash_comparisons == 0
    assert result.stats == {"modified": 0, "inserted": 0, "deleted": 0}


def test_content_equivalent_metadata_change() -> None:
    data = (PDFS / "contract_3page.pdf").read_bytes()
    doc = pymupdf.open(stream=data, filetype="pdf")
    doc.set_metadata({"title": "Changed metadata"})
    changed = bytes(doc.tobytes())
    ref, cand = build_integrity_tree(data), build_integrity_tree(changed)
    assert ref.file_hash != cand.file_hash
    result = localize(ref, cand)
    assert result.status is LocalizationStatus.CONTENT_EQUIVALENT
    assert result.regions == () and result.method is None


def test_single_modify_fast_path() -> None:
    ref = _tree([[_para(1), _para(2)], [_para(3), _para(4)]])
    cand = _tree([[_para(1), _para(2)], [_para(3), _para(4) + " amended"]])
    result = localize(ref, cand)
    assert result.status is LocalizationStatus.CHANGED
    assert result.method is LocalizationMethod.MERKLE_FAST_PATH
    assert _kinds(result) == [(RegionType.MODIFIED, "p1-c1", "p1-c1")]
    region = result.regions[0]
    assert region.ref_text == _para(4) and region.cand_text == _para(4) + " amended"
    assert region.ref_page == region.cand_page == 1
    assert region.ref_bbox == region.cand_bbox == BBox(0, 10.0, 100, 19.0)
    assert result.changed_pages_ref == result.changed_pages_cand == (1,)
    assert result.stats == {"modified": 1, "inserted": 0, "deleted": 0}
    # 2 page-root comparisons + the 4 leaves of the one mismatched page
    assert result.hash_comparisons == 2 + 4


def test_insert_in_middle_does_not_cascade() -> None:
    ref = _tree([[_para(1), _para(2), _para(3)]])
    cand = _tree([[_para(1), _para(9), _para(2), _para(3)]])
    result = localize(ref, cand)
    assert result.method is LocalizationMethod.MERKLE_FAST_PATH
    assert _kinds(result) == [(RegionType.INSERTED, None, "p0-c1")]
    assert result.regions[0].cand_text == _para(9)


def test_insert_at_start_no_cascade_across_pages() -> None:
    ref = _tree([[_para(1), _para(2)], [_para(3), _para(4)]])
    cand = _tree([[_para(9), _para(1), _para(2)], [_para(3), _para(4)]])
    result = localize(ref, cand)
    assert _kinds(result) == [(RegionType.INSERTED, None, "p0-c0")]
    assert result.changed_pages_ref == () and result.changed_pages_cand == (0,)
    assert result.stats == {"modified": 0, "inserted": 1, "deleted": 0}


def test_insert_spills_content_to_next_page() -> None:
    ref = _tree([[_para(1), _para(2), _para(3)], [_para(4)]])
    cand = _tree([[_para(1), _para(9), _para(2)], [_para(3), _para(4)]])
    result = localize(ref, cand)
    assert result.method is LocalizationMethod.ALIGNMENT
    assert _kinds(result) == [(RegionType.INSERTED, None, "p0-c1")]


def test_moved_chunk_without_text_change_has_no_regions() -> None:
    """Known limitation: §9 diffs chunk text only, so a pure page move has no regions."""
    ref = _tree([[_para(1), _para(2), _para(3)], [_para(4)]])
    cand = _tree([[_para(1), _para(2)], [_para(3), _para(4)]])
    result = localize(ref, cand)
    assert result.status is LocalizationStatus.CHANGED
    assert result.method is LocalizationMethod.ALIGNMENT
    assert result.regions == ()


def test_delete() -> None:
    ref = _tree([[_para(1), _para(2), _para(3)]])
    cand = _tree([[_para(1), _para(3)]])
    result = localize(ref, cand)
    assert _kinds(result) == [(RegionType.DELETED, "p0-c1", None)]
    assert result.regions[0].ref_text == _para(2)
    assert result.changed_pages_ref == (0,) and result.changed_pages_cand == ()


def test_multi_page_edits_stay_on_fast_path() -> None:
    ref = _tree([[_para(1), _para(2)], [_para(3)], [_para(4), _para(5)]])
    cand = _tree([[_para(1), _para(2) + " x"], [_para(3)], [_para(4) + " y", _para(5)]])
    result = localize(ref, cand)
    assert result.method is LocalizationMethod.MERKLE_FAST_PATH
    assert result.changed_pages_ref == result.changed_pages_cand == (0, 2)
    assert [r.type for r in result.regions] == [RegionType.MODIFIED] * 2
    assert [r.id for r in result.regions] == ["r1", "r2"]


def test_page_count_change_uses_alignment() -> None:
    ref = _tree([[_para(1), _para(2)], [_para(3)]])
    cand = _tree([[_para(1), _para(2)], [_para(3)], [_para(4)]])
    result = localize(ref, cand)
    assert result.method is LocalizationMethod.ALIGNMENT
    assert _kinds(result) == [(RegionType.INSERTED, None, "p2-c0")]
    assert result.hash_comparisons == 3 + 4  # no page-root comparisons when counts differ


def test_replace_pairs_similar_and_leaves_rest() -> None:
    ref = _tree([["the tenant shall pay rent monthly", "zzzz qqqq xxxx"]])
    cand = _tree([["the tenant shall pay rent quarterly", "completely different words here"]])
    result = localize(ref, cand)
    assert [r.type for r in result.regions] == [
        RegionType.MODIFIED,
        RegionType.DELETED,
        RegionType.INSERTED,
    ]
    assert result.regions[0].ref_chunk_id == "p0-c0" and result.regions[0].cand_chunk_id == "p0-c0"
    assert result.stats == {"modified": 1, "inserted": 1, "deleted": 1}


def test_replace_pairing_is_greedy_by_best_ratio() -> None:
    a1, a2 = "alpha beta gamma delta", "alpha beta gamma delta epsilon zeta"
    ref = _tree([[a1, a2]])
    cand = _tree([["alpha beta gamma delta epsilon zeta eta"]])
    result = localize(ref, cand)
    # a2 is the closer match; a1 is left over and reported as deleted
    assert _kinds(result) == [
        (RegionType.MODIFIED, "p0-c1", "p0-c0"),
        (RegionType.DELETED, "p0-c0", None),
    ]


def test_replace_tie_goes_to_lower_index() -> None:
    same = "identical chunk text for the tie"
    # two identical ref chunks score equally against the candidate
    ref = _tree([[same + "a", same + "a"]])
    cand = _tree([[same + "b"]])
    result = localize(ref, cand)
    assert _kinds(result)[0] == (RegionType.MODIFIED, "p0-c0", "p0-c0")
    assert _kinds(result)[1] == (RegionType.DELETED, "p0-c1", None)


def test_repeated_chunks_are_deterministic() -> None:
    boiler = "This page intentionally left blank boilerplate"
    ref = _tree([[boiler, _para(1), boiler]])
    cand = _tree([[boiler, _para(1), boiler, boiler]])
    first = localize(ref, cand)
    assert first.to_dict() == localize(ref, cand).to_dict()
    assert first.stats["inserted"] == 1 and first.stats["modified"] == 0


def test_section_fields_come_from_cand_and_ref_for_deletes() -> None:
    ref_sections = (Section("S1", "Rent", ("p0-c0", "p0-c1"), "h"),)
    cand_sections = (Section("S1", "Rent and Deposit", ("p0-c0",), "h"),)
    ref = _tree([[_para(1), _para(2)]], ref_sections)
    cand = _tree([[_para(1)]], cand_sections)
    deleted = localize(ref, cand).regions[0]
    assert (deleted.section_id, deleted.section_title) == ("S1", "Rent")
    ref2 = _tree([[_para(1)]], cand_sections)
    cand2 = _tree([[_para(1), _para(2)]], (Section("S2", "Term", ("p0-c1",), "h"),))
    inserted = localize(ref2, cand2).regions[0]
    assert (inserted.section_id, inserted.section_title) == ("S2", "Term")


def test_result_round_trips() -> None:
    ref = _tree([[_para(1), _para(2)]])
    cand = _tree([[_para(1), _para(2) + " x", _para(3)]])
    result = localize(ref, cand)
    assert LocalizationResult.from_dict(result.to_dict()) == result


def test_real_pdf_single_edit_has_bbox() -> None:
    ref = build_integrity_tree(_pdf([f"{TEXT} one", f"{TEXT} two", f"{TEXT} three"]))
    cand = build_integrity_tree(_pdf([f"{TEXT} one", f"{TEXT} 2wo", f"{TEXT} three"]))
    result = localize(ref, cand)
    assert result.status is LocalizationStatus.CHANGED
    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.type is RegionType.MODIFIED and region.cand_bbox is not None
    assert region.ref_page == region.cand_page == ref.pages[1].index


@given(
    pages=st.lists(st.integers(min_value=0, max_value=4), min_size=1, max_size=5),
    op=st.sampled_from(["modify", "insert", "delete"]),
    data=st.data(),
)
def test_random_single_mutation_yields_exactly_one_region(
    pages: list[int], op: str, data: st.DataObject
) -> None:
    uid = iter(range(10_000))
    ref_pages = [[_para(next(uid)) for _ in range(n)] for n in pages]
    total = sum(pages)
    cand_pages = [list(p) for p in ref_pages]
    if op == "insert":
        p = data.draw(st.integers(0, len(pages) - 1))
        cand_pages[p].insert(data.draw(st.integers(0, len(cand_pages[p]))), _para(next(uid)))
        expected = RegionType.INSERTED
    else:
        if total == 0:
            return
        p = data.draw(st.sampled_from([i for i, n in enumerate(pages) if n > 0]))
        i = data.draw(st.integers(0, len(cand_pages[p]) - 1))
        if op == "modify":
            cand_pages[p][i] += " amended"
            expected = RegionType.MODIFIED
        else:
            del cand_pages[p][i]
            expected = RegionType.DELETED
    result = localize(_tree(ref_pages), _tree(cand_pages))
    assert result.status is LocalizationStatus.CHANGED
    assert [r.type for r in result.regions] == [expected]


def _autojunk_pair() -> tuple[str, str]:
    """590-char chunk and a copy with its first 20 chars rewritten; every char is 'popular'."""
    words = ["alpha", "beta", "gamma", "delta", "mama", "data"]
    base = " ".join(words[(i * i + i) % len(words)] for i in range(200))[:590]
    return base, "delta alpha beta gam" + base[20:]


def test_replace_pairing_uses_autojunk_default_known_limitation() -> None:
    """P1-09 finding 2 / ADR-018: the §9.4 text ratio keeps difflib's autojunk=True.

    On a long chunk made only of frequent characters every character is 'junk', so the
    ratio collapses to 0.0 and a MODIFIED chunk is reported as DELETED + INSERTED.
    """
    base, edited = _autojunk_pair()
    assert len(base) == 590 and base[20:] == edited[20:] and base[:20] != edited[:20]
    assert SequenceMatcher(None, base, edited).ratio() == 0.0
    assert SequenceMatcher(None, base, edited, autojunk=False).ratio() > 0.9
    result = localize(_tree([[base]]), _tree([[edited]]))
    assert _kinds(result) == [
        (RegionType.DELETED, "p0-c0", None),
        (RegionType.INSERTED, None, "p0-c0"),
    ]


def test_equal_count_swap_between_adjacent_pages_stays_on_fast_path() -> None:
    """P1-09 finding 6: chunk counts unchanged, so no spill-over is detected (§9.3 wording)."""
    ref = _tree([[_para(1), _para(2)], [_para(3), _para(4)]])
    cand = _tree([[_para(3), _para(2)], [_para(1), _para(4)]])
    result = localize(ref, cand)
    assert result.status is LocalizationStatus.CHANGED
    assert result.method is LocalizationMethod.MERKLE_FAST_PATH
    assert _kinds(result) == [
        (RegionType.MODIFIED, "p0-c0", "p0-c0"),
        (RegionType.MODIFIED, "p1-c0", "p1-c0"),
    ]
