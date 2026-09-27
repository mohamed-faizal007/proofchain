"""Wires classification (+ optional LLM explanation) over cryptographically localized regions
(docs/06_NLP_SPEC.md: NLP "runs only on regions that cryptographic localization already
flagged"). Advisory only: callers never let a failure here change a verdict (06 "crypto
decides, AI explains").

Privacy: each region is classified and (optionally) explained using only that region's own
`ref_text`/`cand_text` and its own detected category labels. No other region, no document/tree/
revision metadata (title, ids, section, page, bbox, chunk id) is ever part of an LLM request --
see `app/nlp/llm.py`'s `explain_with_llm` signature, which structurally cannot accept them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import anyio.to_thread

from app.nlp.classifier import ChangeClassifier
from app.nlp.llm import explain_with_llm
from app.nlp.types import ChangeAnalysis
from proofchain_core.types import ChangeRegion


def _classify_all(
    regions: list[ChangeRegion], classifier: ChangeClassifier
) -> list[ChangeAnalysis]:
    return [classifier.analyze(r) for r in regions]


async def _with_llm_explanation(
    analysis: ChangeAnalysis, region: ChangeRegion, llm_client: Any, llm_model: str
) -> ChangeAnalysis:
    explanation = await explain_with_llm(
        region.ref_text or "",
        region.cand_text or "",
        [c.value for c in analysis.categories],
        llm_client,
        llm_model,
    )
    if explanation is None:
        return analysis
    return dataclasses.replace(analysis, explanation=explanation, method="RULES+EMBEDDINGS+LLM")


async def analyze_regions(
    regions: Sequence[ChangeRegion],
    classifier: ChangeClassifier,
    llm_client: Any | None,
    llm_model: str,
) -> list[ChangeAnalysis]:
    """One `ChangeAnalysis` per region, in order. Classification (CPU-heavy: spaCy/embeddings)
    runs off the event loop (CLAUDE.md); the optional LLM step is per-region, isolated by
    construction (see module docstring).
    """
    results = await anyio.to_thread.run_sync(_classify_all, list(regions), classifier)
    if llm_client is None:
        return results
    return [
        await _with_llm_explanation(result, region, llm_client, llm_model)
        for result, region in zip(results, regions, strict=True)
    ]


@dataclass(frozen=True)
class NlpPipeline:
    """Bundles the classifier and optional LLM client/model so services take one dependency."""

    classifier: ChangeClassifier
    enabled: bool
    llm_client: Any | None
    llm_model: str

    async def analyze(self, regions: Sequence[ChangeRegion]) -> list[ChangeAnalysis]:
        if not self.enabled or not regions:
            return []
        return await analyze_regions(regions, self.classifier, self.llm_client, self.llm_model)
