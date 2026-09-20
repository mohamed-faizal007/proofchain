import datetime as dt

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.db import ensure_indexes
from app.errors import ConflictError
from app.models.provenance_event import ProvenanceEvent
from app.models.verification import Verification
from app.repositories.event_hash import compute_event_hash
from app.repositories.events import EventRepository
from app.repositories.verifications import VerificationRepository
from tests.unit.repositories.factories import now_ms


@pytest.fixture
async def events(mongo_db: AsyncIOMotorDatabase) -> EventRepository:
    await ensure_indexes(mongo_db)
    return EventRepository(mongo_db)


async def _three(events: EventRepository, doc: str = "d1") -> list[ProvenanceEvent]:
    a = await events.append(doc, "DOCUMENT_CREATED", actor_id="u1")
    b = await events.append(doc, "REVISION_SUBMITTED", actor_id="u1", revision_id="r1")
    c = await events.append(
        doc, "REVISION_APPROVED", actor_id="u2", revision_id="r1", data={"comment": "ok"}
    )
    return [a, b, c]


async def test_first_event_is_genesis_and_events_link(events: EventRepository) -> None:
    a, b, c = await _three(events)
    assert a.prev_event_hash is None
    assert b.prev_event_hash == a.event_hash
    assert c.prev_event_hash == b.event_hash


async def test_event_hash_matches_recomputation_after_round_trip(events: EventRepository) -> None:
    await _three(events)
    stored = await events.list_by_document("d1")
    assert len(stored) == 3
    for ev in stored:
        assert ev.at.tzinfo is not None
        assert ev.at.microsecond % 1000 == 0  # ms precision (ADR-019)
        assert compute_event_hash(ev) == ev.event_hash


async def test_list_by_document_is_in_chain_order_even_with_equal_timestamps(
    events: EventRepository,
) -> None:
    same = now_ms()
    made = [await events.append("d1", "VERIFIED", now=same) for _ in range(4)]
    assert [e.id for e in await events.list_by_document("d1")] == [e.id for e in made]


async def test_chains_are_per_document(events: EventRepository) -> None:
    await _three(events, "d1")
    other = await events.append("d2", "DOCUMENT_CREATED")
    assert other.prev_event_hash is None
    assert (await events.verify_chain("d1")).ok
    assert (await events.verify_chain("d2")).ok


async def test_verify_chain_ok_and_empty(events: EventRepository) -> None:
    await _three(events)
    res = await events.verify_chain("d1")
    assert (res.ok, res.checked, res.first_bad_index) == (True, 3, None)
    empty = await events.verify_chain("none")
    assert (empty.ok, empty.checked) == (True, 0)


async def test_verify_chain_detects_mutated_event(
    events: EventRepository, mongo_db: AsyncIOMotorDatabase
) -> None:
    _, b, _ = await _three(events)
    await mongo_db.provenance_events.update_one({"_id": b.id}, {"$set": {"actor_id": "evil"}})
    res = await events.verify_chain("d1")
    assert res.ok is False
    assert res.first_bad_index == 1
    assert res.bad_event_id == b.id


async def test_verify_chain_detects_removed_middle_event(
    events: EventRepository, mongo_db: AsyncIOMotorDatabase
) -> None:
    _, b, c = await _three(events)
    await mongo_db.provenance_events.delete_one({"_id": b.id})
    res = await events.verify_chain("d1")
    assert res.ok is False
    assert res.first_bad_index == 1
    assert res.bad_event_id == c.id


async def test_verify_chain_detects_rewritten_link(
    events: EventRepository, mongo_db: AsyncIOMotorDatabase
) -> None:
    _, _, c = await _three(events)
    await mongo_db.provenance_events.update_one(
        {"_id": c.id}, {"$set": {"prev_event_hash": "0" * 64}}
    )
    assert (await events.verify_chain("d1")).ok is False


@pytest.mark.parametrize("victim", [0, 1, 2])
async def test_verify_chain_detects_overwritten_event_hash(
    events: EventRepository, mongo_db: AsyncIOMotorDatabase, victim: int
) -> None:
    # (b) the stored event_hash itself is edited: it no longer matches its own content
    # (and, for non-tail events, no longer matches the next event's prev_event_hash).
    made = await _three(events)
    await mongo_db.provenance_events.update_one(
        {"_id": made[victim].id}, {"$set": {"event_hash": "0" * 64}}
    )
    res = await events.verify_chain("d1")
    assert res.ok is False
    assert res.first_bad_index == victim
    assert res.bad_event_id == made[victim].id


