"""Revocation (04 `POST /revisions/{id}/revoke`): APPROVED -> REVOKED, on-chain first.

Only an ANCHORED revision can be revoked, because `revokeVersion` needs its on-chain version.
Maker != checker does not apply here: revoking is a corrective action on an already anchored
fact, not the approval gate, so any APPROVER may revoke (PROGRESS.md, P5-05).

Write order: chain -> revision REVOKED (conditional on APPROVED + ANCHORED) -> VERSION_REVOKED
event -> document pointer. The chain is authoritative and a revoke cannot be undone there, so it
goes first and nothing after it is rolled back. Each call re-reads the chain before sending:
a version that is already revoked on-chain (a previous call whose Mongo write failed) is not
sent again, so a retried revoke finishes the job. A missing event is appended by the startup
reconciler and a stale pointer is repaired by it (compare-and-set).

Revocations are serialized by one in-process lock, so concurrent revokes of the same revision
send one tx and the loser gets 409. Assumes a single worker, like anchoring (PROGRESS.md).
"""

import asyncio
import datetime as dt
import logging
import weakref

from app.chain import RegistryClient
from app.errors import (
    AnchorFailedError,
    ChainUnavailableError,
    ConflictError,
    DomainError,
    NotFoundError,
    RevisionNotApprovedError,
    ValidationFailed,
)
from app.models.revision import Revision, Revocation
from app.models.user import User
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository

logger = logging.getLogger(__name__)

# The reason is stored on-chain in the VersionRevoked event: public and paid for in gas.
MAX_REASON_CHARS = 500

# One lock per event loop (an asyncio.Lock must not be shared across loops, e.g. in tests).
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock


def _now_ms() -> dt.datetime:
    now = dt.datetime.now(dt.UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _clean_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if not text:
        raise ValidationFailed("reason is required")
    if len(text) > MAX_REASON_CHARS:
        raise ValidationFailed(f"reason must be at most {MAX_REASON_CHARS} characters")
    return text


def revoke_event_data(rev: Revision, revocation: Revocation) -> dict[str, object]:
    """VERSION_REVOKED event payload (shared with the reconciler)."""
    return {
        "version_no": rev.version_no,
        "reason": revocation.reason,
        "tx_hash": revocation.tx_hash,
        "block_number": revocation.block_number,
        "already_revoked": revocation.tx_hash is None,
    }


class RevocationService:
    def __init__(
        self,
        documents: DocumentRepository,
        revisions: RevisionRepository,
        events: EventRepository,
        client: RegistryClient | None,
    ) -> None:
        self._documents = documents
        self._revisions = revisions
        self._events = events
        self._client = client

    async def revoke(self, approver: User, revision_id: str, reason: str | None) -> Revision:
        text = _clean_reason(reason)
        async with _lock():
            rev = await self._get_revocable(revision_id)
            if self._client is None:
                raise ChainUnavailableError("Blockchain registry is not configured")
            document = await self._documents.get(rev.document_id)
            if document is None:
                logger.error("revoke: document missing: revision_id=%s", rev.id)
                raise DomainError("Document of the revision is missing")
            assert rev.version_no is not None  # checked by _get_revocable
            tx_hash, block = await self._revoke_on_chain(
                self._client, document.chain_doc_id, rev.version_no, text
            )
            revocation = Revocation(
                by=approver.id, at=_now_ms(), reason=text, tx_hash=tx_hash, block_number=block
            )
            if not await self._mark(rev, revocation):
                # Changed outside this lock (e.g. a direct DB edit); report what is there now.
                now = await self._revisions.get(rev.id)
                raise RevisionNotApprovedError(
                    "Only APPROVED revisions can be revoked",
                    details={"status": now.status if now else None},
                )
        revoked = rev.model_copy(update={"status": "REVOKED", "revocation": revocation})
        await self._append_event(revoked, revocation)
        await self._repair_pointer(revoked, revocation.at)
        return revoked

    async def _get_revocable(self, revision_id: str) -> Revision:
        rev = await self._revisions.get(revision_id)
        if rev is None:
            raise NotFoundError("Revision not found")
        if rev.status != "APPROVED":
            raise RevisionNotApprovedError(
                "Only APPROVED revisions can be revoked", details={"status": rev.status}
            )
        if rev.anchor.status != "ANCHORED" or rev.version_no is None:
            raise ConflictError(
                "Only anchored revisions can be revoked",
                details={"anchor_status": rev.anchor.status},
            )
        return rev

    async def _revoke_on_chain(
        self, client: RegistryClient, chain_doc_id: str, version_no: int, reason: str
    ) -> tuple[str | None, int | None]:
        """(tx_hash, block), or (None, None) if the version is already revoked on-chain."""
        on_chain = await client.get_version(chain_doc_id, version_no)
        if on_chain is None:
            raise AnchorFailedError("Anchored version not found on-chain")
        if on_chain.revoked:
            logger.warning("revoke: version already revoked on-chain, no tx sent")
            return None, None
        receipt = await client.revoke_version(chain_doc_id, version_no, reason)
        return receipt.tx_hash, receipt.block_number

    async def _mark(self, rev: Revision, revocation: Revocation) -> bool:
        try:
            return await self._revisions.mark_revoked(rev.id, revocation)
        except Exception as exc:
            # Chain is revoked, Mongo is not: a retried revoke skips the tx and finishes.
            logger.error(
                "revoke: revoked on-chain but revision not updated (%s); retry the revoke: "
                "revision_id=%s",
                type(exc).__name__,
                rev.id,
            )
            raise

    async def _append_event(self, rev: Revision, revocation: Revocation) -> None:
        try:
            await self._events.append(
                rev.document_id,
                "VERSION_REVOKED",
                actor_id=revocation.by,
                revision_id=rev.id,
                data=revoke_event_data(rev, revocation),
                now=revocation.at,
            )
        except Exception as exc:  # noqa: BLE001 - state is final; the reconciler appends it
            logger.error(
                "revoke: VERSION_REVOKED event not written (%s): revision_id=%s",
                type(exc).__name__,
                rev.id,
            )

    async def _repair_pointer(self, rev: Revision, at: dt.datetime) -> None:
        """Point the document at its newest remaining APPROVED revision (or null)."""
        try:
            doc = await self._documents.get(rev.document_id)
            if doc is None:
                return
            latest = await self._revisions.get_latest_approved(doc.id)
            want = (latest.id, latest.version_no) if latest else (None, None)
            seen = (doc.latest_approved_revision_id, doc.latest_approved_version_no)
            if want != seen:
                await self._documents.repair_pointer(doc.id, seen, want, at)
        except Exception as exc:  # noqa: BLE001 - the reconciler repairs the pointer
            logger.error(
                "revoke: pointer update failed (%s): document_id=%s",
                type(exc).__name__,
                rev.document_id,
            )
