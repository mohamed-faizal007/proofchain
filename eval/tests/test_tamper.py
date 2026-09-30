"""P9-02 tamper operations + ground truth tests (docs/08 C.2)."""

from __future__ import annotations

import copy
import difflib
import hashlib
import subprocess
import sys
import unicodedata
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from proofchain_core import build_integrity_tree

from generate_corpus import generate_one
from inplace import InPlaceSkip, _stable_id, apply_inplace
from spec_edit import apply_edits
from tamper import TamperRun, build_case, build_run
from tamper_ops import OPS, SINGLE_EDIT_OPS, make_context

EVAL_DIR = Path(__file__).resolve().parent.parent
Report = Callable[[str], None]

ENTITY_OPS = {
    "amount_change": ("AMOUNT", "AMOUNT_CHANGE"),
    "date_change": ("DATE", "DATE_CHANGE"),
    "party_change": ("PARTY", "PARTY_CHANGE"),
    "percentage_change": ("PERCENTAGE", "PERCENTAGE_CHANGE"),
    "number_change": ("NUMBER", "NUMBER_CHANGE"),
}
TEXT_OPS = {
    "obligation_flip": "OBLIGATION_CHANGE",
    "clause_insert": "CLAUSE_ADDED",
    "clause_delete": "CLAUSE_REMOVED",
    "clause_reword": "CLAUSE_MODIFIED",
    "typo_fix": "MINOR_EDIT",
}


@pytest.fixture(scope="session")
def run(cfg: dict[str, Any]) -> TamperRun:
    """The full default tamper run (all cases), built once in-process."""
    return build_run(cfg)


def _first_spec_with(cfg: dict[str, Any], op: str) -> dict[str, Any]:
    for i in range(cfg["n_docs"]):
        spec, _ = generate_one(cfg, i)
        if OPS[op].plan(spec, make_context(spec["doc_type"], 7)) is not None:
            return spec
    raise AssertionError(f"no document supports {op}")


def _block_map(spec: dict[str, Any]) -> dict[str, str]:
    return {b["id"]: b["text"] for b in spec["blocks"]}


# ---- 1. each op does exactly what the C.2 table says (spec level) --------------------------


@pytest.mark.parametrize("op", sorted(ENTITY_OPS))
def test_entity_op_changes_only_the_entity_span(cfg: dict[str, Any], op: str) -> None:
    kind, category = ENTITY_OPS[op]
    spec = _first_spec_with(cfg, op)
    edits = OPS[op].plan(spec, make_context(spec["doc_type"], 7))
    assert edits is not None and len(edits) == 1
    edit = edits[0]
    assert edit["category"] == category and edit["kind"] == "replace"
    before = next(b for b in spec["blocks"] if b["id"] == edit["block_id"])
    start, end = edit["span"]
    ent = next(e for e in before["entities"] if (e["start"], e["end"]) == (start, end))
    assert ent["kind"] == kind and ent["value"] == edit["old"]
    after_spec = apply_edits(spec, edits)
    after_text = _block_map(after_spec)[edit["block_id"]]
    assert after_text != before["text"]
    assert after_text[: ent["start"]] == before["text"][: ent["start"]]
    # exactly the entity value differs; the rest of the sentence is byte-identical
    tail = before["text"][ent["end"] :]
    assert after_text.endswith(tail)
    new_value = after_text[ent["start"] : len(after_text) - len(tail)]
    assert new_value != ent["value"] and new_value
    changed = [i for i, t in _block_map(after_spec).items() if t != _block_map(spec).get(i)]
    assert changed == [edit["block_id"]]


@pytest.mark.parametrize("op", sorted(ENTITY_OPS))
def test_entity_op_keeps_entities_exact_substrings(cfg: dict[str, Any], op: str) -> None:
    spec = _first_spec_with(cfg, op)
    edits = OPS[op].plan(spec, make_context(spec["doc_type"], 7))
    assert edits is not None
    for b in apply_edits(spec, edits)["blocks"]:
        for e in b["entities"]:
            assert b["text"][e["start"] : e["end"]] == e["value"]


