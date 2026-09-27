from datetime import datetime

from app.nlp.entities import (
    _DATEPARSER_SETTINGS,
    diff_entities,
    extract_dates,
    extract_money,
    extract_numbers,
    extract_percentages,
)


def test_extract_money_matches_inr_symbol_rs_and_usd():
    assert extract_money("Amount payable: ₹50,000.") == ["INR:50000.00"]
    assert extract_money("Amount payable: Rs. 50,000.") == ["INR:50000.00"]
    assert extract_money("Amount payable: Rs 50000.") == ["INR:50000.00"]
    assert extract_money("Amount payable: INR 50,000.") == ["INR:50000.00"]
    assert extract_money("Amount payable: $80,000.") == ["USD:80000.00"]
    assert extract_money("Amount payable: USD 80,000.") == ["USD:80000.00"]


def test_extract_money_normalizes_lakh_and_crore():
    assert extract_money("Consideration of 50 lakh only.") == ["INR:5000000.00"]
    assert extract_money("Consideration of 2 crore rupees only.") == ["INR:20000000.00"]


def test_extract_money_ignores_bare_numbers():
    assert extract_money("Clause 50 of the agreement.") == []


def test_extract_dates_normalizes_to_iso_dmy_preferred():
    assert extract_dates("This agreement is dated 5th March, 2024.") == ["2024-03-05"]
    # ambiguous numeric date: DMY order means day=1, month=2 (not month=1, day=2)
    assert extract_dates("Effective from 01/02/2024.") == ["2024-02-01"]


def test_extract_dates_settings_pin_date_order_and_relative_base():
    # asserts the pinned config directly, so a future edit that removes the pin fails loudly
    assert _DATEPARSER_SETTINGS["DATE_ORDER"] == "DMY"
    assert _DATEPARSER_SETTINGS["RELATIVE_BASE"] == datetime(2000, 1, 1)


def test_extract_dates_relative_expression_is_anchored_not_wall_clock():
    # "next year" must resolve relative to the fixed RELATIVE_BASE (2000-01-01), never
    # datetime.now(); this proves the result cannot depend on when the test runs.
    assert extract_dates("Renewal due next year.") == ["2001-01-01"]


def test_extract_percentage_matches_symbol_and_per_cent():
    assert extract_percentages("Interest of 12.5% per annum.") == ["12.50%"]
    assert extract_percentages("Interest of 12.5 per cent per annum.") == ["12.50%"]


def test_extract_numbers_excludes_already_matched_money_date_percent():
    text = "On 5th March 2024, pay ₹50,000 at 12% interest for 3 installments."
    assert extract_numbers(text) == ["3"]


def test_diff_entities_multiset_comparison_detects_added_removed_changed():
    before = "Pay ₹50,000 within 30 days at 5% interest."
    after = "Pay ₹80,000 within 30 days at 5% interest."
    changes = diff_entities(before, after)
    money_changes = [c for c in changes if c.type == "MONEY"]
    assert len(money_changes) == 2
    assert {(c.before, c.after) for c in money_changes} == {
        ("INR:50000.00", None),
        (None, "INR:80000.00"),
    }
    # unchanged entities (30 days, 5%) produce no EntityChange
    assert not [c for c in changes if c.type == "NUMBER"]
    assert not [c for c in changes if c.type == "PERCENTAGE"]


def test_diff_entities_is_empty_for_identical_text():
    text = "Pay ₹50,000 within 30 days at 5% interest, dated 5th March 2024."
    assert diff_entities(text, text) == []
