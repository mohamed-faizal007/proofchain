from app.config import Settings
from app.nlp import warmup as warmup_module


def test_warm_nlp_models_calls_ner_and_embedding_getters_with_configured_settings(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setattr(warmup_module, "get_ner_model", lambda name: calls.__setitem__("ner", name))
    monkeypatch.setattr(
        warmup_module,
        "get_embedding_model",
        lambda enabled, name: calls.__setitem__("embeddings", (enabled, name)),
    )
    monkeypatch.setattr(warmup_module, "get_llm_client", lambda key: calls.__setitem__("llm", key))

    settings = Settings(
        app_env="test",
        nlp_spacy_model="custom-spacy-model",
        nlp_embeddings_enabled=True,
        nlp_embedding_model="custom-embed-model",
        nlp_llm_explanations=False,
    )
    warmup_module.warm_nlp_models(settings)

    assert calls["ner"] == "custom-spacy-model"
    assert calls["embeddings"] == (True, "custom-embed-model")
    assert "llm" not in calls  # nlp_llm_explanations=False -> never constructed


def test_warm_nlp_models_warms_the_llm_client_only_when_explanations_are_enabled(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setattr(warmup_module, "get_ner_model", lambda name: None)
    monkeypatch.setattr(warmup_module, "get_embedding_model", lambda enabled, name: None)
    monkeypatch.setattr(warmup_module, "get_llm_client", lambda key: calls.__setitem__("llm", key))

    settings = Settings(
        app_env="test",
        nlp_llm_explanations=True,
        anthropic_api_key="sk-fake-key",
    )
    warmup_module.warm_nlp_models(settings)

    assert calls["llm"] == "sk-fake-key"


def test_warm_nlp_models_with_embeddings_disabled_passes_enabled_false(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setattr(warmup_module, "get_ner_model", lambda name: None)
    monkeypatch.setattr(
        warmup_module,
        "get_embedding_model",
        lambda enabled, name: calls.__setitem__("embeddings", (enabled, name)),
    )
    monkeypatch.setattr(warmup_module, "get_llm_client", lambda key: None)

    settings = Settings(app_env="test", nlp_embeddings_enabled=False)
    warmup_module.warm_nlp_models(settings)

    assert calls["embeddings"] == (False, settings.nlp_embedding_model)
