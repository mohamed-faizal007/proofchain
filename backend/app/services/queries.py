"""Read-only document/revision queries (04 Documents & revisions, GET routes). No writes here."""

import re
from dataclasses import dataclass
from typing import Any

import anyio.to_thread

from app.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.document import DocType, Document
from app.models.integrity_tree import IntegrityTreeDoc
from app.models.provenance_event import ProvenanceEvent
from app.models.revision import Revision, RevisionStatus
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.services.tree_mapping import doc_to_tree
from app.storage import S3Storage
from proofchain_core import localize
from proofchain_core.types import LocalizationResult


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


class QueryService:
    def __init__(
        self,
        documents: DocumentRepository,
        revisions: RevisionRepository,
        trees: TreeRepository,
        events: EventRepository,
        storage: S3Storage,
    ) -> None:
        self._documents = documents
        self._revisions = revisions
        self._trees = trees
        self._events = events
        self._storage = storage

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
        return RevisionDiff(revision_id, against_id, result)

    async def presign_file(self, revision_id: str) -> tuple[str, int]:
        """(url, expires_in). The URL pins the stored S3 version, so it serves those exact bytes.

        KNOWN LIMITATION: signed against the internal S3 endpoint (PROGRESS.md "Presigned URL
        host", owned by P8-03 / P10-03).
        """
        revision = await self.get_revision(revision_id)
        url = await self._storage.presign_get(revision.file.s3_key, revision.file.s3_version_id)
        return url, self._storage.presign_expiry_seconds

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
