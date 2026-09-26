"""Motor client factory and index creation (indexes per docs/03_DATA_MODEL.md)."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.config import Settings

ASCENDING = 1

MongoClient = AsyncIOMotorClient[dict[str, Any]]
MongoDatabase = AsyncIOMotorDatabase[dict[str, Any]]
MongoCollection = AsyncIOMotorCollection[dict[str, Any]]


def create_client(settings: Settings) -> MongoClient:
    # tz_aware=True: BSON datetimes come back as aware UTC (the default is naive UTC).
    return AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)


def get_database(client: MongoClient, settings: Settings) -> MongoDatabase:
    return client[settings.mongo_db]


async def ensure_indexes(db: MongoDatabase) -> None:
    """Create all indexes. Idempotent; safe to call on every startup."""
    await db.users.create_index([("email", ASCENDING)], unique=True)

    await db.documents.create_index([("owner_id", ASCENDING)])
    await db.documents.create_index([("chain_doc_id", ASCENDING)], unique=True)
    await db.documents.create_index([("title", "text")])

    await db.revisions.create_index(
        [("document_id", ASCENDING), ("revision_no", ASCENDING)], unique=True
    )
    # 03: one PENDING revision per document, enforced atomically (P5 review H1: the service's
    # pending check can be raced across the tree build).
    await db.revisions.create_index(
        [("document_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": "PENDING"},
        name="one_pending_per_document",
    )
    await db.revisions.create_index([("file_hash", ASCENDING)])
    await db.revisions.create_index([("text_root", ASCENDING)])
    await db.revisions.create_index([("document_id", ASCENDING), ("status", ASCENDING)])
    await db.revisions.create_index([("anchor.status", ASCENDING)])

    await db.provenance_events.create_index([("document_id", ASCENDING), ("at", ASCENDING)])
    # One genesis event per document, at most one successor per event: no chain forks (ADR-019).
    await db.provenance_events.create_index(
        [("document_id", ASCENDING), ("prev_event_hash", ASCENDING)], unique=True
    )

    await db.verifications.create_index([("document_id", ASCENDING), ("at", ASCENDING)])
    await db.verifications.create_index([("requested_by", ASCENDING)])
