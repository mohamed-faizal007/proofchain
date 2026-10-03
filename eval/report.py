"""REPORT.md and figures from a results directory (docs/08 C.3). Offline; every number is read
from a result file, none is typed here.

    python report.py --results results/seed20260930 [--measurements measurements/seed20260930]

Required: ``metrics.json`` and ``latency.csv``. Optional: ``classification.json`` / ``.csv`` and the
chain measurement files (``chain_sepolia.json``, ``chain_local.json``, ``chain_prices.json``) in
the measurements directory; a missing optional input gives a "not run" section, not an error.
The output is byte-identical for identical inputs (no clock, no randomness).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import figures
import metrics
import report_chain
from report_fmt import fig, pct, table

METHOD_NAMES = {
    "localize": "ProofChain localize",
    "positional": "positional (no alignment)",
    "plain_diff": "plain diff (see caveat)",
}


class ReportInputError(Exception):
    """A required input file is missing."""


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _detection(m: dict[str, Any]) -> str:
    c, o = m["detection"]["content_changing"], m["detection"]["metadata_only"]
    rows = [
        ["file hash detection (content-changing)", c["file_hash_detection_rate"], c["n"]],
        ["text root detection (content-changing)", c["text_root_detection_rate"], c["n"]],
        ["status changed (content-changing)", c["localize_status_changed_rate"], c["n"]],
        ["text root false positive (metadata-only)", o["text_root_false_positive_rate"], o["n"]],
        ["localize false positive (metadata-only)", o["localize_false_positive_rate"], o["n"]],
        ["whole-file false positive (metadata-only)", o["whole_file_false_positive_rate"], o["n"]],
    ]
    rows = [[name, pct(rate), n] for name, rate, n in rows]
    return (
        "## Detection\n\n"
        + table(["metric", "rate", "cases"], rows)
        + "\n\nA whole-file hash flags every metadata-only re-save as a change; "
        "the text Merkle root does not."
    )


def _localization(m: dict[str, Any]) -> str:
    overall = m["localization"]["overall"]
    parts = ["## Localization\n", f"Content-changing cases scored: {overall['n']}.\n"]
    for level in ("chunk", "page"):
        rows = []
        for key, name in METHOD_NAMES.items():
            s = overall[level][key]
            rows.append(
                [name]
                + [f"{s[k]:.3f}" for k in ("precision", "recall", "f1")]
                + [s["tp"], s["fp"], s["fn"]]
            )
        header = ["method", "precision", "recall", "F1", "TP", "FP", "FN"]
        parts.append(f"**{level} level**\n\n" + table(header, rows) + "\n")
    parts.append(f"> **Plain diff caveat.** {metrics.PLAIN_DIFF_CAVEAT}\n")
    return "\n".join(parts) + "\n" + fig(["localization"])


def _efficiency(m: dict[str, Any]) -> str:
    e = m["efficiency"]
    groups = [*e["by_page_bucket"].items(), ("all", e["overall"])]
    rows = [
        [
            k,
            v["n"],
            f"{v['mean_naive']:.1f}",
            f"{v['mean_hash_comparisons']:.1f}",
            f"{v['mean_descent']:.1f}",
            pct(v["fast_path_share"]),
        ]
        for k, v in groups
    ]
    header = ["page bucket", "cases", "naive", "Merkle (total)", "descent only", "fast-path share"]
    return (
        "## Merkle efficiency\n\nMean hash comparisons per case: naive full chunk scan vs the "
        "Merkle fast path plus descent. On small documents the Merkle count can match or exceed "
        "the naive scan; the saving appears as documents grow.\n\n"
        + table(header, rows)
        + "\n\n"
        + fig(["efficiency"])
    )


def _latency(rows: list[dict[str, str]]) -> str:
    cols = ["page_count", "chunks", "repeats", "build_tree_ms", "localize_ms", "verify_ms"]
    cols += ["file_hash_ms", "plain_diff_ms"]
    header = ["pages", "chunks", "repeats", "build tree", "localize", "verify", "file hash"]
    header += ["plain diff"]
    return (
        "## Latency\n\nMedian wall time in ms on synthetic lease documents, one machine, one run: "
        "indicative, not a benchmark.\n\n"
        + table(header, [[r[c] for c in cols] for r in rows])
        + "\n\n"
        + fig(["latency"])
    )


def _classification(results: Path) -> str:
    if not (results / "classification.json").exists():
        return (
            "## Classification\n\nnot run (no `classification.json`; run `run_eval.py` "
            "without `--no-classification`)."
        )
    c = _json(results / "classification.json")
    arms, mt = c["arms"], c["matching"]
    rows = [
        [a]
        + [f"{v[k]:.3f}" for k in ("macro_f1", "accuracy", "lenient_accuracy")]
        + [f"{v['document_level']['exact_match']:.3f}"]
        for a, v in arms.items()
    ]
    header = ["arm", "macro-F1", "accuracy", "lenient accuracy", "document exact match"]
    text = (
        "## Classification\n\nStrict scoring (primary category equals the tamper edit's "
        "category) is the headline; lenient accuracy is alongside.\n\n"
        + table(header, rows)
        + f"\n\nRegion-to-edit matching: {mt['matched']} of {mt['n_regions']} regions matched "
        f"to {mt['n_edits']} edits, {mt['unmatched']} unmatched, {mt['ambiguous']} ambiguous, "
        f"{mt['missed_edits']} edits missed, {mt['excluded_content_equivalent']} metadata-only "
        "cases excluded.\n"
    )
    both = {"rules_ner", "rules_ner_emb"} <= set(arms)
    if both and arms["rules_ner_emb"]["macro_f1"] < arms["rules_ner"]["macro_f1"]:
        text += (
            "\nAdding embeddings to rules + NER lowered macro-F1 on this corpus; "
            "thresholds were not tuned.\n"
        )
    cat = _csv(results / "classification.csv")
    names = list(arms)
    cats = [r["category"] for r in cat if r["arm"] == names[0]]
    f1 = {(r["arm"], r["category"]): float(r["f1"]) for r in cat}
    support = {r["category"]: r["support"] for r in cat if r["arm"] == names[0]}
    cat_rows = [[k, support[k]] + [f"{f1[(a, k)]:.3f}" for a in names] for k in cats]
    figures.classification(cat, results / "figures")
    cat_header = ["category", "support"] + [f"F1 {a}" for a in names]
    return text + "\n" + table(cat_header, cat_rows) + "\n\n" + fig(["classification"])


def build(results: Path, measurements: Path | None) -> Path:
    for name in ("metrics.json", "latency.csv"):
        if not (results / name).exists():
            raise ReportInputError(f"missing required input {results / name}")
    m = _json(results / "metrics.json")
    lat = _csv(results / "latency.csv")
    figs = results / "figures"
    figures.efficiency(m["efficiency"]["by_page_count"], figs)
    figures.latency(lat, figs)
    figures.localization(m["localization"]["overall"]["chunk"], figs)

    head = (
        f"# ProofChain evaluation report\n\nSeed {m['seed']} (tamper seed {m['tamper_seed']}); "
        f"{m['n_cases']} tamper cases. Generated by `report.py` from the result files in this "
        "directory; no value is typed by hand.\n"
    )
    sections = [
        head,
        _detection(m),
        _localization(m),
        _efficiency(m),
        _latency(lat),
        _classification(results),
        report_chain.section(measurements, results),
    ]
    path = results / "REPORT.md"
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--measurements", type=Path)
    args = ap.parse_args(argv)
    try:
        print(build(args.results, args.measurements))
    except ReportInputError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
