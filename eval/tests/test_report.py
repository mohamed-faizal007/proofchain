"""P9-05 figures and REPORT.md: built only from result files, deterministic, honest about gaps."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from test_chain_metrics import FakeProbe

import chain_metrics
import metrics
import report
import run_eval
from tamper import TamperRun, build_run

FIGURES = ["efficiency", "latency", "localization"]
LIVE_PRICES = {
    "taken_at_utc": "2026-10-03T12:30:45Z",
    "live": True,
    "gas_price_gwei": {"value": 1.5, "source": "live: ethereum-rpc.publicnode.com"},
    "eth_usd": {"value": 2500.0, "source": "live: api.coingecko.com"},
    "eth_inr": {"value": 210000.0, "source": "live: api.coingecko.com"},
}
STALE_PRICES = {
    "taken_at_utc": "2026-10-03T12:30:45Z",
    "live": False,
    "gas_price_gwei": {"value": 20.0, "source": "config default"},
    "eth_usd": {"value": 3000.0, "source": "config default"},
    "eth_inr": {"value": 250000.0, "source": "config default"},
}


@pytest.fixture(scope="session")
def small_run(cfg: dict[str, Any]) -> TamperRun:
    return build_run(cfg, limit=2)


@pytest.fixture(scope="session")
def results(cfg: dict[str, Any], small_run: TamperRun, tmp_path_factory: Any) -> Path:
    out = tmp_path_factory.mktemp("results")
    run_eval.run(cfg, run_eval.cases_from_run(small_run), out, pages=[1, 3], repeats=1)
    return out


def _copy(src: Path, dst: Path) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            (dst / f.name).write_bytes(f.read_bytes())
    return dst


def _chain_file(directory: Path, prices: dict[str, Any] | None) -> None:
    cfg = {"latency_samples": 10, "subsequent_versions": 5, "max_transactions": 20, "seed": 1}
    data = asyncio.run(chain_metrics.run_measurement(FakeProbe(), cfg, "sepolia", "n"))
    data["confirmations"] = 2
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "chain_sepolia.json").write_text(metrics.dumps(data), encoding="utf-8")
    if prices is not None:
        (directory / "chain_prices.json").write_text(metrics.dumps(prices), encoding="utf-8")


def test_missing_metrics_json_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(report.ReportInputError, match="metrics.json"):
        report.build(tmp_path, None)


def test_report_and_figures_are_written(results: Path, tmp_path: Path) -> None:
    out = _copy(results, tmp_path / "r")
    path = report.build(out, None)
    assert path == out / "REPORT.md"
    for name in FIGURES:
        for ext in ("png", "pdf"):
            assert (out / "figures" / f"{name}.{ext}").stat().st_size > 0


def test_report_sections_and_numbers_come_from_the_result_files(
    results: Path, tmp_path: Path
) -> None:
    out = _copy(results, tmp_path / "r")
    text = report.build(out, None).read_text(encoding="utf-8")
    data = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    for heading in ("## Detection", "## Localization", "## Merkle efficiency", "## Latency"):
        assert heading in text
    assert f"{data['n_cases']} tamper cases" in text
    assert f"{data['localization']['overall']['chunk']['localize']['f1']:.3f}" in text


def test_plain_diff_caveat_travels_with_its_numbers(results: Path, tmp_path: Path) -> None:
    out = _copy(results, tmp_path / "r")
    text = report.build(out, None).read_text(encoding="utf-8")
    assert metrics.PLAIN_DIFF_CAVEAT in text


def test_sections_without_inputs_say_not_run_and_do_not_fail(results: Path, tmp_path: Path) -> None:
    out = _copy(results, tmp_path / "r")
    text = report.build(out, tmp_path / "none").read_text(encoding="utf-8")
    assert "## Classification" in text and "not run" in text.split("## Classification")[1][:300]
    assert "## Chain" in text and "not run" in text.split("## Chain")[1][:300]


def test_build_is_byte_identical_twice(results: Path, tmp_path: Path) -> None:
    out = _copy(results, tmp_path / "r")
    meas = tmp_path / "m"
    _chain_file(meas, LIVE_PRICES)
    report.build(out, meas)
    first = {p.name: p.read_bytes() for p in [out / "REPORT.md", *(out / "figures").iterdir()]}
    report.build(out, meas)
    second = {p.name: p.read_bytes() for p in [out / "REPORT.md", *(out / "figures").iterdir()]}
    assert first == second and "chain.png" in first and "chain.pdf" in first


def test_live_snapshot_is_dated_next_to_the_cost_numbers(results: Path, tmp_path: Path) -> None:
    out, meas = _copy(results, tmp_path / "r"), tmp_path / "m"
    _chain_file(meas, LIVE_PRICES)
    text = report.build(out, meas).read_text(encoding="utf-8")
    chain = text.split("## Chain")[1]
    assert "snapshot 2026-10-03T12:30:45Z" in chain
    assert "1.5 gwei" in chain and "$2,500" in chain
    assert "ILLUSTRATIVE" not in chain


def test_fallback_prices_are_labelled_illustrative_prominently(
    results: Path, tmp_path: Path
) -> None:
    out, meas = _copy(results, tmp_path / "r"), tmp_path / "m"
    _chain_file(meas, STALE_PRICES)
    chain = report.build(out, meas).read_text(encoding="utf-8").split("## Chain")[1]
    banner = chain.lstrip().splitlines()[0:6]
    assert any("ILLUSTRATIVE" in line and "NOT CURRENT" in line for line in banner)


def test_chain_section_reports_gas_latency_balance_and_cap(results: Path, tmp_path: Path) -> None:
    out, meas = _copy(results, tmp_path / "r"), tmp_path / "m"
    _chain_file(meas, LIVE_PRICES)
    chain = report.build(out, meas).read_text(encoding="utf-8").split("## Chain")[1]
    assert "90,000" in chain and "60,000" in chain  # v1 and subsequent gas
    assert "15 transactions" in chain and "cap of 20" in chain
    assert "balance before" in chain.lower() and "balance after" in chain.lower()


def test_chain_without_prices_file_is_still_labelled_not_current(
    results: Path, tmp_path: Path
) -> None:
    out, meas = _copy(results, tmp_path / "r"), tmp_path / "m"
    _chain_file(meas, None)
    chain = report.build(out, meas).read_text(encoding="utf-8").split("## Chain")[1]
    assert "no price snapshot" in chain.lower()


def test_classification_section_is_built_from_the_classification_files(
    results: Path, tmp_path: Path
) -> None:
    out = _copy(results, tmp_path / "r")
    doc = {"exact_match": 0.5, "mean_jaccard": 0.6}
    arm = {"macro_f1": 0.9, "accuracy": 0.8, "lenient_accuracy": 0.85, "document_level": doc}
    worse = arm | {"macro_f1": 0.8}
    matching = {
        "matched": 9, "n_regions": 10, "n_edits": 11, "unmatched": 1, "ambiguous": 0,
        "missed_edits": 2, "excluded_content_equivalent": 3,
    }  # fmt: skip
    arms = {"rules": arm, "rules_ner": arm, "rules_ner_emb": worse}
    (out / "classification.json").write_text(
        json.dumps({"arms": arms, "matching": matching, "categories": []}), encoding="utf-8"
    )
    lines = ["arm,category,support,tp,fp,fn,precision,recall,f1,lenient_recall"]
    lines += [f"{a},AMOUNT_CHANGE,5,5,0,0,1.0,1.0,0.987,1.0" for a in arms]
    (out / "classification.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    text = report.build(out, None).read_text(encoding="utf-8")
    section = text.split("## Classification")[1].split("## Chain")[0]
    assert "9 of 10 regions matched to 11 edits" in section and "0.987" in section
    assert "lowered macro-F1" in section
    assert (out / "figures" / "classification.png").stat().st_size > 0
