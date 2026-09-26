"""RevisionRepository write guards and anchoring transitions; pointer helpers (P5-04)."""

import datetime as dt

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.revision import Anchor
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from tests.unit.repositories.factories import make_document, make_revision, now_ms

STALE = dt.timedelta(minutes=10)


@pytest.fixture
def revs(mongo_db: AsyncIOMotorDatabase) -> RevisionRepository:
    return RevisionRepository(mongo_db)


@pytest.fixture
def docs(mongo_db: AsyncIOMotorDatabase) -> DocumentRepository:
    return DocumentRepository(mongo_db)


# --- write guards (P2-review repo bypass) ---


async def test_update_one_is_disabled(revs: RevisionRepository) -> None:
    r = await revs.insert(make_revision())
    with pytest.raises(NotImplementedError):
        await revs.update_one(r.id, {"$set": {"status": "APPROVED"}})
    assert (await revs.get(r.id)).status == "PENDING"  # type: ignore[union-attr]


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED", "REVOKED"])
async def test_delete_of_reviewed_revision_is_a_no_op(
    revs: RevisionRepository, status: str
) -> None:
    r = await revs.insert(make_revision(status=status))
    assert await revs.delete(r.id) is False
    assert await revs.get(r.id) is not None


async def test_delete_of_pending_revision_works(revs: RevisionRepository) -> None:
    r = await revs.insert(make_revision())
    assert await revs.delete(r.id) is True
    assert await revs.get(r.id) is None
    assert await revs.delete(r.id) is False


# --- claim / finish ---


async def _approved(revs: RevisionRepository, n: int = 1, **anchor: object) -> str:
    fields: dict[str, object] = {"status": "ANCHORING", **anchor}
    r = await revs.insert(make_revision(revision_no=n, status="APPROVED", anchor=Anchor(**fields)))  # type: ignore[arg-type]
    return r.id


async def test_claim_queued_sets_attempted_at_and_bumps_attempts(revs: RevisionRepository) -> None:
    rid = await _approved(revs)
    at = now_ms()
    assert await revs.claim_anchor(rid, at, at - STALE) is True
    got = (await revs.get(rid)).anchor  # type: ignore[union-attr]
    assert (got.status, got.attempted_at, got.attempts) == ("ANCHORING", at, 1)
    assert await revs.claim_anchor(rid, at, at - STALE) is False  # in flight now


async def test_claim_takes_failed_and_stale_but_not_live(revs: RevisionRepository) -> None:
    at = now_ms()
    failed = await _approved(revs, 1, status="FAILED", error="X", attempted_at=at)
    stale = await _approved(revs, 2, attempted_at=at - STALE - dt.timedelta(seconds=1))
    live = await _approved(revs, 3, attempted_at=at - dt.timedelta(seconds=30))
    assert await revs.claim_anchor(failed, at, at - STALE) is True
    assert (await revs.get(failed)).anchor.error is None  # type: ignore[union-attr]
    assert await revs.claim_anchor(stale, at, at - STALE) is True
    assert await revs.claim_anchor(live, at, at - STALE) is False


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "REVOKED"])
async def test_no_anchor_write_touches_a_non_approved_revision(
    revs: RevisionRepository, status: str
) -> None:
    at = now_ms()
    r = await revs.insert(
        make_revision(status=status, anchor=Anchor(status="FAILED", attempted_at=at))  # type: ignore[arg-type]
    )
    assert await revs.claim_anchor(r.id, at, at - STALE) is False
    assert await revs.requeue_anchor(r.id) is False
    assert await revs.mark_anchored(r.id, at, Anchor(status="ANCHORED"), 1) is False
    assert await revs.mark_anchor_failed(r.id, at, "X") is False
    got = await revs.get(r.id)
    assert got.anchor == Anchor(status="FAILED", attempted_at=at)  # type: ignore[union-attr]
    assert got.version_no is None  # type: ignore[union-attr]


async def test_finish_only_matches_our_own_claim(revs: RevisionRepository) -> None:
    rid = await _approved(revs)
    ours = now_ms()
    await revs.claim_anchor(rid, ours, ours - STALE)
    other = ours - dt.timedelta(seconds=1)
    assert await revs.mark_anchored(rid, other, Anchor(status="ANCHORED"), 1) is False
    assert await revs.mark_anchor_failed(rid, other, "X") is False
    done = Anchor(status="ANCHORED", tx_hash="0xab", attempts=1, attempted_at=ours)
    assert await revs.mark_anchored(rid, ours, done, 4) is True
    got = await revs.get(rid)
    assert (got.anchor, got.version_no) == (done, 4)  # type: ignore[union-attr]


