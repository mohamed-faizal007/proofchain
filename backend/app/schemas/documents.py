"""Request/response DTOs for documents and revisions (04_API_SPEC Documents & revisions)."""

import datetime as dt

from pydantic import BaseModel

from app.models.document import DocType, Document
from app.models.revision import Anchor, Revision, RevisionStatus


class DocumentOut(BaseModel):
    id: str
    title: str
    doc_type: DocType
    owner_id: str
    chain_doc_id: str
    latest_approved_revision_id: str | None
    latest_approved_version_no: int | None
    revision_count: int
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_document(cls, d: Document) -> "DocumentOut":
        return cls(**d.model_dump())


class RevisionOut(BaseModel):
    id: str
    document_id: str
    revision_no: int
    parent_revision_id: str | None
    change_note: str | None
    status: RevisionStatus
    version_no: int | None
    submitted_by: str
    submitted_at: dt.datetime
    reviewed_by: str | None
    reviewed_at: dt.datetime | None
    review_comment: str | None
    original_filename: str
    size_bytes: int
    file_hash: str
    text_root: str
    canon_version: int
    page_count: int
    chunk_count: int
    anchor: Anchor

    @classmethod
    def from_revision(cls, r: Revision) -> "RevisionOut":
        data = r.model_dump(exclude={"file"})
        return cls(
            **data,
            original_filename=r.file.original_filename,
            size_bytes=r.file.size_bytes,
        )


class RegisterResponse(BaseModel):
    document: DocumentOut
    revision: RevisionOut
