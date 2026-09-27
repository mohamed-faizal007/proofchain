"""POST /verify NLP integration (P7-04, docs/06_NLP_SPEC.md): `analysis` is populated for
authenticated TAMPERED reports with localized regions, and skipped (never the verdict) when
NLP is disabled, has nothing to analyze, fails, or the caller is anonymous.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from proofchain_core.types import ChangeRegion
from tests.unit.app.docs_env import Env, settings
from tests.unit.app.verify_helpers import edited, original, register_approved, step, verify


def _authenticated(env: Env) -> dict[str, str]:
    return env.auth(env.user(["VERIFIER"], "verifier@example.com"))


class _RaisingClassifier:
    def analyze(self, region: ChangeRegion) -> None:
        raise RuntimeError("boom")


def test_tampered_with_regions_populates_analysis_for_authenticated_callers(
    env_factory: Callable[..., Env], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = env_factory()
    doc_id = register_approved(env)[2]
    data = edited(tmp_path, monkeypatch)

    r = verify(env, data, headers=_authenticated(env), document_id=doc_id)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "TAMPERED"
    assert step(body, "SEMANTIC_ANALYSIS") == {"name": "SEMANTIC_ANALYSIS", "status": "DONE"}
    [analysis] = body["analysis"]
    assert analysis["primary_category"] == "PERCENTAGE_CHANGE"
    assert analysis["severity"] == "HIGH"
    assert analysis["method"] == "RULES"  # env's default test classifier is RuleOnlyClassifier
    assert analysis["similarity"] is None
    assert body["timings_ms"]["nlp"] >= 0


def test_classifier_failure_never_changes_the_verdict(
    env_factory: Callable[..., Env], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The literal P7-04 Accept criterion: an NLP failure must not change the verdict."""
    env = env_factory(change_classifier=_RaisingClassifier())
    doc_id = register_approved(env)[2]
    data = edited(tmp_path, monkeypatch)

    r = verify(env, data, headers=_authenticated(env), document_id=doc_id)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "TAMPERED"  # unaffected by the classifier raising below
    assert body["localization"] is not None  # crypto localization still ran and is reported
    assert body["analysis"] is None
    assert step(body, "SEMANTIC_ANALYSIS") == {
        "name": "SEMANTIC_ANALYSIS",
        "status": "SKIPPED",
        "detail": "NLP analysis failed",
    }


def test_nlp_disabled_skips_analysis_but_not_the_verdict(
    env_factory: Callable[..., Env], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    disabled = settings().model_copy(update={"nlp_enabled": False})
    env = env_factory(settings_override=disabled)
    doc_id = register_approved(env)[2]
    data = edited(tmp_path, monkeypatch)

    r = verify(env, data, headers=_authenticated(env), document_id=doc_id)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "TAMPERED"
    assert body["analysis"] is None
    assert step(body, "SEMANTIC_ANALYSIS")["detail"] == "NLP disabled"


def test_authentic_verdict_has_no_regions_to_analyze(env_factory: Callable[..., Env]) -> None:
    env = env_factory()
    doc_id = register_approved(env)[2]

    r = verify(env, original(), headers=_authenticated(env), document_id=doc_id)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "AUTHENTIC_LATEST"
    assert body["analysis"] is None
    assert step(body, "SEMANTIC_ANALYSIS")["detail"] == "No localized regions to analyze"


def test_anonymous_callers_never_get_analysis_even_when_tampered(
    env_factory: Callable[..., Env], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = env_factory()
    doc_id = register_approved(env)[2]
    data = edited(tmp_path, monkeypatch)

    r = verify(env, data, document_id=doc_id)  # no headers => anonymous

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "TAMPERED"
    assert body["analysis"] is None
    assert step(body, "SEMANTIC_ANALYSIS")["detail"] == "Not available for anonymous requests"


@pytest.mark.nlp
def test_real_hybrid_classifier_end_to_end(
    env_factory: Callable[..., Env], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.nlp.classifier import HybridClassifier

    env = env_factory(change_classifier=HybridClassifier())
    doc_id = register_approved(env)[2]
    data = edited(tmp_path, monkeypatch)

    r = verify(env, data, headers=_authenticated(env), document_id=doc_id)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "TAMPERED"
    [analysis] = body["analysis"]
    assert analysis["primary_category"] == "PERCENTAGE_CHANGE"
    assert analysis["method"] == "RULES+EMBEDDINGS"
    assert analysis["similarity"] is not None
