import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import ensure_indexes
from app.errors import ConflictError
from app.models.integrity_tree import IntegrityTreeDoc, TreeChunk, TreePage, TreeSection
from app.models.revision import Anchor
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from tests.unit.repositories.factories import make_revision, now_ms


@pytest.fixture
async def revs(mongo_db: AsyncIOMotorDatabase) -> RevisionRepository:
    await ensure_indexes(mongo_db)
    return RevisionRepository(mongo_db)


@pytest.fixture
async def trees(mongo_db: AsyncIOMotorDatabase) -> TreeRepository:
    await ensure_indexes(mongo_db)
    return TreeRepository(mongo_db)


async def test_revision_round_trip_defaults(revs: RevisionRepository) -> None:
    r = await revs.insert(make_revision())
    got = await revs.get(r.id)
    assert got == r
    assert got.status == "PENDING"
    assert got.anchor.status == "NOT_REQUESTED"
    assert got.submitted_at.tzinfo is not None


async def test_document_revision_no_is_unique(revs: RevisionRepository) -> None:
    await revs.insert(make_revision("d1", 1))
    with pytest.raises(ConflictError):
        await revs.insert(make_revision("d1", 1))
    await revs.insert(make_revision("d2", 1))  # same number, other document


async def test_next_revision_no_is_sequential_per_document(revs: RevisionRepository) -> None:
    assert await revs.next_revision_no("d1") == 1
    await revs.insert(make_revision("d1", 1))
    await revs.insert(make_revision("d1", 2))
    await revs.insert(make_revision("d2", 1))
    assert await revs.next_revision_no("d1") == 3
    assert await revs.next_revision_no("d2") == 2


async def test_get_pending_and_list_by_document(revs: RevisionRepository) -> None:
    a = await revs.insert(make_revision("d1", 1, status="APPROVED"))
    b = await revs.insert(make_revision("d1", 2))
    assert (await revs.get_pending("d1")).id == b.id  # type: ignore[union-attr]
    assert await revs.get_pending("d2") is None
    assert [r.id for r in await revs.list_by_document("d1")] == [a.id, b.id]


async def test_find_by_hashes(revs: RevisionRepository) -> None:
    r = await revs.insert(make_revision("d1", 1, file_hash="c" * 64, text_root="d" * 64))
    assert [x.id for x in await revs.find_by_file_hash("c" * 64)] == [r.id]
    assert [x.id for x in await revs.find_by_text_root("d" * 64)] == [r.id]
    assert await revs.find_by_file_hash("e" * 64) == []


async def test_set_review_persists_and_only_applies_to_pending(revs: RevisionRepository) -> None:
    r = await revs.insert(make_revision())
    at = now_ms()
    assert await revs.set_review(r.id, "APPROVED", "u2", "ok", at) is True
    got = await revs.get(r.id)
    assert (got.status, got.reviewed_by, got.review_comment) == ("APPROVED", "u2", "ok")  # type: ignore[union-attr]
    assert got.reviewed_at == at  # type: ignore[union-attr]
    # terminal now: a second review must not overwrite it
    assert await revs.set_review(r.id, "REJECTED", "u3", "no", at) is False
    assert (await revs.get(r.id)).status == "APPROVED"  # type: ignore[union-attr]


async def test_set_review_rejects_non_review_status(revs: RevisionRepository) -> None:
    r = await revs.insert(make_revision())
    with pytest.raises(ValueError):
        await revs.set_review(r.id, "REVOKED", "u2", None, now_ms())


async def test_set_anchor_and_version_no(revs: RevisionRepository) -> None:
    r = await revs.insert(make_revision(status="APPROVED"))
    anchor = Anchor(
        status="ANCHORED",
        tx_hash="0xab",
        block_number=5,
        chain_id=31337,
        anchored_at=now_ms(),
        attempts=1,
    )
    assert await revs.set_anchor(r.id, anchor, version_no=1) is True
    got = await revs.get(r.id)
    assert got.anchor == anchor  # type: ignore[union-attr]
    assert got.version_no == 1  # type: ignore[union-attr]
    # failed retry keeps the existing version_no untouched
    failed = Anchor(status="FAILED", error="boom", attempts=2)
    await revs.set_anchor(r.id, failed)
    assert (await revs.get(r.id)).version_no == 1  # type: ignore[union-attr]


def _tree(rev_id: str, text: str = "hello") -> IntegrityTreeDoc:
    chunk = TreeChunk(
        id="p0-c0", index=0, text=text, leaf_hash="a" * 64, bbox=[0, 1, 2.5, 3], section_id="S1"
    )
    return IntegrityTreeDoc(
        id=rev_id,
        document_id="d1",
        canon_version=2,
        file_hash="f" * 64,
        text_root="a" * 64,
        page_count=1,
        pages=[TreePage(index=0, root="a" * 64, chunks=[chunk])],
        sections=[TreeSection(id="S1", title="1. Intro", chunk_ids=["p0-c0"], hash="b" * 64)],
    )


async def test_tree_round_trip_nested(trees: TreeRepository) -> None:
    t = _tree("r1")
    await trees.upsert(t)
    got = await trees.get("r1")
    assert got == t
    assert got.pages[0].chunks[0].bbox == [0, 1, 2.5, 3]
    assert got.page_levels is None


async def test_tree_upsert_replaces(trees: TreeRepository, mongo_db: AsyncIOMotorDatabase) -> None:
    await trees.upsert(_tree("r1", "one"))
    await trees.upsert(_tree("r1", "two"))
    assert await mongo_db.integrity_trees.count_documents({}) == 1
    assert (await trees.get("r1")).pages[0].chunks[0].text == "two"  # type: ignore[union-attr]
