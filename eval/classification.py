"""Classification evaluation against the tamper ground truth (docs/06 Evaluation, docs/08 C.3).

What "correct" means. ``localize`` returns regions; each region is matched to the tamper edit whose
before/after text it carries (exact equality after the docs/02 s3 canonicalization), and that edit's
category is the region's expected label.

* strict (headline): ``primary_category == expected``; per-category P/R/F1, macro-F1, confusion
  matrix. Macro-F1 averages the categories that have support (at least one expected label).
* lenient (reported alongside, never mixed in): ``expected in categories``.
* a region that matches no edit, or edits that conflict, is counted (``unmatched`` /
  ``ambiguous``) and scored as a false positive for its predicted category (truth ``NONE``); an
  edit that no region matches is a ``missed_edit``, a false negative (prediction ``NONE``).
  Cases whose region count differs from the edit count are counted in ``region_count_mismatch``.
* CONTENT_EQUIVALENT (metadata-only) cases have no regions; they are excluded and counted.

``score`` is order-independent and ``dumps`` is stable, so ``classification.json`` reproduces byte
for byte. Timings and library versions go to their own files.
"""

from __future__ import annotations

import csv
import math
import statistics
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.nlp.classifier import ChangeClassifier
from app.nlp.types import Category
from proofchain_core.canonical import normalize_text
from proofchain_core.types import ChangeRegion, RegionType

import metrics

CATEGORIES = [c.value for c in Category]
NONE = "NONE"
LABELS = [*CATEGORIES, NONE]
_KIND = {
    RegionType.MODIFIED: "replace",
    RegionType.INSERTED: "insert",
    RegionType.DELETED: "delete",
}


def dumps(obj: Any) -> str:
    return metrics.dumps(obj)


def _norm(text: str | None) -> str | None:
    return None if text is None else normalize_text(text)


def match_region(
    region: ChangeRegion, edits: list[dict[str, Any]]
) -> tuple[str, str | None, list[int]]:
    """(status, category, edit indexes) of the edits a region carries.

    ``matched``: every candidate edit has the same category; ``ambiguous``: candidates disagree;
    ``unmatched``: none.
    """
    kind = _KIND[region.type]
    ref, cand = region.ref_text, region.cand_text
    hits = [
        i
        for i, e in enumerate(edits)
        if e["kind"] == kind
        and (kind == "insert" or _norm(e["before"]) == ref)
        and (kind == "delete" or _norm(e["after"]) == cand)
    ]
    if not hits:
        return "unmatched", None, []
    cats = {edits[i]["category"] for i in hits}
    if len(cats) > 1:
        return "ambiguous", None, hits
    return "matched", cats.pop(), hits


