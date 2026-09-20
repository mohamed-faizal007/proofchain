"""revisions collection (03_DATA_MODEL)."""

import datetime as dt
from typing import Literal

from pydantic import Field

from app.models.base import MongoModel, new_id

RevisionStatus = Literal["PENDING", "APPROVED", "REJECTED", "REVOKED"]
AnchorStatus = Literal["NOT_REQUESTED", "ANCHORING", "ANCHORED", "FAILED"]


class FileInfo(MongoModel):
    s3_key: str
    s3_version_id: str | None = None
    size_bytes: int
    original_filename: str
    content_type: str = "application/pdf"


class Anchor(MongoModel):
    status: AnchorStatus = "NOT_REQUESTED"
    tx_hash: str | None = None
    block_number: int | None = None
    chain_id: int | None = None
    contract: str | None = None
    anchored_at: dt.datetime | None = None
    error: str | None = None
    attempts: int = 0


class Revision(MongoModel):
    id: str = Field(default_factory=new_id, alias="_id")
    document_id: str
    revision_no: int
    parent_revision_id: str | None = None
    change_note: str | None = None
    status: RevisionStatus = "PENDING"
    version_no: int | None = None  # 1-based on-chain versionNo (ADR-016); set when anchored
    submitted_by: str
    submitted_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    reviewed_by: str | None = None
    reviewed_at: dt.datetime | None = None
    review_comment: str | None = None
    file: FileInfo
    file_hash: str
    text_root: str
    canon_version: int
    page_count: int
    chunk_count: int
    anchor: Anchor = Field(default_factory=Anchor)
