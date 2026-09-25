"""DocumentRepository.bump_revision_count is one atomic server-side $inc (P5-02)."""

import asyncio
import datetime as dt

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.document import Document
from app.repositories.documents import DocumentRepository


@pytest.fixture
async def repo(mongo_db: AsyncIOMotorDatabase) -> DocumentRepository:
    return DocumentRepository(mongo_db)


async def make(repo: DocumentRepository, count: int = 1) -> Document:
    return await repo.insert(
        Document(title="t", owner_id="o", chain_doc_id="c" * 64, revision_count=count)
    )


async def test_concurrent_bumps_are_not_lost(repo: DocumentRepository) -> None:
    doc = await make(repo)
    now = dt.datetime.now(dt.UTC)
    results = await asyncio.gather(*(repo.bump_revision_count(doc.id, now) for _ in range(50)))
    assert all(results)
    stored = await repo.get(doc.id)
    assert stored is not None and stored.revision_count == 51


async def test_bump_sets_updated_at_and_negative_delta_undoes(repo: DocumentRepository) -> None:
    doc = await make(repo)
    later = doc.updated_at + dt.timedelta(minutes=5)
    assert await repo.bump_revision_count(doc.id, later)
    assert await repo.bump_revision_count(doc.id, later, -1)
    stored = await repo.get(doc.id)
    assert stored is not None and stored.revision_count == 1
    assert stored.updated_at.replace(microsecond=0) == later.replace(microsecond=0)


async def test_bump_on_missing_document_is_false(repo: DocumentRepository) -> None:
    assert not await repo.bump_revision_count("missing", dt.datetime.now(dt.UTC))


async def test_bump_only_touches_its_own_document(repo: DocumentRepository) -> None:
    a, b = await make(repo), await make(repo, 7)
    await repo.bump_revision_count(a.id, dt.datetime.now(dt.UTC))
    other = await repo.get(b.id)
    assert other is not None and other.revision_count == 7