def test_obligation_flip_changes_modal(cfg: dict[str, Any]) -> None:
    spec = _first_spec_with(cfg, "obligation_flip")
    seen = set()
    for seed in range(12):
        edits = OPS["obligation_flip"].plan(spec, make_context(spec["doc_type"], seed))
        assert edits is not None and edits[0]["category"] == "OBLIGATION_CHANGE"
        b, a = edits[0]["before"].split(), edits[0]["after"].split()
        (tag, i1, i2, j1, j2), *rest = [
            o for o in difflib.SequenceMatcher(None, b, a).get_opcodes() if o[0] != "equal"
        ]
        assert not rest
        if tag == "insert":  # "shall" -> "shall not"
            assert b[i1 - 1] in ("shall", "must") and a[j1:j2] == ["not"]
            seen.add("not")
        else:  # "shall" -> "may"
            assert tag == "replace" and b[i1:i2] in (["shall"], ["must"]) and a[j1:j2] == ["may"]
            seen.add("may")
    assert seen == {"may", "not"}, seen


def test_insert_adds_one_block_after_an_existing_one(cfg: dict[str, Any]) -> None:
    spec = _first_spec_with(cfg, "clause_insert")
    edits = OPS["clause_insert"].plan(spec, make_context(spec["doc_type"], 3))
    assert edits is not None and edits[0]["category"] == "CLAUSE_ADDED"
    after = apply_edits(spec, edits)
    assert len(after["blocks"]) == len(spec["blocks"]) + 1
    ids = [b["id"] for b in after["blocks"]]
    assert len(set(ids)) == len(ids)
    pos = ids.index(edits[0]["after_block_id"])
    assert ids[pos - 1] == edits[0]["insert_after"]
    assert [b["id"] for b in after["blocks"] if b["id"] != ids[pos]] == [
        b["id"] for b in spec["blocks"]
    ]


def test_delete_removes_exactly_one_clause(cfg: dict[str, Any]) -> None:
    spec = _first_spec_with(cfg, "clause_delete")
    edits = OPS["clause_delete"].plan(spec, make_context(spec["doc_type"], 3))
    assert edits is not None and edits[0]["category"] == "CLAUSE_REMOVED"
    after = apply_edits(spec, edits)
    gone = set(_block_map(spec)) - set(_block_map(after))
    assert gone == {edits[0]["block_id"]}
    kind = next(b["kind"] for b in spec["blocks"] if b["id"] == edits[0]["block_id"])
    assert kind == "clause"


def test_reword_changes_at_least_four_tokens_and_keeps_entities(cfg: dict[str, Any]) -> None:
    spec = _first_spec_with(cfg, "clause_reword")
    edit = OPS["clause_reword"].plan(spec, make_context(spec["doc_type"], 3))[0]  # type: ignore[index]
    b, a = edit["before"].lower().split(), edit["after"].lower().split()
    assert edit["category"] == "CLAUSE_MODIFIED"
    assert len(a) - len(b) >= 4 or sum(1 for x in a if x not in b) >= 4
    old_ents = [
        e["value"]
        for e in next(x for x in spec["blocks"] if x["id"] == edit["block_id"])["entities"]
    ]
    assert all(v in edit["after"] for v in old_ents)


def test_typo_is_a_single_small_edit(cfg: dict[str, Any]) -> None:
    spec = _first_spec_with(cfg, "typo_fix")
    for seed in range(8):
        edit = OPS["typo_fix"].plan(spec, make_context(spec["doc_type"], seed))[0]  # type: ignore[index]
        assert edit["category"] == "MINOR_EDIT"
        b, a = edit["before"].split(), edit["after"].split()
        assert len(b) == len(a) and sum(x != y for x, y in zip(b, a, strict=True)) == 1
        assert difflib.SequenceMatcher(None, edit["before"], edit["after"]).ratio() >= 0.95


