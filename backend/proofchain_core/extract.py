"""Text extraction per docs/02_ALGORITHMS.md §2.

Returns raw (un-normalized) block text with geometry and span styling. Canonicalization and
chunking happen later; the only canonical use here is the minimum-text check.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from proofchain_core.canonical import normalize_text
from proofchain_core.errors import EncryptedPdfError, InvalidPdfError, NoExtractableTextError
from proofchain_core.types import BBox

MIN_CANONICAL_CHARS = 20  # 02 §2
BOLD_FLAG = 16  # 02 §2: bold = flags & 16


@dataclass(frozen=True)
class SpanInfo:
    size: float
    flags: int

    @property
    def bold(self) -> bool:
        return bool(self.flags & BOLD_FLAG)


@dataclass(frozen=True)
class ExtractedBlock:
    text: str
    bbox: BBox
    spans: tuple[SpanInfo, ...]


@dataclass(frozen=True)
class ExtractedPage:
    index: int  # 0-based
    blocks: tuple[ExtractedBlock, ...]


def _open(pdf_bytes: bytes) -> pymupdf.Document:
    if not pdf_bytes:
        raise InvalidPdfError("empty input")
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:  # pymupdf raises several types for malformed input
        raise InvalidPdfError("not a readable PDF") from exc
    if not doc.is_pdf:
        raise InvalidPdfError("not a PDF")
    # Stricter than "needs a password": owner-only encryption also lands here (see PROGRESS.md).
    # PyMuPDF auto-authenticates an empty user password and then reports is_encrypted=False,
    # so the reliable signal is the "encryption" metadata entry (None for unencrypted files).
    if doc.needs_pass or doc.is_encrypted or (doc.metadata or {}).get("encryption"):
        raise EncryptedPdfError("PDF is encrypted")
    return doc


def _extract_block(block: dict) -> ExtractedBlock:  # type: ignore[type-arg]
    line_texts: list[str] = []
    spans: list[SpanInfo] = []
    for line in block["lines"]:
        line_texts.append("".join(span["text"] for span in line["spans"]))
        spans.extend(SpanInfo(float(s["size"]), int(s["flags"])) for s in line["spans"])
    x0, y0, x1, y1 = block["bbox"]
    return ExtractedBlock(
        text=" ".join(line_texts),
        bbox=BBox(float(x0), float(y0), float(x1), float(y1)),
        spans=tuple(spans),
    )


def extract_pages(pdf_bytes: bytes) -> list[ExtractedPage]:
    """Extract text blocks per page (02 §2).

    Raises InvalidPdfError, EncryptedPdfError, NoExtractableTextError.
    """
    doc = _open(pdf_bytes)
    try:
        pages: list[ExtractedPage] = []
        for index in range(doc.page_count):
            data = doc[index].get_text("dict", sort=True)  # type: ignore[no-untyped-call]
            blocks = tuple(_extract_block(b) for b in data["blocks"] if b["type"] == 0)
            pages.append(ExtractedPage(index=index, blocks=blocks))
    except Exception as exc:
        raise InvalidPdfError("failed to read PDF pages") from exc
    finally:
        doc.close()  # type: ignore[no-untyped-call]

    total = sum(len(normalize_text(b.text).strip()) for p in pages for b in p.blocks)
    if total < MIN_CANONICAL_CHARS:
        raise NoExtractableTextError(f"only {total} canonical characters extracted")
    return pages
