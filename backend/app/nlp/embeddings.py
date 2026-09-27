"""Sentence-embedding cosine similarity (docs/06_NLP_SPEC.md Pipeline step 4), MODIFIED
regions only.

Lazy singleton (`sentence-transformers` "all-MiniLM-L6-v2", CPU), loaded once on first use;
None if the package or model is unavailable, so callers degrade gracefully (06 "must degrade
gracefully" rule): `similarity` stays None rather than raising.
"""

from __future__ import annotations

import math
from typing import Any

_model: Any | None = None
_load_attempted = False


def _load_model() -> Any | None:
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer("all-MiniLM-L6-v2")
    except (ImportError, OSError):
        return None


def get_embedding_model() -> Any | None:
    """Lazy singleton; None if sentence-transformers or the model is unavailable."""
    global _model, _load_attempted
    if not _load_attempted:
        _model = _load_model()
        _load_attempted = True
    return _model


def cosine_similarity(before: str, after: str, model: Any | None) -> float | None:
    """Cosine similarity of `before`/`after` embeddings, or None if `model` is None
    (unavailable) or either text is empty (nothing to embed).
    """
    if model is None or not before or not after:
        return None
    vectors = model.encode([before, after])
    a, b = vectors[0], vectors[1]
    dot = sum(float(x) * float(y) for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(float(x) * float(x) for x in a))
    norm_b = math.sqrt(sum(float(x) * float(x) for x in b))
    if norm_a == 0 or norm_b == 0:
        return None
    return float(dot / (norm_a * norm_b))
