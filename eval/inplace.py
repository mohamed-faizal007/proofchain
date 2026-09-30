"""In-place PDF tampering with PyMuPDF (docs/08 C.2) and the metadata-only re-save.

An in-place edit works on the *original* PDF bytes (no re-render): the block's rectangle, known
from the shared layout in render.py, is redacted and the edited text is written back with
``insert_textbox`` in the same font, size and width. It is skipped (``InPlaceSkip``) when the new
text no longer fits the block's box, e.g. a longer party name that wraps onto an extra line.
"""

from __future__ import annotations

import re
from typing import Any

import pymupdf

from render import (
    _SPACE_AFTER,
    FONT_DIR,
    MARGIN_TOP,
    MARGIN_X,
    TEXT_W,
    Cursor,
    block_height,
)

_mupdf: Any = pymupdf  # PyMuPDF's stubs are partial; keep this module free of per-call ignores
_PAD = 2.0  # points of slack around the block's box
_FONT = str(FONT_DIR / "DejaVuSans.ttf")
_REGULAR_KINDS = ("clause", "line", "signature")  # render.py: regular 10 pt / 14 pt leading
_LINE_HEIGHT = 1.4  # 14 pt leading at 10 pt (render.py "clause" style)


# The second /ID is random per save; MuPDF writes it as <hex> or, when the bytes allow, as a
# literal (string) with backslash escapes.
_TRAILER_ID = re.compile(
    rb"/ID\[(<[0-9A-Fa-f]{32}>)(<[0-9A-Fa-f]{32}>|\((?:[^()\\]|\\.)*\))\]", re.DOTALL
)


def _stable_id(pdf: bytes) -> bytes:
    """Set the random second /ID to the first. The trailer follows ``startxref``' target, so the
    length change moves no offset; without this two runs of one tamper differ in bytes."""
    matches = list(_TRAILER_ID.finditer(pdf))
    if not matches:
        raise RuntimeError("saved PDF has no /ID pair in its trailer")
    m = matches[-1]
    return pdf[: m.start(2)] + m.group(1) + pdf[m.end(2) :]


class InPlaceSkip(Exception):
    """The edit cannot be applied in place; ``reason`` is a short stable key for the stats."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def block_layout(spec: dict[str, Any]) -> list[tuple[int, float, float]]:
    """Per block: (0-based page, top offset from the page's top edge in points, text height)."""
    cursor = Cursor()
    out: list[tuple[int, float, float]] = []
    for b in spec["blocks"]:
        height = block_height(b["kind"], b["text"])
        nxt = cursor.advance(height)
        out.append((nxt.page - 1, MARGIN_TOP + nxt.used - height, height - _SPACE_AFTER[b["kind"]]))
        cursor = nxt
    return out


def apply_inplace(pdf: bytes, spec: dict[str, Any], edits: list[dict[str, Any]]) -> bytes:
    """Apply ``replace`` edits to ``pdf`` (rendered from ``spec``); raises InPlaceSkip."""
    if any(e["kind"] != "replace" for e in edits):
        raise InPlaceSkip("unsupported_op")
    layout = block_layout(spec)
    index = {b["id"]: i for i, b in enumerate(spec["blocks"])}
    doc = _mupdf.open(stream=pdf, filetype="pdf")
    try:
        for edit in edits:
            kind = spec["blocks"][index[edit["block_id"]]]["kind"]
            if kind not in _REGULAR_KINDS:
                raise InPlaceSkip("unsupported_block")
            page_no, top, height = layout[index[edit["block_id"]]]
            page = doc[page_no]
            box = _mupdf.Rect(MARGIN_X - 1, top - 1, MARGIN_X + TEXT_W + 1, top + height + 1)
            page.add_redact_annot(box, fill=(1, 1, 1))
            page.apply_redactions(images=_mupdf.PDF_REDACT_IMAGE_NONE)
            room = _mupdf.Rect(MARGIN_X, top - _PAD, MARGIN_X + TEXT_W, top + height + _PAD)
            left = page.insert_textbox(
                room,
                edit["after"],
                fontname="dejavu",
                fontfile=_FONT,
                fontsize=10,
                lineheight=_LINE_HEIGHT,
            )
            if left < 0:
                raise InPlaceSkip("overflow")
        return _stable_id(bytes(doc.tobytes(garbage=4, deflate=True)))
    finally:
        doc.close()


# (metadata to set, save options): the text layer is untouched, the bytes change.
_RESAVE_VARIANTS: tuple[tuple[dict[str, str], dict[str, Any]], ...] = (
    ({"producer": "ProofChain-eval resave A", "title": "Re-saved copy"}, {"garbage": 4}),
    ({"producer": "ProofChain-eval resave B", "author": "Records Office"}, {"garbage": 3}),
    ({"producer": "", "title": "", "author": "", "creator": ""}, {"garbage": 1, "clean": True}),
)
_FIXED_DATE = "D:20260101000000Z"
RESAVE_VARIANTS = len(_RESAVE_VARIANTS)


def resave_metadata(pdf: bytes, variant: int) -> bytes:
    """Same text, different metadata and save options: expected CONTENT_EQUIVALENT."""
    meta, options = _RESAVE_VARIANTS[variant % RESAVE_VARIANTS]
    doc = _mupdf.open(stream=pdf, filetype="pdf")
    try:
        doc.set_metadata({**meta, "creationDate": _FIXED_DATE, "modDate": _FIXED_DATE})
        return _stable_id(bytes(doc.tobytes(deflate=True, **options)))
    finally:
        doc.close()
