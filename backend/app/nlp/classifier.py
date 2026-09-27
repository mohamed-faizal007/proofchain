"""`ChangeClassifier`s (docs/06_NLP_SPEC.md Categories table; Pipeline steps 1-6).

`RuleOnlyClassifier` uses only regex/word-diff/modal rules (`method="RULES"`, no PARTY_CHANGE,
`similarity` always None). `HybridClassifier` additionally uses spaCy NER (PARTY_CHANGE) and
sentence embeddings (real `similarity`, the spec's MINOR_EDIT threshold), each degrading
independently and silently to the rule-only behavior when its model is unavailable (06 "must
degrade gracefully" rule) -- never a partial category (e.g. PARTY_CHANGE must never appear
when NER did not actually run, even if embeddings loaded fine).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

from app.nlp.embeddings import cosine_similarity, get_embedding_model
from app.nlp.entities import diff_entities, extract_dates, extract_money
from app.nlp.ner import diff_party_entities, get_ner_model
from app.nlp.obligation import contains_obligation_term, detect_obligation_change
from app.nlp.token_diff import changed_token_count, diff_tokens
from app.nlp.types import Category, ChangeAnalysis, DiffOp, EntityChange
from proofchain_core.types import ChangeRegion, RegionType

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Method = Literal["RULES", "RULES+EMBEDDINGS"]

# MINOR_EDIT vs CLAUSE_MODIFIED (06 table): "similarity >= 0.90 and <= 3 word tokens changed".
# Without embeddings (RuleOnlyClassifier, or HybridClassifier when the embedding model is
# unavailable) the word-count half is the sole signal, per 06's "degrade gracefully" rule.
_MINOR_EDIT_MAX_CHANGED_TOKENS = 3
_MINOR_EDIT_MIN_SIMILARITY = 0.90

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
_PARTY_ENTITY_TYPE = "PARTY"
_PARTY_LABEL = "party"

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


def _describe_multiset(
    entity_changes: list[EntityChange],
    type_order: tuple[str, ...],
    label_for_type: dict[str, str],
) -> list[str]:
    removed: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    for c in entity_changes:
        if c.before is not None:
            removed.setdefault(c.type, []).append(c.before)
        if c.after is not None:
            added.setdefault(c.type, []).append(c.after)

    descriptions: list[str] = []
    for entity_type in type_order:
        label = label_for_type[entity_type]
        before_values = removed.get(entity_type, [])
        after_values = added.get(entity_type, [])
        for before_value, after_value in zip(before_values, after_values, strict=False):
            descriptions.append(f"the {label} changed from {before_value} to {after_value}")
        for before_value in before_values[len(after_values) :]:
            descriptions.append(f"the {label} {before_value} was removed")
        for after_value in after_values[len(before_values) :]:
            descriptions.append(f"the {label} {after_value} was added")
    return descriptions


def _entity_descriptions(entity_changes: list[EntityChange]) -> list[str]:
    return _describe_multiset(entity_changes, _ENTITY_TYPES_IN_TEMPLATE_ORDER, _ENTITY_LABEL)


def _party_descriptions(party_changes: list[EntityChange]) -> list[str]:
    return _describe_multiset(
        party_changes, (_PARTY_ENTITY_TYPE,), {_PARTY_ENTITY_TYPE: _PARTY_LABEL}
    )


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


def _modified_fallback_category(diff_ops: list[DiffOp], similarity: float | None) -> Category:
    """MINOR_EDIT vs CLAUSE_MODIFIED when no entity/party/obligation category applies (06 table).
    With `similarity` (embeddings available) both conditions are required, per 06's wording;
    without it (embeddings unavailable or not wired in), word count alone decides.
    """
    changed = changed_token_count(diff_ops)
    word_count_ok = changed <= _MINOR_EDIT_MAX_CHANGED_TOKENS
    is_minor = (
        word_count_ok
        if similarity is None
        else (word_count_ok and similarity >= _MINOR_EDIT_MIN_SIMILARITY)
    )
    return Category.MINOR_EDIT if is_minor else Category.CLAUSE_MODIFIED


def _fallback_generic(category: Category) -> str:
    return (
        "a minor wording edit was made"
        if category is Category.MINOR_EDIT
        else "the clause text was modified"
    )


def _analyze_modified(
    region: ChangeRegion,
    party_changes: list[EntityChange],
    similarity: float | None,
    method: Method,
) -> ChangeAnalysis:
    before = region.ref_text or ""
    after = region.cand_text or ""
    diff_ops: list[DiffOp] = diff_tokens(before, after)
    entity_changes = diff_entities(before, after)
    obligation_flip = detect_obligation_change(diff_ops)

    categories = _entity_categories(entity_changes)
    if party_changes:
        categories.add(Category.PARTY_CHANGE)
    if obligation_flip:
        categories.add(Category.OBLIGATION_CHANGE)

    if categories:
        primary = _pick_primary(categories)
        generic = ""  # unreachable in _explain: entity/party/obligation fragments are present
    else:
        primary = _modified_fallback_category(diff_ops, similarity)
        categories = {primary}
        generic = _fallback_generic(primary)

    severity = _DEFAULT_SEVERITY[primary]
    ordered_categories = tuple(c for c in _CATEGORY_ORDER if c in categories)
    entity_descriptions = _entity_descriptions(entity_changes) + _party_descriptions(party_changes)
    explanation = _explain(region, entity_descriptions, obligation_flip, generic)

    return ChangeAnalysis(
        region_id=region.id,
        primary_category=primary,
        categories=ordered_categories,
        severity=severity,
        similarity=similarity,
        entity_changes=tuple(entity_changes) + tuple(party_changes),
        token_diff=tuple(diff_ops),
        explanation=explanation,
        method=method,
    )


_ANALYZERS = {
    RegionType.INSERTED: _analyze_inserted,
    RegionType.DELETED: _analyze_deleted,
}


class RuleOnlyClassifier:
    """`ChangeClassifier` using only regex/word-diff/modal rules (`method="RULES"`, no
    PARTY_CHANGE, `similarity` always None).
    """

    def analyze(self, region: ChangeRegion) -> ChangeAnalysis:
        if region.type is RegionType.MODIFIED:
            return _analyze_modified(region, party_changes=[], similarity=None, method="RULES")
        return _ANALYZERS[region.type](region)


class HybridClassifier:
    """`ChangeClassifier` adding spaCy NER (PARTY_CHANGE) and embedding similarity on top of
    `RuleOnlyClassifier`'s rules. Each model degrades independently: if spaCy is unavailable,
    no PARTY_CHANGE category is ever produced (even when embeddings did load); if the
    embedding model is unavailable, `similarity` stays None and the MINOR_EDIT/CLAUSE_MODIFIED
    split falls back to the word-count-only rule. `method` reflects only the embedding step,
    per 06's `Literal["RULES", "RULES+EMBEDDINGS", ...]`; NER availability is not represented
    there (06 does not distinguish a NER-only method).
    """

    def __init__(
        self,
        ner_getter: Callable[[], Any | None] = get_ner_model,
        embedder_getter: Callable[[], Any | None] = get_embedding_model,
    ) -> None:
        self._ner_getter = ner_getter
        self._embedder_getter = embedder_getter

    def analyze(self, region: ChangeRegion) -> ChangeAnalysis:
        if region.type is not RegionType.MODIFIED:
            return _ANALYZERS[region.type](region)

        before = region.ref_text or ""
        after = region.cand_text or ""
        ner_model = self._ner_getter()
        embedder = self._embedder_getter()

        party_changes = diff_party_entities(before, after, ner_model)
        similarity = cosine_similarity(before, after, embedder) if embedder is not None else None
        method: Method = "RULES+EMBEDDINGS" if embedder is not None else "RULES"

        return _analyze_modified(region, party_changes, similarity, method)
