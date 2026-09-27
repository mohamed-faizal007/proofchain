"""Obligation/negation flip detection (docs/06_NLP_SPEC.md Pipeline step 3, OBLIGATION_CHANGE row).

A "flip" is a change in obligation strength within one diff opcode: a strong modal
(shall/must/will) traded for the weak modal "may" (or the reverse), or a negation word
(not/no/never/without) added or removed. Swapping one negation word for another (e.g.
"not" -> "never") is not a flip -- the negation is present on both sides, only the word
changed.
"""

from __future__ import annotations

import re

from app.nlp.types import DiffOp

_STRONG_MODALS = {"shall", "must", "will"}
_WEAK_MODAL = "may"
_NEGATIONS = {"not", "no", "never", "without"}
OBLIGATION_TERMS = _STRONG_MODALS | {_WEAK_MODAL} | _NEGATIONS

_WORD_RE = re.compile(r"\w+")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def contains_obligation_term(text: str) -> bool:
    """True if `text` mentions any modal/negation term from `OBLIGATION_TERMS`."""
    return bool(_words(text) & OBLIGATION_TERMS)


def _tuple_words(tokens: tuple[str, ...]) -> set[str]:
    return {t.lower() for t in tokens}


def _is_modal_flip(before: set[str], after: set[str]) -> bool:
    before_weak = _WEAK_MODAL in before
    after_weak = _WEAK_MODAL in after
    strong_to_weak = bool(before & _STRONG_MODALS) and after_weak and not before_weak
    weak_to_strong = bool(after & _STRONG_MODALS) and before_weak and not after_weak
    return strong_to_weak or weak_to_strong


def _is_negation_flip(before: set[str], after: set[str]) -> bool:
    return bool(before & _NEGATIONS) != bool(after & _NEGATIONS)


def detect_obligation_change(diff_ops: list[DiffOp]) -> bool:
    """True if any non-equal opcode flips a modal or a negation (see module docstring)."""
    for op in diff_ops:
        if op.op == "equal":
            continue
        before = _tuple_words(op.before)
        after = _tuple_words(op.after)
        if _is_modal_flip(before, after) or _is_negation_flip(before, after):
            return True
    return False
