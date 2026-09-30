"""Generate tamper cases with ground truth (docs/08 C.2).

Usage (from eval/):  python tamper.py --config configs/default.yaml [--seed N] [--out DIR]
                     [--corpus-dir DIR] [--limit N] [--ops OP ...]

Writes ``{out}/{case_id}.pdf`` + ``{case_id}.json`` per case and ``manifest.json`` (all cases,
counts, in-place attempt statistics). Every case is a pure function of (config, tamper seed, op,
mode, attempt): its own RNG and Faker, no shared state, so cases are reproducible one by one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from proofchain_core import build_integrity_tree
from proofchain_core.types import IntegrityTree

from generate_corpus import generate_one, load_config
from ground_truth import derive_truth, tree_summary
from inplace import RESAVE_VARIANTS, InPlaceSkip, apply_inplace, resave_metadata
from render import render_pdf
from spec_edit import apply_edits
from tamper_ops import OPS, make_context

EVAL_DIR = Path(__file__).resolve().parent


@dataclass
class BaseDoc:
    spec: dict[str, Any]
    pdf: bytes
    tree: IntegrityTree


class CorpusSource:
    """Base documents by index: read from ``corpus_dir`` when present, else generated."""

    def __init__(self, cfg: dict[str, Any], corpus_dir: Path | None = None) -> None:
        self.cfg = cfg
        self.corpus_dir = corpus_dir
        self._cache: dict[int, BaseDoc] = {}

    def get(self, index: int) -> BaseDoc:
        if index not in self._cache:
            spec, pdf = generate_one(self.cfg, index)
            if self.corpus_dir is not None:
                on_disk = self.corpus_dir / f"{spec['doc_id']}.pdf"
                if on_disk.exists() and on_disk.read_bytes() != pdf:
                    raise RuntimeError(f"{on_disk} differs from the deterministic generator output")
            self._cache[index] = BaseDoc(spec, pdf, build_integrity_tree(pdf))
        return self._cache[index]


@dataclass
class TamperCase:
    case_id: str
    op: str
    mode: str
    pdf: bytes
    record: dict[str, Any]
    spec_before: dict[str, Any]
    spec_after: dict[str, Any]


@dataclass
class CaseResult:
    case: TamperCase | None
    skip: str | None = None


@dataclass
class TamperRun:
    cases: list[TamperCase] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def case_seed(seed: int, op: str, mode: str, attempt: int) -> int:
    digest = hashlib.sha256(f"proofchain-tamper:{seed}:{op}:{mode}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _multi_range(tcfg: dict[str, Any]) -> tuple[int, int]:
    r = tcfg.get("multi_edit_ops", {"min": 2, "max": 5})
    return int(r["min"]), int(r["max"])


def build_case(
    cfg: dict[str, Any],
    source: CorpusSource | None,
    op: str,
    mode: str,
    attempt: int,
    case_no: int | None = None,
) -> CaseResult:
    """One attempt: pick a base document the op applies to, tamper it, derive ground truth."""
    tcfg = cfg["tamper"]
    source = source or CorpusSource(cfg)
    seed = case_seed(int(tcfg["seed"]), op, mode, attempt)
    start = random.Random(seed).randrange(int(cfg["n_docs"]))
    tries = (
        int(tcfg.get("inplace_party_candidates", 1))
        if (op, mode) == ("party_change", "inplace")
        else 1
    )
    for probe in range(int(cfg["n_docs"])):
        index = (start + probe) % int(cfg["n_docs"])
        base = source.get(index)
        last_skip = ""
        for k in range(tries):
            ctx = make_context(base.spec["doc_type"], seed + k, _multi_range(tcfg))
            edits = OPS[op].plan(base.spec, ctx)
            if edits is None:
                break
            spec_after = apply_edits(base.spec, edits)
            if mode == "rerender":
                pdf = render_pdf(spec_after)
            elif mode == "resave":
                pdf = resave_metadata(base.pdf, random.Random(seed).randrange(RESAVE_VARIANTS))
            else:
                try:
                    pdf = apply_inplace(base.pdf, base.spec, edits)
                except InPlaceSkip as skip:
                    last_skip = skip.reason
                    continue
            no = attempt if case_no is None else case_no
            return CaseResult(
                _finish(op, mode, f"{op}-{mode}-{no:03d}", seed, base, edits, spec_after, pdf, k)
            )
        if last_skip:
            return CaseResult(None, last_skip)
    return CaseResult(None, "no_applicable_doc")


def _finish(
    op: str,
    mode: str,
    case_id: str,
    seed: int,
    base: BaseDoc,
    edits: list[dict[str, Any]],
    spec_after: dict[str, Any],
    pdf: bytes,
    candidates_tried: int,
) -> TamperCase:
    cand_tree = build_integrity_tree(pdf)
    categories = sorted({e["category"] for e in edits})
    record: dict[str, Any] = {
        "case_id": case_id,
        "op": op,
        "mode": mode,
        "seed": seed,
        "base_doc_id": base.spec["doc_id"],
        "doc_type": base.spec["doc_type"],
        "expected_categories": categories,
        "expected_status": "CHANGED" if edits else "CONTENT_EQUIVALENT",
        "edits": edits,
        "ref": tree_summary(base.tree),
        "cand": tree_summary(cand_tree),
        "truth": derive_truth(base.tree, cand_tree),
    }
    if mode == "inplace":
        record["inplace_candidates_tried"] = candidates_tried + 1
    return TamperCase(case_id, op, mode, pdf, record, base.spec, spec_after)


def build_run(
    cfg: dict[str, Any],
    source: CorpusSource | None = None,
    limit: int | None = None,
    ops: list[str] | None = None,
) -> TamperRun:
    source = source or CorpusSource(cfg)
    run = TamperRun()
    inplace: dict[str, dict[str, Any]] = {}
    for op, modes in cfg["tamper"]["cases"].items():
        if ops and op not in ops:
            continue
        for mode, target in modes.items():
            want = min(int(target), limit) if limit else int(target)
            stat = inplace.setdefault(op, {"attempted": 0, "succeeded": 0, "skipped": {}})
            done, attempt = 0, 0
            while done < want:
                if attempt > 20 * want + 20:
                    raise RuntimeError(f"{op}/{mode}: {done}/{want} cases after {attempt} attempts")
                result = build_case(cfg, source, op, mode, attempt, case_no=done)
                attempt += 1
                if mode == "inplace":
                    stat["attempted"] += 1
                if result.case is None:
                    if result.skip == "no_applicable_doc":
                        raise RuntimeError(f"no document supports {op}/{mode}")
                    stat["skipped"][result.skip] = stat["skipped"].get(result.skip, 0) + 1
                    continue
                if mode == "inplace":
                    stat["succeeded"] += 1
                run.cases.append(result.case)
                done += 1
    run.stats = {
        "counts": _counts(run.cases),
        "inplace": {op: s for op, s in inplace.items() if s["attempted"]},
        "base_docs_used": len({c.record["base_doc_id"] for c in run.cases}),
    }
    return run


def _counts(cases: list[TamperCase]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cases:
        key = f"{c.op}/{c.mode}"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def summary_lines(run: TamperRun) -> list[str]:
    lines = [f"{len(run.cases)} cases from {run.stats['base_docs_used']} base documents"]
    lines += [f"  {key:<32} {n:>3}" for key, n in run.stats["counts"].items()]
    for op, s in run.stats["inplace"].items():
        rate = s["succeeded"] / s["attempted"]
        lines.append(
            f"  in-place {op}: {s['succeeded']}/{s['attempted']} succeeded ({rate:.0%}), "
            f"skipped {s['skipped']}"
        )
    return lines


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_run(run: TamperRun, out: Path, seed: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for c in run.cases:
        (out / f"{c.case_id}.pdf").write_bytes(c.pdf)
        (out / f"{c.case_id}.json").write_text(_dump(c.record), encoding="utf-8")
    manifest = {
        "tamper_seed": seed,
        "n_cases": len(run.cases),
        "stats": run.stats,
        "cases": [
            {
                "case_id": c.case_id,
                "op": c.op,
                "mode": c.mode,
                "base_doc_id": c.record["base_doc_id"],
                "expected_categories": c.record["expected_categories"],
                "expected_status": c.record["expected_status"],
            }
            for c in run.cases
        ],
    }
    (out / "manifest.json").write_text(_dump(manifest), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=EVAL_DIR / "configs" / "default.yaml")
    ap.add_argument("--seed", type=int, help="override tamper.seed")
    ap.add_argument("--out", type=Path, help="override tamper.out_dir")
    ap.add_argument("--corpus-dir", type=Path, help="verify base documents against this corpus")
    ap.add_argument("--limit", type=int, help="cap the case count of every (op, mode)")
    ap.add_argument("--ops", nargs="*", help="only these ops")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.seed is not None:
        cfg["tamper"]["seed"] = args.seed
    run = build_run(cfg, CorpusSource(cfg, args.corpus_dir), args.limit, args.ops)
    out = args.out or (EVAL_DIR / cfg["tamper"]["out_dir"])
    write_run(run, out, int(cfg["tamper"]["seed"]))
    print(f"wrote {len(run.cases)} cases to {out}")
    print("\n".join(summary_lines(run)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
