"""P9-04 classification evaluation + ablation tests (docs/06 Evaluation, docs/08 C.3).

"Correct" is defined against the tamper ground truth: each localized region is matched to the
tamper edit whose before/after text it carries, and that edit's category is the expected label
(strict: ``primary_category`` equals it; lenient: it is among ``categories``).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest
from app.nlp.classifier import HybridClassifier, RuleOnlyClassifier
from proofchain_core import build_integrity_tree, localize
from proofchain_core.types import ChangeRegion, RegionType

import classification
import nlp_arms
import run_eval
from tamper import TamperRun, build_run

ARMS = ["rules", "rules_ner", "rules_ner_emb"]


# ---- helpers ---------------------------------------------------------------------------------


def _region(kind: RegionType, ref: str | None, cand: str | None) -> ChangeRegion:
    return ChangeRegion(id="r0", type=kind, ref_text=ref, cand_text=cand)


def _edit(kind: str, cat: str, before: str | None, after: str | None) -> dict[str, Any]:
    return {"kind": kind, "category": cat, "before": before, "after": after}


def _pred(primary: str, cats: list[str] | None = None, method: str = "RULES") -> dict[str, Any]:
    return {"primary": primary, "categories": cats or [primary], "method": method}


def _case(
    op: str,
    regions: list[tuple[str | None, str, dict[str, Any]]],
    expected: list[str] | None = None,
    n_edits: int | None = None,
    missed: list[str] | None = None,
    mode: str = "rerender",
    case_id: str = "c",
    status: str = "CHANGED",
) -> dict[str, Any]:
    """regions: (expected category or None, match status, per-arm prediction used for every arm)."""
    exp = expected or sorted({r[0] for r in regions if r[0]})
    return {
        "case_id": case_id,
        "op": op,
        "mode": mode,
        "expected_status": status,
        "expected": exp,
        "n_edits": len(exp) if n_edits is None else n_edits,
        "n_regions": len(regions),
        "regions": [
            {"expected": e, "match": m, "arms": {a: p for a in ARMS}} for e, m, p in regions
        ],
        "missed_edits": missed or [],
    }


# ---- matching a region to its tamper edit ----------------------------------------------------


def test_modified_region_matches_the_edit_with_equal_before_and_after() -> None:
    edits = [_edit("replace", "AMOUNT_CHANGE", "Fee is ₹5.", "Fee is ₹6.")]
    status, cat, idx = classification.match_region(
        _region(RegionType.MODIFIED, "Fee is ₹5.", "Fee is ₹6."), edits
    )
    assert (status, cat, idx) == ("matched", "AMOUNT_CHANGE", [0])


def test_inserted_matches_on_after_only_and_deleted_on_before_only() -> None:
    edits = [
        _edit("insert", "CLAUSE_ADDED", None, "New clause."),
        _edit("delete", "CLAUSE_REMOVED", "Old clause.", None),
    ]
    assert classification.match_region(_region(RegionType.INSERTED, None, "New clause."), edits)[
        :2
    ] == ("matched", "CLAUSE_ADDED")
    assert classification.match_region(_region(RegionType.DELETED, "Old clause.", None), edits)[
        :2
    ] == ("matched", "CLAUSE_REMOVED")
    # An INSERTED region never matches a delete edit, even if the text were equal.
    assert (
        classification.match_region(_region(RegionType.INSERTED, None, "Old clause."), edits)[0]
        == "unmatched"
    )


def test_edit_text_is_canonicalized_before_comparison() -> None:
    """Chunk text is canonical (docs/02 s3); the spec text keeps U+2019 and double spaces."""
    edits = [_edit("replace", "PARTY_CHANGE", "Mr D’Souza  signs.", "Ms Rao signs.")]
    region = _region(RegionType.MODIFIED, "Mr D'Souza signs.", "Ms Rao signs.")
    assert classification.match_region(region, edits)[0] == "matched"


def test_unknown_text_is_unmatched_and_conflicting_edits_are_ambiguous() -> None:
    edits = [_edit("replace", "AMOUNT_CHANGE", "a", "b")]
    assert classification.match_region(_region(RegionType.MODIFIED, "x", "y"), edits) == (
        "unmatched",
        None,
        [],
    )
    twins = [_edit("replace", "AMOUNT_CHANGE", "a", "b"), _edit("replace", "DATE_CHANGE", "a", "b")]
    status, cat, idx = classification.match_region(_region(RegionType.MODIFIED, "a", "b"), twins)
    assert (status, cat, idx) == ("ambiguous", None, [0, 1])


def test_edits_with_the_same_text_and_category_are_not_ambiguous() -> None:
    twins = [_edit("replace", "OBLIGATION_CHANGE", "a", "b")] * 2
    assert classification.match_region(_region(RegionType.MODIFIED, "a", "b"), twins)[:2] == (
        "matched",
        "OBLIGATION_CHANGE",
    )


# ---- scoring (hand computed) -----------------------------------------------------------------


def _single(expected: str, primary: str, cats: list[str] | None = None, i: int = 0) -> Any:
    return _case(
        "x", [(expected, "matched", _pred(primary, cats))], case_id=f"c{i}-{expected}-{primary}"
    )


def test_per_category_prf_macro_f1_and_confusion_hand_computed() -> None:
    cases = [
        _single("AMOUNT_CHANGE", "AMOUNT_CHANGE", i=0),
        _single("AMOUNT_CHANGE", "NUMBER_CHANGE", i=1),
        _single("NUMBER_CHANGE", "NUMBER_CHANGE", i=2),
        _single("DATE_CHANGE", "DATE_CHANGE", i=3),
    ]
    arm = classification.score(cases, ARMS)["arms"]["rules"]
    amount, number = arm["per_category"]["AMOUNT_CHANGE"], arm["per_category"]["NUMBER_CHANGE"]
    assert (amount["tp"], amount["fp"], amount["fn"]) == (1, 0, 1)
    assert (amount["precision"], amount["recall"]) == (1.0, 0.5)
    assert (number["tp"], number["fp"], number["fn"]) == (1, 1, 0)
    assert number["f1"] == pytest.approx(2 / 3, abs=1e-6)
    assert arm["per_category"]["DATE_CHANGE"]["f1"] == 1.0
    # macro over the three categories that have support: (2/3 + 2/3 + 1) / 3
    assert arm["macro_f1"] == pytest.approx(7 / 9, abs=1e-6)
    assert arm["accuracy"] == 0.75
    assert arm["confusion"]["AMOUNT_CHANGE"]["NUMBER_CHANGE"] == 1
    assert arm["confusion"]["AMOUNT_CHANGE"]["AMOUNT_CHANGE"] == 1


def test_macro_f1_ignores_categories_without_support() -> None:
    result = classification.score([_single("DATE_CHANGE", "DATE_CHANGE")], ARMS)["arms"]["rules"]
    assert result["macro_f1"] == 1.0
    assert result["per_category"]["PARTY_CHANGE"]["support"] == 0


def test_lenient_counts_a_category_present_among_categories() -> None:
    cases = [_single("AMOUNT_CHANGE", "NUMBER_CHANGE", ["NUMBER_CHANGE", "AMOUNT_CHANGE"])]
    arm = classification.score(cases, ARMS)["arms"]["rules"]
    assert arm["accuracy"] == 0.0 and arm["lenient_accuracy"] == 1.0
    assert arm["per_category"]["AMOUNT_CHANGE"]["recall"] == 0.0
    assert arm["per_category"]["AMOUNT_CHANGE"]["lenient_recall"] == 1.0


def test_unmatched_region_is_a_false_positive_and_a_missed_edit_a_false_negative() -> None:
    cases = [
        _case("multi_edit", [(None, "unmatched", _pred("AMOUNT_CHANGE"))], expected=["DATE_CHANGE"],
              n_edits=1, missed=["DATE_CHANGE"], case_id="a"),
    ]  # fmt: skip
    res = classification.score(cases, ARMS)
    arm = res["arms"]["rules"]
    assert arm["per_category"]["AMOUNT_CHANGE"]["fp"] == 1
    assert arm["per_category"]["DATE_CHANGE"]["fn"] == 1
    assert arm["confusion"]["NONE"]["AMOUNT_CHANGE"] == 1
    assert arm["confusion"]["DATE_CHANGE"]["NONE"] == 1
    m = res["matching"]
    assert (m["matched"], m["unmatched"], m["ambiguous"], m["missed_edits"]) == (0, 1, 0, 1)


def test_ambiguous_region_is_reported_and_scored_as_a_false_positive() -> None:
    cases = [_case("x", [(None, "ambiguous", _pred("AMOUNT_CHANGE"))], expected=[], n_edits=2)]
    res = classification.score(cases, ARMS)
    assert res["matching"]["ambiguous"] == 1
    assert res["arms"]["rules"]["per_category"]["AMOUNT_CHANGE"]["fp"] == 1


def test_region_count_mismatch_is_counted_per_op_never_dropped() -> None:
    ok = _case("amount_change", [("AMOUNT_CHANGE", "matched", _pred("AMOUNT_CHANGE"))], case_id="1")
    split = _case(
        "amount_change",
        [("AMOUNT_CHANGE", "matched", _pred("AMOUNT_CHANGE"))] * 2,
        n_edits=1,
        case_id="2",
    )
    m = classification.score([ok, split], ARMS)["matching"]
    assert m["region_count_mismatch"] == {"total": 1, "by_op": {"amount_change": 1}}
    assert m["n_regions"] == 3 and m["n_cases"] == 2


def test_metadata_only_cases_are_excluded_and_counted() -> None:
    meta = _case("metadata_only", [], expected=[], n_edits=0, status="CONTENT_EQUIVALENT")
    res = classification.score([meta, _single("DATE_CHANGE", "DATE_CHANGE")], ARMS)
    assert res["matching"]["n_cases"] == 1
    assert res["matching"]["excluded_content_equivalent"] == 1


def test_document_level_exact_match_and_jaccard_for_multi_edit() -> None:
    both = _case(
        "multi_edit",
        [
            ("DATE_CHANGE", "matched", _pred("DATE_CHANGE")),
            ("OBLIGATION_CHANGE", "matched", _pred("OBLIGATION_CHANGE")),
        ],
        case_id="1",
    )
    half = _case(
        "multi_edit",
        [
            ("DATE_CHANGE", "matched", _pred("DATE_CHANGE")),
            ("OBLIGATION_CHANGE", "matched", _pred("CLAUSE_MODIFIED")),
        ],
        case_id="2",
    )
    doc = classification.score([both, half], ARMS)["arms"]["rules"]["document_level"]
    # case 2: predicted {DATE, CLAUSE_MODIFIED} vs {DATE, OBLIGATION}: jaccard 1/3
    assert doc["exact_match"] == 0.5
    assert doc["mean_jaccard"] == pytest.approx((1 + 1 / 3) / 2, abs=1e-6)


def test_score_is_byte_identical_under_case_order() -> None:
    rng = random.Random(4)
    cats = ["AMOUNT_CHANGE", "DATE_CHANGE", "NUMBER_CHANGE", "MINOR_EDIT"]
    cases = [
        _case(
            "x",
            [(rng.choice(cats), "matched", _pred(rng.choice(cats)))],
            case_id=f"c{i:03d}",
            mode=["inplace", "rerender"][i % 2],
        )
        for i in range(60)
    ]
    shuffled = cases[:]
    random.Random(8).shuffle(shuffled)
    assert shuffled != cases
    a = classification.dumps(classification.score(cases, ARMS))
    b = classification.dumps(classification.score(shuffled, ARMS))
    c = classification.dumps(classification.score(list(reversed(cases)), ARMS))
    assert a.encode() == b.encode() == c.encode()


# ---- the three arms --------------------------------------------------------------------------


class _Ent:
    def __init__(self, text: str) -> None:
        self.text, self.label_ = text, "PERSON"


class _FakeNER:
    NAMES = ("Asha Rao", "Vikram Mehta")

    def __call__(self, text: str) -> Any:
        class _Doc:
            ents = [_Ent(n) for n in _FakeNER.NAMES if n in text]

        return _Doc()


class _FakeEmbedder:
    """Identical-ish texts -> similar vectors, so the 0.90 MINOR_EDIT gate is exercised."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "typo" not in t else [0.0, 1.0] for t in texts]


