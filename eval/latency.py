"""Latency vs page count (docs/08 C.3): median of N runs on synthetic lease documents.

The corpus tops out at 49 pages, so the 50- and 100-page points use documents built with the
corpus generator's own ``build_spec`` (a config copy whose page-count bucket is pinned to the
size) and a candidate that differs by one amended clause. Timings are the only non-deterministic
output of the evaluation and are kept out of ``metrics.json``.
"""

from __future__ import annotations

import copy
import hashlib
import statistics
import time
from collections.abc import Callable
from typing import Any

from proofchain_core import build_integrity_tree, localize

import baselines
from generate_corpus import build_spec
from render import render_pdf


def time_median(fn: Callable[[], object], repeats: int) -> float:
    """Median wall time of ``fn`` over ``repeats`` runs, in milliseconds."""
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - start)
    return round(statistics.median(samples) / 1e6, 3)


def _size_cfg(cfg: dict[str, Any], pages: int) -> dict[str, Any]:
    c = copy.deepcopy(cfg)
    c["doc_types"] = ["lease"]
    c["type_max_pages"] = {"lease": pages}
    c["page_count"] = {
        "function": "bucketed_skewed",
        "params": {"buckets": [{"name": "fixed", "min": pages, "max": pages, "weight": 1}]},
    }
    return c


def _amended(spec: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(spec)
    clauses = [b for b in out["blocks"] if b["kind"] == "clause"]
    clauses[len(clauses) // 2]["text"] += " This clause has been amended by the parties."
    return out


def measure(cfg: dict[str, Any], pages: list[int], repeats: int) -> list[dict[str, Any]]:
    return [_measure_one(cfg, n, repeats) for n in pages]


def _measure_one(cfg: dict[str, Any], n: int, repeats: int) -> dict[str, Any]:
    spec = build_spec(_size_cfg(cfg, n), 0)
    cand_pdf = render_pdf(_amended(spec))
    ref = build_integrity_tree(render_pdf(spec))
    cand = build_integrity_tree(cand_pdf)
    ref_chunks = [c for p in ref.pages for c in p.chunks]
    cand_chunks = [c for p in cand.pages for c in p.chunks]

    return {
        "target_pages": n,
        "page_count": ref.page_count,
        "chunks": len(ref_chunks),
        "repeats": repeats,
        "build_tree_ms": time_median(lambda: build_integrity_tree(cand_pdf), repeats),
        "localize_ms": time_median(lambda: localize(ref, cand), repeats),
        "verify_ms": time_median(lambda: localize(ref, build_integrity_tree(cand_pdf)), repeats),
        "file_hash_ms": time_median(lambda: hashlib.sha256(cand_pdf).hexdigest(), repeats),
        "plain_diff_ms": time_median(
            lambda: baselines.plain_diff(ref_chunks, cand_chunks), repeats
        ),
    }