def classify_case(
    record: dict[str, Any],
    regions: Iterable[ChangeRegion],
    classifiers: dict[str, ChangeClassifier],
    timings: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    edits = record["edits"]
    covered: set[int] = set()
    out_regions: list[dict[str, Any]] = []
    for region in regions:
        status, category, idx = match_region(region, edits)
        covered.update(idx)
        arms: dict[str, Any] = {}
        for arm, clf in classifiers.items():
            t0 = time.perf_counter()
            analysis = clf.analyze(region)
            if timings is not None:
                timings.setdefault(arm, []).append((time.perf_counter() - t0) * 1000)
            arms[arm] = {
                "primary": analysis.primary_category.value,
                "categories": [c.value for c in analysis.categories],
                "method": analysis.method,
            }
        out_regions.append({"expected": category, "match": status, "arms": arms})
    return {
        "case_id": record["case_id"],
        "op": record["op"],
        "mode": record["mode"],
        "expected_status": record["expected_status"],
        "expected": sorted(record["expected_categories"]),
        "n_edits": len(edits),
        "n_regions": len(out_regions),
        "regions": out_regions,
        "missed_edits": sorted(e["category"] for i, e in enumerate(edits) if i not in covered),
    }


def latency_summary(timings: dict[str, list[float]]) -> dict[str, Any]:
    return {
        arm: {
            "n": len(v),
            "median_ms": round(statistics.median(v), 3),
            "mean_ms": round(math.fsum(v) / len(v), 3),
        }
        for arm, v in sorted(timings.items())
        if v
    }


def _matching(cases: list[dict[str, Any]], excluded: int) -> dict[str, Any]:
    regions = [x for c in cases for x in c["regions"]]
    mismatch = Counter(c["op"] for c in cases if c["n_regions"] != c["n_edits"])
    return {
        "n_cases": len(cases),
        "excluded_content_equivalent": excluded,
        "n_edits": sum(c["n_edits"] for c in cases),
        "n_regions": len(regions),
        "matched": sum(x["match"] == "matched" for x in regions),
        "unmatched": sum(x["match"] == "unmatched" for x in regions),
        "ambiguous": sum(x["match"] == "ambiguous" for x in regions),
        "missed_edits": sum(len(c["missed_edits"]) for c in cases),
        "region_count_mismatch": {
            "total": sum(mismatch.values()),
            "by_op": dict(sorted(mismatch.items())),
        },
    }


def _units(cases: list[dict[str, Any]], arm: str) -> list[tuple[str, str, bool, str]]:
    """(truth, primary, lenient hit, mode) per scored unit; NONE marks the missing side."""
    units: list[tuple[str, str, bool, str]] = []
    for c in cases:
        for x in c["regions"]:
            p = x["arms"][arm]
            truth = x["expected"] if x["match"] == "matched" and x["expected"] else NONE
            units.append((truth, p["primary"], truth in p["categories"], c["mode"]))
        units += [(cat, NONE, False, c["mode"]) for cat in c["missed_edits"]]
    return units


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def _document_level(cases: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    def one(group: list[dict[str, Any]]) -> dict[str, Any]:
        pred = [{x["arms"][arm]["primary"] for x in c["regions"]} for c in group]
        exp = [set(c["expected"]) for c in group]
        jac = [_jaccard(p, e) for p, e in zip(pred, exp, strict=True)]
        return {
            "n": len(group),
            "exact_match": metrics.rate([p == e for p, e in zip(pred, exp, strict=True)]),
            "mean_jaccard": round(math.fsum(jac) / len(jac), metrics.ROUND) if jac else 0.0,
        }

    return {**one(cases), "multi_edit": one([c for c in cases if c["op"] == "multi_edit"])}


def _score_arm(cases: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    units = _units(cases, arm)
    confusion = {t: dict.fromkeys(LABELS, 0) for t in LABELS}
    for truth, pred, _, _ in units:
        confusion[truth][pred] += 1
    per_category: dict[str, Any] = {}
    f1s: list[float] = []
    for cat in CATEGORIES:
        tp = confusion[cat][cat]
        fn = sum(v for p, v in confusion[cat].items() if p != cat)
        fp = sum(confusion[t][cat] for t in LABELS if t != cat)
        entry = {"support": tp + fn, "tp": tp, "fp": fp, "fn": fn, **metrics.prf(tp, fp, fn)}
        hits = sum(1 for t, _, lenient, _ in units if t == cat and lenient)
        entry["lenient_recall"] = round(hits / (tp + fn), metrics.ROUND) if tp + fn else 0.0
        per_category[cat] = entry
        if tp + fn:
            f1s.append(entry["f1"])
    truthy = [u for u in units if u[0] != NONE]
    by_mode = {
        m: {
            "n": len(g),
            "accuracy": metrics.rate([t == p for t, p, _, _ in g]),
            "lenient_accuracy": metrics.rate([lenient for _, _, lenient, _ in g]),
        }
        for m in sorted({u[3] for u in truthy})
        for g in [[u for u in truthy if u[3] == m]]
    }
    methods = Counter(x["arms"][arm]["method"] for c in cases for x in c["regions"])
    return {
        "per_category": per_category,
        "macro_f1": round(math.fsum(f1s) / len(f1s), metrics.ROUND) if f1s else 0.0,
        "accuracy": metrics.rate([t == p for t, p, _, _ in truthy]),
        "lenient_accuracy": metrics.rate([lenient for _, _, lenient, _ in truthy]),
        "confusion": confusion,
        "by_mode": by_mode,
        "document_level": _document_level(cases, arm),
        "methods": dict(sorted(methods.items())),
    }


def score(case_results: list[dict[str, Any]], arms: list[str]) -> dict[str, Any]:
    ordered = sorted(case_results, key=lambda c: c["case_id"])
    changed = [c for c in ordered if c["expected_status"] == "CHANGED"]
    return {
        "categories": CATEGORIES,
        "matching": _matching(changed, len(ordered) - len(changed)),
        "arms": {arm: _score_arm(changed, arm) for arm in arms},
    }


def _write_csv(path: Path, header: list[str], lines: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(lines)


def write(
    out: Path,
    result: dict[str, Any],
    case_results: list[dict[str, Any]],
    latency: dict[str, Any],
    env: dict[str, str],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "classification.json").write_text(dumps(result), encoding="utf-8")
    (out / "classification_latency.json").write_text(dumps(latency), encoding="utf-8")
    (out / "classification_env.json").write_text(dumps(env), encoding="utf-8")
    keys = ["support", "tp", "fp", "fn", "precision", "recall", "f1", "lenient_recall"]
    lines: list[list[Any]] = []
    for arm, a in result["arms"].items():
        lines += [[arm, c, *(a["per_category"][c][k] for k in keys)] for c in CATEGORIES]
        lines.append([arm, "MACRO", "", "", "", "", "", "", a["macro_f1"], ""])
    _write_csv(out / "classification.csv", ["arm", "category", *keys], lines)
    for arm, a in result["arms"].items():
        _write_csv(
            out / f"confusion_{arm}.csv",
            ["expected\\predicted", *LABELS],
            [[t, *(a["confusion"][t][p] for p in LABELS)] for t in LABELS],
        )
    rows = [
        [c["case_id"], arm, c["op"], c["mode"], x["match"], x["expected"] or NONE,
         p["primary"], "|".join(p["categories"]), p["method"]]
        for c in sorted(case_results, key=lambda c: c["case_id"])
        for x in c["regions"]
        for arm, p in x["arms"].items()
    ]  # fmt: skip
    _write_csv(
        out / "classification_regions.csv",
        ["case_id", "arm", "op", "mode", "match", "expected", "primary", "categories", "method"],
        rows,
    )
