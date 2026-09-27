"""Rule-based `ChangeClassifier` (docs/06_NLP_SPEC.md Categories table; Pipeline steps
1, 2 (regex half), 3, 5, 6). Embeddings (step 4, similarity) and spaCy NER (PARTY_CHANGE,
the other half of step 2) are P7-03; until then `similarity` is always None and
PARTY_CHANGE is never produced -- a name-only substitution (e.g. a counterparty change)
has no entity or obligation signal and falls through to the CLAUSE_MODIFIED/MINOR_EDIT
word-count heuristic below. See PROGRESS.md's P7-02 entry for the resulting known limitation.
"""

from __future__ import annotations

from typing import Literal, Protocol

from app.nlp.entities import diff_entities, extract_dates, extract_money
from app.nlp.obligation import contains_obligation_term, detect_obligation_change
from app.nlp.token_diff import changed_token_count, diff_tokens
from app.nlp.types import Category, ChangeAnalysis, DiffOp, EntityChange
from proofchain_core.types import ChangeRegion, RegionType

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# MINOR_EDIT vs CLAUSE_MODIFIED (06 table) is stated in terms of embedding similarity
# (P7-03, not available yet); until then this word-count threshold is the sole signal,
# per the "degrade gracefully" engineering rule in 06.
_MINOR_EDIT_MAX_CHANGED_TOKENS = 3

