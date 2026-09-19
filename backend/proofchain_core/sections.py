"""Sections overlay (02_ALGORITHMS.md §8).

Sections are for reporting only; they are not part of `text_root`.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from proofchain_core.canonical import normalize_text
from proofchain_core.chunking import ChunkOrigin
from proofchain_core.extract import ExtractedBlock
from proofchain_core.merkle import merkle_root
from proofchain_core.types import Chunk, Section

HEADING_MAX_CHARS = 120  # §8
HEADING_SIZE_RATIO = 1.15  # §8 (a)
BODY_SIZE_STEP = 0.5  # §8: body_size is rounded to 0.5pt

# §8 (c). Case-insensitive for the keywords only, not for roman numerals. Known limitation
# (02 §13): the numeric branch matches ordinary prose such as "5 apples were sold".
_HEADING_PATTERN = re.compile(
    r"^(?i:ARTICLE|SECTION|CLAUSE|SCHEDULE|ANNEXURE)\b"
    r"|^(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)])\s+\S"
)


def _round_half_point(size: float) -> float:
    # Half-up, not round(): banker's rounding would send 10.25 and 10.75 opposite ways.
    return math.floor(size / BODY_SIZE_STEP + 0.5) * BODY_SIZE_STEP


def _distinct_blocks(origins: Sequence[ChunkOrigin]) -> list[ExtractedBlock]:
    """Each block once: chunks split from one block are consecutive and share the object."""
    blocks: list[ExtractedBlock] = []
    for origin in origins:
        if not blocks or blocks[-1] is not origin.block:
            blocks.append(origin.block)
    return blocks


def body_size(origins: Sequence[ChunkOrigin]) -> float | None:
    """Most frequent span size (rounded to 0.5pt); ties take the smaller size (§8).

    Blank spans (empty canonical text) and blocks whose canonical text is empty (dropped before
    chunking) do not count. Returns None when no block has any non-blank span.
    """
    counts = Counter(
        _round_half_point(span.size)
        for block in _distinct_blocks(origins)
        for span in block.spans
        if not span.blank
    )
    if not counts:
        return None
    return min(counts, key=lambda size: (-counts[size], size))


def _is_heading(block: ExtractedBlock, body: float | None) -> bool:
    text = normalize_text(block.text)
    if not text or len(text) > HEADING_MAX_CHARS or text.endswith("."):
        return False
    spans = [span for span in block.spans if not span.blank]
    larger = (
        body is not None
        and bool(spans)
        and max(span.size for span in spans) >= body * HEADING_SIZE_RATIO
    )
    all_bold = bool(spans) and all(span.bold for span in spans)
    return larger or all_bold or _HEADING_PATTERN.search(text) is not None


def _section(number: int, title: str, chunks: Sequence[Chunk]) -> Section:
    return Section(
        id=f"S{number}",
        title=title,
        chunk_ids=tuple(c.id for c in chunks),
        hash=merkle_root([c.leaf_hash for c in chunks]),
    )


def build_sections(origins: Sequence[ChunkOrigin]) -> tuple[Section, ...]:
    """Group chunks into sections: a heading starts one, chunks before the first form S0 (§8).

    A heading block is at most 120 canonical characters, so it is always a single chunk.
    """
    body = body_size(origins)
    sections: list[Section] = []
    title = "Preamble"
    number = 0
    current: list[Chunk] = []
    for origin in origins:
        if _is_heading(origin.block, body):
            if current:
                sections.append(_section(number, title, current))
            number = number + 1
            title = origin.chunk.text
            current = []
        current.append(origin.chunk)
    if current:
        sections.append(_section(number, title, current))
    return tuple(sections)
