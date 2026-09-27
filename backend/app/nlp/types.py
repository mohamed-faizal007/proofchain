"""Shared NLP dataclasses (docs/06_NLP_SPEC.md Interface). Fields beyond token_diff and
entity_changes are wired up in P7-02+; this module exists now so those tasks share one shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal


class Category(StrEnum):
    AMOUNT_CHANGE = "AMOUNT_CHANGE"
    DATE_CHANGE = "DATE_CHANGE"
    PARTY_CHANGE = "PARTY_CHANGE"
    PERCENTAGE_CHANGE = "PERCENTAGE_CHANGE"
    NUMBER_CHANGE = "NUMBER_CHANGE"
    OBLIGATION_CHANGE = "OBLIGATION_CHANGE"
    CLAUSE_ADDED = "CLAUSE_ADDED"
    CLAUSE_REMOVED = "CLAUSE_REMOVED"
    CLAUSE_MODIFIED = "CLAUSE_MODIFIED"
    MINOR_EDIT = "MINOR_EDIT"


DiffOpKind = Literal["equal", "insert", "delete", "replace"]


@dataclass(frozen=True, slots=True)
class DiffOp:
    """One `difflib.SequenceMatcher` opcode over word tokens, for UI highlighting."""

    op: DiffOpKind
    before: tuple[str, ...]
    after: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "before": list(self.before), "after": list(self.after)}


@dataclass(frozen=True, slots=True)
class EntityChange:
    """One multiset difference between before/after entities of a given `type`.

    Exactly one of `before`/`after` is None: None on `before` means the entity was added,
    None on `after` means it was removed.
    """

    type: str
    before: str | None
    after: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "before": self.before, "after": self.after}


@dataclass(frozen=True, slots=True)
class ChangeAnalysis:
    region_id: str
    primary_category: Category
    categories: tuple[Category, ...]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    similarity: float | None
    entity_changes: tuple[EntityChange, ...]
    token_diff: tuple[DiffOp, ...]
    explanation: str
    method: Literal["RULES", "RULES+EMBEDDINGS", "RULES+EMBEDDINGS+LLM"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "primary_category": self.primary_category.value,
            "categories": [c.value for c in self.categories],
            "severity": self.severity,
            "similarity": self.similarity,
            "entity_changes": [e.to_dict() for e in self.entity_changes],
            "token_diff": [d.to_dict() for d in self.token_diff],
            "explanation": self.explanation,
            "method": self.method,
        }
