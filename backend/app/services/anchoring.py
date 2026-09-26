"""Anchoring (01_ARCHITECTURE §3.2, ADR-012): APPROVED revision -> `anchorVersion`, with provenance.

`anchor.status` of an APPROVED revision:
- ANCHORING, `attempted_at` null: queued (just approved, re-queued by a retry, or waiting for an
  older approved revision of the same document).
- ANCHORING, `attempted_at` set: claimed by one attempt. A claim older than CLAIM_STALE_AFTER is
  stuck (crash) and the reconciler may take it over; a younger one is in flight and left alone.
- ANCHORED, or FAILED with an error CODE (never exception text).

Ordering: revision N is only sent once every older APPROVED revision of the document is ANCHORED,
so on-chain version order and `prevTextRoot` links follow revision order. Otherwise N stays
queued and is picked up when its predecessor anchors (or by the reconciler). Approval is never
blocked by this.

Retries: ChainUnavailableError (node unreachable / timed out) is retried after 1 s and 4 s, three
attempts in total. Anything else (contract or node rejection) fails at once. Re-sending is safe:
the chain client re-reads the chain first and reports an already-anchored version with
`tx_hash=None` (05, Backend client).

Write order on success: revision ANCHORED -> VERSION_ANCHORED event -> document version pointer.
The tx is final, so later failures are logged, never rolled back; the reconciler appends a
missing VERSION_ANCHORED event and repairs the pointer. Assumes a single worker (PROGRESS.md).
"""

import asyncio
import datetime as dt
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

from app.chain import AnchorReceipt, RegistryClient
from app.config import Settings
from app.db import MongoDatabase
from app.errors import (
    ChainUnavailableError,
    ConflictError,
    DomainError,
    NotFoundError,
    RevisionNotApprovedError,
)
from app.models.revision import Anchor, Revision
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository

logger = logging.getLogger(__name__)

RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 4.0)  # 3 attempts in total
CLAIM_STALE_AFTER = dt.timedelta(minutes=10)  # > receipt (120 s) + confirmation waits + backoff
CHAIN_NOT_CONFIGURED = "CHAIN_NOT_CONFIGURED"
UNEXPECTED_ERROR = "UNEXPECTED_ERROR"

Outcome = Literal["ANCHORED", "FAILED", "QUEUED", "SKIPPED", "ALREADY_ANCHORED"]
Trigger = Literal["approve", "retry", "reconcile", "successor"]
Sleep = Callable[[float], Awaitable[None]]