def _fake_arms() -> dict[str, Any]:
    return {
        "rules": RuleOnlyClassifier(),
        "rules_ner": HybridClassifier(ner_getter=lambda: _FakeNER(), embedder_getter=lambda: None),
        "rules_ner_emb": HybridClassifier(
            ner_getter=lambda: _FakeNER(), embedder_getter=lambda: _FakeEmbedder()
        ),
    }


def _party_record() -> dict[str, Any]:
    return {
        "case_id": "p",
        "op": "party_change",
        "mode": "rerender",
        "expected_status": "CHANGED",
        "expected_categories": ["PARTY_CHANGE"],
        "edits": [
            _edit(
                "replace",
                "PARTY_CHANGE",
                "Lessor Asha Rao signs.",
                "Lessor Vikram Mehta signs.",
            )
        ],
    }


def test_party_change_needs_ner_so_only_the_ner_arms_find_it() -> None:
    region = _region(RegionType.MODIFIED, "Lessor Asha Rao signs.", "Lessor Vikram Mehta signs.")
    res = classification.classify_case(_party_record(), [region], _fake_arms())
    arms = res["regions"][0]["arms"]
    assert res["regions"][0]["match"] == "matched"
    assert arms["rules"]["primary"] != "PARTY_CHANGE"
    assert arms["rules_ner"]["primary"] == "PARTY_CHANGE"
    assert arms["rules_ner_emb"]["primary"] == "PARTY_CHANGE"


