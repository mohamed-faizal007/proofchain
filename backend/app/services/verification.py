"""POST /verify orchestration (02 §10-11, 04 VerificationReport).

Crypto decides, AI explains: the verdict is fixed here from hashes and the chain; NLP (P7) can only
add `analysis` afterwards.
"""

import datetime as dt
import time
from typing import Any

from app.errors import ForbiddenError, NotFoundError
from app.models.document import Document
from app.models.revision import Revision
from app.models.user import User
from app.models.verification import Verification
from app.repositories.documents import DocumentRepository
from app.repositories.verifications import VerificationRepository
from app.services._intake import build_tree_from_upload, clean_filename
from app.services.chain_check import ChainCheckResult, ChainCheckService
from app.services.matching import CandidateMatch, MatchingService
from app.services.reference import ReferenceResult, ReferenceService
from app.services.verdict import (
    Verdict,
    chain_step,
    decide,
    localization_step,
    summarize,
)
from proofchain_core.types import IntegrityTree

NOT_APPLICABLE = "NOT_APPLICABLE"
NLP_NOT_INTEGRATED = "NLP analysis is not available yet"


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _now_ms() -> dt.datetime:
    """Mongo stores milliseconds; truncate here so POST and GET report the same instant."""
    now = dt.datetime.now(dt.UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def revision_ref(rev: Revision) -> dict[str, Any]:
    """Snapshot of a revision for the report (never the S3 key)."""
    return {
        "id": rev.id,
        "revision_no": rev.revision_no,
        "version_no": rev.version_no,
        "status": rev.status,
        "anchored_tx": rev.anchor.tx_hash,
        "revocation": rev.revocation.model_dump(mode="json") if rev.revocation else None,
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
    ) -> None:
        self._documents = documents
        self._matching = matching
        self._reference = reference
        self._chain = chain
        self._verifications = verifications
        self._max_bytes = max_bytes
        self._explorer = explorer_tx_url

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
        cm = await self._matching.match(cand, document_id)
        timings["match"] = _ms(t)
        decision = decide(cm)

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
        timings["nlp"] = 0.0  # P7-04 fills this in; the verdict is already final
        timings["total"] = _ms(t0)

        record = self._record(
            user, cand, filename, cm, decision, verdict, ref, chain, include_nlp, timings
        )
        return await self._verifications.insert(record)

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
        include_nlp: bool,
        timings: dict[str, float],
    ) -> Verification:
        doc = cm.document
        loc = ref.localization
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
            _step(
                "SEMANTIC_ANALYSIS",
                "SKIPPED",
                NLP_NOT_INTEGRATED if include_nlp else "Not requested",
            ),
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
            matched_revision=revision_ref(cm.match) if cm.match else None,
            reference_revision=revision_ref(ref.reference) if ref.reference else None,
            no_reference_reason=ref.no_localization_reason,
            chain_check={
                "performed": chain.performed,
                "ok": chain.ok,
                "reason": chain.reason,
                "mismatches": list(chain.mismatches),
                "tx_hash": tx,
                "explorer_url": f"{self._explorer}{tx}" if self._explorer and tx else None,
            },
            localization=loc.to_dict() if loc else None,
            analysis=[],
            timings_ms=timings,
        )

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