# ---- 2. determinism ------------------------------------------------------------------------


def test_same_seed_same_case_bytes_and_ground_truth(cfg: dict[str, Any]) -> None:
    for op, mode in (
        ("party_change", "inplace"),
        ("clause_insert", "rerender"),
        ("metadata_only", "resave"),
    ):
        a = build_case(cfg, None, op, mode, 0)
        b = build_case(cfg, None, op, mode, 0)
        assert a.case is not None and b.case is not None
        assert a.case.pdf == b.case.pdf
        assert a.case.record == b.case.record


def test_different_seed_differs(cfg: dict[str, Any]) -> None:
    other = copy.deepcopy(cfg)
    other["tamper"]["seed"] = int(cfg["tamper"]["seed"]) + 1
    a = build_case(cfg, None, "amount_change", "rerender", 0).case
    b = build_case(other, None, "amount_change", "rerender", 0).case
    assert a is not None and b is not None
    assert a.pdf != b.pdf or a.record["edits"] != b.record["edits"]


def _digest_dir(path: Path) -> dict[str, str]:
    return {
        p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def test_cli_is_byte_identical_across_fresh_processes(tmp_path: Path) -> None:
    outs = []
    for name in ("a", "b"):
        out = tmp_path / name
        subprocess.run(
            [
                sys.executable,
                "tamper.py",
                "--config",
                "configs/default.yaml",
                "--limit",
                "2",
                "--out",
                str(out),
            ],
            cwd=EVAL_DIR,
            check=True,
            capture_output=True,
        )
        outs.append(_digest_dir(out))
    assert outs[0] == outs[1]
    assert len(outs[0]) > 2 * 12  # pdf + json per case, plus the manifest


# ---- 3. coverage (counts are reported, not only asserted) ----------------------------------


def test_every_op_meets_its_target_count(
    run: TamperRun, cfg: dict[str, Any], report: Report
) -> None:
    counts = Counter((c.op, c.mode) for c in run.cases)
    report("tamper cases per (op, mode):")
    for (op, mode), n in sorted(counts.items()):
        report(f"  {op:<18} {mode:<9} {n:>3}")
    report(f"  total {sum(counts.values())}")
    for op, modes in cfg["tamper"]["cases"].items():
        for mode, target in modes.items():
            assert counts[(op, mode)] >= target, (op, mode, counts[(op, mode)], target)
    assert set(counts) >= {(op, "rerender") for op in SINGLE_EDIT_OPS} | {
        ("multi_edit", "rerender")
    }
    for op in ("amount_change", "date_change", "party_change"):
        assert counts[(op, "inplace")] > 0  # 08 C.2: method "both"
    assert counts[("metadata_only", "resave")] > 0
    assert run.stats["counts"] == {f"{o}/{m}": n for (o, m), n in sorted(counts.items())}


def test_cases_span_doc_types_and_page_counts(run: TamperRun, report: Report) -> None:
    types = Counter(c.record["doc_type"] for c in run.cases)
    report(f"tamper cases by doc type: {dict(sorted(types.items()))}")
    assert len(types) == 5
    assert max(c.record["ref"]["page_count"] for c in run.cases) >= 13


# ---- 4. ground truth -----------------------------------------------------------------------


def test_metadata_only_cases_are_content_equivalent(run: TamperRun) -> None:
    cases = [c for c in run.cases if c.op == "metadata_only"]
    assert cases
    for c in cases:
        t = c.record["truth"]
        assert t["file_hash_changed"] and not t["text_root_changed"], c.case_id
        assert t["changed_ref_chunk_ids"] == [] and t["changed_cand_chunk_ids"] == []
        assert c.record["expected_status"] == "CONTENT_EQUIVALENT"
        assert c.record["expected_categories"] == []


def test_content_cases_change_text_root(run: TamperRun) -> None:
    for c in run.cases:
        if c.op == "metadata_only":
            continue
        t = c.record["truth"]
        assert t["file_hash_changed"] and t["text_root_changed"], c.case_id
        assert c.record["expected_status"] == "CHANGED"
        assert t["changed_ref_chunk_ids"] or t["changed_cand_chunk_ids"], c.case_id
        assert c.record["expected_categories"], c.case_id


def _page_of(chunk_id: str) -> int:
    return int(chunk_id[1 : chunk_id.index("-")])


def test_ground_truth_pages_follow_chunk_ids(run: TamperRun) -> None:
    for c in run.cases:
        t = c.record["truth"]
        assert t["changed_pages_ref"] == sorted({_page_of(i) for i in t["changed_ref_chunk_ids"]})
        assert t["changed_pages_cand"] == sorted({_page_of(i) for i in t["changed_cand_chunk_ids"]})


def test_insert_and_delete_flag_only_the_inserted_or_deleted_chunks(run: TamperRun) -> None:
    """Later content shifts (chunk ids move) but is not reported as changed (tests alignment)."""
    ins = [c for c in run.cases if c.op == "clause_insert"]
    dele = [c for c in run.cases if c.op == "clause_delete"]
    assert ins and dele
    for c in ins:
        t = c.record["truth"]
        assert t["changed_ref_chunk_ids"] == [] and len(t["changed_cand_chunk_ids"]) >= 1, c.case_id
    for c in dele:
        t = c.record["truth"]
        assert t["changed_cand_chunk_ids"] == [] and len(t["changed_ref_chunk_ids"]) >= 1, c.case_id


def test_multi_edit_has_two_to_five_ops_and_union_of_categories(run: TamperRun) -> None:
    cases = [c for c in run.cases if c.op == "multi_edit"]
    assert cases
    sizes = Counter(len(c.record["edits"]) for c in cases)
    assert set(sizes) <= {2, 3, 4, 5} and len(sizes) >= 3, sizes
    for c in cases:
        cats = sorted({e["category"] for e in c.record["edits"]})
        assert c.record["expected_categories"] == cats


def test_inplace_cases_keep_page_count_and_are_valid_pdfs(run: TamperRun) -> None:
    cases = [c for c in run.cases if c.mode == "inplace"]
    assert cases
    for c in cases:
        assert c.record["cand"]["page_count"] == c.record["ref"]["page_count"], c.case_id
        assert build_integrity_tree(c.pdf).text_root == c.record["cand"]["text_root"]


# ---- 5. independent ground-truth cross-check (spec-level diff vs rendered-PDF diff) --------


_QUOTES = str.maketrans("‘’‚‛′“”„‟″", "'''''\"\"\"\"\"")
_DASHES = str.maketrans("‐‑‒–—―", "------")


def _norm(text: str) -> str:
    """docs/02 section 3 re-implemented from the spec text (stdlib only, not proofchain_core):
    NFKC, drop soft hyphen / zero-width chars, map quotes and dashes, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate({c: None for c in (0xAD, 0x200B, 0x200C, 0x200D, 0xFEFF)})
    return " ".join(text.translate(_QUOTES).translate(_DASHES).split())


def _spec_level_expectation(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Expected changed texts straight from the two specs; no core, no PDF."""
    old = {b["id"]: b["text"] for b in before["blocks"]}
    new = {b["id"]: b["text"] for b in after["blocks"]}
    ref = [_norm(t) for i, t in old.items() if i not in new or new[i] != t]
    cand = [_norm(t) for i, t in new.items() if i not in old or old[i] != t]
    return ref, cand


def _rendered_texts(record: dict[str, Any]) -> tuple[list[str], list[str]]:
    ref: list[str] = []
    cand: list[str] = []
    for region in record["truth"]["regions"]:
        ref += [_norm(t) for t in region["ref_texts"]]
        cand += [_norm(t) for t in region["cand_texts"]]
    return ref, cand


def _agree(expected: list[str], derived: list[str]) -> str | None:
    """Both directions: every expected text is in the derived chunks and vice versa."""
    joined = " ".join(derived)
    for text in expected:
        if text not in joined:
            return f"expected {text!r} not found in derived chunks"
    for text in derived:
        if not any(text in e for e in expected):
            return f"derived chunk {text!r} is not explained by any changed spec block"
    return None


def test_spec_level_diff_agrees_with_rendered_pdf_diff(run: TamperRun, report: Report) -> None:
    """The ground truth built from rendered trees must equal a direct spec string diff, so a bug
    shared by core's extraction/chunking and ground_truth.py cannot go unnoticed."""
    checked = [c for c in run.cases if c.op != "metadata_only"]
    assert len(checked) >= 20 and len({c.op for c in checked}) >= 10
    disagreements = []
    for c in checked:
        exp_ref, exp_cand = _spec_level_expectation(c.spec_before, c.spec_after)
        got_ref, got_cand = _rendered_texts(c.record)
        problem = _agree(exp_ref, got_ref) or _agree(exp_cand, got_cand)
        if problem:
            disagreements.append(f"{c.case_id}: {problem}")
    report(
        f"ground-truth cross-check: {len(checked) - len(disagreements)}/{len(checked)} cases agree "
        f"({len({c.op for c in checked})} ops, {len({c.mode for c in checked})} modes)"
    )
    assert not disagreements, "\n".join(disagreements[:10])


# ---- 6. in-place coverage floor ------------------------------------------------------------


def test_inplace_party_change_success_rate_is_at_least_half(run: TamperRun, report: Report) -> None:
    s = run.stats["inplace"]["party_change"]
    rate = s["succeeded"] / s["attempted"]
    report(
        f"in-place party_change: attempted {s['attempted']}, succeeded {s['succeeded']}, "
        f"skipped {s['skipped']} -> success rate {rate:.0%}"
    )
    for op, st in sorted(run.stats["inplace"].items()):
        report(f"  in-place {op}: {st['succeeded']}/{st['attempted']} skipped={st['skipped']}")
    assert s["succeeded"] + sum(s["skipped"].values()) == s["attempted"]
    assert rate >= 0.5


def test_inplace_skips_when_the_new_text_overflows_the_block(cfg: dict[str, Any]) -> None:
    """The skip path is real: a name far longer than the original wraps onto extra lines."""
    spec, pdf = generate_one(cfg, 0)
    edit = OPS["party_change"].plan(spec, make_context(spec["doc_type"], 7))
    assert edit is not None
    huge = {**edit[0], "after": edit[0]["after"] + " " + "Extraordinarily Long Name " * 12}
    with pytest.raises(InPlaceSkip) as info:
        apply_inplace(pdf, spec, [huge])
    assert info.value.reason == "overflow"
    with pytest.raises(InPlaceSkip) as info:
        apply_inplace(pdf, spec, [{**edit[0], "kind": "delete"}])
    assert info.value.reason == "unsupported_op"


@pytest.mark.parametrize(
    "second",
    [b"<" + b"AB" * 16 + b">", rb"(:%BW\303SUH\202/H\220\f\2634\241)", rb"(a\(b\)c\d)"],
)
def test_stable_id_handles_hex_and_literal_second_id(second: bytes) -> None:
    """MuPDF randomly writes the second /ID as <hex> or as an escaped literal string."""
    first = b"<" + b"CD" * 16 + b">"
    body = b"%PDF-1.4\n...\nstartxref\n12\n%%EOF\n"
    pdf = b"trailer\n<</Size 3/ID[" + first + second + b"]>>\n" + body
    fixed = _stable_id(pdf)
    assert fixed == b"trailer\n<</Size 3/ID[" + first + first + b"]>>\n" + body