def now_ms() -> dt.datetime:
    # BSON keeps milliseconds; claims are matched on attempted_at, so it must round-trip.
    now = dt.datetime.now(dt.UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


class AnchorService:
    def __init__(
        self,
        documents: DocumentRepository,
        revisions: RevisionRepository,
        events: EventRepository,
        client: RegistryClient | None,
        *,
        chain_id: int,
        contract: str | None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._documents = documents
        self._revisions = revisions
        self._events = events
        self._client = client
        self._chain_id = chain_id
        self._contract = contract
        self._sleep = sleep

    async def anchor(self, revision_id: str, trigger: Trigger = "approve") -> Outcome:
        """Anchor one revision, then any queued successors it was holding back.

        Raises NotFoundError / RevisionNotApprovedError for the requested revision only.
        """
        outcome, revision = await self._anchor_one(revision_id, trigger)
        result = outcome
        while outcome == "ANCHORED":
            nxt = await self._revisions.next_queued_successor(
                revision.document_id, revision.revision_no
            )
            if nxt is None:
                break
            outcome, revision = await self._anchor_one(nxt.id, "successor")
        return result

    async def request_retry(self, revision_id: str) -> tuple[Revision, bool]:
        """Admin retry: FAILED -> queued (True: caller schedules `anchor`); ANCHORED -> no-op."""
        revision = await self._get_approved(revision_id)
        if revision.anchor.status == "ANCHORED":
            return revision, False
        if revision.anchor.status != "FAILED" or not await self._revisions.requeue_anchor(
            revision_id
        ):
            raise ConflictError(
                "Anchoring is already queued or in progress",
                details={"anchor_status": revision.anchor.status},
            )
        queued = revision.anchor.model_copy(update={"status": "ANCHORING", "attempted_at": None})
        return revision.model_copy(update={"anchor": queued}), True

    async def _get_approved(self, revision_id: str) -> Revision:
        revision = await self._revisions.get(revision_id)
        if revision is None:
            raise NotFoundError("Revision not found")
        if revision.status != "APPROVED":
            raise RevisionNotApprovedError(
                "Only APPROVED revisions are anchored", details={"status": revision.status}
            )
        return revision

    async def _anchor_one(self, revision_id: str, trigger: Trigger) -> tuple[Outcome, Revision]:
        rev = await self._get_approved(revision_id)
        if rev.anchor.status == "ANCHORED":
            return "ALREADY_ANCHORED", rev
        if await self._must_wait(rev):
            return "QUEUED", rev

        claimed_at = now_ms()
        if not await self._revisions.claim_anchor(
            rev.id, claimed_at, claimed_at - CLAIM_STALE_AFTER
        ):
            return "SKIPPED", rev  # another attempt holds a live claim, or it just finished
        attempts = rev.anchor.attempts + 1
        document = await self._documents.get(rev.document_id)
        if self._client is None:
            return await self._fail(rev, claimed_at, CHAIN_NOT_CONFIGURED, attempts, trigger), rev
        if document is None:
            logger.error("anchoring: document missing: revision_id=%s", rev.id)
            return await self._fail(rev, claimed_at, UNEXPECTED_ERROR, attempts, trigger), rev
        try:
            receipt = await self._send(self._client, document.chain_doc_id, rev)
        except DomainError as exc:
            return await self._fail(rev, claimed_at, exc.code, attempts, trigger), rev
        except Exception as exc:  # noqa: BLE001 - never leave a claim open; class name only
            logger.error("anchoring: unexpected %s: revision_id=%s", type(exc).__name__, rev.id)
            return await self._fail(rev, claimed_at, UNEXPECTED_ERROR, attempts, trigger), rev
        return await self._succeed(rev, claimed_at, receipt, attempts, trigger), rev

    async def _must_wait(self, rev: Revision) -> bool:
        """True (and N left queued) while an older APPROVED revision is not ANCHORED yet."""
        blocker = await self._revisions.find_unanchored_predecessor(
            rev.document_id, rev.revision_no
        )
        if blocker is None:
            return False
        if rev.anchor.status == "FAILED":
            await self._revisions.requeue_anchor(rev.id)
            # The predecessor may have anchored (and looked for queued successors) meanwhile.
            if (
                await self._revisions.find_unanchored_predecessor(rev.document_id, rev.revision_no)
                is None
            ):
                return False
        logger.info(
            "anchoring queued behind an older approved revision: revision_id=%s waiting_for=%s",
            rev.id,
            blocker.id,
        )
        return True

    async def _send(
        self, client: RegistryClient, chain_doc_id: str, rev: Revision
    ) -> AnchorReceipt:
        delays: tuple[float | None, ...] = (*RETRY_BACKOFF_SECONDS, None)
        for delay in delays:
            try:
                return await client.anchor_version(
                    chain_doc_id, rev.file_hash, rev.text_root, rev.canon_version
                )
            except ChainUnavailableError:
                if delay is None:
                    raise
                logger.warning(
                    "anchoring: chain unavailable, retry in %ss: revision_id=%s", delay, rev.id
                )
                await self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _succeed(
        self,
        rev: Revision,
        claimed_at: dt.datetime,
        receipt: AnchorReceipt,
        attempts: int,
        trigger: Trigger,
    ) -> Outcome:
        at = now_ms()
        anchor = Anchor(
            status="ANCHORED",
            tx_hash=receipt.tx_hash,  # None when recovered as already anchored (no tx sent)
            block_number=receipt.block_number,
            chain_id=self._chain_id,
            contract=self._contract,
            anchored_at=at,
            attempts=attempts,
            attempted_at=claimed_at,
        )
        if not await self._revisions.mark_anchored(rev.id, claimed_at, anchor, receipt.version_no):
            logger.error("anchoring: claim lost after the chain call: revision_id=%s", rev.id)
            return "SKIPPED"
        data = {
            "version_no": receipt.version_no,
            "tx_hash": receipt.tx_hash,
            "block_number": receipt.block_number,
            "chain_id": self._chain_id,
            "contract": self._contract,
            "already_anchored": receipt.already_anchored,
            "trigger": trigger,
        }
        await self._append_logged(rev, "VERSION_ANCHORED", data, at)
        try:
            await self._documents.set_latest_version_no(
                rev.document_id, rev.id, receipt.version_no, at
            )
        except Exception as exc:  # noqa: BLE001 - the reconciler repairs the pointer
            logger.error(
                "anchoring: pointer update failed (%s): document_id=%s",
                type(exc).__name__,
                rev.document_id,
            )
        return "ANCHORED"

    async def _fail(
        self, rev: Revision, claimed_at: dt.datetime, code: str, attempts: int, trigger: Trigger
    ) -> Outcome:
        if not await self._revisions.mark_anchor_failed(rev.id, claimed_at, code):
            logger.error("anchoring: claim lost before recording failure: revision_id=%s", rev.id)
            return "SKIPPED"
        logger.warning("anchoring failed (%s): revision_id=%s", code, rev.id)
        data = {"error": code, "attempts": attempts, "trigger": trigger}
        await self._append_logged(rev, "ANCHOR_FAILED", data, now_ms())
        return "FAILED"

    async def _append_logged(
        self,
        rev: Revision,
        type_: Literal["VERSION_ANCHORED", "ANCHOR_FAILED"],
        data: Mapping[str, object],
        at: dt.datetime,
    ) -> None:
        try:
            await self._events.append(
                rev.document_id, type_, revision_id=rev.id, data=dict(data), now=at
            )
        except Exception as exc:  # noqa: BLE001 - state is recorded; event repaired or superseded
            logger.error(
                "anchoring: %s event not written (%s): revision_id=%s",
                type_,
                type(exc).__name__,
                rev.id,
            )


def build_anchor_service(
    db: MongoDatabase, client: RegistryClient | None, settings: Settings
) -> AnchorService:
    return AnchorService(
        DocumentRepository(db),
        RevisionRepository(db),
        EventRepository(db),
        client,
        chain_id=settings.chain_id,
        contract=settings.registry_address.strip() or None,
    )


async def run_anchor_job(service: AnchorService, revision_id: str, trigger: Trigger) -> None:
    """Background-task entry point: never raises (class names and ids only in the log)."""
    try:
        await service.anchor(revision_id, trigger)
    except Exception as exc:  # noqa: BLE001
        code = exc.code if isinstance(exc, DomainError) else type(exc).__name__
        logger.error("anchoring job failed (%s): revision_id=%s", code, revision_id)