def test_arm_method_reflects_whether_embeddings_ran() -> None:
    region = _region(RegionType.MODIFIED, "Lessor Asha Rao signs.", "Lessor Vikram Mehta signs.")
    arms = classification.classify_case(_party_record(), [region], _fake_arms())["regions"][0][
        "arms"
    ]
    assert arms["rules"]["method"] == "RULES"
    assert arms["rules_ner"]["method"] == "RULES"
    assert arms["rules_ner_emb"]["method"] == "RULES+EMBEDDINGS"


def test_classify_case_reports_missed_edits_and_timings() -> None:
    timings: dict[str, list[float]] = {}
    res = classification.classify_case(_party_record(), [], _fake_arms(), timings)
    assert res["missed_edits"] == ["PARTY_CHANGE"] and res["n_regions"] == 0
    region = _region(RegionType.MODIFIED, "Lessor Asha Rao signs.", "Lessor Vikram Mehta signs.")
    classification.classify_case(_party_record(), [region], _fake_arms(), timings)
    assert sorted(timings) == sorted(ARMS) and all(len(v) == 1 for v in timings.values())


def test_missing_models_raise_instead_of_silently_falling_back() -> None:
    with pytest.raises(nlp_arms.ArmUnavailable, match="spaCy"):
        nlp_arms.build_arms(ner_getter=lambda: None, embedder_getter=lambda: object())
    with pytest.raises(nlp_arms.ArmUnavailable, match="embedding"):
        nlp_arms.build_arms(ner_getter=lambda: object(), embedder_getter=lambda: None)