_SEVERITY_RANK: dict[Severity, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# 06 Categories table order decides primary_category ties.
_CATEGORY_ORDER = [
    Category.AMOUNT_CHANGE,
    Category.DATE_CHANGE,
    Category.PARTY_CHANGE,
    Category.PERCENTAGE_CHANGE,
    Category.NUMBER_CHANGE,
    Category.OBLIGATION_CHANGE,
    Category.CLAUSE_ADDED,
    Category.CLAUSE_REMOVED,
    Category.CLAUSE_MODIFIED,
    Category.MINOR_EDIT,
]

_DEFAULT_SEVERITY: dict[Category, Severity] = {
    Category.AMOUNT_CHANGE: "HIGH",
    Category.DATE_CHANGE: "HIGH",
    Category.PARTY_CHANGE: "HIGH",
    Category.PERCENTAGE_CHANGE: "HIGH",
    Category.NUMBER_CHANGE: "MEDIUM",
    Category.OBLIGATION_CHANGE: "CRITICAL",
    Category.CLAUSE_ADDED: "MEDIUM",
    Category.CLAUSE_REMOVED: "MEDIUM",
    Category.CLAUSE_MODIFIED: "MEDIUM",
    Category.MINOR_EDIT: "LOW",
}

_ESCALATED_SEVERITY: Severity = "HIGH"

_ENTITY_TYPE_TO_CATEGORY = {
    "MONEY": Category.AMOUNT_CHANGE,
    "DATE": Category.DATE_CHANGE,
    "PERCENTAGE": Category.PERCENTAGE_CHANGE,
    "NUMBER": Category.NUMBER_CHANGE,
}
_ENTITY_LABEL = {
    "MONEY": "amount",
    "DATE": "date",
    "PERCENTAGE": "percentage",
    "NUMBER": "number",
}
_ENTITY_TYPES_IN_TEMPLATE_ORDER = ("MONEY", "DATE", "PERCENTAGE", "NUMBER")

_OBLIGATION_FRAGMENT = (
    "an obligation term changed (shall/must/will <-> may, or a negation was added/removed)"
)


class ChangeClassifier(Protocol):
    def analyze(self, region: ChangeRegion) -> ChangeAnalysis: ...


def _entity_categories(entity_changes: list[EntityChange]) -> set[Category]:
    return {
        _ENTITY_TYPE_TO_CATEGORY[c.type]
        for c in entity_changes
        if c.type in _ENTITY_TYPE_TO_CATEGORY
    }


def _pick_primary(categories: set[Category]) -> Category:
    return min(
        categories,
        key=lambda c: (-_SEVERITY_RANK[_DEFAULT_SEVERITY[c]], _CATEGORY_ORDER.index(c)),
    )


def _entity_descriptions(entity_changes: list[EntityChange]) -> list[str]:
    removed: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    for c in entity_changes:
        if c.before is not None:
            removed.setdefault(c.type, []).append(c.before)
        if c.after is not None:
            added.setdefault(c.type, []).append(c.after)

    descriptions: list[str] = []
    for entity_type in _ENTITY_TYPES_IN_TEMPLATE_ORDER:
        label = _ENTITY_LABEL[entity_type]
        before_values = removed.get(entity_type, [])
        after_values = added.get(entity_type, [])
        for before_value, after_value in zip(before_values, after_values, strict=False):
            descriptions.append(f"the {label} changed from {before_value} to {after_value}")
        for before_value in before_values[len(after_values) :]:
            descriptions.append(f"the {label} {before_value} was removed")
        for after_value in after_values[len(before_values) :]:
            descriptions.append(f"the {label} {after_value} was added")
    return descriptions


def _location_prefix(region: ChangeRegion) -> str:
    page = region.cand_page if region.cand_page is not None else region.ref_page
    parts: list[str] = []
    if region.section_title:
        parts.append(f'Section "{region.section_title}"')
    if page is not None:
        parts.append(f"page {page}")
    if not parts:
        return "In this document"
    return "In " + ", ".join(parts)


def _explain(
    region: ChangeRegion,
    entity_descriptions: list[str],
    obligation_flip: bool,
    generic: str,
) -> str:
    fragments = list(entity_descriptions)
    if obligation_flip:
        fragments.append(_OBLIGATION_FRAGMENT)
    if not fragments:
        fragments.append(generic)
    return f"{_location_prefix(region)}: {'; '.join(fragments)}."


def _analyze_inserted(region: ChangeRegion) -> ChangeAnalysis:
    text = region.cand_text or ""
    escalate = bool(extract_money(text) or extract_dates(text) or contains_obligation_term(text))
    severity = _ESCALATED_SEVERITY if escalate else _DEFAULT_SEVERITY[Category.CLAUSE_ADDED]
    generic = "a new clause was added"
    if escalate:
        generic += " (it mentions an amount, date, or obligation term)"
    return ChangeAnalysis(
        region_id=region.id,
        primary_category=Category.CLAUSE_ADDED,
        categories=(Category.CLAUSE_ADDED,),
        severity=severity,
        similarity=None,
        entity_changes=(),
        token_diff=tuple(diff_tokens("", text)),
        explanation=_explain(region, [], False, generic),
        method="RULES",
    )


def _analyze_deleted(region: ChangeRegion) -> ChangeAnalysis:
    text = region.ref_text or ""
    escalate = bool(extract_money(text) or extract_dates(text) or contains_obligation_term(text))
    severity = _ESCALATED_SEVERITY if escalate else _DEFAULT_SEVERITY[Category.CLAUSE_REMOVED]
    generic = "a clause was removed"
    if escalate:
        generic += " (it mentioned an amount, date, or obligation term)"
    return ChangeAnalysis(
        region_id=region.id,
        primary_category=Category.CLAUSE_REMOVED,
        categories=(Category.CLAUSE_REMOVED,),
        severity=severity,
        similarity=None,
        entity_changes=(),
        token_diff=tuple(diff_tokens(text, "")),
        explanation=_explain(region, [], False, generic),
        method="RULES",
    )


def _analyze_modified(region: ChangeRegion) -> ChangeAnalysis:
    before = region.ref_text or ""
    after = region.cand_text or ""
    diff_ops: list[DiffOp] = diff_tokens(before, after)
    entity_changes = diff_entities(before, after)
    obligation_flip = detect_obligation_change(diff_ops)

    categories = _entity_categories(entity_changes)
    if obligation_flip:
        categories.add(Category.OBLIGATION_CHANGE)

    if categories:
        primary = _pick_primary(categories)
        generic = ""  # unreachable in _explain: entity/obligation fragments are always present
    else:
        changed = changed_token_count(diff_ops)
        primary = (
            Category.MINOR_EDIT
            if changed <= _MINOR_EDIT_MAX_CHANGED_TOKENS
            else Category.CLAUSE_MODIFIED
        )
        categories = {primary}
        generic = (
            "a minor wording edit was made"
            if primary is Category.MINOR_EDIT
            else "the clause text was modified"
        )

    severity = _DEFAULT_SEVERITY[primary]
    ordered_categories = tuple(c for c in _CATEGORY_ORDER if c in categories)
    entity_descriptions = _entity_descriptions(entity_changes)
    explanation = _explain(region, entity_descriptions, obligation_flip, generic)

    return ChangeAnalysis(
        region_id=region.id,
        primary_category=primary,
        categories=ordered_categories,
        severity=severity,
        similarity=None,
        entity_changes=tuple(entity_changes),
        token_diff=tuple(diff_ops),
        explanation=explanation,
        method="RULES",
    )


_ANALYZERS = {
    RegionType.INSERTED: _analyze_inserted,
    RegionType.DELETED: _analyze_deleted,
    RegionType.MODIFIED: _analyze_modified,
}


class RuleOnlyClassifier:
    """`ChangeClassifier` using only regex/word-diff/modal rules (`method="RULES"`)."""

    def analyze(self, region: ChangeRegion) -> ChangeAnalysis:
        return _ANALYZERS[region.type](region)
