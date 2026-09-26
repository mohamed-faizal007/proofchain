"""Shared harness for anchoring and reconciler service tests (P5-04): mongomock + fake chain."""

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from typing import Any

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.chain import AnchorReceipt, FakeRegistryClient
from app.models.document import Document
from app.models.revision import Anchor, Revision
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.services.anchoring import AnchorService, now_ms
from app.services.reconciler import Reconciler
from tests.unit.repositories.factories import make_document, make_revision

CONTRACT = "0x" + "2" * 40
SECRET = "SECRET-INTERNAL-DETAIL-hunter2"


def h(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


class ScriptedRegistryClient(FakeRegistryClient):
    """FakeRegistryClient that raises the queued exceptions first, one per anchor call."""

    def __init__(self) -> None:
        super().__init__()
        self.failures: list[BaseException] = []
        self.anchor_calls = 0

    async def anchor_version(
        self, doc_id: str, file_hash: str, text_root: str, canon_version: int
    ) -> AnchorReceipt:
        self.anchor_calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return await super().anchor_version(doc_id, file_hash, text_root, canon_version)


@dataclass
class Harness:
    db: AsyncIOMotorDatabase
    client: ScriptedRegistryClient
    documents: DocumentRepository
    revisions: RevisionRepository
    events: EventRepository
    sleeps: list[float] = field(default_factory=list)

    def service(self, *, chain: bool = True) -> AnchorService:
        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        return AnchorService(
            self.documents,
            self.revisions,
            self.events,
            self.client if chain else None,
            chain_id=31337,
            contract=CONTRACT,
            sleep=sleep,
        )

    def reconciler(self, *, chain: bool = True) -> Reconciler:
        return Reconciler(self.documents, self.revisions, self.events, self.service(chain=chain))

    async def document(self, name: str = "d") -> Document:
        return await self.documents.insert(make_document(chain_doc_id=h("doc", name)))

    async def revision(
        self,
        doc: Document,
        n: int,
        status: str = "APPROVED",
        *,
        anchor: Anchor | None = None,
        reviewed_ago: dt.timedelta = dt.timedelta(minutes=5),
        **kw: Any,
    ) -> Revision:
        reviewed = status != "PENDING"
        default_anchor = Anchor(status="ANCHORING") if status == "APPROVED" else Anchor()
        rev = make_revision(
            document_id=doc.id,
            revision_no=n,
            status=status,
            file_hash=h("file", doc.id, n),
            text_root=h("root", doc.id, n),
            reviewed_by="approver-1" if reviewed else None,
            reviewed_at=now_ms() - reviewed_ago if reviewed else None,
            review_comment="ok" if reviewed else None,
            anchor=anchor or default_anchor,
            **kw,
        )
        return await self.revisions.insert(rev)

    async def get(self, rev: Revision) -> Revision:
        got = await self.revisions.get(rev.id)
        assert got is not None
        return got

    async def event_list(self, type_: str | None = None) -> list[dict[str, Any]]:
        q = {} if type_ is None else {"type": type_}
        return [e async for e in self.db["provenance_events"].find(q)]

    async def raw_update(self, rev: Revision, fields: dict[str, Any]) -> None:
        """Test-only direct write (the repository deliberately exposes no such method)."""
        await self.db["revisions"].update_one({"_id": rev.id}, {"$set": fields})


@pytest.fixture
def hx(mongo_db: AsyncIOMotorDatabase) -> Harness:
    return Harness(
        mongo_db,
        ScriptedRegistryClient(),
        DocumentRepository(mongo_db),
        RevisionRepository(mongo_db),
        EventRepository(mongo_db),
    )
