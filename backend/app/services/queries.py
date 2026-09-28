"""Read-only document/revision queries (04 Documents & revisions, GET routes). No writes here."""

import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import anyio.to_thread

from app.errors import ConflictError, NotFoundError, StorageError, ValidationFailed
from app.models.document import DocType, Document
from app.models.integrity_tree import IntegrityTreeDoc
from app.models.provenance_event import ProvenanceEvent
from app.models.revision import Revision, RevisionStatus
from app.nlp.analyze import NlpPipeline
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.services.tree_mapping import doc_to_tree
from app.storage import S3Storage
from proofchain_core import localize
from proofchain_core.types import LocalizationResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentPage:
    items: list[Document]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class Provenance:
    document_id: str
    chain_valid: bool
    events: list[ProvenanceEvent]


@dataclass(frozen=True)
class RevisionDiff:
    revision_id: str
    against_revision_id: str
    localization: LocalizationResult
    analysis: list[dict[str, Any]] | None


@dataclass(frozen=True)
class DownloadedFile:
    content: bytes
    filename: str
    content_type: str


def _sanitize_download_filename(name: str) -> str:
    """Path-stripped, ASCII-printable, no quotes/backslash: safe inside a Content-Disposition
    header with no further escaping (P8-03)."""
    stripped = PurePosixPath(PureWindowsPath(name).name).name
    cleaned = "".join(ch for ch in stripped if 32 <= ord(ch) < 127 and ch not in '"\\')
    return cleaned.strip() or "revision.pdf"


class QueryService:
    def __init__(
        self,
        documents: DocumentRepository,
        revisions: RevisionRepository,
        trees: TreeRepository,
        events: EventRepository,
        storage: S3Storage,
        nlp: NlpPipeline | None = None,
    ) -> None:
        self._documents = documents
        self._revisions = revisions
        self._trees = trees
        self._events = events
        self._storage = storage
        self._nlp = nlp

    async def list_documents(
        self,
        *,
        q: str | None,
        doc_type: DocType | None,
        status: RevisionStatus | None,
        page: int,
        page_size: int,
    ) -> DocumentPage:
        """`status` matches documents with at least one revision in that status, so a document
        whose revisions span several statuses appears under each of them (PROGRESS.md, P5-05)."""
        filter_: dict[str, Any] = {}
        text = (q or "").strip()
        if text:
            # Literal, case-insensitive substring: user input is never a regex.
            filter_["title"] = {"$regex": re.escape(text), "$options": "i"}
        if doc_type is not None:
            filter_["doc_type"] = doc_type
        if status is not None:
            filter_["_id"] = {"$in": await self._revisions.document_ids_with_status(status)}
        items, total = await self._documents.page(
            filter_, skip=(page - 1) * page_size, limit=page_size
        )
        return DocumentPage(items, page, page_size, total)

    async def get_document(self, document_id: str) -> tuple[Document, Revision | None]:
        """The document and its newest APPROVED revision, read from the revisions themselves."""
        document = await self._document(document_id)
        return document, await self._revisions.get_latest_approved(document_id)

    async def list_revisions(self, document_id: str) -> list[Revision]:
        await self._document(document_id)
        return await self._revisions.list_by_document(document_id)

    async def get_revision(self, revision_id: str) -> Revision:
        revision = await self._revisions.get(revision_id)
        if revision is None:
            raise NotFoundError("Revision not found")
        return revision

    async def get_tree(self, revision_id: str) -> IntegrityTreeDoc:
        await self.get_revision(revision_id)
        return await self._tree(revision_id)

    async def diff(self, revision_id: str, against_id: str | None) -> RevisionDiff:
        """Localize `revision_id` (candidate) against `against_id` (reference, default the parent).

        Any status may be diffed. Trees built under different canon versions are refused
        (409): their hashes are not comparable and `localize` does not check (P1-09 finding 9).
        """
        revision = await self.get_revision(revision_id)
        if against_id is None:
            if revision.parent_revision_id is None:
                raise ValidationFailed(
                    "Revision has no parent; pass `against`", {"field": "against"}
                )
            against_id = revision.parent_revision_id
        against = await self.get_revision(against_id)
        if against.document_id != revision.document_id:
            raise ValidationFailed(
                "`against` must be a revision of the same document", {"field": "against"}
            )
        cand = await self._tree(revision_id)
        ref = await self._tree(against_id)
        if ref.canon_version != cand.canon_version:
            raise ConflictError(
                "Revisions were hashed under different canonicalization versions",
                {"canon_version": cand.canon_version, "against_canon_version": ref.canon_version},
            )
        result = await anyio.to_thread.run_sync(localize, doc_to_tree(ref), doc_to_tree(cand))
        analysis = await self._analyze(result)
        return RevisionDiff(revision_id, against_id, result, analysis)

    async def _analyze(self, result: LocalizationResult) -> list[dict[str, Any]] | None:
        """`None` until NLP is integrated or disabled (04: "`analysis` is `null` until NLP is
        integrated"); advisory-only and never raises past here (06 "crypto decides, AI
        explains" -- this has no verdict to protect, but a diff must still not 500 on an NLP
        bug)."""
        if self._nlp is None or not self._nlp.enabled or not result.regions:
            return None
        try:
            analyzed = await self._nlp.analyze(result.regions)
        except Exception as exc:
            logger.warning(
                "nlp analysis failed (%d regions): %s", len(result.regions), type(exc).__name__
            )
            return None
        return [a.to_dict() for a in analyzed]

    async def presign_file(self, revision_id: str) -> tuple[str, int]:
        """(url, expires_in). The URL pins the stored S3 version, so it serves those exact bytes.

        KNOWN LIMITATION: signed against the internal S3 endpoint (PROGRESS.md "Presigned URL
        host", owned by P8-03 / P10-03).
        """
        revision = await self.get_revision(revision_id)
        url = await self._storage.presign_get(revision.file.s3_key, revision.file.s3_version_id)
        return url, self._storage.presign_expiry_seconds

    async def download_file(self, revision_id: str) -> DownloadedFile:
        """Streams the stored PDF bytes for a revision instead of a presigned URL, so the
        frontend never needs a browser-reachable route to the internal S3 endpoint (P8-03,
        PROGRESS.md "Presigned URL host"; `/file` above keeps the old behavior and its limit).
        """
        revision = await self.get_revision(revision_id)
        try:
            content = await self._storage.get(revision.file.s3_key, revision.file.s3_version_id)
        except NotFoundError as exc:
            raise NotFoundError("Revision file not found") from exc
        except StorageError as exc:
            # Generic message: the S3 key must never reach the response body (04_API_SPEC).
            raise StorageError("failed to read revision file") from exc
        filename = _sanitize_download_filename(revision.file.original_filename)
        return DownloadedFile(
            content=content, filename=filename, content_type=revision.file.content_type
        )

    async def provenance(self, document_id: str) -> Provenance:
        await self._document(document_id)
        events = await self._events.list_by_document(document_id)
        check = await self._events.verify_chain(document_id)
        return Provenance(document_id, check.ok, events)

    async def _tree(self, revision_id: str) -> IntegrityTreeDoc:
        tree = await self._trees.get_for_revision(revision_id)
        if tree is None:
            raise NotFoundError("Integrity tree not found")
        return tree

    async def _document(self, document_id: str) -> Document:
        document = await self._documents.get(document_id)
        if document is None:
            raise NotFoundError("Document not found")
        return document
