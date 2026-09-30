"""Named page-count functions selectable from the config (``page_count.function``).

A page-count function is pure: ``(index, seed, doc_type, cap, rng, params) -> target pages``.
Adding a function means adding it to ``PAGE_COUNT_FUNCTIONS``; nothing is implicit in the generator.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

# Knuth multiplicative constant (2^32 / golden ratio). Consecutive indices map to well-spread
# points of [0, 2^32), a low-discrepancy sequence that needs no shared random state.
_FIB = 2654435761
_MOD = 2**32


def bucket_for(index: int, seed: int, buckets: list[dict[str, Any]]) -> dict[str, Any]:
    """Stratified bucket choice: a pure function of (index, seed, weights)."""
    total = sum(int(b["weight"]) for b in buckets)
    point = (((index + seed) * _FIB) % _MOD) * total // _MOD
    acc = 0
    for b in buckets:
        acc += int(b["weight"])
        if point < acc:
            return b
    return buckets[-1]


def bucketed_skewed(
    index: int,
    seed: int,
    doc_type: str,
    cap: int,
    rng: random.Random,
    params: dict[str, Any],
) -> int:
    bucket = bucket_for(index, seed, params["buckets"])
    lo, hi = int(bucket["min"]), int(bucket["max"])
    if lo > cap:  # bucket unreachable for this type: fall back to its whole range
        lo, hi = 1, cap
    return rng.randint(lo, min(hi, cap))


PageCountFn = Callable[[int, int, str, int, random.Random, dict[str, Any]], int]
PAGE_COUNT_FUNCTIONS: dict[str, PageCountFn] = {"bucketed_skewed": bucketed_skewed}


def bucket_name(pages: int, buckets: list[dict[str, Any]]) -> str:
    """Label of the bucket a *measured* page count falls into."""
    for b in buckets:
        if int(b["min"]) <= pages <= int(b["max"]):
            return str(b["name"])
    return "out_of_range"
