"""Generate the fixture PDFs used by the core tests (08 §A).

Run ``python tests/fixtures/make_fixtures.py`` to regenerate ``tests/fixtures/pdfs/``.
Regenerate only intentionally: tests that need exact hashes read the committed PDFs.

Determinism: every canvas uses ``invariant=1`` (fixed dates and document ID) and
compression is left at reportlab's default. Only the built-in base-14 fonts are used,
except ``unicode_variants.pdf``, which embeds reportlab's bundled Vera font because
the standard fonts cannot encode ligatures. reportlab is pinned exactly in
pyproject.toml so this output only changes when the pin does.
Byte-identity has been checked on one machine only; it is not claimed across OSes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import reportlab
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

OUT_DIR = Path(__file__).resolve().parent / "pdfs"
PAGE_W, PAGE_H = A4
MARGIN = 72

ONE_PAGE_LINES = [
    "Service Agreement",
    "This agreement is made between Acme Traders and Bharat Supplies.",
    "The total fee payable is Rs. 50,000 within 30 days of invoice.",
]

CONTRACT_PAGES: list[list[tuple[str, str]]] = [
    [
        ("h", "1. Definitions"),
        (
            "p",
            "Supplier means Bharat Supplies and Client means Acme Traders.",
        ),
        ("p", "Goods means the items listed in Schedule A delivered under this agreement."),
        ("h", "2. Payment Terms"),
        (
            "p",
            "The Client shall pay the Supplier Rs. 1,20,000 within 30 days of each invoice.",
        ),
    ],
    [
        (
            "p",
            "Late payments accrue interest at 2% per month until the amount is settled.",
        ),
        ("p", "The Supplier may suspend deliveries if any invoice remains unpaid after 45 days."),
        ("h", "3. Termination"),
        (
            "p",
            "Either party may terminate this agreement with 60 days written notice.",
        ),
    ],
    [
        (
            "p",
            "On termination the Client must pay all amounts due for goods delivered.",
        ),
        ("p", "The Supplier shall return any advance payment for goods that were not delivered."),
        (
            "p",
            "This agreement is governed by the laws of India and disputes go to courts in Chennai.",
        ),
    ],
]

NBSP_LINE = "Total\u00a0amount\u00a0due:\u00a0Rs.\u00a075,000"
QUOTE_LINE = "The \u201cSupplier\u201d shall not be liable for the Client\u2019s delays."
LIGATURE_LINE = "The \ufb01nal \ufb01le and the \ufb02agged \ufb02yer."


def _canvas(path: Path, **kwargs: object) -> Canvas:
    return Canvas(str(path), pagesize=A4, invariant=1, pageCompression=1, **kwargs)  # type: ignore[arg-type]


def _one_page(path: Path) -> None:
    c = _canvas(path)
    y = PAGE_H - MARGIN
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, y, ONE_PAGE_LINES[0])
    c.setFont("Helvetica", 11)
    for line in ONE_PAGE_LINES[1:]:
        y -= 28
        c.drawString(MARGIN, y, line)
    c.save()


def _contract(path: Path) -> None:
    c = _canvas(path)
    for page in CONTRACT_PAGES:
        y = PAGE_H - MARGIN
        for kind, text in page:
            if kind == "h":
                y -= 12
                c.setFont("Helvetica-Bold", 14)
                c.drawString(MARGIN, y, text)
                y -= 26
            else:
                c.setFont("Helvetica", 11)
                c.drawString(MARGIN, y, text)
                y -= 34
        c.showPage()
    c.save()


def _unicode_variants(path: Path) -> None:
    font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    pdfmetrics.registerFont(TTFont("Vera", str(font_path)))
    c = _canvas(path)
    c.setFont("Vera", 11)
    y = PAGE_H - MARGIN
    for line in (NBSP_LINE, QUOTE_LINE, LIGATURE_LINE):
        c.drawString(MARGIN, y, line)
        y -= 28
    c.save()


def _image_only(path: Path) -> None:
    # Fixed synthetic raster (bars), no text layer: simulates a scan.
    width, height = 200, 100
    pixels = bytearray()
    for row in range(height):
        for col in range(width):
            shade = 0 if (row // 10 + col // 20) % 2 == 0 else 255
            pixels += bytes((shade, shade, shade))
    image = Image.frombytes("RGB", (width, height), bytes(pixels))
    c = _canvas(path)
    c.drawInlineImage(image, MARGIN, PAGE_H - MARGIN - 300, width=400, height=200)
    c.save()


def _encrypted(path: Path) -> None:
    enc = StandardEncryption("user-secret", ownerPassword="owner-secret", strength=128)
    c = _canvas(path, encrypt=enc)
    c.setFont("Helvetica", 11)
    c.drawString(MARGIN, PAGE_H - MARGIN, "This document is password protected and not readable.")
    c.save()


def _not_a_pdf(path: Path) -> None:
    path.write_bytes(b"This is plain text renamed to .pdf, not a PDF document.\n")


def generate(out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _one_page(out_dir / "one_page.pdf")
    _contract(out_dir / "contract_3page.pdf")
    _unicode_variants(out_dir / "unicode_variants.pdf")
    _image_only(out_dir / "image_only.pdf")
    _encrypted(out_dir / "encrypted.pdf")
    _not_a_pdf(out_dir / "not_a_pdf.pdf")


if __name__ == "__main__":
    generate(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR)
