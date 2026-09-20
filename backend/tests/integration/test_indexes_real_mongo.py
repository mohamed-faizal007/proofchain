"""Needs a real MongoDB (`docker compose -f infra/docker-compose.yml up -d mongo`).

Run with: python -m pytest -m mongo tests/integration/test_indexes_real_mongo.py
Uses MONGO_URI (default mongodb://localhost:27017) and a throwaway database.
"""

import hashlib
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.db import ensure_indexes

pytestmark = pytest.mark.mongo


def _chain_doc_id(document_id: str) -> str:
    # 03_DATA_MODEL.md: chain_doc_id = hex(sha256(_id)); always set at document creation.
    return hashlib.sha256(document_id.encode()).hexdigest()


def _doc(document_id: str, title: str) -> dict[str, str]:
    return {"_id": document_id, "title": title, "chain_doc_id": _chain_doc_id(document_id)}


@pytest.fixture
async def real_db() -> AsyncIterator[AsyncIOMotorDatabase]:
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client: AsyncIOMotorClient = AsyncIOMotorClient(
        uri, tz_aware=True, serverSelectionTimeoutMS=3000
    )
    name = f"proofchain_it_{uuid.uuid4().hex[:8]}"
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        client.close()
        pytest.fail(f"MongoDB not reachable at {uri}: {exc}")
    try:
        yield client[name]
    finally:
        await client.drop_database(name)
        client.close()


async def test_title_text_index_created_and_queryable(real_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(real_db)
    info = await real_db.documents.index_information()
    assert "title_text" in info
    assert ("_fts", "text") in info["title_text"]["key"]

    await real_db.documents.insert_one(_doc("d1", "Lease Agreement - Flat 4B"))
    await real_db.documents.insert_one(_doc("d2", "Invoice 2026"))
    hits = [d["_id"] async for d in real_db.documents.find({"$text": {"$search": "lease"}})]
    assert hits == ["d1"]


async def test_ensure_indexes_idempotent_and_unique_enforced(real_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(real_db)
    await ensure_indexes(real_db)
    await real_db.users.insert_one({"_id": "u1", "email": "a@b.com"})
    with pytest.raises(DuplicateKeyError):
        await real_db.users.insert_one({"_id": "u2", "email": "a@b.com"})


async def test_chain_doc_id_unique_rejects_real_duplicate(real_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(real_db)
    await real_db.documents.insert_one(_doc("d1", "First"))
    await real_db.documents.insert_one(_doc("d2", "Second"))  # distinct ids coexist
    dup = {"_id": "d3", "title": "Third", "chain_doc_id": _chain_doc_id("d1")}
    with pytest.raises(DuplicateKeyError):
        await real_db.documents.insert_one(dup)


async def test_datetime_is_aware_on_real_mongo(real_db: AsyncIOMotorDatabase) -> None:
    import datetime as dt

    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    await real_db.users.insert_one({"_id": "u1", "created_at": now})
    got = (await real_db.users.find_one({"_id": "u1"}))["created_at"]
    assert got.tzinfo is not None
    assert got == now
