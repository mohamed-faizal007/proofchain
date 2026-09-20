"""Provenance event chain against a real MongoDB (ADR-019): the (document_id, prev_event_hash)
unique index and the append retry-on-conflict path, which mongomock cannot vouch for.

Run with: python -m pytest -m mongo tests/integration/test_events_real_mongo.py
"""

import asyncio

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.db import ensure_indexes
from app.errors import ConflictError
from app.models.provenance_event import ProvenanceEvent
from app.repositories.event_hash import compute_event_hash
from app.repositories.events import EventRepository

pytestmark = pytest.mark.mongo


@pytest.fixture
async def events(real_db: AsyncIOMotorDatabase) -> EventRepository:
    await ensure_indexes(real_db)
    return EventRepository(real_db)


def _raw(event: ProvenanceEvent, **over: object) -> dict[str, object]:
    return {**event.model_dump(by_alias=True), **over}


async def test_index_exists_unique_on_real_mongo(real_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(real_db)
    info = (await real_db.provenance_events.index_information())["document_id_1_prev_event_hash_1"]
    assert info["key"] == [("document_id", 1), ("prev_event_hash", 1)]
    assert info["unique"] is True


async def test_second_genesis_rejected_by_real_index(
    events: EventRepository, real_db: AsyncIOMotorDatabase
) -> None:
    first = await events.append("d1", "DOCUMENT_CREATED")
    assert first.prev_event_hash is None
    # Explicit null prev on the same document collides (one genesis per document)...
    with pytest.raises(DuplicateKeyError):
        await real_db.provenance_events.insert_one(_raw(first, _id="other", event_hash="1" * 64))
    # ...and so does a missing prev_event_hash field (null and missing are the same key).
    doc = _raw(first, _id="other2")
    del doc["prev_event_hash"]
    with pytest.raises(DuplicateKeyError):
        await real_db.provenance_events.insert_one(doc)
    # A different document has its own genesis.
    other = await events.append("d2", "DOCUMENT_CREATED")
    assert other.prev_event_hash is None


async def test_second_successor_of_same_event_rejected(
    events: EventRepository, real_db: AsyncIOMotorDatabase
) -> None:
    a = await events.append("d1", "DOCUMENT_CREATED")
    b = await events.append("d1", "REVISION_SUBMITTED")
    assert b.prev_event_hash == a.event_hash
    with pytest.raises(DuplicateKeyError):
        await real_db.provenance_events.insert_one(_raw(b, _id="fork", event_hash="2" * 64))


async def test_chain_round_trips_and_verifies_on_real_mongo(events: EventRepository) -> None:
    made = [
        await events.append("d1", "DOCUMENT_CREATED", actor_id="u1"),
        await events.append("d1", "REVISION_SUBMITTED", actor_id="u1", revision_id="r1"),
        await events.append(
            "d1", "REVISION_APPROVED", actor_id="u2", revision_id="r1", data={"n": 3, "ok": True}
        ),
    ]
    stored = await events.list_by_document("d1")
    assert [e.id for e in stored] == [e.id for e in made]
    for ev in stored:
        assert ev.at.tzinfo is not None  # tz_aware client
        assert compute_event_hash(ev) == ev.event_hash  # ms truncation survives real BSON
    res = await events.verify_chain("d1")
    assert (res.ok, res.checked) == (True, 3)


async def test_append_retries_after_real_duplicate_key(
    events: EventRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    await events.append("d1", "DOCUMENT_CREATED")
    real_tip = events._tip
    calls = 0

    async def stale_first(document_id: str) -> ProvenanceEvent | None:
        nonlocal calls
        calls += 1
        return None if calls == 1 else await real_tip(document_id)  # stale read, then fresh

    monkeypatch.setattr(events, "_tip", stale_first)
    ev = await events.append("d1", "REVISION_SUBMITTED")  # 1st insert hits the real E11000
    assert calls == 2
    assert ev.prev_event_hash is not None
    assert (await events.verify_chain("d1")).ok


async def test_append_raises_conflict_when_retry_also_loses(
    events: EventRepository, real_db: AsyncIOMotorDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    await events.append("d1", "DOCUMENT_CREATED")

    async def always_stale(document_id: str) -> ProvenanceEvent | None:
        return None

    monkeypatch.setattr(events, "_tip", always_stale)
    with pytest.raises(ConflictError) as exc:
        await events.append("d1", "REVISION_SUBMITTED")
    assert exc.value.status_code == 409
    assert await real_db.provenance_events.count_documents({"document_id": "d1"}) == 1


async def test_two_concurrent_appends_both_succeed_and_chain_stays_linear(
    events: EventRepository,
) -> None:
    await events.append("d1", "DOCUMENT_CREATED")
    # With two writers the loser re-reads once and must win on the retry.
    a, b = await asyncio.gather(
        events.append("d1", "VERIFIED", actor_id="x"),
        events.append("d1", "VERIFIED", actor_id="y"),
    )
    assert a.prev_event_hash != b.prev_event_hash
    res = await events.verify_chain("d1")
    assert (res.ok, res.checked) == (True, 3)


async def test_many_concurrent_appends_never_fork(events: EventRepository) -> None:
    # Retry is once, so with many writers some may get ConflictError; the invariant is that
    # every success is in the chain exactly once and the chain never forks.
    results = await asyncio.gather(
        *(events.append("d1", "VERIFIED", data={"i": i}) for i in range(8)),
        return_exceptions=True,
    )
    wins = [r for r in results if isinstance(r, ProvenanceEvent)]
    losses = [r for r in results if not isinstance(r, ProvenanceEvent)]
    assert wins, "at least one writer must succeed"
    assert all(isinstance(r, ConflictError) for r in losses), losses
    chain = await events.list_by_document("d1")
    assert {e.id for e in chain} == {e.id for e in wins}
    res = await events.verify_chain("d1")
    assert (res.ok, res.checked) == (True, len(wins))
