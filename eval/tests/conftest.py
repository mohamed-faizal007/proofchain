from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from generate_corpus import generate_one, load_config

EVAL_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def cfg() -> dict[str, Any]:
    return load_config(EVAL_DIR / "configs" / "default.yaml")


@pytest.fixture(scope="session")
def corpus(cfg: dict[str, Any]) -> list[tuple[dict[str, Any], bytes]]:
    """The full default corpus, generated once in index order."""
    return [generate_one(cfg, i) for i in range(cfg["n_docs"])]
