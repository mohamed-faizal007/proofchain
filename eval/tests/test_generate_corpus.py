"""P9-01 corpus generator tests (docs/08 C.1)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from proofchain_core import build_integrity_tree, extract_pages, normalize_text

from corpus_spec import dump_spec, load_spec
from generate_corpus import doc_seed, generate_one
from page_counts import PAGE_COUNT_FUNCTIONS, bucket_name

EVAL_DIR = Path(__file__).resolve().parent.parent
Corpus = list[tuple[dict[str, Any], bytes]]


def _squash(s: str) -> str:
    return "".join(normalize_text(s).split())


def _has_rupee(spec: dict[str, Any]) -> bool:
    return any(
        "₹" in b["text"] and any(e["kind"] == "AMOUNT" for e in b["entities"])
        for b in spec["blocks"]
    )


# ---- 1. determinism, incl. the rupee case (embedded TTF) -----------------------------------


def test_same_seed_same_bytes_for_rupee_document(cfg: dict[str, Any]) -> None:
    index = next(i for i in range(cfg["n_docs"]) if _has_rupee(generate_one(cfg, i)[0]))
    (spec_a, pdf_a), (spec_b, pdf_b) = generate_one(cfg, index), generate_one(cfg, index)
    assert _has_rupee(spec_a)
    assert dump_spec(spec_a) == dump_spec(spec_b)
    assert pdf_a == pdf_b


def test_rupee_pdf_is_byte_identical_across_fresh_processes(tmp_path: Path) -> None:
    """A fresh interpreter each time: no hidden reliance on process-global font/Faker state."""
    digests = []
    for run in ("a", "b"):
        out = tmp_path / run
        subprocess.run(
            [
                sys.executable,
                "generate_corpus.py",
                "--config",
                "configs/default.yaml",
                "--n-docs",
                "10",
                "--out",
                str(out),
            ],
            cwd=EVAL_DIR,
            check=True,
            capture_output=True,
        )
        digests.append(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}
        )
    assert digests[0] == digests[1]
    rupee_specs = [
        n for n in digests[0] if n.endswith(".json") and _has_rupee(load_spec(tmp_path / "a" / n))
    ]
    assert rupee_specs, "the sample must contain at least one rupee document"


def test_different_seed_differs(cfg: dict[str, Any]) -> None:
    other = {**cfg, "seed": cfg["seed"] + 1}
    assert generate_one(cfg, 3)[1] != generate_one(other, 3)[1]


def test_pdf_has_no_wallclock_metadata(corpus: Corpus) -> None:
    import pymupdf

    with pymupdf.open(stream=corpus[0][1], filetype="pdf") as doc:
        assert "2026" not in (doc.metadata["creationDate"] or "")
        assert "2026" not in (doc.metadata["modDate"] or "")


# ---- 3. per-document independence ----------------------------------------------------------


def test_doc_seed_is_pure_and_distinct() -> None:
    assert doc_seed(1, 5) == doc_seed(1, 5)
    assert len({doc_seed(1, i) for i in range(1000)}) == 1000
    assert doc_seed(1, 5) != doc_seed(2, 5)


def test_document_150_alone_equals_document_150_of_full_run(
    cfg: dict[str, Any], corpus: Corpus
) -> None:
    """Skips documents 0-149 entirely (a fresh call, nothing generated before it)."""
    spec, pdf = generate_one(cfg, 150)
    assert dump_spec(spec) == dump_spec(corpus[150][0])
    assert pdf == corpus[150][1]


@pytest.mark.parametrize("index", [0, 1, 77, 199])
def test_any_document_is_independent_of_generation_order(
    cfg: dict[str, Any], corpus: Corpus, index: int
) -> None:
    for i in (199, 3, 120):  # unrelated documents first, in scrambled order
        generate_one(cfg, i)
    spec, pdf = generate_one(cfg, index)
    assert dump_spec(spec) == dump_spec(corpus[index][0])
    assert pdf == corpus[index][1]


# ---- spec ----------------------------------------------------------------------------------


def test_spec_roundtrip_is_lossless(corpus: Corpus, tmp_path: Path) -> None:
    spec = corpus[7][0]
    path = tmp_path / "s.json"
    path.write_text(dump_spec(spec), encoding="utf-8")
    assert load_spec(path) == spec
    assert dump_spec(load_spec(path)) == dump_spec(spec)
    assert json.loads(dump_spec(spec)) == spec


def test_entities_are_exact_substrings(corpus: Corpus) -> None:
    kinds: Counter[str] = Counter()
    for spec, _ in corpus:
        for b in spec["blocks"]:
            for e in b["entities"]:
                assert b["text"][e["start"] : e["end"]] == e["value"]
                kinds[e["kind"]] += 1
    assert {"AMOUNT", "DATE", "PARTY", "PERCENTAGE", "NUMBER"} <= set(kinds)


def test_block_ids_unique_and_clause_texts_unique(corpus: Corpus) -> None:
    for spec, _ in corpus:
        ids = [b["id"] for b in spec["blocks"]]
        assert len(ids) == len(set(ids))
        texts = [b["text"] for b in spec["blocks"] if b["kind"] == "clause"]
        assert len(texts) == len(set(texts))


def test_contracts_contain_obligation_words(corpus: Corpus) -> None:
    for spec, _ in corpus:
        if spec["doc_type"] in ("lease", "service_agreement", "nda") and spec["page_count"] >= 2:
            body = " ".join(b["text"] for b in spec["blocks"])
            assert " shall " in body and " may " in body


# ---- PDF <-> spec --------------------------------------------------------------------------


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4, 150])
def test_pdf_text_matches_spec(corpus: Corpus, index: int) -> None:
    spec, pdf = corpus[index]
    pages = extract_pages(pdf)
    assert len(pages) == spec["page_count"]
    extracted = _squash(" ".join(b.text for p in pages for b in p.blocks))
    cursor = 0
    for b in spec["blocks"]:  # every block present, in order
        pos = extracted.find(_squash(b["text"]), cursor)
        assert pos >= 0, b["text"]
        cursor = pos


def test_every_pdf_builds_a_tree(corpus: Corpus) -> None:
    roots = set()
    for spec, pdf in corpus:
        tree = build_integrity_tree(pdf)
        assert tree.page_count == spec["page_count"]
        assert sum(len(p.chunks) for p in tree.pages) >= 2
        roots.add(tree.text_root)
    assert len(roots) == len(corpus)


# ---- 2. balance and coverage ---------------------------------------------------------------

TYPE_SHARE_TOLERANCE = 0.10  # relative, around 1/len(doc_types)
MIN_DOCS_PER_BUCKET = 40  # of 200 (20 %); long is contract-only, so its weight is raised
MIN_DOCS_PER_CONTRACT_TYPE_BUCKET = 8


def test_doc_types_are_balanced(cfg: dict[str, Any], corpus: Corpus) -> None:
    counts = Counter(s["doc_type"] for s, _ in corpus)
    ideal = cfg["n_docs"] / len(cfg["doc_types"])
    assert set(counts) == set(cfg["doc_types"])
    for t, c in counts.items():
        assert abs(c - ideal) <= TYPE_SHARE_TOLERANCE * ideal, (t, c)


def test_page_counts_within_spec_range(corpus: Corpus) -> None:
    assert all(1 <= s["page_count"] <= 50 for s, _ in corpus)


def test_page_count_buckets_have_real_coverage(cfg: dict[str, Any], corpus: Corpus) -> None:
    buckets = cfg["page_count"]["params"]["buckets"]
    by_bucket: Counter[str] = Counter(bucket_name(s["page_count"], buckets) for s, _ in corpus)
    for b in buckets:
        assert by_bucket[b["name"]] >= MIN_DOCS_PER_BUCKET, dict(by_bucket)
    assert "out_of_range" not in by_bucket
    # skewed toward short: short is the largest bucket, long the smallest
    assert by_bucket["short"] > by_bucket["medium"] > by_bucket["long"]
    # contracts (the types that can be long) cover every bucket individually
    cross: Counter[tuple[str, str]] = Counter(
        (s["doc_type"], bucket_name(s["page_count"], buckets)) for s, _ in corpus
    )
    for t in ("lease", "service_agreement", "nda"):
        for b in buckets:
            assert cross[(t, b["name"])] >= MIN_DOCS_PER_CONTRACT_TYPE_BUCKET, (t, b["name"])


def test_measured_pages_track_target(corpus: Corpus) -> None:
    assert all(s["target_pages"] - 1 <= s["page_count"] <= s["target_pages"] for s, _ in corpus)
    exact = sum(s["page_count"] == s["target_pages"] for s, _ in corpus)
    assert exact >= 0.95 * len(corpus)


# ---- 4. named page-count function ----------------------------------------------------------


def test_page_count_function_is_named_in_config_and_recorded(
    cfg: dict[str, Any], corpus: Corpus
) -> None:
    assert cfg["page_count"]["function"] in PAGE_COUNT_FUNCTIONS
    assert all(s["page_count_function"] == cfg["page_count"]["function"] for s, _ in corpus)
    assert "params" in cfg["page_count"]


def test_unknown_page_count_function_is_rejected(cfg: dict[str, Any]) -> None:
    bad = {**cfg, "page_count": {**cfg["page_count"], "function": "nope"}}
    with pytest.raises(ValueError, match="nope"):
        generate_one(bad, 0)
