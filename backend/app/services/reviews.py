"""Maker-checker review (01_ARCHITECTURE §3.2): PENDING -> APPROVED | REJECTED, with provenance.

Write order: `set_review` (conditional on PENDING, so concurrent reviews have one winner) ->
provenance event -> (approve only) document pointer. The event is the commit point. Before it is
known to be written, a failure reverts the revision to PENDING. If the revert fails, or it is
unknown whether the event was written, the revision is left reviewed with no event, which is the
state the P5-04 reconciler repairs. It is never reverted blindly: an event pointing at a PENDING
revision could not be repaired. After the event, a pointer failure is logged, not rolled back.
Anchoring is scheduled by the approve route after the response (services/anchoring.py).
"""

import datetime as dt
import logging
from typing import Literal

from app.errors import (
    NotFoundError,
    RevisionNotPendingError,
    SelfApprovalForbiddenError,
    ValidationFailed,
)
from app.models.provenance_event import EventType
from app.models.revision import Anchor, Revision
from app.models.user import User
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.services._intake import MAX_NOTE_CHARS

logger = logging.getLogger(__name__)

_Decision = Literal["APPROVED", "REJECTED"]
_EVENT: dict[_Decision, EventType] = {
    "APPROVED": "REVISION_APPROVED",
    "REJECTED": "REVISION_REJECTED",
}


def _clean_comment(comment: str | None, *, required: bool) -> str | None:
    text = (comment or "").strip() or None
    if text is None and required:
        raise ValidationFailed("comment is required")
    if text and len(text) > MAX_NOTE_CHARS:
        raise ValidationFailed(f"comment must be at most {MAX_NOTE_CHARS} characters")
    return text


def _now_ms() -> dt.datetime:
    # BSON keeps milliseconds; the revert filter matches on reviewed_at, so it must round-trip.
    now = dt.datetime.now(dt.UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


class ReviewService:
    def __init__(
        self,
        documents: DocumentRepository,
        revisions: RevisionRepository,
        events: EventRepository,
    ) -> None:
        self._documents = documents
        self._revisions = revisions
        self._events = events

    async def approve(self, approver: User, revision_id: str, comment: str | None) -> Revision:
        return await self._review(
            approver, revision_id, "APPROVED", _clean_comment(comment, required=False)
        )

    async def reject(self, approver: User, revision_id: str, comment: str | None) -> Revision:
        return await self._review(
            approver, revision_id, "REJECTED", _clean_comment(comment, required=True)
        )

    async def _review(
        self, reviewer: User, revision_id: str, decision: _Decision, comment: str | None
    ) -> Revision:
        revision = await self._revisions.get(revision_id)
        if revision is None:
            raise NotFoundError("Revision not found")
        # Maker != checker (CLAUDE.md invariant); 01 §3.2 checks this before the status.
        if revision.submitted_by == reviewer.id:
            raise SelfApprovalForbiddenError("The submitter cannot review their own revision")
        if revision.status != "PENDING":
            raise RevisionNotPendingError("Revision is not pending")

        at = _now_ms()
        try:
            won = await self._revisions.set_review(revision_id, decision, reviewer.id, comment, at)
        except Exception:
            # The write may have committed before raising; the revert only matches our own review.
            await self._revert(revision, reviewer.id, at, decision)
            raise
        if not won:
            raise RevisionNotPendingError("Revision is not pending")  # lost a concurrent review

        event_type = _EVENT[decision]
        try:
            await self._events.append(
                revision.document_id,
                event_type,
                actor_id=reviewer.id,
                revision_id=revision_id,
                data={"revision_no": revision.revision_no, "comment": comment},
                now=at,
            )
        except Exception:
            recorded = await self._event_recorded(revision, event_type, reviewer.id, at)
            if recorded is not True:
                if recorded is False:
                    await self._revert(revision, reviewer.id, at, decision)
                else:
                    self._log_unrecorded(revision, decision, "event outcome unknown")
                raise
            logger.warning(
                "review event append raised but the event was stored: revision_id=%s",
                revision_id,
            )

        if decision == "APPROVED":
            await self._move_pointer(revision, at)
        return revision.model_copy(
            update={
                "status": decision,
                "reviewed_by": reviewer.id,
                "reviewed_at": at,
                "review_comment": comment,
                "anchor": Anchor(status="ANCHORING") if decision == "APPROVED" else revision.anchor,
            }
        )

    async def _event_recorded(
        self, revision: Revision, event_type: EventType, actor_id: str, at: dt.datetime
    ) -> bool | None:
        """Whether this review's event exists; None if that cannot be determined."""
        try:
            events = await self._events.list_by_document(revision.document_id)
        except Exception as exc:
            logger.error("review event lookup failed: %s", type(exc).__name__)
            return None
        return any(
            e.type == event_type
            and e.revision_id == revision.id
            and e.actor_id == actor_id
            and e.at == at
            for e in events
        )

    async def _revert(
        self, revision: Revision, reviewer_id: str, at: dt.datetime, decision: _Decision
    ) -> None:
        """Best effort, never raises, so the caller sees the original error."""
        try:
            await self._revisions.revert_review(revision.id, reviewer_id, at)
        except Exception as exc:
            logger.error("review revert failed: %s", type(exc).__name__)
            self._log_unrecorded(revision, decision, "revert failed")

    @staticmethod
    def _log_unrecorded(revision: Revision, decision: _Decision, why: str) -> None:
        # Class names and ids only, never str(exc). The P5-04 reconciler appends the event.
        logger.error(
            "review may be left %s without its provenance event (%s): "
            "revision_id=%s document_id=%s",
            decision,
            why,
            revision.id,
            revision.document_id,
        )

    async def _move_pointer(self, revision: Revision, at: dt.datetime) -> None:
        try:
            ok = await self._documents.set_latest_approved(revision.document_id, revision.id, at)
        except Exception as exc:
            logger.error("set_latest_approved failed: %s", type(exc).__name__)
            ok = False
        if not ok:
            logger.error(
                "approval recorded but latest_approved_revision_id not updated: "
                "document_id=%s revision_id=%s",
                revision.document_id,
                revision.id,
            )
