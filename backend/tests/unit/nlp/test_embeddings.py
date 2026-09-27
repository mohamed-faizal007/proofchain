import math
import sys

import pytest

from app.nlp.embeddings import cosine_similarity


class _FakeEmbedder:
    """Maps a fixed text -> a fixed vector, for deterministic cosine-similarity tests."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[t] for t in texts]


def test_cosine_similarity_identical_vectors_is_one():
    model = _FakeEmbedder({"a": [1.0, 0.0], "b": [1.0, 0.0]})
    assert cosine_similarity("a", "b", model) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    model = _FakeEmbedder({"a": [1.0, 0.0], "b": [0.0, 1.0]})
    assert cosine_similarity("a", "b", model) == pytest.approx(0.0)


def test_cosine_similarity_known_value():
    model = _FakeEmbedder({"a": [1.0, 1.0], "b": [1.0, 0.0]})
    assert cosine_similarity("a", "b", model) == pytest.approx(1 / math.sqrt(2))


def test_cosine_similarity_returns_none_when_model_is_none():
    assert cosine_similarity("a", "b", None) is None


def test_cosine_similarity_returns_none_for_a_zero_vector():
    # defensive: guards a division by zero if an embedding model ever returns a null vector
    model = _FakeEmbedder({"a": [0.0, 0.0], "b": [1.0, 0.0]})
    assert cosine_similarity("a", "b", model) is None


def test_cosine_similarity_returns_none_for_empty_before_or_after():
    model = _FakeEmbedder({"": [0.0, 0.0], "a": [1.0, 0.0], "b": [1.0, 0.0]})
    assert cosine_similarity("", "b", model) is None
    assert cosine_similarity("a", "", model) is None


def test_get_embedding_model_returns_none_when_loader_reports_unavailable(monkeypatch):
    import app.nlp.embeddings as emb_module

    monkeypatch.setattr(emb_module, "_load_attempted", False)
    monkeypatch.setattr(emb_module, "_model", None)
    monkeypatch.setattr(emb_module, "_load_model", lambda: None)
    assert emb_module.get_embedding_model() is None


def test_get_embedding_model_caches_after_first_load(monkeypatch):
    import app.nlp.embeddings as emb_module

    calls = []

    def _fake_loader():
        calls.append(1)
        return "sentinel-model"

    monkeypatch.setattr(emb_module, "_load_attempted", False)
    monkeypatch.setattr(emb_module, "_model", None)
    monkeypatch.setattr(emb_module, "_load_model", _fake_loader)
    assert emb_module.get_embedding_model() == "sentinel-model"
    assert emb_module.get_embedding_model() == "sentinel-model"
    assert len(calls) == 1


def test_load_model_returns_none_when_sentence_transformers_is_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    import app.nlp.embeddings as emb_module

    assert emb_module._load_model() is None


@pytest.mark.nlp
def test_load_model_returns_none_when_model_construction_raises_oserror(monkeypatch):
    st = pytest.importorskip("sentence_transformers")
    import app.nlp.embeddings as emb_module

    def _raise_oserror(name: str):
        raise OSError(f"model '{name}' not found")

    monkeypatch.setattr(st, "SentenceTransformer", _raise_oserror)
    assert emb_module._load_model() is None


@pytest.mark.nlp
def test_real_embedding_model_loads_and_computes_similarity():
    import app.nlp.embeddings as emb_module

    emb_module._load_attempted = False
    emb_module._model = None
    model = emb_module.get_embedding_model()
    assert model is not None

    identical = cosine_similarity(
        "The tenant shall pay rent monthly.", "The tenant shall pay rent monthly.", model
    )
    unrelated = cosine_similarity(
        "The tenant shall pay rent monthly.", "Photosynthesis converts sunlight to energy.", model
    )
    assert identical is not None and unrelated is not None
    assert identical == pytest.approx(1.0, abs=0.01)
    assert unrelated < identical
