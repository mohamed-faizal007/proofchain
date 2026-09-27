"""Candidate matching and document association (02 §11). Read-only; no verdict is decided here."""

from dataclasses import dataclass
from typing import Literal

from app.errors import NotFoundError
from app.models.document import Document
from app.models.revision import Revision
from app.repositories.documents import DocumentRepository
from app.repositories.revisions import RevisionRepository
from proofchain_core.types import IntegrityTree

MatchKind = Literal["FILE_HASH", "TEXT_ROOT"]


@dataclass(frozen=True)
class CandidateMatch:
    """`match` keeps its real status (incl. REVOKED); P6-04 maps it to a verdict."""

    document: Document | None
    match: Revision | None
    match_kind: MatchKind | None
    is_latest_approved: bool


def _rank(rev: Revision) -> tuple[bool, int, object, str]:
    """Approved beats every other status, then the highest revision_no, then newest submission.

    Without this a resubmitted-but-rejected copy could shadow the approved original.
    """
    return (rev.status == "APPROVED", rev.revision_no, rev.submitted_at, rev.id)


class MatchingService:
    def __init__(self, documents: DocumentRepository, revisions: RevisionRepository) -> None:
        self._documents = documents
        self._revisions = revisions

    async def match(self, cand: IntegrityTree, document_id: str | None = None) -> CandidateMatch:
        document: Document | None = None
        if document_id is not None:
            document = await self._documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")

        # 02 §11: file hash first, then text root (only under the same canon version).
        found = await self._revisions.find_by_file_hash(cand.file_hash, document_id)
        kind: MatchKind | None = "FILE_HASH" if found else None
        if not found:
            found = await self._revisions.find_by_text_root(
                cand.text_root, document_id, cand.canon_version
            )
            kind = "TEXT_ROOT" if found else None
        if not found:
            return CandidateMatch(document, None, None, False)

        match = max(found, key=_rank)
        if document is None:
            document = await self._documents.get(match.document_id)
        latest = document.latest_approved_revision_id if document else None
        return CandidateMatch(
            document,
            match,
            kind,
            match.status == "APPROVED" and latest == match.id,
        )
