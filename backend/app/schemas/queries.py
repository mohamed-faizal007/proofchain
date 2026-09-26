"""Response DTOs for the read-only document/revision routes (04_API_SPEC Documents & revisions)."""

import datetime as dt
from typing import Any

from pydantic import BaseModel

from app.models.integrity_tree import IntegrityTreeDoc, TreePage, TreeSection
from app.models.provenance_event import EventType, ProvenanceEvent
from app.schemas.documents import DocumentOut, RevisionOut
from app.services.queries import DocumentPage, Provenance, RevisionDiff


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    page: int
    page_size: int
    total: int

    @classmethod
    def from_page(cls, p: DocumentPage) -> "DocumentListOut":
        items = [DocumentOut.from_document(d) for d in p.items]
        return cls(items=items, page=p.page, page_size=p.page_size, total=p.total)


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    latest_approved_revision: RevisionOut | None


class TreeOut(BaseModel):
    revision_id: str
    document_id: str
    canon_version: int
    file_hash: str
    text_root: str
    page_count: int
    pages: list[TreePage]
    sections: list[TreeSection]

    @classmethod
    def from_tree(cls, t: IntegrityTreeDoc) -> "TreeOut":
        return cls(revision_id=t.id, **t.model_dump(exclude={"id", "page_levels"}))


class FileUrlOut(BaseModel):
    url: str
    expires_in: int


class EventOut(BaseModel):
    id: str
    document_id: str
    revision_id: str | None
    type: EventType
    actor_id: str | None
    at: dt.datetime
    data: dict[str, Any]
    prev_event_hash: str | None
    event_hash: str

    @classmethod
    def from_event(cls, e: ProvenanceEvent) -> "EventOut":
        return cls(**e.model_dump())


class ProvenanceOut(BaseModel):
    document_id: str
    chain_valid: bool
    events: list[EventOut]

    @classmethod
    def from_provenance(cls, p: Provenance) -> "ProvenanceOut":
        events = [EventOut.from_event(e) for e in p.events]
        return cls(document_id=p.document_id, chain_valid=p.chain_valid, events=events)


class RevisionDiffOut(BaseModel):
    """`localization` is a LocalizationResult (02 §9). `analysis` stays null until NLP (P7)."""

    revision_id: str
    against_revision_id: str
    localization: dict[str, Any]
    analysis: list[dict[str, Any]] | None = None

    @classmethod
    def from_diff(cls, d: RevisionDiff) -> "RevisionDiffOut":
        return cls(
            revision_id=d.revision_id,
            against_revision_id=d.against_revision_id,
            localization=d.localization.to_dict(),
        )
