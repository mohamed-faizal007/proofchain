from app.nlp.obligation import contains_obligation_term, detect_obligation_change
from app.nlp.token_diff import diff_tokens


def test_detects_shall_to_may_flip():
    ops = diff_tokens("The tenant shall pay rent.", "The tenant may pay rent.")
    assert detect_obligation_change(ops) is True


def test_detects_must_to_may_flip():
    ops = diff_tokens("Payment must be made in full.", "Payment may be made in full.")
    assert detect_obligation_change(ops) is True


def test_detects_will_to_may_flip():
    ops = diff_tokens("The landlord will repair the roof.", "The landlord may repair the roof.")
    assert detect_obligation_change(ops) is True


def test_detects_may_to_shall_flip_reverse_direction():
    ops = diff_tokens("The tenant may vacate early.", "The tenant shall vacate early.")
    assert detect_obligation_change(ops) is True


def test_detects_negation_added():
    ops = diff_tokens("The tenant shall sublet the unit.", "The tenant shall not sublet the unit.")
    assert detect_obligation_change(ops) is True


def test_detects_negation_removed():
    ops = diff_tokens("The tenant shall not sublet the unit.", "The tenant shall sublet the unit.")
    assert detect_obligation_change(ops) is True


def test_no_flip_when_wording_changes_but_obligation_strength_does_not():
    ops = diff_tokens("The tenant shall pay rent monthly.", "The tenant shall pay rent quarterly.")
    assert detect_obligation_change(ops) is False


def test_swapping_one_negation_word_for_another_is_not_a_flip():
    # negation is present on both sides; only the word itself changed
    ops = diff_tokens(
        "The tenant shall not sublet the unit.", "The tenant shall never sublet the unit."
    )
    assert detect_obligation_change(ops) is False


def test_negation_word_inside_a_larger_word_is_not_matched():
    # "notwithstanding" is one token (tokenize splits on \w+), never equal to "not"
    ops = diff_tokens("Rent is due monthly.", "Notwithstanding anything, rent is due monthly.")
    assert detect_obligation_change(ops) is False


def test_contains_obligation_term_detects_modals_and_negations():
    assert contains_obligation_term("The tenant shall pay rent.") is True
    assert contains_obligation_term("The tenant may pay rent.") is True
    assert contains_obligation_term("The tenant shall not sublet.") is True
    assert contains_obligation_term("The rent is due monthly.") is False
