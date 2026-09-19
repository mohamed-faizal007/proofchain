"""Blocks to chunks (02_ALGORITHMS.md §4)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from proofchain_core.canonical import normalize_text
from proofchain_core.extract import ExtractedBlock, ExtractedPage
from proofchain_core.hashing import leaf_hash
from proofchain_core.types import Chunk

MAX_CHUNK_CHARS = 600  # §4

# §4 sentence boundary: after . ! ? ; : and before an uppercase letter, digit or opener.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+(?=[A-Z0-9(\"'\[])")


def _hard_split(sentence: str) -> list[str]:
    """§4: split a >600-char sentence at the last space before 600, or hard at 600."""
    pieces: list[str] = []
    while len(sentence) > MAX_CHUNK_CHARS:
        cut = sentence.rfind(" ", 0, MAX_CHUNK_CHARS + 1)
        if cut <= 0:
            pieces.append(sentence[:MAX_CHUNK_CHARS])
            sentence = sentence[MAX_CHUNK_CHARS:]
        else:
            pieces.append(sentence[:cut])
            sentence = sentence[cut + 1 :]
    pieces.append(sentence)
    return pieces


def split_paragraph(text: str) -> list[str]:
    """Split one canonical paragraph into chunk texts (§4)."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    out: list[str] = []
    current = ""
    for sentence in _SENTENCE_BOUNDARY.split(text):
        if len(sentence) > MAX_CHUNK_CHARS:
            if current:
                out.append(current)
            *head, current = _hard_split(sentence)
            out.extend(head)
            continue
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
        else:
            out.append(current)
            current = sentence
    if current:
        out.append(current)
    return out


@dataclass(frozen=True)
class ChunkOrigin:
    """A chunk paired with the extracted block it was split from.

    Never serialized: the section overlay (§8) needs block styling that `Chunk` does not carry.
    Chunks split from one block share the same `block` object.
    """

    chunk: Chunk
    block: ExtractedBlock


def chunk_blocks(pages: Sequence[ExtractedPage]) -> list[ChunkOrigin]:
    """Canonicalize each block, drop empties, split, and id chunks `p{page}-c{index}` (§4)."""
    origins: list[ChunkOrigin] = []
    for page in pages:
        index = 0
        for block in page.blocks:
            text = normalize_text(block.text)
            if not text:
                continue
            for piece in split_paragraph(text):
                chunk = Chunk(
                    id=f"p{page.index}-c{index}",
                    page=page.index,
                    index=index,
                    text=piece,
                    bbox=block.bbox,
                    leaf_hash=leaf_hash(piece),
                )
                origins.append(ChunkOrigin(chunk=chunk, block=block))
                index += 1
    return origins


def chunk_pages(pages: Sequence[ExtractedPage]) -> list[Chunk]:
    """The chunks of `chunk_blocks`, without their source blocks (§4)."""
    return [origin.chunk for origin in chunk_blocks(pages)]
