"""revision_count $inc under real concurrency on MongoDB 7 (P5-02).

Run with: python -m pytest -m mongo tests/integration/test_document_counter_real_mongo.py
"""

import asyncio
import datetime as dt

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.document import Document
from app.repositories.documents import DocumentRepository

pytestmark = pytest.mark.mongo


async def test_concurrent_bumps_are_not_lost_on_real_mongo(real_db: AsyncIOMotorDatabase) -> None:
    repo = DocumentRepository(real_db)
    doc = await repo.insert(
        Document(title="t", owner_id="o", chain_doc_id="c" * 64, revision_count=1)
    )
    now = dt.datetime.now(dt.UTC)
    results = await asyncio.gather(*(repo.bump_revision_count(doc.id, now) for _ in range(100)))
    assert all(results)
    stored = await repo.get(doc.id)
    assert stored is not None and stored.revision_count == 101
