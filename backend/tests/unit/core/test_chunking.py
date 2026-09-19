"""Tests for 02_ALGORITHMS.md §4 chunking."""

from pathlib import Path

from proofchain_core import (
    MAX_CHUNK_CHARS,
    ExtractedBlock,
    ExtractedPage,
    SpanInfo,
    chunk_blocks,
    chunk_pages,
    extract_pages,
    leaf_hash,
)
from proofchain_core.types import BBox

PDFS = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs"
BOX = BBox(72.0, 100.0, 500.0, 140.0)


def _block(text: str, bbox: BBox = BOX) -> ExtractedBlock:
    return ExtractedBlock(text=text, bbox=bbox, spans=(SpanInfo(size=11.0, flags=0),))


def _page(index: int, *texts: str) -> ExtractedPage:
    return ExtractedPage(index=index, blocks=tuple(_block(t) for t in texts))


def _texts(*texts: str) -> list[str]:
    return [c.text for c in chunk_pages([_page(0, *texts)])]


def _sentence(n: int) -> str:
    """A sentence of exactly n chars: uppercase start, no spaces, ends with a period."""
    return "S" + "x" * (n - 2) + "."


def _words(n: int) -> str:
    """Space-separated words, no sentence boundary, exactly n chars."""
    return ("word " * 200)[:n].rstrip() + "d" * (n - len(("word " * 200)[:n].rstrip()))


def test_max_chunk_chars_constant() -> None:
    assert MAX_CHUNK_CHARS == 600


def test_boundary_599_600_one_chunk_601_splits() -> None:
    for n in (599, 600):
        text = _words(n)
        assert len(text) == n
        assert _texts(text) == [text]
    text = _words(601)
    assert len(text) == 601
    out = _texts(text)
    assert len(out) == 2
    assert all(len(t) <= 600 for t in out)


def test_short_block_is_one_chunk_canonicalized() -> None:
    assert _texts("  Hello world  ") == ["Hello world"]


def test_greedy_sentence_packing() -> None:
    a, b, c = _sentence(300), _sentence(299), _sentence(100)
    # a + " " + b = 600 fits exactly; c starts a new chunk.
    assert _texts(f"{a} {b} {c}") == [f"{a} {b}", c]


def test_packing_flushes_when_next_sentence_would_exceed() -> None:
    a, b = _sentence(300), _sentence(300)  # 300 + 1 + 300 = 601
    assert _texts(f"{a} {b}") == [a, b]


def test_regex_does_not_split_before_lowercase() -> None:
    a = _sentence(400)
    tail = ("e.g. lower case continues here and is long enough " * 5).strip()
    text = f"{a} {tail}"
    out = _texts(text)
    # "." followed by a lowercase letter is not a boundary, so this is one 650-char sentence
    # and falls to the long-sentence rule (space split near 600), not a split after `a`.
    assert len(out[0]) > len(a)
    assert " ".join(out) == text
    # With an uppercase follower the same text does split after `a`.
    assert _texts(f"{a} {tail[0].upper()}{tail[1:]}")[0] == a


def test_long_sentence_splits_at_last_space_before_600() -> None:
    text = "S" + " ".join(["abcde"] * 200)  # one sentence, no boundary
    out = _texts(text)
    assert all(len(t) <= 600 for t in out)
    assert " ".join(out) == text
    assert not out[0].endswith(" ")
    # First chunk is as long as possible: adding the next word would exceed 600.
    assert len(out[0]) + 1 + len(out[1].split(" ")[0]) > 600


def test_long_sentence_without_spaces_hard_splits_at_600() -> None:
    assert _texts("A" * 1300) == ["A" * 600, "A" * 600, "A" * 100]


def test_long_sentence_flushes_pack_before_split() -> None:
    short = _sentence(50)
    long = "L" + " ".join(["abcde"] * 150) + "."  # > 600, single sentence
    after = _sentence(40)
    out = _texts(f"{short} {long} {after}")
    assert out[0] == short
    assert all(len(t) <= 600 for t in out)
    assert out[-1].endswith(after)
    assert " ".join(out) == f"{short} {long} {after}"


