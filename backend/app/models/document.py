"""documents collection (03_DATA_MODEL)."""

import datetime as dt
from typing import Literal

from pydantic import Field

from app.models.base import MongoModel, new_id

DocType = Literal["CONTRACT", "CERTIFICATE", "INVOICE", "LEGAL", "OTHER"]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Document(MongoModel):
    id: str = Field(default_factory=new_id, alias="_id")
    title: str
    doc_type: DocType = "OTHER"
    owner_id: str
    chain_doc_id: str
    latest_approved_revision_id: str | None = None
    latest_approved_version_no: int | None = None
    revision_count: int = 0
    created_at: dt.datetime = Field(default_factory=_now)
    updated_at: dt.datetime = Field(default_factory=_now)
