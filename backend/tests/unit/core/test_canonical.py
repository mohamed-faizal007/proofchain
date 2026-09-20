"""Table-driven tests for 02_ALGORITHMS.md §3 canonicalization."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from proofchain_core import CANON_VERSION, normalize_text

CASES = [
    # step 1: NFKC
    pytest.param("ﬁnal", "final", id="ligature-fi"),
    pytest.param("ﬂow", "flow", id="ligature-fl"),
    pytest.param("oﬃce", "office", id="ligature-ffi"),
    pytest.param("ＡＢＣ １２３", "ABC 123", id="fullwidth"),
    pytest.param("x²", "x2", id="superscript"),
    pytest.param("é", "é", id="combining-composed"),
    # step 2: removals
    pytest.param("co­op", "coop", id="soft-hyphen"),
    pytest.param("a​b", "ab", id="zwsp"),
    pytest.param("a‌b", "ab", id="zwnj"),
    pytest.param("a‍b", "ab", id="zwj"),
    pytest.param("﻿hello", "hello", id="bom"),
    pytest.param("a ​ b", "a b", id="zero-width-between-spaces"),
    # step 3: quotes
    pytest.param("‘a’", "'a'", id="single-curly"),
    pytest.param("‚‛′", "'''", id="single-other"),
    pytest.param("“q”", '"q"', id="double-curly"),
    pytest.param("„‟", '""', id="double-other"),
    # NFKC (step 1) expands U+2033 to two U+2032 before step 3 can map it to '"'.
    pytest.param("″", "''", id="double-prime-nfkc-first"),
    # step 3: dashes
    pytest.param("1‐2", "1-2", id="hyphen"),
    pytest.param("1‑2", "1-2", id="non-breaking-hyphen"),
    pytest.param("1‒2", "1-2", id="figure-dash"),
    pytest.param("1–2", "1-2", id="en-dash"),
    pytest.param("1—2", "1-2", id="em-dash"),
    pytest.param("1―2", "1-2", id="horizontal-bar"),
    # step 4: whitespace
    pytest.param("a b", "a b", id="nbsp"),
    pytest.param("a\tb\nc\r\nd", "a b c d", id="tab-newline"),
    pytest.param("a   　 b", "a b", id="mixed-unicode-space-run"),
    # step 5: strip
    pytest.param("  \n hi \t", "hi", id="strip"),
    pytest.param("", "", id="empty"),
    pytest.param("  \t\n​", "", id="whitespace-only"),
    # preserved
    pytest.param("Rs ₹1,00,000.50", "Rs ₹1,00,000.50", id="rupee-preserved"),
    pytest.param("$5 €6 £7", "$5 €6 £7", id="currency-preserved"),
    pytest.param("Due: 12/03/2024, PAID.", "Due: 12/03/2024, PAID.", id="case-punct-digits"),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_canon_version() -> None:
    assert CANON_VERSION == 2


def test_case_is_preserved() -> None:
    assert normalize_text("ABC abc") == "ABC abc"


@given(st.text())
def test_idempotent(s: str) -> None:
    once = normalize_text(s)
    assert normalize_text(once) == once


@given(st.text())
def test_output_shape(s: str) -> None:
    out = normalize_text(s)
    assert out == out.strip(" ")
    assert "  " not in out
    assert not set(out) & set("­​‌‍﻿\t\n\r ")


def test_not_idempotent_zwj_between_base_and_mark_known_limitation() -> None:
    """P1-09 finding 4: NFKC (step 1) cannot compose across a ZWJ; step 2 then removes it.

    The result is a decomposed 'é'; a second pass composes it. Spec-compliant and
    deterministic (same input, same output), but normalize_text is not idempotent here.
    Callers must never re-normalize stored canonical text.
    """
    raw = "e\u200d\u0301"
    once = normalize_text(raw)
    assert once == "e\u0301"
    assert normalize_text(once) == "\u00e9"
    assert normalize_text(raw) == once
