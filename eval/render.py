"""Spec -> PDF (reportlab, DejaVu Sans embedded) and the page layout shared with the generator.

Determinism: ``invariant=1`` (fixed dates and document id); the fonts are the pinned files in
``templates/fonts`` (SHA-256 recorded in FONT_SHA256, checked on first use).
Byte-identity is checked on one machine and by tests only; it holds for the pinned
reportlab/PyMuPDF/font versions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

FONT_DIR = Path(__file__).resolve().parent / "templates" / "fonts"
FONT_SHA256 = {
    "DejaVuSans.ttf": "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954",
    "DejaVuSans-Bold.ttf": "e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724",
}
REGULAR, BOLD = "DejaVuSans", "DejaVuSans-Bold"

PAGE_W, PAGE_H = A4
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 60.0, 64.0, 64.0
TEXT_W = PAGE_W - 2 * MARGIN_X

_STYLES: dict[str, ParagraphStyle] = {}
_SPACE_AFTER = {"title": 14.0, "heading": 5.0, "clause": 6.0, "line": 4.0, "signature": 10.0}


def _register_fonts() -> None:
    if _STYLES:
        return
    for name, digest in FONT_SHA256.items():
        actual = hashlib.sha256((FONT_DIR / name).read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError(f"{name}: SHA-256 {actual} does not match the pinned {digest}")
    pdfmetrics.registerFont(TTFont(REGULAR, str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))

    def style(name: str, font: str, size: float, leading: float, align: int) -> None:
        _STYLES[name] = ParagraphStyle(
            name, fontName=font, fontSize=size, leading=leading, alignment=align
        )

    style("title", BOLD, 16, 20, TA_CENTER)
    style("heading", BOLD, 11, 15, TA_LEFT)
    style("clause", REGULAR, 10, 14, TA_LEFT)
    style("line", REGULAR, 10, 14, TA_LEFT)
    style("signature", REGULAR, 10, 14, TA_LEFT)


def _paragraph(kind: str, text: str) -> tuple[Paragraph, float]:
    _register_fonts()
    para = Paragraph(escape(text), _STYLES[kind])
    _, height = para.wrap(TEXT_W, 1e6)
    return para, height + _SPACE_AFTER[kind]


def block_height(kind: str, text: str) -> float:
    return _paragraph(kind, text)[1]


@dataclass(frozen=True)
class Cursor:
    """Layout position: 1-based page and distance from the top margin."""

    page: int = 1
    used: float = 0.0

    def advance(self, height: float) -> Cursor:
        room = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM
        if self.used + height > room and self.used > 0:
            return Cursor(self.page + 1, height)
        return Cursor(self.page, self.used + height)


def render_pdf(spec: dict[str, Any]) -> bytes:
    """Deterministic PDF bytes for a spec."""
    _register_fonts()
    buf = BytesIO()
    canvas = Canvas(buf, pagesize=A4, invariant=1, pageCompression=1)
    canvas.setTitle(spec["title"])
    cursor = Cursor()
    for block in spec["blocks"]:
        para, height = _paragraph(block["kind"], block["text"])
        nxt = cursor.advance(height)
        if nxt.page != cursor.page:
            canvas.showPage()
        top = PAGE_H - MARGIN_TOP - (nxt.used - height)
        para.drawOn(canvas, MARGIN_X, top - (height - _SPACE_AFTER[block["kind"]]))
        cursor = nxt
    canvas.save()
    return buf.getvalue()
