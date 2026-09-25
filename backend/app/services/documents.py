"""Document registration (01_ARCHITECTURE §3.1): revision 1 of a new document, PENDING."""

import hashlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import anyio.to_thread

from app.errors import (
    EncryptedPdfError,
    FileTooLargeError,
    InvalidPdfError,
    NoExtractableTextError,
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
from app.services.tree_mapping import tree_to_doc
from app.storage import S3Storage, revision_key
from proofchain_core import build_integrity_tree
from proofchain_core import errors as core_errors

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 200
MAX_NOTE_CHARS = 2000
MAX_FILENAME_CHARS = 255

_Undo = tuple[str, Callable[[], Awaitable[Any]]]


def _clean_filename(name: str | None) -> str:
    base = PurePosixPath(PureWindowsPath(name or "").name).name.strip()
    return (base or "document.pdf")[:MAX_FILENAME_CHARS]


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
        note = (change_note or "").strip() or None
        if note and len(note) > MAX_NOTE_CHARS:
            raise ValidationFailed(f"change_note must be at most {MAX_NOTE_CHARS} characters")
        if len(data) > self._max_bytes:
            raise FileTooLargeError(
                "File exceeds the upload limit", details={"max_bytes": self._max_bytes}
            )
        if b"%PDF-" not in data[:1024]:
            raise InvalidPdfError("File is not a PDF")

        try:
            tree = await anyio.to_thread.run_sync(build_integrity_tree, data)
        except core_errors.EncryptedPdfError as exc:
            raise EncryptedPdfError("PDF is encrypted") from exc
        except core_errors.NoExtractableTextError as exc:
            raise NoExtractableTextError("PDF has no extractable text") from exc
        except core_errors.InvalidPdfError as exc:
            raise InvalidPdfError("File is not a readable PDF") from exc

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
                    original_filename=_clean_filename(filename),
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

    @staticmethod
    async def _rollback(
        undo: list[_Undo], document_id: str, revision_id: str, key: str, events_written: int
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
                logger.error("registration rollback step %s failed: %s", name, type(exc).__name__)
        if failed:
            logger.error(
                "registration rollback incomplete, orphaned resources: steps=%s "
                "document_id=%s revision_id=%s s3_key=%s",
                ",".join(failed),
                document_id,
                revision_id,
                key,
            )
        if events_written:
            logger.error(
                "registration failed after %d provenance event(s) were written; events are "
                "append-only, so they now reference a rolled-back document: document_id=%s",
                events_written,
                document_id,
            )
