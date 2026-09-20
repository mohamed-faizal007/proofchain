"""Text canonicalization. Normative spec: docs/02_ALGORITHMS.md §3."""

import re
import unicodedata

CANON_VERSION = 2

_REMOVED = dict.fromkeys(map(ord, "­​‌‍﻿"))
_PUNCT = str.maketrans(
    {
        **dict.fromkeys(map(ord, "‘’‚‛′"), "'"),
        **dict.fromkeys(map(ord, "“”„‟″"), '"'),
        **dict.fromkeys(map(ord, "‐‑‒–—―"), "-"),
    }
)
_WS_RUN = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Canonicalize block text; steps 1-5 in the exact order of §3."""
    s = unicodedata.normalize("NFKC", s)  # 1
    s = s.translate(_REMOVED)  # 2
    s = s.translate(_PUNCT)  # 3
    s = _WS_RUN.sub(" ", s)  # 4
    return s.strip(" ")  # 5
