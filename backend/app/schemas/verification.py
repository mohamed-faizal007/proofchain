"""Response DTOs for /verify and /verifications (04_API_SPEC Verification)."""

import datetime as dt
from typing import Any

from pydantic import BaseModel

from app.models.verification import Verification


class DocumentRefOut(BaseModel):
    id: str
    title: str | None


class VerificationReportOut(BaseModel):
    id: str
    at: dt.datetime
    verdict: str
    summary: str
    document: DocumentRefOut | None
    matched_revision: dict[str, Any] | None
    reference_revision: dict[str, Any] | None
    # Set (with `localization` null) when a TAMPERED verdict had nothing to compare against.
    no_reference_reason: str | None
    steps: list[dict[str, Any]]
    candidate: dict[str, Any]
    localization: dict[str, Any] | None
    analysis: list[dict[str, Any]] | None
    chain_check: dict[str, Any] | None
    timings_ms: dict[str, float]

    @classmethod
    def from_verification(cls, v: Verification) -> "VerificationReportOut":
        document = (
            DocumentRefOut(id=v.document_id, title=v.document_title) if v.document_id else None
        )
        return cls(
            id=v.id,
            at=v.at,
            verdict=v.verdict,
            summary=v.summary,
            document=document,
            matched_revision=v.matched_revision,
            reference_revision=v.reference_revision,
            no_reference_reason=v.no_reference_reason,
            steps=v.steps,
            candidate=v.candidate,
            localization=v.localization,
            analysis=v.analysis or None,  # null until NLP is integrated (P7-04)
            chain_check=v.chain_check,
            timings_ms=v.timings_ms,
        )


class VerificationItemOut(BaseModel):
    id: str
    at: dt.datetime
    verdict: str
    summary: str
    document: DocumentRefOut | None
    filename: str
    file_hash: str


class VerificationListOut(BaseModel):
    items: list[VerificationItemOut]
    page: int
    page_size: int
    total: int

    @classmethod
    def build(
        cls, items: list[Verification], page: int, page_size: int, total: int
    ) -> "VerificationListOut":
        rows = [
            VerificationItemOut(
                id=v.id,
                at=v.at,
                verdict=v.verdict,
                summary=v.summary,
                document=DocumentRefOut(id=v.document_id, title=v.document_title)
                if v.document_id
                else None,
                filename=v.candidate.get("filename", ""),
                file_hash=v.candidate["file_hash"],
            )
            for v in items
        ]
        return cls(items=rows, page=page, page_size=page_size, total=total)
