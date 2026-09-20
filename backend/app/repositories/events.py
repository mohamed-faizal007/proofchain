"""provenance_events repository: append-only, hash-chained per document (ADR-019).

Deliberately does not extend BaseRepository, so no update/delete/insert is exposed.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.db import MongoDatabase
from app.errors import ConflictError
from app.models.base import new_id
from app.models.provenance_event import EventType, ProvenanceEvent
from app.repositories.event_hash import compute_event_hash


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    checked: int
    first_bad_index: int | None = None
    bad_event_id: str | None = None
    reason: str | None = None


def _walk(events: list[ProvenanceEvent]) -> tuple[list[ProvenanceEvent], list[ProvenanceEvent]]:
    """Follow prev_event_hash links from genesis. Returns (chain in order, unreachable events)."""
    by_prev: dict[str | None, ProvenanceEvent] = {}
    for ev in events:
        by_prev.setdefault(ev.prev_event_hash, ev)
    ordered: list[ProvenanceEvent] = []
    cur: str | None = None
    while cur in by_prev and len(ordered) < len(events):
        ev = by_prev[cur]
        ordered.append(ev)
        cur = ev.event_hash
    seen = {e.id for e in ordered}
    leftover = sorted((e for e in events if e.id not in seen), key=lambda e: (e.at, e.id))
    return ordered, leftover


class EventRepository:
    collection_name = "provenance_events"

    def __init__(self, db: MongoDatabase) -> None:
        self._col = db[self.collection_name]

    async def _load(self, document_id: str) -> list[ProvenanceEvent]:
        cursor = self._col.find({"document_id": document_id})
        return [ProvenanceEvent.model_validate(d) async for d in cursor]

    async def _tip(self, document_id: str) -> ProvenanceEvent | None:
        ordered, _ = _walk(await self._load(document_id))
        return ordered[-1] if ordered else None

    async def append(
        self,
        document_id: str,
        type_: EventType,
        *,
        actor_id: str | None = None,
        revision_id: str | None = None,
        data: dict[str, Any] | None = None,
        now: dt.datetime | None = None,
    ) -> ProvenanceEvent:
        at = now or dt.datetime.now(dt.UTC)
        if at.tzinfo is None:
            raise ValueError("event timestamp must be timezone-aware")
        # Truncate to ms: BSON precision, so a stored event re-hashes identically (ADR-019).
        at = at.astimezone(dt.UTC).replace(microsecond=at.microsecond // 1000 * 1000)
        for attempt in (1, 2):
            tip = await self._tip(document_id)
            event = ProvenanceEvent(
                _id=new_id(),
                document_id=document_id,
                revision_id=revision_id,
                type=type_,
                actor_id=actor_id,
                at=at,
                data=data or {},
                prev_event_hash=tip.event_hash if tip else None,
                event_hash="",
            )
            event.event_hash = compute_event_hash(event)  # ValueError before anything is stored
            try:
                await self._col.insert_one(event.model_dump(by_alias=True))
            except DuplicateKeyError:
                # Lost a race: another event was appended after we read the tip. Re-read once.
                if attempt == 2:
                    raise ConflictError(
                        "Concurrent event append", details={"document_id": document_id}
                    ) from None
                continue
            return event
        raise AssertionError("unreachable")  # pragma: no cover

    async def list_by_document(self, document_id: str) -> list[ProvenanceEvent]:
        """Events in chain order; any unreachable (broken-chain) events are appended by time."""
        ordered, leftover = _walk(await self._load(document_id))
        return ordered + leftover

    async def verify_chain(self, document_id: str) -> ChainVerification:
        events = await self._load(document_id)
        ordered, leftover = _walk(events)
        for i, ev in enumerate(ordered):
            try:
                good = compute_event_hash(ev) == ev.event_hash
            except ValueError:
                good = False
            if not good:
                return ChainVerification(False, len(events), i, ev.id, "event_hash mismatch")
        if leftover:
            return ChainVerification(
                False, len(events), len(ordered), leftover[0].id, "broken or forked chain"
            )
        return ChainVerification(True, len(events))
