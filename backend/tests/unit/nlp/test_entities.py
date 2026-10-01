from datetime import datetime

import pytest

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


def test_extract_dates_does_not_misread_the_modal_verb_may_as_the_month():
    # dateparser otherwise reads bare "may" as the month name May (RELATIVE_BASE's year, no
    # day); "may" is one of 06's three obligation modals (shall/must/will <-> may), so this
    # collision would tag every modal flip to "may" with a fabricated DATE_CHANGE.
    assert extract_dates("The tenant may pay rent.") == []
    assert extract_dates("We may terminate this agreement.") == []
    assert extract_dates("This may or may not happen.") == []
    assert extract_dates("You may not sublet the unit.") == []


def test_extract_dates_still_detects_may_with_a_day_or_year():
    # a real May date always carries a digit (day and/or year), so it is not filtered
    assert extract_dates("Payment is due in May 2025.") == ["2025-05-01"]
    assert extract_dates("The deadline is May 5, 2025.") == ["2025-05-05"]


def test_extract_dates_bare_month_may_with_no_day_or_year_is_a_known_tradeoff():
    # deliberate false negative: a bare "May" with neither day nor year is indistinguishable
    # from the modal-verb collision above by this regex-only rule, so it is dropped too. Rare
    # in contract text (which specifies exact dates); the alternative is a fabricated date on
    # every "may"-modal clause, which is worse and far more common. See entities.py
    # `_is_bare_modal_may`.
    assert extract_dates("Payment is due in May.") == []


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


@pytest.mark.parametrize(
    "text",
    [
        "Either party may terminate with 60 days written notice.",
        "with 10 days written notice",
        "60 days",
        "10 days",
        "within 30 days of each invoice",
        "thirty (30) days written notice",
        "a period of six months",
        "valid for 2 business days",
        "a term of 5 years",
    ],
)
def test_extract_dates_ignores_durations(text):
    # Regression (P8-06 live check): dateparser reads "60 days" as a relative date (1999-11-02).
    assert extract_dates(text) == []


def test_durations_are_still_reported_as_numbers():
    assert extract_numbers("with 60 days written notice") == ["60"]
    assert extract_numbers("with 10 days written notice") == ["10"]


@pytest.mark.parametrize(
    "text",
    [
        "25%",
        "10%",
        "scored an aggregate of 25%.",
        "The holder completed 12 modules over 6 months and scored an aggregate of 10%.",
        "interest at 12.5% per annum",
        "a rebate of 5 per cent",
        "a rebate of 5 percent",
        "30 % of the fee",
    ],
)
def test_extract_dates_ignores_percentages(text):
    # Regression (P9-04 eval): dateparser read "25%" / "10%" as the 25th / 10th of January
    # (2000-01-25), so a PERCENTAGE_CHANGE also got DATE_CHANGE. Third dateparser-too-eager case
    # after the modal "may" and durations; percentages are blanked before the search, like those.
    assert extract_dates(text) == []


def test_percentages_are_still_reported_as_percentages_not_numbers():
    assert extract_percentages("scored 25%") == ["25.00%"]
    assert extract_numbers("scored 25%") == []
    assert extract_percentages("a rebate of 5 per cent") == ["5.00%"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A 10% rebate applies until 15 March 2024.", ["2024-03-15"]),
        ("On 10 January 2024 the rate rose to 25%.", ["2024-01-10"]),
        ("Pay 5 per cent by 5th March, 2024.", ["2024-03-05"]),
        ("Pay 10% by Jan 5, 2025.", ["2025-01-05"]),
        ("Effective from 01/02/2024 at 12.5%.", ["2024-02-01"]),
        ("within 30 days of 10 January 2024 at 25%", ["2024-01-10"]),
        ("a rebate of 5 per cent on 3 May 2023", ["2023-05-03"]),
        ("a rebate of 12.5 percent on 3 May 2023", ["2023-05-03"]),
    ],
)
def test_extract_dates_finds_real_dates_next_to_percentages(text, expected):
    assert extract_dates(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "pay a refundable security deposit of ₹46,10,000 on 3 May 2023, without interest.",
            ["2023-05-03"],
        ),
        ("a fee of ₹99,05,000 was received in full on 9 June 2020.", ["2020-06-09"]),
        ("Rs. 5,00,000 payable by 15 March 2024", ["2024-03-15"]),
        ("INR 2500 due on 1 April 2025.", ["2025-04-01"]),
        ("a sum of $1,200.50 on 10 January 2024", ["2024-01-10"]),
        ("50 lakh rupees by 5th March, 2024", ["2024-03-05"]),
        ("on 3 May 2023 the deposit of ₹46,10,000 was paid", ["2023-05-03"]),
        ("₹46,10,000 on 3 May 2023 and 10% within 30 days", ["2023-05-03"]),
    ],
)
def test_extract_dates_finds_the_real_date_next_to_an_amount(text, expected):
    # Regression (P9-04 eval): digits inside "₹46,10,000" were read as a year (2046-01-01), which
    # swallowed the real date, so a DATE_CHANGE was classified NUMBER_CHANGE. Fourth
    # dateparser-too-eager case; money spans are blanked before the search.
    assert extract_dates(text) == expected


