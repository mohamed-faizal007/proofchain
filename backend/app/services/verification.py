"""POST /verify orchestration (02 §10-11, 04 VerificationReport).

Crypto decides, AI explains: the verdict is fixed here from hashes and the chain; NLP (P7) can only
add `analysis` afterwards.
"""

import datetime as dt
import logging
import time
from typing import Any

from app.errors import ForbiddenError, NotFoundError
from app.models.document import Document
from app.models.revision import Revision
from app.models.user import User
from app.models.verification import Verification
from app.nlp.analyze import NlpPipeline
from app.repositories.documents import DocumentRepository
from app.repositories.verifications import VerificationRepository
from app.services._intake import build_tree_from_upload, clean_filename
from app.services.chain_check import ChainCheckResult, ChainCheckService
from app.services.matching import CandidateMatch, MatchingService
from app.services.reference import ReferenceResult, ReferenceService
from app.services.verdict import (
    StepStatus,
    Verdict,
    chain_step,
    decide,
    localization_step,
    summarize,
)
from proofchain_core.types import IntegrityTree, LocalizationResult

logger = logging.getLogger(__name__)

NOT_APPLICABLE = "NOT_APPLICABLE"
NLP_NOT_REQUESTED = "Not requested"
NLP_DISABLED = "NLP disabled"
NLP_NO_REGIONS = "No localized regions to analyze"
NLP_FAILED = "NLP analysis failed"
NLP_ANONYMOUS = "Not available for anonymous requests"


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _now_ms() -> dt.datetime:
    """Mongo stores milliseconds; truncate here so POST and GET report the same instant."""
    now = dt.datetime.now(dt.UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


_REDACTED_REGION_FIELDS = (
    "ref_text",
    "cand_text",
    "ref_bbox",
    "cand_bbox",
    "ref_chunk_id",
    "section_title",
)


def redact_localization(loc: dict[str, Any]) -> dict[str, Any]:
    """Anonymous callers keep region type, pages and counts, never stored or uploaded text."""
    regions = [{**r, **dict.fromkeys(_REDACTED_REGION_FIELDS)} for r in loc["regions"]]
    return {**loc, "regions": regions}


def revision_ref(rev: Revision, redact: bool = False) -> dict[str, Any]:
    """Snapshot of a revision for the report (never the S3 key).

    `redact` keeps only the date of a revocation (not the reason, the revoker or the tx).
    """
    revocation = None
    if rev.revocation is not None:
        full = rev.revocation.model_dump(mode="json")
        revocation = {"at": full["at"]} if redact else full
    return {
        "id": rev.id,
        "revision_no": rev.revision_no,
        "version_no": rev.version_no,
        "status": rev.status,
        "anchored_tx": rev.anchor.tx_hash,
        "revocation": revocation,
    }


class VerificationService:
    def __init__(
        self,
        documents: DocumentRepository,
        matching: MatchingService,
        reference: ReferenceService,
        chain: ChainCheckService,
        verifications: VerificationRepository,
        max_bytes: int,
        explorer_tx_url: str = "",
        nlp: NlpPipeline | None = None,
    ) -> None:
        self._documents = documents
        self._matching = matching
        self._reference = reference
        self._chain = chain
        self._verifications = verifications
        self._max_bytes = max_bytes
        self._explorer = explorer_tx_url
        self._nlp = nlp

    async def verify(
        self,
        user: User | None,
        *,
        data: bytes,
        filename: str | None,
        document_id: str | None = None,
        include_nlp: bool = True,
    ) -> Verification:
        t0 = time.perf_counter()
        timings: dict[str, float] = {}

        t = time.perf_counter()
        cand = await build_tree_from_upload(data, self._max_bytes)
        timings["hash"] = _ms(t)

        t = time.perf_counter()
        anonymous = user is None
        try:
            cm = await self._matching.match(cand, document_id)
        except NotFoundError:
            if not anonymous:
                raise
            # An anonymous caller cannot tell an unknown id from no id (no existence oracle).
            cm = await self._matching.match(cand, None)
        timings["match"] = _ms(t)
        decision = decide(cm, redact=anonymous)

        ref = ReferenceResult(None, None, None)
        t = time.perf_counter()
        if decision.verdict == "TAMPERED" and cm.document is not None:
            ref = await self._reference.localize_against(cand, cm.document.id)
        timings["localize"] = _ms(t)

        target = cm.match or ref.reference
        t = time.perf_counter()
        chain = await self._cross_check(target, cm.document)
        timings["chain"] = _ms(t)

        verdict: Verdict = decision.verdict
        if chain.performed and chain.ok is False:
            verdict = "RECORD_MISMATCH"  # overrides every other verdict (ADR-020)

        # NLP is advisory-only and runs after the verdict above is already final (06 "crypto
        # decides, AI explains"): nothing here can change `verdict`, including a failure.
        t = time.perf_counter()
        analysis, nlp_status, nlp_detail = await self._analyze(
            include_nlp, anonymous, ref.localization
        )
        timings["nlp"] = _ms(t)
        timings["total"] = _ms(t0)

        record = self._record(
            user,
            cand,
            filename,
            cm,
            decision,
            verdict,
            ref,
            chain,
            timings,
            analysis,
            nlp_status,
            nlp_detail,
        )
        return await self._verifications.insert(record)

    async def _analyze(
        self, include_nlp: bool, anonymous: bool, loc: LocalizationResult | None
    ) -> tuple[list[dict[str, Any]], StepStatus, str | None]:
        if not include_nlp:
            return [], "SKIPPED", NLP_NOT_REQUESTED
        if anonymous:
            # `explanation`/`entity_changes` would reveal reference document content the same
            # way region text did before ADR-021's redaction; simplest safe answer is to never
            # run NLP for anonymous callers, rather than inventing a second redaction shape.
            return [], "SKIPPED", NLP_ANONYMOUS
        if self._nlp is None or not self._nlp.enabled:
            return [], "SKIPPED", NLP_DISABLED
        if loc is None or not loc.regions:
            return [], "SKIPPED", NLP_NO_REGIONS
        try:
            results = await self._nlp.analyze(loc.regions)
        except Exception as exc:
            # Class name only, never str(exc)/exc_info: a region carries document text and an
            # exception message could echo it (same rule as chain errors, PROGRESS.md P5-04).
            logger.warning(
                "nlp analysis failed (%d regions): %s", len(loc.regions), type(exc).__name__
            )
            return [], "SKIPPED", NLP_FAILED
        return [r.to_dict() for r in results], "DONE", None

    async def _cross_check(self, target: Revision | None, doc: Document | None) -> ChainCheckResult:
        if target is None or doc is None:
            return ChainCheckResult(performed=False, ok=None, reason=NOT_APPLICABLE)
        return await self._chain.check(target, doc.chain_doc_id)

    def _record(
        self,
        user: User | None,
        cand: IntegrityTree,
        filename: str | None,
        cm: CandidateMatch,
        decision: Any,
        verdict: Verdict,
        ref: ReferenceResult,
        chain: ChainCheckResult,
        timings: dict[str, float],
        analysis: list[dict[str, Any]],
        nlp_status: StepStatus,
        nlp_detail: str | None,
    ) -> Verification:
        doc = cm.document
        loc = ref.localization
        anonymous = user is None
        loc_status, loc_detail = localization_step(
            ref.reference, loc, ref.no_localization_reason, decision.verdict == "TAMPERED"
        )
        chain_status, chain_detail = chain_step(chain)
        exact = cm.match is not None and cm.match_kind == "FILE_HASH"
        steps: list[dict[str, Any]] = [
            _step("FILE_HASH", "PASS" if exact else "FAIL", None),
            _step("TEXT_ROOT", "PASS" if cm.match else "FAIL", None),
            _step("LOCALIZATION", loc_status, loc_detail),
            _step("AUTHORIZATION", decision.status, decision.detail),
            _step("CHAIN_CHECK", chain_status, chain_detail),
            _step("SEMANTIC_ANALYSIS", nlp_status, nlp_detail),
        ]
        tx = chain.tx_hash
        return Verification(
            requested_by=user.id if user else None,
            at=_now_ms(),
            document_id=doc.id if doc else None,
            document_title=doc.title if doc else None,
            candidate={
                "filename": clean_filename(filename),
                "file_hash": cand.file_hash,
                "text_root": cand.text_root,
                "page_count": cand.page_count,
            },
            verdict=verdict,
            summary=summarize(
                decision,
                verdict,
                doc.title if doc else None,
                ref.reference,
                loc,
                ref.no_localization_reason,
                chain,
            ),
            steps=steps,
            matched_revision_id=cm.match.id if cm.match else None,
            reference_revision_id=ref.reference.id if ref.reference else None,
            matched_revision=revision_ref(cm.match, anonymous) if cm.match else None,
            reference_revision=revision_ref(ref.reference, anonymous) if ref.reference else None,
            no_reference_reason=ref.no_localization_reason,
            chain_check={
                "performed": chain.performed,
                "ok": chain.ok,
                "reason": chain.reason,
                "mismatches": list(chain.mismatches),
                "tx_hash": tx,
                "explorer_url": f"{self._explorer}{tx}" if self._explorer and tx else None,
            },
            localization=self._localization_out(loc, anonymous),
            analysis=analysis,
            timings_ms=timings,
        )

    @staticmethod
    def _localization_out(loc: Any, anonymous: bool) -> dict[str, Any] | None:
        if loc is None:
            return None
        out: dict[str, Any] = loc.to_dict()
        return redact_localization(out) if anonymous else out

    async def get(self, user: User, verification_id: str) -> Verification:
        """Owner or ADMIN only; an anonymous run (`requested_by` None) is ADMIN-only."""
        found = await self._verifications.get(verification_id)
        if found is None:
            raise NotFoundError("Verification not found")
        if "ADMIN" not in user.roles and found.requested_by != user.id:
            raise ForbiddenError("Not your verification")
        return found

    async def history(
        self, user: User, page: int, page_size: int
    ) -> tuple[list[Verification], int]:
        return await self._verifications.page_by_requester(
            user.id, (page - 1) * page_size, page_size
        )


def _step(name: str, status: str, detail: str | None) -> dict[str, Any]:
    step: dict[str, Any] = {"name": name, "status": status}
    if detail is not None:
        step["detail"] = detail
    return step