async def test_mark_failed_and_requeue(revs: RevisionRepository) -> None:
    rid = await _approved(revs)
    at = now_ms()
    await revs.claim_anchor(rid, at, at - STALE)
    assert await revs.mark_anchor_failed(rid, at, "CHAIN_UNAVAILABLE") is True
    got = (await revs.get(rid)).anchor  # type: ignore[union-attr]
    assert (got.status, got.error) == ("FAILED", "CHAIN_UNAVAILABLE")
    assert await revs.requeue_anchor(rid) is True
    got = (await revs.get(rid)).anchor  # type: ignore[union-attr]
    assert (got.status, got.attempted_at) == ("ANCHORING", None)
    assert await revs.requeue_anchor(rid) is False  # only FAILED


# --- ordering and reconciler queries ---


async def test_predecessor_and_successor_queries(revs: RevisionRepository) -> None:
    await revs.insert(
        make_revision(revision_no=1, status="APPROVED", anchor=Anchor(status="ANCHORED"))
    )
    await revs.insert(make_revision(revision_no=2, status="REJECTED"))
    v3 = await _approved(revs, 3, status="FAILED")
    await _approved(revs, 4, attempted_at=now_ms())  # claimed, not queued
    v5 = await _approved(revs, 5)
    await revs.insert(make_revision(document_id="other", revision_no=1, status="APPROVED"))

    assert await revs.find_unanchored_predecessor("d1", 1) is None
    assert await revs.find_unanchored_predecessor("d1", 3) is None
    assert (await revs.find_unanchored_predecessor("d1", 5)).id == v3  # type: ignore[union-attr]
    assert (await revs.next_queued_successor("d1", 1)).id == v5  # type: ignore[union-attr]
    assert await revs.next_queued_successor("d1", 5) is None


async def test_anchor_candidates(revs: RevisionRepository) -> None:
    at = now_ms()
    a = await _approved(revs, 1, status="FAILED")
    b = await _approved(revs, 2)
    c = await _approved(revs, 3, attempted_at=at - STALE - dt.timedelta(seconds=1))
    await _approved(revs, 4, attempted_at=at)
    await revs.insert(
        make_revision(revision_no=5, status="APPROVED", anchor=Anchor(status="ANCHORED"))
    )
    ids = [r.id for r in await revs.find_anchor_candidates(at - STALE)]
    assert ids == [a, b, c]


async def test_revision_ids_with_event(mongo_db: AsyncIOMotorDatabase) -> None:
    events = EventRepository(mongo_db)
    await events.append("d1", "DOCUMENT_CREATED")
    await events.append("d1", "REVISION_APPROVED", revision_id="r1")
    await events.append("d1", "REVISION_REJECTED", revision_id="r2")
    assert await events.revision_ids_with_event("REVISION_APPROVED") == {"r1"}
    assert await events.revision_ids_with_event("VERSION_ANCHORED") == set()


# --- document pointer (adjustment 8) ---


async def test_set_latest_approved_resets_version_no(docs: DocumentRepository) -> None:
    d = await docs.insert(
        make_document(latest_approved_revision_id="r1", latest_approved_version_no=1)
    )
    await docs.set_latest_approved(d.id, "r2", now_ms())
    got = await docs.get(d.id)
    assert (got.latest_approved_revision_id, got.latest_approved_version_no) == ("r2", None)  # type: ignore[union-attr]


async def test_set_latest_version_no_only_for_the_pointed_revision(
    docs: DocumentRepository,
) -> None:
    d = await docs.insert(make_document(latest_approved_revision_id="r2"))
    assert await docs.set_latest_version_no(d.id, "r1", 1, now_ms()) is False
    assert await docs.set_latest_version_no(d.id, "r2", 2, now_ms()) is True
    assert (await docs.get(d.id)).latest_approved_version_no == 2  # type: ignore[union-attr]


async def test_repair_pointer_is_compare_and_set(docs: DocumentRepository) -> None:
    d = await docs.insert(
        make_document(latest_approved_revision_id="r1", latest_approved_version_no=1)
    )
    assert await docs.repair_pointer(d.id, ("r0", None), ("r2", 2), now_ms()) is False
    assert await docs.repair_pointer(d.id, ("r1", 1), ("r2", 2), now_ms()) is True
    got = await docs.get(d.id)
    assert (got.latest_approved_revision_id, got.latest_approved_version_no) == ("r2", 2)  # type: ignore[union-attr]