async def test_verify_chain_detects_consistent_rewrite_via_next_prev_link(
    events: EventRepository, mongo_db: AsyncIOMotorDatabase
) -> None:
    # Attacker edits event b AND recomputes its event_hash so b is self-consistent; only the
    # successor's prev_event_hash (still the old hash) exposes the rewrite.
    _, b, c = await _three(events)
    forged = b.model_copy(update={"actor_id": "evil"})
    forged.event_hash = compute_event_hash(forged)
    assert forged.event_hash != b.event_hash
    await mongo_db.provenance_events.replace_one({"_id": b.id}, forged.model_dump(by_alias=True))
    res = await events.verify_chain("d1")
    assert res.ok is False
    assert res.first_bad_index == 2  # a, forged b verify; c is unreachable from the new tip
    assert res.bad_event_id == c.id


async def test_truncated_tail_is_not_detectable_known_limit(
    events: EventRepository, mongo_db: AsyncIOMotorDatabase
) -> None:
    # ADR-019 "Limits": deleting the newest event leaves a valid shorter chain.
    _, _, c = await _three(events)
    await mongo_db.provenance_events.delete_one({"_id": c.id})
    assert (await events.verify_chain("d1")).ok is True


async def test_fork_is_rejected_by_unique_index(
    events: EventRepository, mongo_db: AsyncIOMotorDatabase
) -> None:
    a = await events.append("d1", "DOCUMENT_CREATED")
    fork = a.model_copy(update={"id": "other", "event_hash": "1" * 64})
    fork.prev_event_hash = None  # second genesis
    with pytest.raises(DuplicateKeyError):
        await mongo_db.provenance_events.insert_one(fork.model_dump(by_alias=True))


async def test_append_retries_once_on_lost_race(
    events: EventRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    await events.append("d1", "DOCUMENT_CREATED")
    real_tip = events._tip
    calls = {"n": 0}

    async def stale_first(document_id: str) -> ProvenanceEvent | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # simulate reading the tip before a concurrent append landed
        return await real_tip(document_id)

    monkeypatch.setattr(events, "_tip", stale_first)
    ev = await events.append("d1", "REVISION_SUBMITTED")
    assert calls["n"] == 2
    assert ev.prev_event_hash is not None
    assert (await events.verify_chain("d1")).ok


async def test_append_raises_conflict_after_second_lost_race(
    events: EventRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    await events.append("d1", "DOCUMENT_CREATED")

    async def always_stale(document_id: str) -> ProvenanceEvent | None:
        return None

    monkeypatch.setattr(events, "_tip", always_stale)
    with pytest.raises(ConflictError):
        await events.append("d1", "REVISION_SUBMITTED")


async def test_append_rejects_non_json_native_data(events: EventRepository) -> None:
    with pytest.raises(ValueError):
        await events.append("d1", "VERIFIED", data={"score": 0.5})
    assert await events.list_by_document("d1") == []


async def test_event_repository_is_append_only() -> None:
    for name in ("update_one", "delete", "insert", "find_many"):
        assert not hasattr(EventRepository, name), name


async def test_append_truncates_supplied_time_to_ms(events: EventRepository) -> None:
    ev = await events.append(
        "d1", "VERIFIED", now=dt.datetime(2026, 9, 20, 1, 2, 3, 456789, tzinfo=dt.UTC)
    )
    assert ev.at.microsecond == 456000


async def test_verifications_round_trip_and_ordering(mongo_db: AsyncIOMotorDatabase) -> None:
    await ensure_indexes(mongo_db)
    repo = VerificationRepository(mongo_db)
    base = now_ms()
    for i in range(3):
        await repo.insert(
            Verification(
                requested_by="u1",
                at=base + dt.timedelta(seconds=i),
                document_id="d1",
                candidate={"filename": f"{i}.pdf", "file_hash": "a" * 64},
                verdict="IDENTICAL",
                timings_ms={"total": 1.5},
            )
        )
    await repo.insert(Verification(candidate={}, verdict="UNKNOWN", document_id="d2", at=base))
    got = await repo.list_by_document("d1")
    assert [v.candidate["filename"] for v in got] == ["2.pdf", "1.pdf", "0.pdf"]  # newest first
    assert got[0].at.tzinfo is not None
    assert len(await repo.list_by_requester("u1", limit=2)) == 2
    assert await repo.list_by_document("none") == []
