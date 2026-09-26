"""Startup reconciler (ADR-012, P5-04): one pass that repairs what a crash between writes leaves.

1. Reviewed revisions (APPROVED / REJECTED) with no REVISION_APPROVED / REVISION_REJECTED event:
   the event is appended with the reviewer as actor and `reconciled: true` (P2 review finding).
2. ANCHORED revisions with no VERSION_ANCHORED event: appended from the stored anchor fields.
   A FAILED revision with no ANCHOR_FAILED event is deliberately NOT repaired: the retry below
   supersedes that attempt and writes its own events.
3. Anchors that are FAILED, queued, or held by a stuck claim are re-sent (safe: the chain client
   checks the chain first). The anchoring service enforces APPROVED and ordering.
4. Stale document pointers: `latest_approved_revision_id` / `latest_approved_version_no` are
   recomputed from the newest APPROVED revision (compare-and-set).

Steps 1, 2 and 4 skip anything newer than GRACE, so writes still in flight are not duplicated.
Every item is isolated: one failure is logged (class name and ids) and the pass continues.
"""

import datetime as dt
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.chain import RegistryClient
from app.config import Settings
from app.db import MongoDatabase
from app.errors import DomainError
from app.models.provenance_event import EventType
from app.models.revision import Revision
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.services.anchoring import CLAIM_STALE_AFTER, AnchorService, build_anchor_service, now_ms

logger = logging.getLogger(__name__)

GRACE = dt.timedelta(seconds=60)
_REVIEW_EVENTS: tuple[tuple[Literal["APPROVED", "REJECTED"], EventType], ...] = (
    ("APPROVED", "REVISION_APPROVED"),
    ("REJECTED", "REVISION_REJECTED"),
)


@dataclass
class ReconcileReport:
    review_events: int = 0
    anchor_events: int = 0
    anchors_attempted: int = 0
    pointers: int = 0
    errors: int = 0


class Reconciler:
    def __init__(
        self,
        documents: DocumentRepository,
        revisions: RevisionRepository,
        events: EventRepository,
        anchoring: AnchorService,
    ) -> None:
        self._documents = documents
        self._revisions = revisions
        self._events = events
        self._anchoring = anchoring

    async def run_once(self, now: dt.datetime | None = None) -> ReconcileReport:
        now = now or now_ms()
        report = ReconcileReport()
        for step in (
            self._repair_review_events,
            self._repair_anchor_events,
            self._retry_anchors,
            self._repair_pointers,
        ):
            try:
                await step(now, report)
            except Exception as exc:  # noqa: BLE001 - a failed query must not stop later steps
                report.errors += 1
                logger.error("reconcile %s failed: %s", step.__name__, type(exc).__name__)
        logger.info("reconcile pass done: %s", report)
        return report

    async def _repair_review_events(self, now: dt.datetime, report: ReconcileReport) -> None:
        for status, event_type in _REVIEW_EVENTS:
            have = await self._events.revision_ids_with_event(event_type)
            for rev in await self._revisions.find_reviewed_before(status, now - GRACE):
                if rev.id in have:
                    continue
                data = {"revision_no": rev.revision_no, "comment": rev.review_comment}
                if await self._append(rev, event_type, rev.reviewed_by, data, now, report):
                    report.review_events += 1

    async def _repair_anchor_events(self, now: dt.datetime, report: ReconcileReport) -> None:
        have = await self._events.revision_ids_with_event("VERSION_ANCHORED")
        for rev in await self._revisions.find_anchored_before(now - GRACE):
            if rev.id in have:
                continue
            data = {
                "version_no": rev.version_no,
                "tx_hash": rev.anchor.tx_hash,
                "block_number": rev.anchor.block_number,
                "chain_id": rev.anchor.chain_id,
                "contract": rev.anchor.contract,
            }
            if await self._append(rev, "VERSION_ANCHORED", None, data, now, report):
                report.anchor_events += 1

    async def _retry_anchors(self, now: dt.datetime, report: ReconcileReport) -> None:
        for rev in await self._revisions.find_anchor_candidates(now - CLAIM_STALE_AFTER):
            report.anchors_attempted += 1
            try:
                await self._anchoring.anchor(rev.id, "reconcile")
            except Exception as exc:  # noqa: BLE001
                report.errors += 1
                code = exc.code if isinstance(exc, DomainError) else type(exc).__name__
                logger.error("reconcile anchor skipped (%s): revision_id=%s", code, rev.id)

    async def _repair_pointers(self, now: dt.datetime, report: ReconcileReport) -> None:
        for doc in await self._documents.find_many({}):
            try:
                latest = await self._revisions.get_latest_approved(doc.id)
                if latest is not None and (latest.reviewed_at or now) >= now - GRACE:
                    continue  # approval may still be in flight (it sets the pointer itself)
                want = (latest.id, latest.version_no) if latest else (None, None)
                seen = (doc.latest_approved_revision_id, doc.latest_approved_version_no)
                if want != seen and await self._documents.repair_pointer(doc.id, seen, want, now):
                    report.pointers += 1
                    logger.warning("reconcile: repaired stale pointer: document_id=%s", doc.id)
            except Exception as exc:  # noqa: BLE001
                report.errors += 1
                logger.error(
                    "reconcile pointer failed (%s): document_id=%s", type(exc).__name__, doc.id
                )

    async def _append(
        self,
        rev: Revision,
        event_type: EventType,
        actor_id: str | None,
        data: Mapping[str, object],
        now: dt.datetime,
        report: ReconcileReport,
    ) -> bool:
        try:
            await self._events.append(
                rev.document_id,
                event_type,
                actor_id=actor_id,
                revision_id=rev.id,
                data={**data, "reconciled": True},
                now=now,
            )
        except Exception as exc:  # noqa: BLE001
            report.errors += 1
            logger.error(
                "reconcile %s append failed (%s): revision_id=%s",
                event_type,
                type(exc).__name__,
                rev.id,
            )
            return False
        logger.warning("reconcile: appended missing %s: revision_id=%s", event_type, rev.id)
        return True


def build_reconciler(
    db: MongoDatabase, client: RegistryClient | None, settings: Settings
) -> Reconciler:
    return Reconciler(
        DocumentRepository(db),
        RevisionRepository(db),
        EventRepository(db),
        build_anchor_service(db, client, settings),
    )


async def run_startup_reconcile(
    db: MongoDatabase, client: RegistryClient | None, settings: Settings
) -> None:
    """Background task started by the app lifespan; never raises."""
    try:
        await build_reconciler(db, client, settings).run_once()
    except Exception as exc:  # noqa: BLE001
        logger.error("startup reconcile failed: %s", type(exc).__name__)
