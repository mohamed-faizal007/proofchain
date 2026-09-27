import sys
import types

import pytest

from app.nlp.ner import diff_party_entities, extract_party_entities


class _FakeEnt:
    def __init__(self, text: str, label: str) -> None:
        self.text = text
        self.label_ = label


class _FakeDoc:
    def __init__(self, ents: list[_FakeEnt]) -> None:
        self.ents = ents


class _FakeNerModel:
    """Maps a fixed sentence -> a fixed set of (label, text) entities, for deterministic tests."""

    def __init__(self, mapping: dict[str, list[tuple[str, str]]]) -> None:
        self._mapping = mapping

    def __call__(self, text: str) -> _FakeDoc:
        return _FakeDoc([_FakeEnt(value, label) for label, value in self._mapping.get(text, [])])


def test_extract_party_entities_keeps_only_person_org_gpe():
    model = _FakeNerModel(
        {
            "ABC Corp is based in Mumbai and pays $5.": [
                ("ORG", "ABC Corp"),
                ("GPE", "Mumbai"),
                ("MONEY", "$5"),
            ],
        }
    )
    result = extract_party_entities("ABC Corp is based in Mumbai and pays $5.", model)
    assert result == ["ORG:ABC Corp", "GPE:Mumbai"]


def test_extract_party_entities_returns_empty_when_model_is_none():
    assert extract_party_entities("ABC Corp.", None) == []


def test_extract_party_entities_returns_empty_for_empty_text():
    model = _FakeNerModel({})
    assert extract_party_entities("", model) == []


def test_diff_party_entities_detects_org_substitution():
    model = _FakeNerModel(
        {
            "This agreement is between ABC Corp and XYZ Ltd.": [
                ("ORG", "ABC Corp"),
                ("ORG", "XYZ Ltd"),
            ],
            "This agreement is between ABC Corp and QRS Ltd.": [
                ("ORG", "ABC Corp"),
                ("ORG", "QRS Ltd"),
            ],
        }
    )
    changes = diff_party_entities(
        "This agreement is between ABC Corp and XYZ Ltd.",
        "This agreement is between ABC Corp and QRS Ltd.",
        model,
    )
    assert {(c.before, c.after) for c in changes} == {
        ("ORG:XYZ Ltd", None),
        (None, "ORG:QRS Ltd"),
    }
    assert all(c.type == "PARTY" for c in changes)


def test_diff_party_entities_is_empty_for_identical_entities():
    model = _FakeNerModel({"ABC Corp signs here.": [("ORG", "ABC Corp")]})
    changes = diff_party_entities("ABC Corp signs here.", "ABC Corp signs here.", model)
    assert changes == []


def test_diff_party_entities_is_empty_when_model_is_none():
    assert diff_party_entities("A.", "B.", None) == []


def test_get_ner_model_returns_none_when_loader_reports_unavailable(monkeypatch):
    import app.nlp.ner as ner_module

    monkeypatch.setattr(ner_module, "_load_attempted", False)
    monkeypatch.setattr(ner_module, "_model", None)
    monkeypatch.setattr(ner_module, "_load_model", lambda model_name: None)
    assert ner_module.get_ner_model() is None


def test_get_ner_model_caches_after_first_load(monkeypatch):
    import app.nlp.ner as ner_module

    calls = []

    def _fake_loader(model_name: str) -> str:
        calls.append(model_name)
        return "sentinel-model"

    monkeypatch.setattr(ner_module, "_load_attempted", False)
    monkeypatch.setattr(ner_module, "_model", None)
    monkeypatch.setattr(ner_module, "_load_model", _fake_loader)
    assert ner_module.get_ner_model() == "sentinel-model"
    assert ner_module.get_ner_model() == "sentinel-model"
    assert len(calls) == 1


def test_load_model_returns_none_when_spacy_is_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "spacy", None)
    import app.nlp.ner as ner_module

    assert ner_module._load_model("en_core_web_sm") is None


@pytest.mark.nlp
def test_load_model_returns_none_when_model_is_not_downloaded(monkeypatch):
    spacy = pytest.importorskip("spacy")
    import app.nlp.ner as ner_module

    def _raise_oserror(name: str):
        raise OSError(f"[E050] Can't find model '{name}'")

    monkeypatch.setattr(spacy, "load", _raise_oserror)
    assert ner_module._load_model("en_core_web_sm") is None


def test_get_ner_model_loads_the_configured_model_name(monkeypatch):
    import app.nlp.ner as ner_module

    calls = []

    def _fake_load(name: str) -> str:
        calls.append(name)
        return "the-model"

    fake_spacy = types.SimpleNamespace(load=_fake_load)
    monkeypatch.setitem(sys.modules, "spacy", fake_spacy)
    monkeypatch.setattr(ner_module, "_load_attempted", False)
    monkeypatch.setattr(ner_module, "_model", None)

    result = ner_module.get_ner_model("custom-model-name")

    assert calls == ["custom-model-name"]
    assert result == "the-model"


@pytest.mark.nlp
def test_real_spacy_model_loads_and_detects_org():
    import app.nlp.ner as ner_module

    ner_module._load_attempted = False
    ner_module._model = None
    model = ner_module.get_ner_model()
    assert model is not None
    changes = ner_module.diff_party_entities(
        "This agreement is between Acme Corporation and Global Industries.",
        "This agreement is between Acme Corporation and Northwind Traders.",
        model,
    )
    assert any(c.type == "PARTY" for c in changes)
