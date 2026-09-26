"""RevisionRepository revocation guard and list helpers (P5-05)."""

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.revision import Anchor, Revocation
from app.repositories.documents import DocumentRepository
from app.repositories.revisions import RevisionRepository
from tests.unit.repositories.factories import make_document, make_revision, now_ms


@pytest.fixture
def revs(mongo_db: AsyncIOMotorDatabase) -> RevisionRepository:
    return RevisionRepository(mongo_db)


def revocation() -> Revocation:
    return Revocation(by="a", at=now_ms(), reason="r", tx_hash="0x" + "1" * 64, block_number=3)


async def test_mark_revoked_moves_an_anchored_approved_revision(revs: RevisionRepository) -> None:
    rev = await revs.insert(
        make_revision(status="APPROVED", anchor=Anchor(status="ANCHORED"), version_no=1)
    )
    rv = revocation()
    assert await revs.mark_revoked(rev.id, rv) is True
    got = await revs.get(rev.id)
    assert got is not None
    assert (got.status, got.revocation, got.anchor.status) == ("REVOKED", rv, "ANCHORED")
    assert await revs.mark_revoked(rev.id, rv) is False  # REVOKED is terminal


@pytest.mark.parametrize(
    ("status", "anchor"),
    [
        ("PENDING", "NOT_REQUESTED"),
        ("REJECTED", "NOT_REQUESTED"),
        ("APPROVED", "ANCHORING"),
        ("APPROVED", "FAILED"),
    ],
)
async def test_mark_revoked_refuses_other_states(
    revs: RevisionRepository, status: str, anchor: str
) -> None:
    rev = await revs.insert(make_revision(status=status, anchor=Anchor(status=anchor)))  # type: ignore[arg-type]
    assert await revs.mark_revoked(rev.id, revocation()) is False
    got = await revs.get(rev.id)
    assert got is not None and (got.status, got.revocation) == (status, None)


async def test_document_ids_with_status(revs: RevisionRepository) -> None:
    await revs.insert(make_revision("d1", 1, status="APPROVED"))
    await revs.insert(make_revision("d1", 2, status="PENDING"))
    await revs.insert(make_revision("d2", 1, status="PENDING"))
    assert sorted(await revs.document_ids_with_status("PENDING")) == ["d1", "d2"]
    assert await revs.document_ids_with_status("APPROVED") == ["d1"]
    assert await revs.document_ids_with_status("REVOKED") == []


async def test_document_page_counts_all_matches(mongo_db: AsyncIOMotorDatabase) -> None:
    docs = DocumentRepository(mongo_db)
    for i in range(5):
        await docs.insert(make_document(chain_doc_id=f"c{i}", title=f"T{i}"))
    items, total = await docs.page({}, skip=2, limit=2)
    assert (len(items), total) == (2, 5)
    items, total = await docs.page({"title": "T1"}, skip=0, limit=10)
    assert ([d.title for d in items], total) == (["T1"], 1)
