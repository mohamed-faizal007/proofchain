"""Regex entity extraction (docs/06_NLP_SPEC.md Pipeline step 2, regex half; spaCy NER is
P7-03). Money/date/percentage/number extraction, plus multiset diffing for `EntityChange`.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from dateparser.search import search_dates

from app.nlp.types import EntityChange

# Deterministic dateparser settings. Per docs/06_NLP_SPEC.md, dates are "normalized with
# dateparser, DMY preferred": DATE_ORDER pins ambiguous numeric dates (e.g. "01/02/2024") to
# day-month-year instead of dateparser's locale-dependent default. RELATIVE_BASE pins a fixed
# anchor so a relative expression (e.g. "next year") does not depend on the wall clock the
# service/tests run on -- NLP output feeds into stored ChangeAnalysis records and must be
# reproducible the same way proofchain_core hashing is (see PROGRESS.md P1 determinism notes).
# PREFER_DAY_OF_MONTH pins the day when a date omits it (e.g. "March 2024") instead of using
# dateparser's implicit "today" fallback. `languages=["en"]` is passed at every call site
# instead of relying on dateparser's language auto-detection, which is a second locale-shaped
# source of nondeterminism this project does not want.
_DATEPARSER_SETTINGS = {
    "DATE_ORDER": "DMY",
    "RELATIVE_BASE": datetime(2000, 1, 1),
    "RETURN_AS_TIMEZONE_AWARE": False,
    "STRICT_PARSING": False,
    "PREFER_DAY_OF_MONTH": "first",
}
_DATE_LANGUAGES = ["en"]

_MONEY_SCALE = {"lakh": Decimal(100_000), "lac": Decimal(100_000), "crore": Decimal(10_000_000)}
_MONEY_SYMBOL_CURRENCY = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "us$": "USD",
    "$": "USD",
    "usd": "USD",
}

_MONEY_RE = re.compile(
    r"(?P<symbol>₹|US\$|\$|Rs\.?|INR|USD)?\s*"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)"
    r"\s*(?P<scale>lakh|lac|crore)?"
    r"\s*(?P<word>rupees?)?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s?(?:%|per\s?cent)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _money_match_spans(text: str) -> list[tuple[int, int, str]]:
    """Money matches, normalized to `"CURRENCY:amount"`, with the matched span."""
    results: list[tuple[int, int, str]] = []
    for m in _MONEY_RE.finditer(text):
        symbol = m.group("symbol")
        scale = m.group("scale")
        word = m.group("word")
        if not (symbol or scale or word):
            continue  # a bare number is not a money match
        amount = Decimal(m.group("amount").replace(",", ""))
        if scale:
            amount *= _MONEY_SCALE[scale.lower()]
        # bare "50 lakh" / "... rupees" (no symbol) implies INR
        currency = _MONEY_SYMBOL_CURRENCY[symbol.lower()] if symbol else "INR"
        results.append((m.start(), m.end(), f"{currency}:{amount:.2f}"))
    return results


def extract_money(text: str) -> list[str]:
    return [value for _, _, value in _money_match_spans(text)]


_BARE_MAY_RE = re.compile(r"\bmay\b", re.IGNORECASE)
_HAS_DIGIT_RE = re.compile(r"\d")


def _is_bare_modal_may(matched_text: str) -> bool:
    """True if `matched_text` is dateparser reading the modal verb "may" (06's OBLIGATION_CHANGE
    weak modal, e.g. "the tenant may pay", "we may terminate") as the month name May, rather than
    a real date. dateparser resolves a bare month name to `RELATIVE_BASE`'s year with no day, so
    the signal is: the word "may" is present and no digit (day/year) anchors the match to an
    actual date. This also drops a genuine bare month reference with no year (e.g. "due in
    May.") as a deliberate tradeoff -- rare in contract text, versus "may" as a modal being one
    of 06's three obligation-modal keywords and therefore common. A month+year or month+day
    match (e.g. "May 2025", "May 5, 2025") always has a digit and is unaffected.
    """
    return bool(_BARE_MAY_RE.search(matched_text)) and not _HAS_DIGIT_RE.search(matched_text)


_NUMBER_WORDS = (
    "a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
    "thirty|forty|forty-five|sixty|ninety|hundred"
)
# A duration ("60 days", "thirty (30) days", "6 months", "2 business weeks"). dateparser reads
# these as relative dates ("60 days" -> some day in 1999), which is wrong for a contract term
# and can also swallow a real date next to it ("within 30 days of 10 January 2024" yields no
# date at all). Durations are blanked (same length, so spans stay valid) before searching.
_DURATION_RE = re.compile(
    rf"\b(?:\d+(?:\.\d+)?|{_NUMBER_WORDS})(?:\s*\(\d+\))?[\s-]*"
    r"(?:(?:business|working|calendar)\s+)?(?:day|week|month|year)s?\b",
    re.IGNORECASE,
)


def _blank(text: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda m: " " * len(m.group()), text)


def _mask_non_dates(text: str) -> str:
    """Blank spans that are never dates before dateparser sees them (same length, spans stay
    valid): durations, and percentages ("25%", "5 per cent"), which dateparser reads as a day of
    the month (2000-01-25) and which would also swallow a real date next to them. A percentage
    span is therefore never both a PERCENTAGE and a DATE candidate (06: mutually exclusive).
    """
    return _blank(_blank(text, _DURATION_RE), _PERCENT_RE)


def _date_match_spans(original: str) -> list[tuple[int, int, str]]:
    text = _mask_non_dates(original)
    matches = search_dates(text, languages=_DATE_LANGUAGES, settings=_DATEPARSER_SETTINGS) or []
    results: list[tuple[int, int, str]] = []
    search_from = 0
    for matched_text, dt in matches:
        if _is_bare_modal_may(matched_text):
            continue
        start = text.find(matched_text, search_from)
        if start == -1:
            start = text.find(matched_text)
        if start == -1:
            continue
        end = start + len(matched_text)
        search_from = end
        results.append((start, end, dt.date().isoformat()))
    return results


def extract_dates(text: str) -> list[str]:
    return [value for _, _, value in _date_match_spans(text)]


def _percent_match_spans(text: str) -> list[tuple[int, int, str]]:
    results: list[tuple[int, int, str]] = []
    for m in _PERCENT_RE.finditer(text):
        results.append((m.start(), m.end(), f"{Decimal(m.group('number')):.2f}%"))
    return results


def extract_percentages(text: str) -> list[str]:
    return [value for _, _, value in _percent_match_spans(text)]


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < s_end and end > s_start for s_start, s_end in spans)


def extract_numbers(text: str) -> list[str]:
    other_spans = (
        *_money_match_spans(text),
        *_date_match_spans(text),
        *_percent_match_spans(text),
    )
    excluded = [(start, end) for start, end, _ in other_spans]
    results = []
    for m in _NUMBER_RE.finditer(text):
        if _overlaps(m.start(), m.end(), excluded):
            continue
        results.append(str(Decimal(m.group().replace(",", ""))))
    return results


_EXTRACTORS: dict[str, Callable[[str], list[str]]] = {
    "MONEY": extract_money,
    "DATE": extract_dates,
    "PERCENTAGE": extract_percentages,
    "NUMBER": extract_numbers,
}


def _diff_multiset(entity_type: str, before: list[str], after: list[str]) -> list[EntityChange]:
    before_counts = Counter(before)
    after_counts = Counter(after)
    removed = before_counts - after_counts
    added = after_counts - before_counts
    changes = [
        EntityChange(type=entity_type, before=value, after=None)
        for value in sorted(removed)
        for _ in range(removed[value])
    ]
    changes += [
        EntityChange(type=entity_type, before=None, after=value)
        for value in sorted(added)
        for _ in range(added[value])
    ]
    return changes


def diff_entities(before: str, after: str) -> list[EntityChange]:
    """Multiset diff of every regex entity type between two texts (docs/06_NLP_SPEC.md step 2)."""
    changes: list[EntityChange] = []
    for entity_type, extractor in _EXTRACTORS.items():
        changes.extend(_diff_multiset(entity_type, extractor(before), extractor(after)))
    return changes