def test_build_arms_returns_the_three_named_arms() -> None:
    arms = nlp_arms.build_arms(
        ner_getter=lambda: _FakeNER(), embedder_getter=lambda: _FakeEmbedder()
    )
    assert list(arms) == ARMS


# ---- on real tamper cases (rules-only needs no models) ---------------------------------------


@pytest.fixture(scope="module")
def small_run(cfg: dict[str, Any]) -> TamperRun:
    return build_run(cfg, limit=3)


@pytest.fixture(scope="module")
def case_results(cfg: dict[str, Any], small_run: TamperRun) -> list[dict[str, Any]]:
    arms = {"rules": RuleOnlyClassifier()}
    cache: dict[str, Any] = {}
    out = []
    for record, pdf in run_eval.cases_from_run(small_run):
        ref = run_eval._ref_tree(cfg, record["base_doc_id"], None, cache)
        regions = list(localize(ref, build_integrity_tree(pdf)).regions)
        out.append(classification.classify_case(record, regions, arms))
    return out


def test_every_region_is_accounted_for(case_results: list[dict[str, Any]]) -> None:
    """matched + unmatched + ambiguous == regions, in every case: nothing is dropped silently."""
    for r in case_results:
        assert len(r["regions"]) == r["n_regions"]
        assert {x["match"] for x in r["regions"]} <= {"matched", "unmatched", "ambiguous"}


