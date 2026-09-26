import datetime as dt

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.config import Settings
from app.db import create_client, ensure_indexes

EXPECTED: dict[str, set[str]] = {
    "users": {"email_1"},
    "documents": {"owner_id_1", "chain_doc_id_1", "title_text"},
    "revisions": {
        "document_id_1_revision_no_1",
        "one_pending_per_document",
        "file_hash_1",
        "text_root_1",
        "document_id_1_status_1",
        "anchor.status_1",
    },
    "provenance_events": {"document_id_1_at_1", "document_id_1_prev_event_hash_1"},
    "verifications": {"document_id_1_at_1", "requested_by_1"},
}


async def _index_names(db: AsyncIOMotorDatabase, coll: str) -> set[str]:
    info = await db[coll].index_information()
    return set(info) - {"_id_"}


async def test_ensure_indexes_creates_expected_set(mongo_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(mongo_db)
    for coll, names in EXPECTED.items():
        assert await _index_names(mongo_db, coll) == names, coll


async def test_ensure_indexes_is_idempotent(mongo_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(mongo_db)
    await ensure_indexes(mongo_db)
    for coll, names in EXPECTED.items():
        assert await _index_names(mongo_db, coll) == names, coll


async def test_unique_email_rejects_duplicate(mongo_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(mongo_db)
    await mongo_db.users.insert_one({"_id": "u1", "email": "a@b.com"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.users.insert_one({"_id": "u2", "email": "a@b.com"})


async def test_unique_chain_doc_id_rejects_duplicate(mongo_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(mongo_db)
    await mongo_db.documents.insert_one({"_id": "d1", "chain_doc_id": "aa"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.documents.insert_one({"_id": "d2", "chain_doc_id": "aa"})


async def test_unique_index_treats_missing_field_as_null(mongo_db: AsyncIOMotorDatabase) -> None:
    # Same as real MongoDB (see integration test): two documents both lacking chain_doc_id
    # collide on null. Guards fixtures/services against inserting documents without it.
    await ensure_indexes(mongo_db)
    await mongo_db.documents.insert_one({"_id": "d1", "title": "a"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.documents.insert_one({"_id": "d2", "title": "b"})


async def test_unique_index_treats_explicit_null_as_duplicate(
    mongo_db: AsyncIOMotorDatabase,
) -> None:
    await ensure_indexes(mongo_db)
    await mongo_db.users.insert_one({"_id": "u1", "email": None})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.users.insert_one({"_id": "u2", "email": None})


async def test_unique_revision_no_per_document(mongo_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(mongo_db)
    await mongo_db.revisions.insert_one({"_id": "r1", "document_id": "d", "revision_no": 1})
    await mongo_db.revisions.insert_one({"_id": "r2", "document_id": "e", "revision_no": 1})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.revisions.insert_one({"_id": "r3", "document_id": "d", "revision_no": 1})


async def test_text_query_unsupported_under_mongomock(mongo_db: AsyncIOMotorDatabase) -> None:
    # Documents a mongomock limitation: the text index is created, but $text queries are not
    # implemented. If this starts failing, mongomock gained support; drop the workaround notes.
    await ensure_indexes(mongo_db)
    await mongo_db.documents.insert_one({"_id": "d1", "title": "Lease Agreement"})
    with pytest.raises(NotImplementedError):
        await mongo_db.documents.find_one({"$text": {"$search": "lease"}})


def test_create_client_is_tz_aware() -> None:
    client = create_client(Settings(app_env="test"))
    try:
        assert client.codec_options.tz_aware is True
    finally:
        client.close()


async def test_datetime_round_trip_is_aware_utc(mongo_db: AsyncIOMotorDatabase) -> None:
    # BSON stores milliseconds, so zero microseconds before comparing equality.
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    await mongo_db.users.insert_one({"_id": "u1", "created_at": now})
    got = (await mongo_db.users.find_one({"_id": "u1"}))["created_at"]
    assert got.tzinfo is not None
    assert got.utcoffset() == dt.timedelta(0)
    assert got == now


async def test_datetime_round_trip_truncates_to_milliseconds(
    mongo_db: AsyncIOMotorDatabase,
) -> None:
    stamp = dt.datetime(2026, 9, 20, 12, 0, 0, 123456, tzinfo=dt.UTC)
    await mongo_db.users.insert_one({"_id": "u1", "created_at": stamp})
    got = (await mongo_db.users.find_one({"_id": "u1"}))["created_at"]
    assert got == stamp.replace(microsecond=123000)
