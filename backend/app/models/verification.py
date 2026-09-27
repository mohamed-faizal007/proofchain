"""verifications collection (03_DATA_MODEL). Nested result blobs stay loosely typed."""

import datetime as dt
from typing import Any

from pydantic import Field

from app.models.base import MongoModel, new_id


class Verification(MongoModel):
    id: str = Field(default_factory=new_id, alias="_id")
    requested_by: str | None = None
    at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    document_id: str | None = None
    candidate: dict[str, Any]
    document_title: str | None = None
    verdict: str
    summary: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    matched_revision_id: str | None = None
    reference_revision_id: str | None = None
    # Snapshots taken at verification time, so a later revoke never rewrites a past report.
    matched_revision: dict[str, Any] | None = None
    reference_revision: dict[str, Any] | None = None
    no_reference_reason: str | None = None
    chain_check: dict[str, Any] | None = None
    localization: dict[str, Any] | None = None
    analysis: list[dict[str, Any]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