def test_split_tail_packs_with_following_sentence_in_same_block() -> None:
    long = "L" + " ".join(["abcde"] * 150) + "."  # 901 chars, one sentence
    after = _sentence(40)
    alone = _texts(long)
    assert len(alone) == 2
    together = _texts(f"{long} {after}")
    # Same number of chunks as without `after`: it joined the tail instead of adding a chunk.
    assert together == [alone[0], f"{alone[1]} {after}"]


def test_split_tail_does_not_pack_across_blocks() -> None:
    long = "L" + " ".join(["abcde"] * 150) + "."
    after = _sentence(40)
    alone = _texts(long)
    # Same content, but `after` is a separate block: it starts its own chunk.
    assert _texts(long, after) == [*alone, after]
    assert _texts("A" * 1300, "Short") == ["A" * 600, "A" * 600, "A" * 100, "Short"]


def test_ids_are_per_page_zero_based_in_reading_order() -> None:
    chunks = chunk_pages([_page(0, "First para", "Second para"), _page(1, "Third para")])
    assert [c.id for c in chunks] == ["p0-c0", "p0-c1", "p1-c0"]
    assert [(c.page, c.index) for c in chunks] == [(0, 0), (0, 1), (1, 0)]


def test_index_counts_split_chunks() -> None:
    chunks = chunk_pages([_page(0, "Lead", "A" * 1300, "Tail")])
    assert [c.id for c in chunks] == ["p0-c0", "p0-c1", "p0-c2", "p0-c3", "p0-c4"]


def test_empty_and_whitespace_blocks_dropped_without_gaps() -> None:
    chunks = chunk_pages([_page(0, "A one", "   ", "​­", "B two")])
    assert [(c.id, c.text) for c in chunks] == [("p0-c0", "A one"), ("p0-c1", "B two")]


def test_page_with_no_surviving_blocks_yields_no_chunks() -> None:
    chunks = chunk_pages([_page(0, "  "), _page(1, "Real text")])
    assert [c.id for c in chunks] == ["p1-c0"]


def test_bbox_inherited_by_split_chunks() -> None:
    box = BBox(1.0, 2.0, 3.0, 4.0)
    page = ExtractedPage(index=0, blocks=(_block("A" * 1300, box),))
    chunks = chunk_pages([page])
    assert len(chunks) == 3
    assert all(c.bbox == box for c in chunks)


def test_leaf_hash_matches_text() -> None:
    for c in chunk_pages([_page(0, "Alpha", "B" * 700)]):
        assert c.leaf_hash == leaf_hash(c.text)


def test_length_is_measured_after_canonicalization() -> None:
    # Each ligature expands to 2 chars under NFKC: 300 -> 600 (one chunk), 301 -> 602 (split).
    assert len(_texts("ﬁ" * 300)) == 1
    assert len(_texts("ﬁ" * 301)) == 2


def test_contract_fixture_is_deterministic_and_bounded() -> None:
    pages = extract_pages((PDFS / "contract_3page.pdf").read_bytes())
    first, second = chunk_pages(pages), chunk_pages(pages)
    assert first == second
    assert first
    assert all(0 < len(c.text) <= MAX_CHUNK_CHARS for c in first)
    assert {c.page for c in first} == {0, 1, 2}


def test_chunk_pages_is_the_chunks_of_chunk_blocks() -> None:
    pages = extract_pages((PDFS / "contract_3page.pdf").read_bytes())
    assert chunk_pages(pages) == [o.chunk for o in chunk_blocks(pages)]


def test_chunks_split_from_one_block_share_that_block_object() -> None:
    long_block = _block("A" * 1300)
    page = ExtractedPage(index=0, blocks=(_block("Lead"), long_block, _block("Tail")))
    origins = chunk_blocks([page])
    assert [o.chunk.text for o in origins] == ["Lead", "A" * 600, "A" * 600, "A" * 100, "Tail"]
    assert [o.block is long_block for o in origins] == [False, True, True, True, False]


def test_chunk_blocks_skips_empty_blocks_and_keeps_the_right_block() -> None:
    kept = _block("Real text")
    page = ExtractedPage(index=0, blocks=(_block("   "), kept, _block("​­")))
    origins = chunk_blocks([page])
    assert len(origins) == 1
    assert origins[0].block is kept
    assert origins[0].chunk.id == "p0-c0"
