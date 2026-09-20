"""provenance_events collection (03_DATA_MODEL; hashing format in ADR-019)."""

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from app.models.base import MongoModel, new_id

EventType = Literal[
    "DOCUMENT_CREATED",
    "REVISION_SUBMITTED",
    "REVISION_APPROVED",
    "REVISION_REJECTED",
    "VERSION_ANCHORED",
    "ANCHOR_FAILED",
    "VERSION_REVOKED",
    "VERIFIED",
]


class ProvenanceEvent(MongoModel):
    id: str = Field(default_factory=new_id, alias="_id")
    document_id: str
    revision_id: str | None = None
    type: EventType
    actor_id: str | None = None
    at: dt.datetime
    data: dict[str, Any] = Field(default_factory=dict)
    prev_event_hash: str | None = None
    event_hash: str
