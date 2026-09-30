"""Tamper operations on a corpus spec (docs/08 C.2). Each op is a pure function of (spec, context).

``OPS[name].plan(spec, ctx)`` returns the edit records (see spec_edit.py) or ``None`` when the
document has nothing the op can act on. Every random choice comes from ``ctx.rng``.
``metadata_only`` plans no spec edit (the PDF is re-saved, see inplace.py); ``multi_edit`` chains
2-5 of the single-edit ops on distinct blocks.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from faker import Faker

from spec_edit import apply_edits, next_block_id, replace_span
from templates import TYPES
from templates.slots import MONTHS, SlotContext, fill, format_date, format_inr

Edit = dict[str, Any]
Plan = Callable[[dict[str, Any], "OpContext"], list[Edit] | None]


@dataclass
class OpContext:
    rng: random.Random
    fake: Faker
    party_kind: str
    touched: set[str] = field(default_factory=set)  # block ids already edited by this case
    multi_range: tuple[int, int] = (2, 5)


def make_context(doc_type: str, seed: int, multi_range: tuple[int, int] = (2, 5)) -> OpContext:
    fake = Faker("en_IN")
    fake.seed_instance(seed)
    return OpContext(random.Random(seed), fake, TYPES[doc_type].party_kind, set(), multi_range)


@dataclass(frozen=True)
class OpDef:
    name: str
    modes: tuple[str, ...]
    plan: Plan


def _edit(
    op: str, category: str, block: dict[str, Any], text: str, ents: list[dict[str, Any]]
) -> Edit:
    return {
        "op": op,
        "category": category,
        "kind": "replace",
        "block_id": block["id"],
        "before": block["text"],
        "after": text,
        "entities": ents,
    }


def _free_blocks(spec: dict[str, Any], ctx: OpContext, kind: str | None = None) -> list[Any]:
    return [
        b
        for b in spec["blocks"]
        if b["id"] not in ctx.touched and (kind is None or b["kind"] == kind)
    ]


# ---- entity ops ---------------------------------------------------------------------------


def _new_amount(old: str, ctx: OpContext) -> str:
    n = int(old.replace("₹", "").replace(",", ""))
    if ctx.rng.random() < 0.5:
        return format_inr(n * ctx.rng.choice((2, 3, 5, 10)))
    return format_inr(n + ctx.rng.choice((100, 500, 1000, 5000, 25000)))


def _new_date(old: str, ctx: OpContext) -> str:
    day, month, year = old.split()
    d = date(int(year), MONTHS.index(month) + 1, int(day))
    return format_date(d + timedelta(days=ctx.rng.choice((-1, 1)) * ctx.rng.randint(1, 365)))


def _new_party(old: str, ctx: OpContext) -> str:
    draw = ctx.fake.name if ctx.party_kind == "person" else ctx.fake.company
    new = str(draw())
    while new == old:
        new = str(draw())
    return new


def _new_percentage(old: str, ctx: OpContext) -> str:
    choices = [f"{p}%" for p in (2, 5, 7.5, 10, 12, 15, 18, 20, 25, 30)]
    return ctx.rng.choice([c.replace(".0", "") for c in choices if c != old])


def _new_number(old: str, ctx: OpContext) -> str:
    n = int(old)
    new = max(1, n + ctx.rng.choice((-5, -3, -2, -1, 1, 2, 3, 5, 10, 12)))
    return str(new if new != n else n + 1)


def _entity_plan(
    op: str, category: str, kind: str, propose: Callable[[str, OpContext], str]
) -> Plan:
    def plan(spec: dict[str, Any], ctx: OpContext) -> list[Edit] | None:
        cands = [
            (b, e) for b in _free_blocks(spec, ctx) for e in b["entities"] if e["kind"] == kind
        ]
        if not cands:
            return None
        block, ent = ctx.rng.choice(cands)
        new = propose(ent["value"], ctx)
        text, ents = replace_span(block["text"], block["entities"], ent["start"], ent["end"], new)
        ctx.touched.add(block["id"])
        return [
            {
                **_edit(op, category, block, text, ents),
                "span": [ent["start"], ent["end"]],
                "old": ent["value"],
                "new": new,
            }
        ]

    return plan


# ---- text ops -----------------------------------------------------------------------------

_MODAL = re.compile(r"\b(shall|must)\b")


def _plan_obligation(spec: dict[str, Any], ctx: OpContext) -> list[Edit] | None:
    cands = [b for b in _free_blocks(spec, ctx, "clause") if _MODAL.search(b["text"])]
    if not cands:
        return None
    block = ctx.rng.choice(cands)
    m = _MODAL.search(block["text"])
    assert m is not None
    new = "may" if ctx.rng.random() < 0.5 else f"{m.group(1)} not"
    text, ents = replace_span(block["text"], block["entities"], m.start(), m.end(), new)
    ctx.touched.add(block["id"])
    return [_edit("obligation_flip", "OBLIGATION_CHANGE", block, text, ents)]


_INSERT_BANK = (
    "Either party may terminate this agreement with immediate effect if the other party fails to "
    "remedy a material breach within {days} days of written notice.",
    "A further sum of {amount} shall be payable within {days} days of a written demand.",
    "All disputes arising out of this agreement shall be referred to arbitration in {city}.",
    "An additional charge of {pct} per month shall apply to any amount overdue after {date}.",
    "The security deposit of {amount} shall be forfeited if this agreement is terminated before "
    "{date}.",
    "Neither party shall assign its rights under this agreement without the prior written consent "
    "of the other party.",
    "The parties shall review the terms of this agreement every {months} months.",
    "Any notice under this agreement shall be deemed received {days} days after dispatch.",
)


def _plan_insert(spec: dict[str, Any], ctx: OpContext) -> list[Edit] | None:
    anchors = _free_blocks(spec, ctx, "clause")
    if not anchors:
        return None
    anchor = ctx.rng.choice(anchors)
    text, ents = fill(ctx.rng.choice(_INSERT_BANK), SlotContext(ctx.rng, ctx.fake))
    new_id = next_block_id(spec)
    ctx.touched.update((anchor["id"], new_id))
    return [
        {
            "op": "clause_insert",
            "category": "CLAUSE_ADDED",
            "kind": "insert",
            "block_id": new_id,
            "insert_after": anchor["id"],
            "after_block_id": new_id,
            "before": None,
            "after": text,
            "entities": ents,
        }
    ]


def _plan_delete(spec: dict[str, Any], ctx: OpContext) -> list[Edit] | None:
    cands = _free_blocks(spec, ctx, "clause")
    if not cands:
        return None
    block = ctx.rng.choice(cands)
    ctx.touched.add(block["id"])
    return [
        {
            "op": "clause_delete",
            "category": "CLAUSE_REMOVED",
            "kind": "delete",
            "block_id": block["id"],
            "before": block["text"],
            "after": None,
            "entities": [],
        }
    ]


_REWORD_PREFIXES = (
    "Subject to the other provisions of this agreement,",
    "For the avoidance of doubt and without limiting the foregoing,",
    "Notwithstanding anything to the contrary elsewhere herein,",
    "In accordance with the terms set out in this agreement,",
)
_LOWERABLE = {"The", "Either", "Each", "Any", "All", "If", "Where", "No", "A", "An"}
_NUMBERED = re.compile(r"^\d+\.\d+ ")


def _plan_reword(spec: dict[str, Any], ctx: OpContext) -> list[Edit] | None:
    cands = _free_blocks(spec, ctx, "clause")
    if not cands:
        return None
    block = ctx.rng.choice(cands)
    text, ents = block["text"], block["entities"]
    m = _NUMBERED.match(text)
    at = m.end() if m else 0
    first = text[at:].split(" ", 1)[0]
    if first in _LOWERABLE:  # the first char is not part of any entity here
        text, ents = replace_span(text, ents, at, at + 1, first[0].lower())
    text, ents = replace_span(text, ents, at, at, ctx.rng.choice(_REWORD_PREFIXES) + " ")
    ctx.touched.add(block["id"])
    return [_edit("clause_reword", "CLAUSE_MODIFIED", block, text, ents)]


def _plan_typo(spec: dict[str, Any], ctx: OpContext) -> list[Edit] | None:
    words: list[tuple[dict[str, Any], re.Match[str]]] = []
    for b in _free_blocks(spec, ctx, "clause"):
        if len(b["text"]) < 50:
            continue
        for m in re.finditer(r"[A-Za-z]{6,}", b["text"]):
            if not any(e["start"] < m.end() and m.start() < e["end"] for e in b["entities"]):
                words.append((b, m))
    if not words:
        return None
    block, m = ctx.rng.choice(words)
    word = m.group()
    i = ctx.rng.randint(1, len(word) - 3)
    new = (
        word[:i] + word[i + 1] + word[i] + word[i + 2 :]
        if word[i] != word[i + 1]
        else (word[:i] + word[i + 1 :])
    )
    text, ents = replace_span(block["text"], block["entities"], m.start(), m.end(), new)
    ctx.touched.add(block["id"])
    return [_edit("typo_fix", "MINOR_EDIT", block, text, ents)]


# ---- registry -----------------------------------------------------------------------------

_SINGLE: dict[str, tuple[tuple[str, ...], Plan]] = {
    "amount_change": (
        ("rerender", "inplace"),
        _entity_plan("amount_change", "AMOUNT_CHANGE", "AMOUNT", _new_amount),
    ),
    "date_change": (
        ("rerender", "inplace"),
        _entity_plan("date_change", "DATE_CHANGE", "DATE", _new_date),
    ),
    "party_change": (
        ("rerender", "inplace"),
        _entity_plan("party_change", "PARTY_CHANGE", "PARTY", _new_party),
    ),
    "percentage_change": (
        ("rerender",),
        _entity_plan("percentage_change", "PERCENTAGE_CHANGE", "PERCENTAGE", _new_percentage),
    ),
    "number_change": (
        ("rerender",),
        _entity_plan("number_change", "NUMBER_CHANGE", "NUMBER", _new_number),
    ),
    "obligation_flip": (("rerender",), _plan_obligation),
    "clause_insert": (("rerender",), _plan_insert),
    "clause_delete": (("rerender",), _plan_delete),
    "clause_reword": (("rerender",), _plan_reword),
    "typo_fix": (("rerender",), _plan_typo),
}
SINGLE_EDIT_OPS: tuple[str, ...] = tuple(_SINGLE)


def _plan_multi(spec: dict[str, Any], ctx: OpContext) -> list[Edit] | None:
    want = ctx.rng.randint(*ctx.multi_range)
    edits: list[Edit] = []
    current = spec
    for _ in range(12 * want):
        if len(edits) >= want:
            break
        name = ctx.rng.choice(SINGLE_EDIT_OPS)
        step = _SINGLE[name][1](current, ctx)
        if step is not None:
            edits += step
            current = apply_edits(current, step)
    return edits if len(edits) >= ctx.multi_range[0] else None


OPS: dict[str, OpDef] = {
    **{name: OpDef(name, modes, plan) for name, (modes, plan) in _SINGLE.items()},
    "metadata_only": OpDef("metadata_only", ("resave",), lambda spec, ctx: []),
    "multi_edit": OpDef("multi_edit", ("rerender",), _plan_multi),
}
