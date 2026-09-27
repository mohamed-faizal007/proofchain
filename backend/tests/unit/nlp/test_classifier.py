import math

import pytest

from app.nlp.classifier import HybridClassifier, RuleOnlyClassifier
from app.nlp.types import Category
from proofchain_core.types import ChangeRegion, RegionType

_classifier = RuleOnlyClassifier()

_PARTY_REF_TEXT = "This agreement is between ABC Corp and XYZ Ltd."
_PARTY_CAND_TEXT = "This agreement is between ABC Corp and QRS Ltd."


class _FakeEnt:
    def __init__(self, text: str, label: str) -> None:
        self.text = text
        self.label_ = label


class _FakeDoc:
    def __init__(self, ents: list[_FakeEnt]) -> None:
        self.ents = ents


class _FakeNerModel:
    def __init__(self, mapping: dict[str, list[tuple[str, str]]]) -> None:
        self._mapping = mapping

    def __call__(self, text: str) -> _FakeDoc:
        return _FakeDoc([_FakeEnt(value, label) for label, value in self._mapping.get(text, [])])


_FAKE_NER_WITH_PARTY_SIGNAL = _FakeNerModel(
    {
        _PARTY_REF_TEXT: [("ORG", "ABC Corp"), ("ORG", "XYZ Ltd")],
        _PARTY_CAND_TEXT: [("ORG", "ABC Corp"), ("ORG", "QRS Ltd")],
    }
)


class _FakeEmbedder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[t] for t in texts]


# cosine([1, 0], [1, 1]) == 1/sqrt(2) ~= 0.7071, deliberately below the 0.90 MINOR_EDIT
# threshold so the "embeddings available" tests below exercise the stricter combined rule.
_FAKE_EMBEDDER_WITH_LOW_SIMILARITY = _FakeEmbedder(
    {_PARTY_REF_TEXT: [1.0, 0.0], _PARTY_CAND_TEXT: [1.0, 1.0]}
)


def _region(
    region_type: RegionType,
    ref_text: str | None = None,
    cand_text: str | None = None,
    section_title: str | None = "Payment Terms",
    ref_page: int | None = 2,
    cand_page: int | None = 2,
) -> ChangeRegion:
    return ChangeRegion(
        id="r1",
        type=region_type,
        ref_text=ref_text,
        cand_text=cand_text,
        ref_page=ref_page,
        cand_page=cand_page,
        section_id="s1",
        section_title=section_title,
    )


