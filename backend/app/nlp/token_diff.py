"""Word-level diff (docs/06_NLP_SPEC.md Pipeline step 1)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.nlp.types import DiffOp, DiffOpKind

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def diff_tokens(before: str, after: str) -> list[DiffOp]:
    before_tokens = tokenize(before)
    after_tokens = tokenize(after)
    matcher = SequenceMatcher(a=before_tokens, b=after_tokens, autojunk=False)
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        op: DiffOpKind = "replace" if tag == "replace" else tag
        ops.append(
            DiffOp(
                op=op,
                before=tuple(before_tokens[i1:i2]),
                after=tuple(after_tokens[j1:j2]),
            )
        )
    return ops


def changed_token_count(ops: list[DiffOp]) -> int:
    """Count of before+after tokens touched by non-equal ops, for the MINOR_EDIT threshold."""
    return sum(len(op.before) + len(op.after) for op in ops if op.op != "equal")
