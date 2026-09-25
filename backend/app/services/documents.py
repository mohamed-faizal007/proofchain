"""Document registration (01_ARCHITECTURE §3.1) and revision submission, PENDING."""

import datetime as dt
import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.errors import (
    ConflictError,
    ForbiddenError,
    NoContentChangeError,
    NotFoundError,
    PendingRevisionExistsError,
    ValidationFailed,
)
from app.models.base import new_id
from app.models.document import DocType, Document
from app.models.revision import FileInfo, Revision
from app.models.user import User
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.services._intake import build_tree_from_upload, clean_filename, clean_note
from app.services.tree_mapping import tree_to_doc
from app.storage import S3Storage, revision_key

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 200

_Undo = tuple[str, Callable[[], Awaitable[Any]]]


class DocumentService:
    def __init__(
        self,
        documents: DocumentRepository,
        revisions: RevisionRepository,
        trees: TreeRepository,
        events: EventRepository,
        storage: S3Storage,
        max_upload_bytes: int,
    ) -> None:
        self._documents = documents
        self._revisions = revisions
        self._trees = trees
        self._events = events
        self._storage = storage
        self._max_bytes = max_upload_bytes

    async def register(
        self,
        owner: User,
        *,
        data: bytes,
        filename: str | None,
        title: str,
        doc_type: DocType,
        change_note: str | None = None,
    ) -> tuple[Document, Revision]:
        title = title.strip()
        if not title or len(title) > MAX_TITLE_CHARS:
            raise ValidationFailed(f"title must be 1-{MAX_TITLE_CHARS} characters")
        note = clean_note(change_note)
        tree = await build_tree_from_upload(data, self._max_bytes)

        document_id = new_id()
        revision_id = new_id()
        key = revision_key(document_id, revision_id)
        document = Document(
            _id=document_id,
            title=title,
            doc_type=doc_type,
            owner_id=owner.id,
            chain_doc_id=hashlib.sha256(document_id.encode("utf-8")).hexdigest(),
            revision_count=1,
        )
        undo: list[_Undo] = []
        events_written = 0
        try:
            stored = await self._storage.put(key, data)
            undo.append(("s3", lambda: self._storage.delete(key, stored.version_id)))
            revision = Revision(
                _id=revision_id,
                document_id=document_id,
                revision_no=1,
                change_note=note,
                submitted_by=owner.id,
                file=FileInfo(
                    s3_key=key,
                    s3_version_id=stored.version_id,
                    size_bytes=len(data),
                    original_filename=clean_filename(filename),
                ),
                file_hash=tree.file_hash,
                text_root=tree.text_root,
                canon_version=tree.canon_version,
                page_count=tree.page_count,
                chunk_count=sum(len(p.chunks) for p in tree.pages),
            )
            # DB undo steps are registered before the write: a write that raises after committing
            # (timeout, lost ack) must still be rolled back; deleting a missing row is a no-op.
            undo.append(("document", lambda: self._documents.delete(document_id)))
            await self._documents.insert(document)
            undo.append(("revision", lambda: self._revisions.delete(revision_id)))
            await self._revisions.insert(revision)
            undo.append(("tree", lambda: self._trees.delete(revision_id)))
            await self._trees.upsert(tree_to_doc(tree, revision_id, document_id))
            # Events are append-only and cannot be rolled back; they are written last.
            await self._events.append(
                document_id,
                "DOCUMENT_CREATED",
                actor_id=owner.id,
                revision_id=revision_id,
                data={"title": title, "doc_type": doc_type},
            )
            events_written = 1
            await self._events.append(
                document_id,
                "REVISION_SUBMITTED",
                actor_id=owner.id,
                revision_id=revision_id,
                data={
                    "revision_no": 1,
                    "file_hash": tree.file_hash,
                    "text_root": tree.text_root,
                    "change_note": note,
                },
            )
        except Exception:
            await self._rollback(undo, document_id, revision_id, key, events_written)
            raise
        return document, revision

    async def submit_revision(
        self,
        submitter: User,
        document_id: str,
        *,
        data: bytes,
        filename: str | None,
        change_note: str | None,
    ) -> tuple[Document, Revision]:
        document = await self._documents.get(document_id)
        if document is None:
            raise NotFoundError("Document not found")
        # 04 says only "ISSUER"; owner-only is an interpretation (PROGRESS P5-02).
        if document.owner_id != submitter.id:
            raise ForbiddenError("Only the document owner can submit revisions")
        note = clean_note(change_note)
        if note is None:
            raise ValidationFailed("change_note is required")
        if await self._revisions.get_pending(document_id) is not None:
            raise PendingRevisionExistsError("A revision is already pending for this document")
        tree = await build_tree_from_upload(data, self._max_bytes)
        parent = await self._revisions.get_latest_approved(document_id)
        if (
            parent is not None
            and parent.canon_version == tree.canon_version
            and parent.text_root == tree.text_root
        ):
            raise NoContentChangeError("Text content is identical to the latest approved revision")

        revision_id = new_id()
        key = revision_key(document_id, revision_id)
        undo: list[_Undo] = []
        events_written = 0
        try:
            revision_no = await self._revisions.next_revision_no(document_id)
            stored = await self._storage.put(key, data)
            undo.append(("s3", lambda: self._storage.delete(key, stored.version_id)))
            revision = Revision(
                _id=revision_id,
                document_id=document_id,
                revision_no=revision_no,
                parent_revision_id=parent.id if parent else None,
                change_note=note,
                submitted_by=submitter.id,
                file=FileInfo(
                    s3_key=key,
                    s3_version_id=stored.version_id,
                    size_bytes=len(data),
                    original_filename=clean_filename(filename),
                ),
                file_hash=tree.file_hash,
                text_root=tree.text_root,
                canon_version=tree.canon_version,
                page_count=tree.page_count,
                chunk_count=sum(len(p.chunks) for p in tree.pages),
            )
            undo.append(("revision", lambda: self._revisions.delete(revision_id)))
            try:
                await self._revisions.insert(revision)
            except ConflictError as exc:
                # Unique (document_id, revision_no): a concurrent submit won the race.
                raise PendingRevisionExistsError(
                    "A revision is already pending for this document"
                ) from exc
            undo.append(("tree", lambda: self._trees.delete(revision_id)))
            await self._trees.upsert(tree_to_doc(tree, revision_id, document_id))
            # Registered after success: a compensating -1 for an increment that never happened
            # would corrupt the counter.
            now = dt.datetime.now(dt.UTC)
            if not await self._documents.bump_revision_count(document_id, now):
                raise NotFoundError("Document not found")
            undo.append(
                ("counter", lambda: self._documents.bump_revision_count(document_id, now, -1))
            )
            await self._events.append(
                document_id,
                "REVISION_SUBMITTED",
                actor_id=submitter.id,
                revision_id=revision_id,
                data={
                    "revision_no": revision_no,
                    "parent_revision_id": revision.parent_revision_id,
                    "file_hash": tree.file_hash,
                    "text_root": tree.text_root,
                    "change_note": note,
                },
            )
            events_written = 1
        except Exception:
            await self._rollback(
                undo, document_id, revision_id, key, events_written, op="revision submission"
            )
            raise
        updated = document.model_copy(
            update={"revision_count": document.revision_count + 1, "updated_at": now}
        )
        return updated, revision

    @staticmethod
    async def _rollback(
        undo: list[_Undo],
        document_id: str,
        revision_id: str,
        key: str,
        events_written: int,
        op: str = "registration",
    ) -> None:
        """Best effort, every step attempted; never raises so the caller sees the original error.

        Logs class names only (never `str(exc)`), plus the ids a reconciler needs.
        """
        failed: list[str] = []
        for name, step in reversed(undo):
            try:
                await step()
            except Exception as exc:
                failed.append(name)
                logger.error("%s rollback step %s failed: %s", op, name, type(exc).__name__)
        if failed:
            logger.error(
                "%s rollback incomplete, orphaned resources: steps=%s "
                "document_id=%s revision_id=%s s3_key=%s",
                op,
                ",".join(failed),
                document_id,
                revision_id,
                key,
            )
        if events_written:
            logger.error(
                "%s failed after %d provenance event(s) were written; events are "
                "append-only, so they now reference a rolled-back document: document_id=%s",
                op,
                events_written,
                document_id,
            )