def test_amount_change_is_high_severity():
    region = _region(
        RegionType.MODIFIED,
        ref_text="Pay Rs. 500 to the vendor.",
        cand_text="Pay Rs. 800 to the vendor.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.AMOUNT_CHANGE
    assert result.categories == (Category.AMOUNT_CHANGE,)
    assert result.severity == "HIGH"
    assert result.method == "RULES"
    assert result.similarity is None


def test_date_change_is_high_severity():
    region = _region(
        RegionType.MODIFIED,
        ref_text="This agreement is dated 1 January 2025.",
        cand_text="This agreement is dated 5 January 2025.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.DATE_CHANGE
    assert result.severity == "HIGH"


def test_percentage_change_is_high_severity():
    region = _region(
        RegionType.MODIFIED,
        ref_text="Interest of 5% per annum applies.",
        cand_text="Interest of 8% per annum applies.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.PERCENTAGE_CHANGE
    assert result.severity == "HIGH"


def test_number_change_is_medium_severity():
    region = _region(
        RegionType.MODIFIED,
        ref_text="Deliver 5 units by Friday.",
        cand_text="Deliver 8 units by Friday.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.NUMBER_CHANGE
    assert result.severity == "MEDIUM"


def test_obligation_change_modal_flip_is_critical():
    region = _region(
        RegionType.MODIFIED,
        ref_text="The tenant shall pay rent by the fifth of each month.",
        cand_text="The tenant may pay rent by the fifth of each month.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.OBLIGATION_CHANGE
    assert result.severity == "CRITICAL"


def test_obligation_change_negation_flip_is_critical():
    region = _region(
        RegionType.MODIFIED,
        ref_text="The tenant shall sublet the unit.",
        cand_text="The tenant shall not sublet the unit.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.OBLIGATION_CHANGE
    assert result.severity == "CRITICAL"


def test_clause_added_without_signal_is_medium():
    region = _region(
        RegionType.INSERTED,
        cand_text="This clause clarifies the delivery procedure.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.CLAUSE_ADDED
    assert result.categories == (Category.CLAUSE_ADDED,)
    assert result.severity == "MEDIUM"


def test_clause_added_with_money_escalates_to_high():
    region = _region(
        RegionType.INSERTED,
        cand_text="The tenant shall pay an additional ₹10,000 deposit.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.CLAUSE_ADDED
    assert result.severity == "HIGH"


def test_clause_removed_without_signal_is_medium():
    region = _region(
        RegionType.DELETED,
        ref_text="This clause clarifies the delivery procedure.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.CLAUSE_REMOVED
    assert result.severity == "MEDIUM"


def test_clause_removed_with_date_escalates_to_high():
    region = _region(
        RegionType.DELETED,
        ref_text="This clause becomes void on 1 January 2025.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.CLAUSE_REMOVED
    assert result.severity == "HIGH"


def test_clause_modified_when_many_tokens_change_with_no_entity_or_obligation_diff():
    region = _region(
        RegionType.MODIFIED,
        ref_text="The vendor will provide reasonable assistance to the client.",
        cand_text=(
            "The vendor will provide diligent support and guidance to the client, "
            "ensuring satisfaction."
        ),
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.CLAUSE_MODIFIED
    assert result.severity == "MEDIUM"
    assert not result.entity_changes


def test_minor_edit_when_few_tokens_change_with_no_entity_or_obligation_diff():
    region = _region(
        RegionType.MODIFIED,
        ref_text="The vendor will provide reasonable assistance.",
        cand_text="The vendor will provide prompt assistance.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.MINOR_EDIT
    assert result.severity == "LOW"
    assert not result.entity_changes


def test_multiple_high_categories_tie_broken_by_table_order():
    # AMOUNT_CHANGE and DATE_CHANGE are both HIGH; 06's table lists AMOUNT_CHANGE first.
    region = _region(
        RegionType.MODIFIED,
        ref_text="This agreement, worth Rs. 500, is dated 1 January 2025.",
        cand_text="This agreement, worth Rs. 800, is dated 5 January 2025.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.AMOUNT_CHANGE
    assert result.categories == (Category.AMOUNT_CHANGE, Category.DATE_CHANGE)
    assert result.severity == "HIGH"


def test_obligation_change_outranks_amount_change_by_severity():
    region = _region(
        RegionType.MODIFIED,
        ref_text="The tenant shall pay Rs. 500 monthly.",
        cand_text="The tenant may pay Rs. 800 monthly.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.OBLIGATION_CHANGE
    assert result.severity == "CRITICAL"
    assert Category.AMOUNT_CHANGE in result.categories


def test_party_name_change_is_currently_misclassified_as_minor_edit_pending_p7_03():
    """Known limitation (06_NLP_SPEC.md PARTY_CHANGE row): party/counterparty detection needs
    spaCy NER (PERSON/ORG), added in P7-03. Until then a counterparty name substitution has no
    regex entity signal and no obligation flip, so it falls through to the generic word-count
    heuristic below. A legally significant change (who the obligation runs to/from) is
    misleadingly classified as LOW-severity MINOR_EDIT instead of HIGH-severity PARTY_CHANGE.
    Flagged in PROGRESS.md's P7-02 entry; re-examine once P7-03 wires NER into the classifier.
    """
    region = _region(
        RegionType.MODIFIED,
        ref_text="This agreement is between ABC Corp and XYZ Ltd.",
        cand_text="This agreement is between ABC Corp and QRS Ltd.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.MINOR_EDIT
    assert result.severity == "LOW"
    assert not result.entity_changes
    assert Category.PARTY_CHANGE not in result.categories


def test_explanation_describes_an_unpaired_removed_entity():
    region = _region(
        RegionType.MODIFIED,
        ref_text="Pay Rs. 500 and Rs. 100 total.",
        cand_text="Pay Rs. 500 total.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.AMOUNT_CHANGE
    assert "the amount INR:100.00 was removed" in result.explanation


def test_explanation_describes_an_unpaired_added_entity():
    region = _region(
        RegionType.MODIFIED,
        ref_text="Pay Rs. 500 total.",
        cand_text="Pay Rs. 500 and Rs. 100 total.",
    )
    result = _classifier.analyze(region)
    assert result.primary_category == Category.AMOUNT_CHANGE
    assert "the amount INR:100.00 was added" in result.explanation


def test_explanation_omits_location_when_region_has_no_section_or_page():
    region = _region(
        RegionType.MODIFIED,
        ref_text="Pay Rs. 500 to the vendor.",
        cand_text="Pay Rs. 800 to the vendor.",
        section_title=None,
        ref_page=None,
        cand_page=None,
    )
    result = _classifier.analyze(region)
    assert result.explanation.startswith("In this document: ")


def test_explanation_is_byte_identical_across_repeated_runs_with_multiple_entity_changes():
    region = _region(
        RegionType.MODIFIED,
        ref_text=(
            "This agreement, worth Rs. 500, is dated 1 January 2025, "
            "charges 5 per cent interest, for 3 installments."
        ),
        cand_text=(
            "This agreement, worth Rs. 800, is dated 5 January 2025, "
            "charges 8 per cent interest, for 6 installments."
        ),
    )
    results = [_classifier.analyze(region) for _ in range(5)]
    explanations = [r.explanation for r in results]
    assert len(set(explanations)) == 1
    assert all(e.encode("utf-8") == explanations[0].encode("utf-8") for e in explanations)
    assert results[0] == results[1] == results[2] == results[3] == results[4]

    explanation = explanations[0]
    assert "the amount changed from INR:500.00 to INR:800.00" in explanation
    assert "the date changed from 2025-01-01 to 2025-01-05" in explanation
    assert "the percentage changed from 5.00% to 8.00%" in explanation
    assert "the number changed from 3 to 6" in explanation
    assert results[0].primary_category == Category.AMOUNT_CHANGE
    assert results[0].severity == "HIGH"


def _party_region() -> ChangeRegion:
    return _region(RegionType.MODIFIED, ref_text=_PARTY_REF_TEXT, cand_text=_PARTY_CAND_TEXT)


def test_hybrid_classifier_with_both_models_available_detects_party_change():
    classifier = HybridClassifier(
        ner_getter=lambda: _FAKE_NER_WITH_PARTY_SIGNAL,
        embedder_getter=lambda: _FAKE_EMBEDDER_WITH_LOW_SIMILARITY,
    )
    result = classifier.analyze(_party_region())
    assert result.primary_category == Category.PARTY_CHANGE
    assert result.severity == "HIGH"
    assert result.method == "RULES+EMBEDDINGS"
    assert result.similarity == pytest.approx(1 / math.sqrt(2))
    assert {(c.before, c.after) for c in result.entity_changes} == {
        ("ORG:XYZ Ltd", None),
        (None, "ORG:QRS Ltd"),
    }


def test_hybrid_classifier_with_ner_unavailable_never_reports_party_change():
    """NER failed to load but embeddings loaded fine: PARTY_CHANGE must never leak through
    just because the *other* model is available (06 "degrade gracefully", no partial state).
    """
    classifier = HybridClassifier(
        ner_getter=lambda: None,
        embedder_getter=lambda: _FAKE_EMBEDDER_WITH_LOW_SIMILARITY,
    )
    result = classifier.analyze(_party_region())
    assert Category.PARTY_CHANGE not in result.categories
    assert not result.entity_changes
    # embeddings still ran independently: method + similarity are unaffected by NER's absence
    assert result.method == "RULES+EMBEDDINGS"
    assert result.similarity == pytest.approx(1 / math.sqrt(2))
    # no entity/party/obligation category applies, so the fallback runs; low similarity
    # (< 0.90) makes it CLAUSE_MODIFIED even though only 2 tokens changed (<= 3)
    assert result.primary_category == Category.CLAUSE_MODIFIED
    assert result.severity == "MEDIUM"


def test_hybrid_classifier_with_embeddings_unavailable_keeps_party_change_from_ner():
    """Embeddings failed to load but NER loaded fine: PARTY_CHANGE (from NER) must still be
    reported, and `method` must correctly report "RULES" (not "RULES+EMBEDDINGS") -- no
    partial state leaking the other way either.
    """
    classifier = HybridClassifier(
        ner_getter=lambda: _FAKE_NER_WITH_PARTY_SIGNAL,
        embedder_getter=lambda: None,
    )
    result = classifier.analyze(_party_region())
    assert result.primary_category == Category.PARTY_CHANGE
    assert result.severity == "HIGH"
    assert result.method == "RULES"
    assert result.similarity is None


def test_hybrid_classifier_with_neither_model_available_matches_rule_only_classifier():
    """Full graceful degradation: with both models unavailable, HybridClassifier must produce
    exactly what RuleOnlyClassifier produces for the same region -- not just similar, equal.
    """
    hybrid = HybridClassifier(ner_getter=lambda: None, embedder_getter=lambda: None)
    region = _party_region()
    hybrid_result = hybrid.analyze(region)
    rule_only_result = _classifier.analyze(region)

    assert hybrid_result == rule_only_result
    assert hybrid_result.method == "RULES"
    assert hybrid_result.similarity is None
    assert Category.PARTY_CHANGE not in hybrid_result.categories
    assert hybrid_result.primary_category == Category.MINOR_EDIT
    assert hybrid_result.severity == "LOW"


def test_hybrid_classifier_embeddings_threshold_is_stricter_than_word_count_alone():
    """With embeddings available, MINOR_EDIT requires similarity >= 0.90 AND <= 3 changed
    tokens (06 table, both conditions) -- strictly more demanding than the word-count-only
    fallback used when embeddings are unavailable, for the identical low-similarity edit.
    """
    with_embeddings = HybridClassifier(
        ner_getter=lambda: None, embedder_getter=lambda: _FAKE_EMBEDDER_WITH_LOW_SIMILARITY
    )
    without_embeddings = HybridClassifier(ner_getter=lambda: None, embedder_getter=lambda: None)
    region = _party_region()

    with_result = with_embeddings.analyze(region)
    without_result = without_embeddings.analyze(region)

    assert with_result.primary_category == Category.CLAUSE_MODIFIED
    assert without_result.primary_category == Category.MINOR_EDIT


def test_hybrid_classifier_non_modified_regions_behave_like_rule_only_classifier():
    inserted = _region(RegionType.INSERTED, cand_text="This clause clarifies delivery.")
    hybrid = HybridClassifier(ner_getter=lambda: None, embedder_getter=lambda: None)
    assert hybrid.analyze(inserted) == _classifier.analyze(inserted)
