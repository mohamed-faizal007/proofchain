import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import ensure_indexes
from app.errors import ConflictError
from app.repositories.documents import DocumentRepository
from app.repositories.users import UserRepository
from tests.unit.repositories.factories import make_document, make_user, now_ms


@pytest.fixture
async def users(mongo_db: AsyncIOMotorDatabase) -> UserRepository:
    await ensure_indexes(mongo_db)
    return UserRepository(mongo_db)


@pytest.fixture
async def docs(mongo_db: AsyncIOMotorDatabase) -> DocumentRepository:
    await ensure_indexes(mongo_db)
    return DocumentRepository(mongo_db)


async def test_user_round_trip_and_get_by_email(users: UserRepository) -> None:
    u = await users.insert(make_user("a@b.com", roles=["ISSUER", "VERIFIER"]))
    got = await users.get_by_email("a@b.com")
    assert got == u
    assert got.created_at.tzinfo is not None
    assert await users.get_by_email("zzz@b.com") is None


async def test_duplicate_email_conflicts(users: UserRepository) -> None:
    await users.insert(make_user("a@b.com"))
    with pytest.raises(ConflictError):
        await users.insert(make_user("a@b.com"))


async def test_document_round_trip_and_chain_doc_id_lookup(docs: DocumentRepository) -> None:
    d = await docs.insert(make_document("aa"))
    assert await docs.get(d.id) == d
    assert (await docs.get_by_chain_doc_id("aa")) == d
    assert await docs.get_by_chain_doc_id("zz") is None


async def test_duplicate_chain_doc_id_conflicts(docs: DocumentRepository) -> None:
    await docs.insert(make_document("aa"))
    with pytest.raises(ConflictError):
        await docs.insert(make_document("aa"))


async def test_list_by_owner(docs: DocumentRepository) -> None:
    await docs.insert(make_document("a1", owner_id="u1"))
    await docs.insert(make_document("a2", owner_id="u1"))
    await docs.insert(make_document("a3", owner_id="u2"))
    assert {d.chain_doc_id for d in await docs.list_by_owner("u1")} == {"a1", "a2"}
    assert await docs.list_by_owner("nobody") == []


async def test_set_latest_approved_moves_pointer_and_touches_updated_at(
    docs: DocumentRepository,
) -> None:
    d = await docs.insert(make_document("aa"))
    at = now_ms()
    assert await docs.set_latest_approved(d.id, "rev-2", at) is True
    got = await docs.get(d.id)
    assert got is not None
    assert (got.latest_approved_revision_id, got.updated_at) == ("rev-2", at)
    assert got.latest_approved_version_no is None  # set at anchor time (P5-04)
    assert await docs.set_latest_approved("missing", "rev-2", at) is False
