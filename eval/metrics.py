"""Pure scoring and aggregation for the evaluation (docs/08 C.3).

Everything here is order-independent: micro-averages sum integer counts, means use ``math.fsum``
(correctly rounded, hence independent of summation order), groups are emitted with sorted keys, and
``dumps`` writes a stable JSON text. The aggregate therefore reproduces byte for byte whatever order
the cases were evaluated in.

Chunk ids are positional (``p{page}-c{index}``), so the same id names different chunks in the
reference and the candidate tree. Sets that mix both trees are therefore *tagged*
(``ref:`` / ``cand:``).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

METHODS = ("localize", "positional", "plain_diff")

# Attached to every reported plain-diff result (metrics.json, localization.csv) so a figure or
# table built from those numbers cannot drop it.
PLAIN_DIFF_CAVEAT = (
    "Plain diff scores this high only because it is handed the stored reference text directly, "
    "with no verification that the reference itself is authentic. It has no tamper-evidence "
    "property: it cannot detect that the reference was substituted or corrupted, which is the "
    "problem the anchored Merkle root and the verification pipeline exist to solve."
)
BASELINES: dict[str, dict[str, Any]] = {
    "whole_file": {"tamper_evident": True, "localizes": False},
    "positional": {"tamper_evident": True, "localizes": True},
    "plain_diff": {
        "tamper_evident": False,
        "localizes": True,
        "requires_trusted_reference_text": True,
        "caveat": PLAIN_DIFF_CAVEAT,
    },
}
ROUND = 6


def page_of(chunk_id: str) -> int:
    """Page index of a chunk id ``p{page}-c{index}``."""
    return int(chunk_id[1 : chunk_id.index("-")])


def tagged(ref_ids: Iterable[Any], cand_ids: Iterable[Any]) -> set[str]:
    return {f"ref:{i}" for i in ref_ids} | {f"cand:{i}" for i in cand_ids}


def counts(truth: set[str], pred: set[str]) -> tuple[int, int, int]:
    """(tp, fp, fn) of a predicted set against the truth set."""
    tp = len(truth & pred)
    return tp, len(pred) - tp, len(truth) - tp


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    """Precision, recall, F1. Nothing predicted and nothing to find counts as a perfect 1.0."""
    if tp + fp + fn == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn)
    return {
        "precision": round(precision, ROUND),
        "recall": round(recall, ROUND),
        "f1": round(f1, ROUND),
    }


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def rate(flags: list[bool]) -> float:
    return round(sum(flags) / len(flags), ROUND) if flags else 0.0


def mean(values: list[int]) -> float:
    return round(math.fsum(values) / len(values), 4) if values else 0.0


def _group(
    rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return {k: groups[k] for k in sorted(groups)}


def _score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows)}
    for level in ("chunk", "page"):
        per_method: dict[str, Any] = {}
        for m in METHODS:
            tp, fp, fn = (sum(r[level][m][i] for r in rows) for i in range(3))
            entry: dict[str, Any] = {"tp": tp, "fp": fp, "fn": fn, **prf(tp, fp, fn)}
            entry["macro_f1"] = round(
                math.fsum(prf(*r[level][m])["f1"] for r in rows) / len(rows), ROUND
            )
            if m == "plain_diff":
                entry["caveat"] = PLAIN_DIFF_CAVEAT
            per_method[m] = entry
        out[level] = per_method
    return out


def localization_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Micro-averaged P/R/F1 at chunk and page level, overall and split by op, mode, etc.

    Only content-changing cases are scored; CONTENT_EQUIVALENT cases have no regions to find and
    are covered by ``detection_table``.
    """
    changed = [r for r in rows if r["expected_status"] == "CHANGED"]
    return {
        "overall": _score(changed),
        "by_op": {k: _score(v) for k, v in _group(changed, lambda r: r["op"]).items()},
        "by_mode": {k: _score(v) for k, v in _group(changed, lambda r: r["mode"]).items()},
        "by_op_mode": {
            k: _score(v) for k, v in _group(changed, lambda r: f"{r['op']}/{r['mode']}").items()
        },
        "by_doc_type": {k: _score(v) for k, v in _group(changed, lambda r: r["doc_type"]).items()},
        "by_page_bucket": {
            k: _score(v) for k, v in _group(changed, lambda r: r["page_bucket"]).items()
        },
    }


def detection_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    changed = [r for r in rows if r["expected_status"] == "CHANGED"]
    same = [r for r in rows if r["expected_status"] == "CONTENT_EQUIVALENT"]
    return {
        "content_changing": {
            "n": len(changed),
            "file_hash_detection_rate": rate([r["file_hash_changed"] for r in changed]),
            "text_root_detection_rate": rate([r["text_root_changed"] for r in changed]),
            "localize_status_changed_rate": rate([r["status"] == "CHANGED" for r in changed]),
        },
        "metadata_only": {
            "n": len(same),
            "text_root_false_positive_rate": rate([r["text_root_changed"] for r in same]),
            "localize_false_positive_rate": rate([r["status"] == "CHANGED" for r in same]),
            "whole_file_false_positive_rate": rate([r["file_hash_changed"] for r in same]),
        },
    }


def _efficiency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eff = [r["efficiency"] for r in rows]
    descent = [e["descent"] for e in eff if e["descent"] is not None]
    return {
        "n": len(rows),
        "mean_hash_comparisons": mean([e["hash_comparisons"] for e in eff]),
        "mean_naive": mean([e["naive"] for e in eff]),
        "mean_descent": mean(descent),
        "n_descent": len(descent),
        "fast_path_share": rate([e["method"] == "MERKLE_FAST_PATH" for e in eff]),
    }


def efficiency_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Hash comparisons of localize (and of a page-level descent) against a naive full compare."""
    changed = [r for r in rows if r["expected_status"] == "CHANGED"]
    return {
        "overall": _efficiency(changed),
        "by_page_bucket": {
            k: _efficiency(v) for k, v in _group(changed, lambda r: r["page_bucket"]).items()
        },
        "by_page_count": {
            k: _efficiency(v)
            for k, v in _group(changed, lambda r: f"{r['efficiency']['page_count']:03d}").items()
        },
    }
