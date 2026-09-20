"""Small builders for model instances used across repository tests."""

import datetime as dt

from app.models.document import Document
from app.models.revision import FileInfo, Revision
from app.models.user import User


def now_ms() -> dt.datetime:
    # BSON keeps milliseconds, so zero microseconds for equality checks.
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def make_user(email: str = "a@b.com", **kw: object) -> User:
    fields: dict[str, object] = {
        "email": email,
        "full_name": "A B",
        "password_hash": "x",
        "roles": ["ISSUER"],
        "created_at": now_ms(),
    }
    fields.update(kw)
    return User.model_validate(fields)


def make_document(chain_doc_id: str = "aa", owner_id: str = "u1", **kw: object) -> Document:
    fields: dict[str, object] = {
        "title": "Lease",
        "owner_id": owner_id,
        "chain_doc_id": chain_doc_id,
        "created_at": now_ms(),
        "updated_at": now_ms(),
    }
    fields.update(kw)
    return Document.model_validate(fields)


def make_revision(document_id: str = "d1", revision_no: int = 1, **kw: object) -> Revision:
    fields: dict[str, object] = {
        "document_id": document_id,
        "revision_no": revision_no,
        "submitted_by": "u1",
        "submitted_at": now_ms(),
        "file": FileInfo(s3_key="k", size_bytes=1, original_filename="a.pdf"),
        "file_hash": "a" * 64,
        "text_root": "b" * 64,
        "canon_version": 2,
        "page_count": 1,
        "chunk_count": 1,
    }
    fields.update(kw)
    return Revision.model_validate(fields)
