"""P9-03 evaluation runner tests (docs/08 C.3)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest
from proofchain_core import build_integrity_tree, localize
from proofchain_core.merkle import changed_leaves_by_descent, merkle_levels
from proofchain_core.types import Chunk

import baselines
import efficiency
import latency
import metrics
import run_eval
from generate_corpus import generate_one
from tamper import TamperRun, build_run


@pytest.fixture(scope="session")
def small_run(cfg: dict[str, Any]) -> TamperRun:
    """A few cases of every (op, mode), built once in-process."""
    return build_run(cfg, limit=3)


@pytest.fixture(scope="session")
def rows(cfg: dict[str, Any], small_run: TamperRun) -> list[dict[str, Any]]:
    return run_eval.evaluate_cases(cfg, run_eval.cases_from_run(small_run))


# ---- metrics.py (pure) ---------------------------------------------------------------------


def test_prf_hand_computed() -> None:
    # tp=3, fp=1, fn=2 -> P=3/4, R=3/5, F1=2*3/(2*3+1+2)=6/9
    out = metrics.prf(3, 1, 2)
    assert out == {"precision": 0.75, "recall": 0.6, "f1": round(6 / 9, 6)}


def test_prf_empty_conventions() -> None:
    assert metrics.prf(0, 0, 0) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert metrics.prf(0, 2, 0)["precision"] == 0.0 and metrics.prf(0, 2, 0)["f1"] == 0.0
    assert metrics.prf(0, 0, 2)["recall"] == 0.0


def test_counts_keep_reference_and_candidate_id_spaces_apart() -> None:
    """Chunk ids are positional (p0-c1 exists in both trees with different content)."""
    truth = metrics.tagged({"p0-c1"}, {"p0-c1"})
    assert metrics.counts(truth, metrics.tagged({"p0-c1"}, set())) == (1, 0, 1)
    assert metrics.counts(truth, metrics.tagged({"p0-c1"}, {"p0-c1"})) == (2, 0, 0)


def test_page_of_chunk_id() -> None:
    assert metrics.page_of("p12-c3") == 12 and metrics.page_of("p0-c0") == 0


def _fake_rows(n: int) -> list[dict[str, Any]]:
    rng = random.Random(5)
    out = []
    for i in range(n):
        out.append(
            {
                "case_id": f"case-{i:03d}",
                "op": ["amount_change", "clause_insert", "typo_fix"][i % 3],
                "mode": ["rerender", "inplace"][i % 2],
                "doc_type": "lease",
                "page_bucket": ["short", "medium", "long"][i % 3],
                "expected_status": "CHANGED",
                "chunk": {
                    m: [rng.randint(0, 5), rng.randint(0, 5), rng.randint(0, 5)]
                    for m in ("localize", "positional", "plain_diff")
                },
                "page": {
                    m: [rng.randint(0, 5), rng.randint(0, 5), rng.randint(0, 5)]
                    for m in ("localize", "positional", "plain_diff")
                },
            }
        )
    return out


def test_aggregation_is_byte_identical_under_case_order() -> None:
    """P9-05 regenerates the report, so the aggregate must not depend on input order."""
    rows = _fake_rows(60)
    shuffled = rows[:]
    random.Random(99).shuffle(shuffled)
    assert shuffled != rows
    a = metrics.dumps(metrics.localization_table(sorted(rows, key=lambda r: r["case_id"])))
    b = metrics.dumps(metrics.localization_table(shuffled))
    c = metrics.dumps(metrics.localization_table(list(reversed(rows))))
    assert a.encode() == b.encode() == c.encode()


def test_metrics_json_is_byte_identical_under_case_order(
    cfg: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    shuffled = rows[:]
    random.Random(3).shuffle(shuffled)
    assert shuffled != rows
    a = metrics.dumps(run_eval.build_metrics(cfg, rows))
    b = metrics.dumps(run_eval.build_metrics(cfg, shuffled))
    assert a.encode() == b.encode()


# ---- baselines.py --------------------------------------------------------------------------


def _chunk(page: int, index: int, text: str) -> Chunk:
    from proofchain_core.types import BBox

    return Chunk(f"p{page}-c{index}", page, index, text, BBox(0, 0, 1, 1), f"h:{text}")


def test_positional_baseline_cascades_after_an_insert() -> None:
    """Insert one chunk at position 1: every later index shifts, so the index-by-index
    comparison flags all of them while one chunk really changed (02 section 9.4, ADR-006)."""
    ref = [_chunk(0, i, f"t{i}") for i in range(6)]
    cand = ref[:1] + [_chunk(0, 1, "new")] + [_chunk(0, i + 1, f"t{i}") for i in range(1, 6)]
    ref_ids, cand_ids = baselines.positional(ref, cand)
    assert len(cand) == 7
    assert cand_ids == {"p0-c1", "p0-c2", "p0-c3", "p0-c4", "p0-c5", "p0-c6"}
    assert ref_ids == {"p0-c1", "p0-c2", "p0-c3", "p0-c4", "p0-c5"}


def test_positional_baseline_flags_nothing_when_identical_and_tail_when_lengths_differ() -> None:
    ref = [_chunk(0, i, f"t{i}") for i in range(3)]
    assert baselines.positional(ref, ref) == (set(), set())
    assert baselines.positional(ref, ref[:2]) == ({"p0-c2"}, set())
    assert baselines.positional(ref[:2], ref) == (set(), {"p0-c2"})


def test_whole_file_baseline_detects_but_cannot_localize(
    small_run: TamperRun,
) -> None:
    case = next(c for c in small_run.cases if c.op == "amount_change")
    ref = case.record["ref"]["file_hash"]
    assert baselines.whole_file_changed(ref, case.record["cand"]["file_hash"]) is True
    assert baselines.whole_file_changed(ref, ref) is False


def test_plain_diff_baseline_matches_hash_alignment_on_an_insert() -> None:
    ref = [_chunk(0, i, f"t{i}") for i in range(6)]
    cand = ref[:1] + [_chunk(0, 1, "new")] + [_chunk(0, i + 1, f"t{i}") for i in range(1, 6)]
    ref_ids, cand_ids = baselines.plain_diff(ref, cand)
    assert (ref_ids, cand_ids) == (set(), {"p0-c1"})


# ---- the runner against the real tamper cases ----------------------------------------------


def test_detection_is_total_and_metadata_only_has_no_false_positive(
    rows: list[dict[str, Any]],
) -> None:
    det = metrics.detection_table(rows)
    assert det["content_changing"]["text_root_detection_rate"] == 1.0
    assert det["content_changing"]["file_hash_detection_rate"] == 1.0
    assert det["content_changing"]["localize_status_changed_rate"] == 1.0
    meta = det["metadata_only"]
    assert meta["n"] > 0
    assert meta["text_root_false_positive_rate"] == 0.0
    assert meta["localize_false_positive_rate"] == 0.0
    # the whole-file baseline flags every re-save: that is the point of the text root
    assert meta["whole_file_false_positive_rate"] == 1.0


def test_localize_scores_against_independent_truth(rows: list[dict[str, Any]]) -> None:
    table = metrics.localization_table(rows)
    overall = table["overall"]["chunk"]["localize"]
    assert overall["f1"] >= 0.95
    # the single-edit in-place and re-render ops localize exactly
    for op in ("amount_change", "date_change", "typo_fix"):
        assert table["by_op"][op]["chunk"]["localize"]["f1"] >= 0.95
    assert set(table["by_mode"]) >= {"rerender", "inplace"}


def test_positional_baseline_is_worse_on_insert_and_delete(rows: list[dict[str, Any]]) -> None:
    table = metrics.localization_table(rows)
    for op in ("clause_insert", "clause_delete"):
        loc = table["by_op"][op]["chunk"]["localize"]
        pos = table["by_op"][op]["chunk"]["positional"]
        assert loc["f1"] > pos["f1"], op
        assert pos["precision"] < loc["precision"], op


def test_localization_excludes_content_equivalent_cases(rows: list[dict[str, Any]]) -> None:
    table = metrics.localization_table(rows)
    assert "metadata_only" not in table["by_op"]


def test_efficiency_counts_are_bounded(rows: list[dict[str, Any]]) -> None:
    eff = [r["efficiency"] for r in rows if r["expected_status"] == "CHANGED"]
    assert eff
    for e in eff:
        assert e["naive"] == e["ref_chunks"] + e["cand_chunks"]
        if e["method"] == "MERKLE_FAST_PATH":
            assert e["hash_comparisons"] <= e["naive"] + e["page_count"]
    table = metrics.efficiency_table(rows)
    long_docs = table["by_page_bucket"].get("long")
    assert long_docs is not None  # the Merkle saving shows on long documents
    assert long_docs["mean_hash_comparisons"] < long_docs["mean_naive"]
    assert long_docs["mean_descent"] < long_docs["mean_naive"]


def test_descent_counter_finds_the_same_leaves_as_core() -> None:
    leaves = [f"{i:064x}" for i in range(13)]
    changed = leaves[:]
    changed[4] = "f" * 64
    changed[11] = "e" * 64
    a, b = merkle_levels(leaves), merkle_levels(changed)
    found, comparisons = efficiency.descent(a, b)
    assert found == changed_leaves_by_descent(a, b) == [4, 11]
    assert comparisons < 2 * len(leaves)  # fewer than comparing every leaf in both trees
    assert efficiency.descent(a, a) == ([], 1)  # identical: only the root is compared


def test_descent_comparisons_grow_slower_than_a_full_scan() -> None:
    small = [f"{i:064x}" for i in range(16)]
    big = [f"{i:064x}" for i in range(1024)]

    def one_change(xs: list[str]) -> int:
        ys = xs[:]
        ys[3] = "f" * 64
        return efficiency.descent(merkle_levels(xs), merkle_levels(ys))[1]

    assert one_change(big) < len(big) / 20
    assert one_change(big) <= one_change(small) + 2 * 6  # ~2 per extra level


def test_latency_reports_median_of_n_and_every_size(cfg: dict[str, Any]) -> None:
    calls: list[int] = []

    def fn() -> None:
        calls.append(1)

    out = latency.time_median(fn, repeats=5)
    assert len(calls) == 5 and out >= 0
    sizes = latency.measure(cfg, pages=[1, 3], repeats=2)
    assert [s["target_pages"] for s in sizes] == [1, 3]
    for s in sizes:
        assert s["page_count"] == s["target_pages"]
        for key in ("build_tree_ms", "localize_ms", "verify_ms", "plain_diff_ms", "file_hash_ms"):
            assert s[key] >= 0


def test_run_is_deterministic_apart_from_latency(
    cfg: dict[str, Any], small_run: TamperRun, tmp_path: Path
) -> None:
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    run_eval.run(cfg, run_eval.cases_from_run(small_run), out_a, pages=[1], repeats=1)
    run_eval.run(cfg, run_eval.cases_from_run(small_run), out_b, pages=[1], repeats=1)
    for name in ("metrics.json", "detection.csv", "localization.csv", "efficiency.csv"):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), name
    assert (out_a / "latency.json").exists() and (out_a / "latency.csv").exists()
    data = json.loads((out_a / "metrics.json").read_text(encoding="utf-8"))
    assert data["n_cases"] == len(small_run.cases)


def test_stale_tamper_data_is_rejected(cfg: dict[str, Any], small_run: TamperRun) -> None:
    case = small_run.cases[0]
    bad_record = {**case.record, "cand": {**case.record["cand"], "file_hash": "0" * 64}}
    with pytest.raises(ValueError, match="stale"):
        run_eval.evaluate_cases(cfg, [(bad_record, case.pdf)])


def test_truth_ids_are_positional_in_both_trees(cfg: dict[str, Any], small_run: TamperRun) -> None:
    """Confirms the data shape the scoring relies on: ids repeat across the two trees."""
    case = next(c for c in small_run.cases if c.op == "clause_insert")
    t = case.record["truth"]
    assert t["changed_cand_chunk_ids"] and not t["changed_ref_chunk_ids"]
    _, ref_pdf = generate_one(cfg, int(case.record["base_doc_id"].split("_")[1]))
    ref_tree, cand_tree = build_integrity_tree(ref_pdf), build_integrity_tree(case.pdf)
    shared = {c.id for p in ref_tree.pages for c in p.chunks} & {
        c.id for p in cand_tree.pages for c in p.chunks
    }
    assert shared  # same id, different content: the two id spaces must be scored apart
    assert localize(ref_tree, cand_tree).stats["inserted"] >= 1


def test_plain_diff_results_always_carry_the_no_tamper_evidence_caveat(
    cfg: dict[str, Any], rows: list[dict[str, Any]], tmp_path: Path
) -> None:
    """The plain diff scores perfectly only because it is handed the stored reference text; P9-05
    must not be able to quote the number without this caveat."""
    result = run_eval.build_metrics(cfg, rows)
    info = result["baselines"]["plain_diff"]
    assert info["tamper_evident"] is False
    assert info["requires_trusted_reference_text"] is True
    assert "no verification that the reference" in info["caveat"]
    table = result["localization"]

    def entries(node: Any) -> Any:
        if isinstance(node, dict):
            if "plain_diff" in node and "chunk" not in node:
                yield node["plain_diff"]
            for v in node.values():
                yield from entries(v)

    scored = list(entries(table))
    assert scored
    assert all(e["caveat"] == info["caveat"] for e in scored)
    assert all("caveat" not in e for e in _other_methods(table))

    run_eval.write_results(tmp_path, result, rows, [])
    import csv

    with (tmp_path / "localization.csv").open(encoding="utf-8") as fh:
        plain = [r for r in csv.DictReader(fh) if r["method"] == "plain_diff"]
    assert plain and all(r["caveat"] == info["caveat"] for r in plain)


def _other_methods(node: Any) -> Any:
    if isinstance(node, dict):
        for m in ("localize", "positional"):
            if m in node and isinstance(node[m], dict) and "tp" in node[m]:
                yield node[m]
        for v in node.values():
            yield from _other_methods(v)
