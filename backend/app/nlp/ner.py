"""spaCy NER (docs/06_NLP_SPEC.md Pipeline step 2, spaCy half): PERSON/ORG/GPE entities feed
PARTY_CHANGE. Regex entities (money/date/percentage/number, P7-01) already own those types, so
spaCy's MONEY/DATE/PERCENT labels are not duplicated here -- only PERSON/ORG/GPE.

Lazy singleton, loaded once on first use; if spaCy or the `en_core_web_sm` model is not
installed the singleton stays None and callers degrade gracefully (06 "must degrade
gracefully" rule): no PARTY_CHANGE is ever produced, rather than raising.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.nlp.types import EntityChange

_PARTY_LABELS = {"PERSON", "ORG", "GPE"}
_PARTY_ENTITY_TYPE = "PARTY"

_model: Any | None = None
_load_attempted = False


def _load_model() -> Any | None:
    try:
        import spacy

        return spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        return None


def get_ner_model() -> Any | None:
    """Lazy singleton; None if spaCy or the model is unavailable. Loaded at most once."""
    global _model, _load_attempted
    if not _load_attempted:
        _model = _load_model()
        _load_attempted = True
    return _model


def extract_party_entities(text: str, model: Any | None) -> list[str]:
    """PERSON/ORG/GPE entities as `"LABEL:text"`, or `[]` if `model` is None (unavailable)."""
    if model is None or not text:
        return []
    doc = model(text)
    return [f"{ent.label_}:{ent.text}" for ent in doc.ents if ent.label_ in _PARTY_LABELS]


def diff_party_entities(before: str, after: str, model: Any | None) -> list[EntityChange]:
    """Multiset diff of PARTY entities, or `[]` if `model` is None (unavailable)."""
    if model is None:
        return []
    before_counts = Counter(extract_party_entities(before, model))
    after_counts = Counter(extract_party_entities(after, model))
    removed = before_counts - after_counts
    added = after_counts - before_counts
    changes = [
        EntityChange(type=_PARTY_ENTITY_TYPE, before=value, after=None)
        for value in sorted(removed)
        for _ in range(removed[value])
    ]
    changes += [
        EntityChange(type=_PARTY_ENTITY_TYPE, before=None, after=value)
        for value in sorted(added)
        for _ in range(added[value])
    ]
    return changes
