"""Verdict table and report wording for /verify (02 §11, 00_PRD §5, ADR-020). Pure functions.

Crypto decides: nothing here reads NLP output.
"""

from dataclasses import dataclass
from typing import Any, Literal

from app.models.revision import Revision
from app.services.chain_check import ChainCheckResult
from app.services.matching import CandidateMatch
from app.services.reference import CANON_MISMATCH
from proofchain_core.types import LocalizationResult

Verdict = Literal[
    "AUTHENTIC_LATEST",
    "AUTHENTIC_SUPERSEDED",
    "CONTENT_EQUIVALENT",
    "UNAUTHORIZED_VERSION",
    "TAMPERED",
    "RECORD_MISMATCH",
    "UNKNOWN_DOCUMENT",
]
StepStatus = Literal["PASS", "FAIL", "WARN", "DONE", "SKIPPED"]


@dataclass(frozen=True)
class Decision:
    """The Mongo-based verdict and the AUTHORIZATION step that explains it."""

    verdict: Verdict
    status: StepStatus
    detail: str


def label(rev: Revision) -> str:
    version = f" (v{rev.version_no})" if rev.version_no is not None else ""
    return f"revision {rev.revision_no}{version}"


def decide(cm: CandidateMatch, redact: bool = False) -> Decision:
    """02 §11 before the chain cross-check. `redact` omits the revocation reason (anonymous)."""
    match = cm.match
    if match is not None and match.status == "APPROVED":
        if cm.match_kind == "FILE_HASH":
            if cm.is_latest_approved:
                return Decision(
                    "AUTHENTIC_LATEST",
                    "PASS",
                    f"Byte-identical to the latest approved version, {label(match)}",
                )
            return Decision(
                "AUTHENTIC_SUPERSEDED",
                "PASS",
                f"Byte-identical to approved {label(match)}; a newer approved version exists",
            )
        return Decision(
            "CONTENT_EQUIVALENT",
            "WARN",
            f"Canonical text equals approved {label(match)} but the file bytes differ "
            "(re-save, metadata or a non-text change); not reported as authentic",
        )
    if match is not None:
        return Decision("UNAUTHORIZED_VERSION", "FAIL", _unauthorized_detail(match, redact))
    if cm.document is not None:
        return Decision("TAMPERED", "FAIL", "No approved, pending or rejected revision matches")
    return Decision("UNKNOWN_DOCUMENT", "FAIL", "No document could be associated with the upload")


def _unauthorized_detail(match: Revision, redact: bool = False) -> str:
    if match.status == "REVOKED" and match.revocation is not None:
        rv = match.revocation
        when = f"Matches {label(match)}, which was revoked on {rv.at.date().isoformat()}"
        return when if redact else f"{when}: {rv.reason}"
    if match.status == "REVOKED":
        return f"Matches {label(match)}, which was revoked"
    return f"Matches {label(match)}, which was submitted but never approved (status {match.status})"


def _pages(loc: LocalizationResult) -> str:
    pages = sorted(
        {
            (r.cand_page if r.cand_page is not None else r.ref_page) + 1  # type: ignore[operator]
            for r in loc.regions
            if r.cand_page is not None or r.ref_page is not None
        }
    )
    return ", ".join(map(str, pages))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def no_reference_text(reason: str | None) -> str:
    if reason == CANON_MISMATCH:
        return (
            "no approved version was built under the current canonicalization rules, so the "
            "file could not be compared"
        )
    return "this document has no approved version yet, so the file could not be compared"


def summarize(
    decision: Decision,
    verdict: Verdict,
    title: str | None,
    reference: Revision | None,
    loc: LocalizationResult | None,
    no_reference_reason: str | None,
    chain: ChainCheckResult,
) -> str:
    """One report line; TAMPERED with and without a reference must never read alike."""
    if verdict == "RECORD_MISMATCH":
        fields = ", ".join(chain.mismatches)
        return (
            f"Off-chain record disagrees with the on-chain anchor ({fields}); database tampering "
            f"suspected. Off-chain records alone indicated {decision.verdict}."
        )
    if verdict == "TAMPERED":
        if reference is None or loc is None:
            return (
                "TAMPERED, no reference available: the file matches no revision of this "
                f"document and {no_reference_text(no_reference_reason)}. No changes were localized."
            )
        n = len(loc.regions)
        if n == 0:
            return f"Matches no revision; no chunk-level changes vs approved {label(reference)}"
        return f"{_plural(n, 'change')} on page(s) {_pages(loc)} vs approved {label(reference)}"
    if verdict == "UNKNOWN_DOCUMENT":
        return "No document could be associated with the upload; select the document to verify"
    doc = f" of '{title}'" if title else ""
    return f"{decision.detail}{doc}"


def localization_step(
    reference: Revision | None, loc: LocalizationResult | None, reason: str | None, applicable: bool
) -> tuple[StepStatus, str]:
    if not applicable:
        return "SKIPPED", "Not needed: the upload matches a known revision or no document is known"
    if reference is None or loc is None:
        return "SKIPPED", f"NO_REFERENCE ({reason}): {no_reference_text(reason)}; nothing localized"
    method = loc.method.value if loc.method else "none"
    stats: dict[str, Any] = loc.stats
    return "DONE", (
        f"vs {label(reference)}: {method}, {loc.hash_comparisons} comparisons, "
        f"{stats['modified']} modified / {stats['inserted']} inserted / {stats['deleted']} deleted"
    )


def chain_step(chain: ChainCheckResult) -> tuple[StepStatus, str | None]:
    if not chain.performed:
        return "SKIPPED", f"Not performed: {chain.reason}"
    if chain.ok:
        return "PASS", None
    return "FAIL", f"On-chain and off-chain records differ in: {', '.join(chain.mismatches)}"
