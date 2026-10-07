"""Deterministic demo documents for scripts/demo.ps1 (P10-04).

One lease: the original (v1), an authorised amendment (v2, a term extension) and copies of v2
that someone altered afterwards (amount, party, obligation, removed clause) or merely re-saved.
Everything is built with the eval generator and tamper operations, so the same bytes come out on
every run and every machine. Needs the backend venv (reportlab, faker, pymupdf, proofchain_core).

The expected verdicts follow 02_ALGORITHMS §11: v1 is byte-identical to an approved revision but
a newer approved one exists (AUTHENTIC_SUPERSEDED); v2 is the latest (AUTHENTIC_LATEST); an altered
copy matches nothing (TAMPERED, with the category of the edit); a metadata re-save has the same
canonical text but different bytes (CONTENT_EQUIVALENT, never reported as authentic).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
DEMO_INDEX = 0  # corpus document 0: a 3-page lease on which every operation below applies
DEMO_TITLE = "Demo Lease Agreement (ProofChain)"
DEMO_DOC_TYPE = "CONTRACT"
CHANGE_NOTE = "Amendment: lease term extended"

# (key, label, op, seed): the op's own edit record supplies the expected category.
_TAMPERS = (
    ("tampered_amount", "Rent amount silently changed", "amount_change", 11),
    ("tampered_party", "Counterparty name swapped", "party_change", 12),
    ("tampered_obligation", "Obligation weakened (shall -> may)", "obligation_flip", 13),
    ("tampered_clause_removed", "A clause deleted", "clause_delete", 14),
)
_AMENDMENT_OP, _AMENDMENT_SEED = "date_change", 7


@dataclass(frozen=True)
class DemoCopy:
    key: str
    label: str
    pdf: bytes
    expected_verdict: str
    expected_category: str | None


@dataclass(frozen=True)
class DemoSet:
    title: str
    doc_type: str
    change_note: str
    v1: bytes
    v2: bytes
    copies: tuple[DemoCopy, ...]


def _eval_modules() -> dict[str, Any]:
    if str(EVAL_DIR) not in sys.path:
        sys.path.insert(0, str(EVAL_DIR))
    import generate_corpus
    import inplace
    import render
    import spec_edit
    import tamper_ops

    return {
        "generate_corpus": generate_corpus,
        "inplace": inplace,
        "render": render,
        "spec_edit": spec_edit,
        "tamper_ops": tamper_ops,
    }


def _tamper(m: dict[str, Any], spec: dict[str, Any], op: str, seed: int) -> tuple[bytes, str]:
    ctx = m["tamper_ops"].make_context(spec["doc_type"], seed)
    edits = m["tamper_ops"].OPS[op].plan(spec, ctx)
    if edits is None:  # would mean the pinned DEMO_INDEX no longer suits the op: test catches it
        raise RuntimeError(f"demo operation {op!r} does not apply to corpus document {DEMO_INDEX}")
    after = m["spec_edit"].apply_edits(spec, edits)
    return m["render"].render_pdf(after), str(edits[0]["category"])


def build_demo_set() -> DemoSet:
    m = _eval_modules()
    cfg = m["generate_corpus"].load_config(EVAL_DIR / "configs" / "default.yaml")
    spec_v1, v1 = m["generate_corpus"].generate_one(cfg, DEMO_INDEX)
    ctx = m["tamper_ops"].make_context(spec_v1["doc_type"], _AMENDMENT_SEED)
    edits = m["tamper_ops"].OPS[_AMENDMENT_OP].plan(spec_v1, ctx)
    if edits is None:
        raise RuntimeError(f"demo amendment {_AMENDMENT_OP!r} does not apply to the document")
    spec_v2 = m["spec_edit"].apply_edits(spec_v1, edits)
    v2 = m["render"].render_pdf(spec_v2)

    copies = [
        DemoCopy(
            "original_v1", "Original (v1), since superseded", v1, "AUTHENTIC_SUPERSEDED", None
        ),
        DemoCopy("approved_v2", "Approved amendment (v2), latest", v2, "AUTHENTIC_LATEST", None),
    ]
    for key, label, op, seed in _TAMPERS:
        pdf, category = _tamper(m, spec_v2, op, seed)
        copies.append(DemoCopy(key, label, pdf, "TAMPERED", category))
    resaved = m["inplace"].resave_metadata(v2, 1)
    copies.append(
        DemoCopy(
            "resaved_v2", "v2 re-saved (same text, new bytes)", resaved, "CONTENT_EQUIVALENT", None
        )
    )
    return DemoSet(DEMO_TITLE, DEMO_DOC_TYPE, CHANGE_NOTE, v1, v2, tuple(copies))


def write_pdfs(demo: DemoSet, out_dir: Path) -> list[Path]:
    """Write every copy as <key>.pdf so the same files can be uploaded by hand in the UI."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for copy in demo.copies:
        path = out_dir / f"{copy.key}.pdf"
        path.write_bytes(copy.pdf)
        written.append(path)
    return written