@pytest.mark.parametrize(
    "text",
    ["a deposit of ₹46,10,000.", "Rs. 5,00,000", "₹99,05,000 and $1,200.50", "50 lakh rupees"],
)
def test_extract_dates_ignores_amounts(text):
    assert extract_dates(text) == []


def test_amounts_next_to_dates_are_still_extracted_once_as_money():
    text = "deposit of ₹46,10,000 on 3 May 2023, balance Rs. 5 lakh by 15 March 2024"
    assert extract_money(text) == ["INR:4610000.00", "INR:500000.00"]
    assert extract_dates(text) == ["2023-05-03", "2024-03-15"]
    assert extract_numbers(text) == []  # neither the amounts nor the dates leak into NUMBER


def test_diff_entities_date_edit_beside_an_amount_is_a_date_change_only():
    before = "deposit of ₹46,10,000 on 3 May 2023, without interest."
    after = "deposit of ₹46,10,000 on 29 August 2023, without interest."
    changes = diff_entities(before, after)
    assert {c.type for c in changes} == {"DATE"}
    assert {(c.before, c.after) for c in changes} == {("2023-05-03", None), (None, "2023-08-29")}


def test_diff_entities_amount_edit_beside_a_date_is_an_amount_change_only():
    before = "deposit of ₹46,10,000 on 3 May 2023, without interest."
    after = "deposit of ₹46,15,000 on 3 May 2023, without interest."
    changes = diff_entities(before, after)
    assert {c.type for c in changes} == {"MONEY"}
    assert {(c.before, c.after) for c in changes} == {
        ("INR:4610000.00", None),
        (None, "INR:4615000.00"),
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "This certificate is valid for 24 months from 2 December 2021 and may be renewed.",
            ["2021-12-02"],
        ),
        (
            "The Tenant shall take possession on 4 January 2023 and may renew this lease.",
            ["2023-01-04"],
        ),
        ("understandings dated before 9 May 2025 and may be amended", ["2025-05-09"]),
        ("dated 9 May 2025 and may be amended", ["2025-05-09"]),
        ("The Tenant may pay on 3 June 2023.", ["2023-06-03"]),
        ("on 5 January 2024 the Tenant may terminate, and may also renew", ["2024-01-05"]),
        ("the 5th of May 2025 and may", ["2025-05-05"]),
        ("May 5, 2025 and the Tenant may renew", ["2025-05-05"]),
    ],
)
def test_extract_dates_finds_the_real_date_in_a_sentence_with_the_modal_may(text, expected):
    # Regression (P9-04 eval): a date and the modal "may" in one sentence made dateparser's search
    # return nothing at all, so 7 of 46 DATE_CHANGE cases were classified NUMBER_CHANGE. The
    # modal is masked before the search unless a day or year digit marks it as the month.
    assert extract_dates(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("understandings dated before 9 May 2025.", ["2025-05-09"]),
        ("valid before 9 January 2025 and", ["2025-01-09"]),
        ("Before 3 June 2023 the Tenant shall pay.", ["2023-06-03"]),
    ],
)
def test_extract_dates_keeps_the_day_and_month_after_the_word_before(text, expected):
    # Regression (P9-04 eval): "before 9 May 2025" parsed as 2025-01-01, so an edited date in such
    # a clause was reported as NUMBER_CHANGE.
    assert extract_dates(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 January 2024", ["2024-01-10"]),
        ("Dated 5th March, 2024.", ["2024-03-05"]),
        ("Effective from 01/02/2024.", ["2024-02-01"]),
        ("March 2024", ["2024-03-01"]),
        ("Jan 5, 2024", ["2024-01-05"]),
        ("the 5th of May 2025", ["2025-05-05"]),
        ("Renewal due next year.", ["2001-01-01"]),
    ],
)
def test_extract_dates_still_detects_genuine_dates(text, expected):
    assert extract_dates(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("within 30 days of 10 January 2024", ["2024-01-10"]),
        ("thirty (30) business days after 3 May 2023", ["2023-05-03"]),
        ("10 days after 10 January 2024", ["2024-01-10"]),
        ("valid for 12 months from 01/04/2024", ["2024-04-01"]),
        ("Term of 5 years ending 31 March 2029", ["2029-03-31"]),
        ("2 business days after 5th March, 2024", ["2024-03-05"]),
    ],
)
def test_extract_dates_finds_the_real_date_next_to_a_duration(text, expected):
    # Before the fix dateparser swallowed the duration and returned a wrong date or no date.
    assert extract_dates(text) == expected
