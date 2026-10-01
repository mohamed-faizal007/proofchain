"""The three ablation arms of the classification evaluation (docs/06 Evaluation, docs/08 C.3).

``rules``          regex / word-diff / modal rules only (``RuleOnlyClassifier``).
``rules_ner``      rules + spaCy NER, embeddings off (PARTY_CHANGE becomes possible).
``rules_ner_emb``  rules + NER + sentence embeddings (the production ``HybridClassifier``).

06 only compares "rules vs rules+embeddings"; the NER-only arm separates the two effects
(PARTY_CHANGE needs NER, the MINOR_EDIT / CLAUSE_MODIFIED split needs similarity).

A hybrid arm whose model is missing would silently behave like a weaker arm (the classifier
degrades gracefully, by design), so ``build_arms`` refuses to build instead of producing numbers
that are labelled as one arm and measure another.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import metadata
from typing import Any

from app.nlp.classifier import ChangeClassifier, HybridClassifier, RuleOnlyClassifier
from app.nlp.embeddings import get_embedding_model
from app.nlp.ner import get_ner_model

ARM_NAMES = ("rules", "rules_ner", "rules_ner_emb")
SPACY_MODEL = "en_core_web_sm"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
INSTALL_HINT = (
    'cd backend; pip install -e ".[dev,eval,nlp]"; python -m spacy download en_core_web_sm'
)


class ArmUnavailable(RuntimeError):
    """A real-model arm cannot run because its model is not installed."""


def build_arms(
    ner_getter: Callable[[], Any | None] = get_ner_model,
    embedder_getter: Callable[[], Any | None] = get_embedding_model,
) -> dict[str, ChangeClassifier]:
    ner, embedder = ner_getter(), embedder_getter()
    if ner is None:
        raise ArmUnavailable(f"spaCy model {SPACY_MODEL} is not available. Install: {INSTALL_HINT}")
    if embedder is None:
        raise ArmUnavailable(
            f"embedding model {EMBEDDING_MODEL} is not available. Install: {INSTALL_HINT}"
        )
    return {
        "rules": RuleOnlyClassifier(),
        "rules_ner": HybridClassifier(ner_getter=lambda: ner, embedder_getter=lambda: None),
        "rules_ner_emb": HybridClassifier(ner_getter=lambda: ner, embedder_getter=lambda: embedder),
    }


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not installed"


def environment() -> dict[str, str]:
    """Versions behind the real-model numbers (written next to, not into, the metrics)."""
    return {
        "spacy": _version("spacy"),
        "spacy_model": SPACY_MODEL,
        "spacy_model_version": _version(SPACY_MODEL.replace("_", "-")),
        "sentence_transformers": _version("sentence-transformers"),
        "torch": _version("torch"),
        "embedding_model": EMBEDDING_MODEL,
    }