def test_single_edit_cases_match_their_region_to_the_expected_category(
    case_results: list[dict[str, Any]], report: Any
) -> None:
    single = [r for r in case_results if r["expected_status"] == "CHANGED" and r["n_edits"] == 1]
    assert single
    matched = [x for r in single for x in r["regions"] if x["match"] == "matched"]
    assert len(matched) >= 0.9 * sum(r["n_regions"] for r in single)
    for r in single:
        for x in r["regions"]:
            if x["match"] == "matched":
                assert x["expected"] in r["expected"]
    report(
        f"classification matching (limit=3 run): {len(matched)} matched of "
        f"{sum(r['n_regions'] for r in single)} single-edit regions"
    )


def test_metadata_only_cases_have_no_regions(case_results: list[dict[str, Any]]) -> None:
    meta = [r for r in case_results if r["expected_status"] == "CONTENT_EQUIVALENT"]
    assert meta and all(r["n_regions"] == 0 for r in meta)


# ---- output files ----------------------------------------------------------------------------


def test_written_files_keep_timings_and_environment_out_of_the_deterministic_json(
    tmp_path: Path,
) -> None:
    cases = [
        _single("DATE_CHANGE", "DATE_CHANGE", i=0),
        _single("AMOUNT_CHANGE", "DATE_CHANGE", i=1),
    ]
    result = classification.score(cases, ARMS)
    classification.write(
        tmp_path,
        result,
        cases,
        {a: {"median_ms": 1.0, "mean_ms": 1.0, "n": 2} for a in ARMS},
        {"spacy": "x"},
    )
    names = {p.name for p in tmp_path.iterdir()}
    assert {
        "classification.json",
        "classification.csv",
        "classification_regions.csv",
        "classification_latency.json",
        "classification_env.json",
        *(f"confusion_{a}.csv" for a in ARMS),
    } <= names
    text = (tmp_path / "classification.json").read_text(encoding="utf-8")
    assert "median_ms" not in text and "spacy" not in text
    assert json.loads(text)["arms"]["rules"]["accuracy"] == 0.5
    rows = (tmp_path / "classification_regions.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("case_id,arm,") and len(rows) == 1 + 2 * len(ARMS)


# ---- real models (CI job eval-nlp, `pytest -m nlp`) ------------------------------------------


@pytest.mark.nlp
def test_real_models_run_every_arm_and_the_ablation_is_real(
    cfg: dict[str, Any], small_run: TamperRun
) -> None:
    arms = nlp_arms.build_arms()  # raises ArmUnavailable if either model is missing
    cache: dict[str, Any] = {}
    results = []
    for record, pdf in run_eval.cases_from_run(small_run):
        ref = run_eval._ref_tree(cfg, record["base_doc_id"], None, cache)
        regions = list(localize(ref, build_integrity_tree(pdf)).regions)
        results.append(classification.classify_case(record, regions, arms))
    modified = [
        x["arms"] for r in results for x in r["regions"] if x["arms"]["rules"]["method"] == "RULES"
    ]
    assert any(a["rules_ner_emb"]["method"] == "RULES+EMBEDDINGS" for a in modified)
    assert all(a["rules_ner"]["method"] == "RULES" for a in modified)
    scored = classification.score(results, list(arms))["arms"]
    assert scored["rules"]["per_category"]["PARTY_CHANGE"]["tp"] == 0  # no NER, no PARTY_CHANGE
    assert scored["rules_ner"]["per_category"]["PARTY_CHANGE"]["tp"] > 0
    env = nlp_arms.environment()
    assert env["spacy_model"] and env["embedding_model"]
