"""Startup model warm-up (docs/06_NLP_SPEC.md: "warmed at startup when NLP_ENABLED=true").

Synchronous by design: `app.main`'s lifespan runs it via `anyio.to_thread.run_sync` so the
cold spaCy/sentence-transformers/Anthropic-client load happens once at startup, off the event
loop, instead of stalling the first real `/verify` or `/diff` request. Never raises: each
getter already degrades to `None` internally on any failure (06 "must degrade gracefully").
"""

from __future__ import annotations

from app.config import Settings
from app.nlp.embeddings import get_embedding_model
from app.nlp.llm import get_llm_client
from app.nlp.ner import get_ner_model


def warm_nlp_models(settings: Settings) -> None:
    get_ner_model(settings.nlp_spacy_model)
    get_embedding_model(settings.nlp_embeddings_enabled, settings.nlp_embedding_model)
    if settings.nlp_llm_explanations:
        get_llm_client(settings.anthropic_api_key)
