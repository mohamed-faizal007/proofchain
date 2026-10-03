"""Evaluation runner (docs/08 C.3): detection, localization, efficiency, latency, baselines.

    python run_eval.py --config configs/default.yaml

Reads the tamper cases written by ``tamper.py`` (``data/tamper``), scores ``proofchain_core``
against the ground truth recorded there (derived with difflib, independently of ``localize``) and
writes ``results/<run>/``. ``metrics.json`` and the ``detection/localization/efficiency/per_case``
CSVs are deterministic; timings go to ``latency.json`` / ``latency.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.nlp.classifier import ChangeClassifier
from proofchain_core import build_integrity_tree, localize
from proofchain_core.types import IntegrityTree

import baselines
import classification
import efficiency
import latency
import metrics
import nlp_arms
import report
from generate_corpus import generate_one, load_config
from tamper import TamperRun

EVAL_DIR = Path(__file__).resolve().parent
Case = tuple[dict[str, Any], bytes]
SCORE_KEYS = ["tp", "fp", "fn", "precision", "recall", "f1", "macro_f1"]
EFF_KEYS = [
    "n",
    "mean_hash_comparisons",
    "mean_naive",
    "mean_descent",
    "n_descent",
    "fast_path_share",
]


def cases_from_run(run: TamperRun) -> list[Case]:
    return [(c.record, c.pdf) for c in run.cases]


def load_cases(tamper_dir: Path) -> list[Case]:
    manifest = json.loads((tamper_dir / "manifest.json").read_text(encoding="utf-8"))
    return [
        (
            json.loads((tamper_dir / f"{c['case_id']}.json").read_text(encoding="utf-8")),
            (tamper_dir / f"{c['case_id']}.pdf").read_bytes(),
        )
        for c in manifest["cases"]
    ]


def page_bucket(cfg: dict[str, Any], pages: int) -> str:
    """Name of the corpus page-count bucket (configs/default.yaml) a page count falls in."""
    buckets = cfg["page_count"]["params"]["buckets"]
    for b in buckets:
        if b["min"] <= pages <= b["max"]:
            return str(b["name"])
    return str(buckets[-1]["name"]) if pages > buckets[-1]["max"] else str(buckets[0]["name"])


def _ref_tree(
    cfg: dict[str, Any], doc_id: str, corpus_dir: Path | None, cache: dict[str, IntegrityTree]
) -> IntegrityTree:
    if doc_id not in cache:
        pdf = corpus_dir / f"{doc_id}.pdf" if corpus_dir else None
        data = (
            pdf.read_bytes()
            if pdf and pdf.exists()
            else generate_one(cfg, int(doc_id.split("_")[1]))[1]
        )
        cache[doc_id] = build_integrity_tree(data)
    return cache[doc_id]


def _flat(tree: IntegrityTree) -> list[Any]:
    return [c for p in tree.pages for c in p.chunks]


def _counts(truth: set[str], pred: set[str]) -> list[int]:
    return list(metrics.counts(truth, pred))


def _pages(ids: set[str]) -> set[int]:
    return {metrics.page_of(i) for i in ids}


def evaluate_case(
    cfg: dict[str, Any],
    record: dict[str, Any],
    ref: IntegrityTree,
    cand: IntegrityTree,
    classifiers: dict[str, ChangeClassifier] | None = None,
    timings: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    if ref.file_hash != record["ref"]["file_hash"] or cand.file_hash != record["cand"]["file_hash"]:
        raise ValueError(f"stale tamper data for {record['case_id']}: re-run tamper.py")
    truth = record["truth"]
    t_chunk = metrics.tagged(truth["changed_ref_chunk_ids"], truth["changed_cand_chunk_ids"])
    t_page = metrics.tagged(truth["changed_pages_ref"], truth["changed_pages_cand"])

    result = localize(ref, cand)
    a, b = _flat(ref), _flat(cand)
    preds = {
        "localize": (
            {r.ref_chunk_id for r in result.regions if r.ref_chunk_id},
            {r.cand_chunk_id for r in result.regions if r.cand_chunk_id},
            set(result.changed_pages_ref),
            set(result.changed_pages_cand),
        )
    }
    for name, fn in (("positional", baselines.positional), ("plain_diff", baselines.plain_diff)):
        ref_ids, cand_ids = fn(a, b)
        preds[name] = (ref_ids, cand_ids, _pages(ref_ids), _pages(cand_ids))

    row: dict[str, Any] = {
        "case_id": record["case_id"],
        "op": record["op"],
        "mode": record["mode"],
        "doc_type": record["doc_type"],
        "page_bucket": page_bucket(cfg, ref.page_count),
        "expected_status": record["expected_status"],
        "status": result.status.value,
        "file_hash_changed": baselines.whole_file_changed(ref.file_hash, cand.file_hash),
        "text_root_changed": ref.text_root != cand.text_root,
        "chunk": {m: _counts(t_chunk, metrics.tagged(p[0], p[1])) for m, p in preds.items()},
        "page": {m: _counts(t_page, metrics.tagged(p[2], p[3])) for m, p in preds.items()},
        "efficiency": efficiency.case_efficiency(ref, cand, result),
    }
    if classifiers:
        row["classification"] = classification.classify_case(
            record, result.regions, classifiers, timings
        )
    return row


def evaluate_cases(
    cfg: dict[str, Any],
    cases: Iterable[Case],
    corpus_dir: Path | None = None,
    classifiers: dict[str, ChangeClassifier] | None = None,
    timings: dict[str, list[float]] | None = None,
) -> list[dict[str, Any]]:
    cache: dict[str, IntegrityTree] = {}
    return [
        evaluate_case(
            cfg,
            record,
            _ref_tree(cfg, record["base_doc_id"], corpus_dir, cache),
            build_integrity_tree(pdf),
            classifiers,
            timings,
        )
        for record, pdf in cases
    ]


def build_metrics(cfg: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda r: r["case_id"])
    return {
        "n_cases": len(rows),
        "seed": cfg["seed"],
        "tamper_seed": cfg["tamper"]["seed"],
        "detection": metrics.detection_table(rows),
        "baselines": metrics.BASELINES,
        "localization": metrics.localization_table(rows),
        "efficiency": metrics.efficiency_table(rows),
    }


def _write_csv(path: Path, header: list[str], lines: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(lines)


def _localization_lines(table: dict[str, Any]) -> list[list[Any]]:
    lines: list[list[Any]] = []
    for group in sorted(table):
        for key, score in [("all", table[group])] if group == "overall" else table[group].items():
            for level in ("chunk", "page"):
                for m in metrics.METHODS:
                    s = score[level][m]
                    lines.append(
                        [group, key, level, m, score["n"]]
                        + [
                            s[k]
                            for k in ("tp", "fp", "fn", "precision", "recall", "f1", "macro_f1")
                        ]
                        + [s.get("caveat", "")]
                    )
    return lines


def _efficiency_lines(table: dict[str, Any]) -> list[list[Any]]:
    keys = [
        "n",
        "mean_hash_comparisons",
        "mean_naive",
        "mean_descent",
        "n_descent",
        "fast_path_share",
    ]
    lines = [["overall", "all"] + [table["overall"][k] for k in keys]]
    for group in ("by_page_bucket", "by_page_count"):
        lines += [[group, k] + [v[k] for k in keys] for k, v in table[group].items()]
    return lines


def write_results(
    out: Path, result: dict[str, Any], rows: list[dict[str, Any]], timings: list[dict[str, Any]]
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(metrics.dumps(result), encoding="utf-8")
    det = result["detection"]
    _write_csv(
        out / "detection.csv",
        ["group", "metric", "value"],
        [[g, k, v] for g in sorted(det) for k, v in det[g].items()],
    )
    _write_csv(
        out / "localization.csv",
        [
            "group",
            "key",
            "level",
            "method",
            "n",
            "tp",
            "fp",
            "fn",
            "precision",
            "recall",
            "f1",
            "macro_f1",
            "caveat",
        ],
        _localization_lines(result["localization"]),
    )
    _write_csv(
        out / "efficiency.csv",
        [
            "group",
            "key",
            "n",
            "mean_hash_comparisons",
            "mean_naive",
            "mean_descent",
            "n_descent",
            "fast_path_share",
        ],
        _efficiency_lines(result["efficiency"]),
    )
    _write_csv(
        out / "per_case.csv",
        [
            "case_id",
            "op",
            "mode",
            "doc_type",
            "page_bucket",
            "status",
            "chunk_tp",
            "chunk_fp",
            "chunk_fn",
        ],
        [
            [r["case_id"], r["op"], r["mode"], r["doc_type"], r["page_bucket"], r["status"]]
            + r["chunk"]["localize"]
            for r in sorted(rows, key=lambda r: r["case_id"])
        ],
    )
    (out / "latency.json").write_text(metrics.dumps(timings), encoding="utf-8")
    cols = [
        "target_pages",
        "page_count",
        "chunks",
        "repeats",
        "build_tree_ms",
        "localize_ms",
        "verify_ms",
        "file_hash_ms",
        "plain_diff_ms",
    ]
    _write_csv(out / "latency.csv", cols, [[t[c] for c in cols] for t in timings])


def run(
    cfg: dict[str, Any],
    cases: list[Case],
    out: Path,
    pages: list[int] | None = None,
    repeats: int | None = None,
    corpus_dir: Path | None = None,
    classifiers: dict[str, ChangeClassifier] | None = None,
) -> dict[str, Any]:
    lat = cfg["eval"]["latency"]
    nlp_timings: dict[str, list[float]] = {}
    rows = evaluate_cases(cfg, cases, corpus_dir, classifiers, nlp_timings)
    result = build_metrics(cfg, rows)
    timings = latency.measure(cfg, pages or lat["pages"], repeats or int(lat["repeats"]))
    write_results(out, result, rows, timings)
    if classifiers:
        scored = classification.score([r["classification"] for r in rows], list(classifiers))
        classification.write(
            out,
            scored,
            [r["classification"] for r in rows],
            classification.latency_summary(nlp_timings),
            nlp_arms.environment(),
        )
        result["classification"] = scored
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=EVAL_DIR / "configs" / "default.yaml")
    ap.add_argument("--seed", type=int, help="override seed (synthetic latency documents)")
    ap.add_argument("--tamper-dir", type=Path, help="override tamper.out_dir")
    ap.add_argument("--corpus-dir", type=Path, help="override corpus_dir (else regenerate refs)")
    ap.add_argument("--out", type=Path, help="override results/<run-name>")
    ap.add_argument("--run-name", help="results sub-directory (default seed<seed>)")
    ap.add_argument(
        "--no-classification",
        action="store_true",
        help="skip the P9-04 classification ablation (needs the [nlp] extras and models)",
    )
    ap.add_argument(
        "--report",
        action="store_true",
        help="after the run, write figures/ and REPORT.md (report.py; offline)",
    )
    ap.add_argument("--measurements-dir", type=Path, help="chain measurements for --report")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.seed is not None:
        cfg["seed"] = args.seed
    tamper_dir = args.tamper_dir or EVAL_DIR / cfg["tamper"]["out_dir"]
    if not (tamper_dir / "manifest.json").exists():
        print(f"no tamper cases in {tamper_dir}; run tamper.py first", file=sys.stderr)
        return 1
    corpus_dir = args.corpus_dir or EVAL_DIR / cfg["corpus_dir"]
    name = args.run_name or f"seed{cfg['seed']}"
    out = args.out or EVAL_DIR / cfg["eval"]["out_dir"] / name
    try:
        arms = None if args.no_classification else nlp_arms.build_arms()
    except nlp_arms.ArmUnavailable as exc:
        print(f"{exc} (or pass --no-classification)", file=sys.stderr)
        return 2
    result = run(cfg, load_cases(tamper_dir), out, corpus_dir=corpus_dir, classifiers=arms)
    d, loc = result["detection"], result["localization"]["overall"]["chunk"]["localize"]
    if args.report:
        meas = args.measurements_dir or EVAL_DIR / cfg["chain"]["measurements_dir"] / name
        print(f"report -> {report.build(out, meas)}")
    print(f"{result['n_cases']} cases -> {out}")
    print(
        f"text-root detection {d['content_changing']['text_root_detection_rate']:.0%}, "
        f"metadata-only FP {d['metadata_only']['text_root_false_positive_rate']:.0%}, "
        f"chunk F1 {loc['f1']:.3f}"
    )
    for arm, a in result.get("classification", {}).get("arms", {}).items():
        print(f"classification {arm}: macro-F1 {a['macro_f1']:.3f}, accuracy {a['accuracy']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
