"""revisions repository. State transitions are guarded in the query (03 state machine)."""

import datetime as dt
from typing import Any, Literal

from app.models.revision import Anchor, Revision, RevisionStatus, Revocation
from app.repositories.base import BaseRepository


class RevisionRepository(BaseRepository[Revision]):
    collection_name = "revisions"
    model = Revision

    async def next_revision_no(self, document_id: str) -> int:
        """Next sequential number; a concurrent duplicate is caught by the unique index."""
        latest = await self.find_many(
            {"document_id": document_id}, sort=[("revision_no", -1)], limit=1
        )
        return latest[0].revision_no + 1 if latest else 1

    async def get_pending(self, document_id: str) -> Revision | None:
        return await self.find_one({"document_id": document_id, "status": "PENDING"})

    async def get_latest_approved(self, document_id: str) -> Revision | None:
        found = await self.find_many(
            {"document_id": document_id, "status": "APPROVED"},
            sort=[("revision_no", -1)],
            limit=1,
        )
        return found[0] if found else None

    async def list_by_document(self, document_id: str) -> list[Revision]:
        return await self.find_many({"document_id": document_id}, sort=[("revision_no", 1)])

    async def find_by_file_hash(self, file_hash: str) -> list[Revision]:
        return await self.find_many({"file_hash": file_hash}, sort=[("submitted_at", 1)])

    async def find_by_text_root(self, text_root: str) -> list[Revision]:
        return await self.find_many({"text_root": text_root}, sort=[("submitted_at", 1)])

    async def set_review(
        self,
        id_: str,
        status: Literal["APPROVED", "REJECTED"],
        reviewed_by: str,
        comment: str | None,
        at: dt.datetime,
    ) -> bool:
        """PENDING -> APPROVED|REJECTED. False if the revision is missing or no longer PENDING.

        Approval also marks the anchor ANCHORING in the same write (01_ARCHITECTURE §3.2), so a
        crash can never leave an APPROVED revision that the anchoring reconciler would not pick up.
        """
        if status not in ("APPROVED", "REJECTED"):
            raise ValueError(f"invalid review status: {status}")
        fields: dict[str, object] = {
            "status": status,
            "reviewed_by": reviewed_by,
            "review_comment": comment,
            "reviewed_at": at,
        }
        if status == "APPROVED":
            fields["anchor.status"] = "ANCHORING"
        result = await self._col.update_one({"_id": id_, "status": "PENDING"}, {"$set": fields})
        return result.modified_count > 0

    async def revert_review(self, id_: str, reviewed_by: str, at: dt.datetime) -> bool:
        """Undo one specific `set_review` (same reviewer and timestamp) back to PENDING.

        Compensation for a review whose provenance event was not written; never touches a review
        made by anyone else. Resets the anchor, which is only safe before anchoring starts.
        """
        result = await self._col.update_one(
            {
                "_id": id_,
                "status": {"$in": ["APPROVED", "REJECTED"]},
                "reviewed_by": reviewed_by,
                "reviewed_at": at,
            },
            {
                "$set": {
                    "status": "PENDING",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "review_comment": None,
                    "anchor": Anchor().model_dump(),
                }
            },
        )
        return result.modified_count > 0

    # --- write guards (P2 review): no state-free writes on revisions ---

    async def update_one(self, id_: str, update: dict[str, Any]) -> bool:
        """Disabled: every revision write must go through a state-guarded method below."""
        raise NotImplementedError("RevisionRepository.update_one bypasses the state guards")

    async def delete(self, id_: str) -> bool:
        """Delete a PENDING revision only (the P5-01/P5-02 rollbacks of a just-inserted row)."""
        result = await self._col.delete_one({"_id": id_, "status": "PENDING"})
        return result.deleted_count > 0

    # --- revocation (P5-05): APPROVED + ANCHORED -> REVOKED, after the on-chain revoke ---

    async def mark_revoked(self, id_: str, revocation: Revocation) -> bool:
        """False if the revision is no longer an ANCHORED, APPROVED revision."""
        result = await self._col.update_one(
            {"_id": id_, "status": "APPROVED", "anchor.status": "ANCHORED"},
            {"$set": {"status": "REVOKED", "revocation": revocation.model_dump()}},
        )
        return result.modified_count > 0

    # --- anchoring (P5-04). Every write requires status APPROVED (CLAUDE.md invariant). ---

    async def claim_anchor(self, id_: str, at: dt.datetime, stale_before: dt.datetime) -> bool:
        """Claim an APPROVED revision for one anchoring attempt.

        Claimable: FAILED, queued ANCHORING (`attempted_at` null) or a stuck claim older than
        `stale_before`. A claim still in flight is never taken.
        """
        result = await self._col.update_one(
            {"_id": id_, "status": "APPROVED", "$or": _claimable(stale_before)},
            {
                "$set": {
                    "anchor.status": "ANCHORING",
                    "anchor.attempted_at": at,
                    "anchor.error": None,
                },
                "$inc": {"anchor.attempts": 1},
            },
        )
        return result.modified_count > 0

    async def requeue_anchor(self, id_: str) -> bool:
        """FAILED -> queued ANCHORING (admin retry, or a retry that must wait its turn)."""
        result = await self._col.update_one(
            {"_id": id_, "status": "APPROVED", "anchor.status": "FAILED"},
            {"$set": {"anchor.status": "ANCHORING", "anchor.attempted_at": None}},
        )
        return result.modified_count > 0

    async def mark_anchored(
        self, id_: str, claimed_at: dt.datetime, anchor: Anchor, version_no: int
    ) -> bool:
        """Finish our own claim (matched by `claimed_at`) as ANCHORED."""
        result = await self._col.update_one(
            _own_claim(id_, claimed_at),
            {"$set": {"anchor": anchor.model_dump(), "version_no": version_no}},
        )
        return result.modified_count > 0

    async def mark_anchor_failed(self, id_: str, claimed_at: dt.datetime, error: str) -> bool:
        """Finish our own claim as FAILED with an error code."""
        result = await self._col.update_one(
            _own_claim(id_, claimed_at),
            {"$set": {"anchor.status": "FAILED", "anchor.error": error}},
        )
        return result.modified_count > 0

    async def find_unanchored_predecessor(
        self, document_id: str, revision_no: int
    ) -> Revision | None:
        """Oldest APPROVED revision before `revision_no` that is not ANCHORED yet."""
        found = await self.find_many(
            {
                "document_id": document_id,
                "status": "APPROVED",
                "revision_no": {"$lt": revision_no},
                "anchor.status": {"$ne": "ANCHORED"},
            },
            sort=[("revision_no", 1)],
            limit=1,
        )
        return found[0] if found else None

    async def next_queued_successor(self, document_id: str, revision_no: int) -> Revision | None:
        """Oldest queued (unclaimed) APPROVED revision after `revision_no`."""
        found = await self.find_many(
            {
                "document_id": document_id,
                "status": "APPROVED",
                "revision_no": {"$gt": revision_no},
                "anchor.status": "ANCHORING",
                "anchor.attempted_at": None,
            },
            sort=[("revision_no", 1)],
            limit=1,
        )
        return found[0] if found else None

    # --- reconciler queries (P5-04) ---

    async def find_anchor_candidates(self, stale_before: dt.datetime) -> list[Revision]:
        """FAILED, queued or stuck-claim anchors, oldest revision first per document.

        Not filtered on `status`: the anchoring service enforces APPROVED and raises otherwise.
        """
        return await self.find_many(
            {"$or": _claimable(stale_before)}, sort=[("document_id", 1), ("revision_no", 1)]
        )

    async def find_reviewed_before(
        self, statuses: tuple[RevisionStatus, ...], cutoff: dt.datetime
    ) -> list[Revision]:
        return await self.find_many(
            {"status": {"$in": list(statuses)}, "reviewed_at": {"$lt": cutoff}},
            sort=[("reviewed_at", 1)],
        )

    async def find_revoked_before(self, cutoff: dt.datetime) -> list[Revision]:
        return await self.find_many(
            {"status": "REVOKED", "revocation.at": {"$lt": cutoff}}, sort=[("revocation.at", 1)]
        )

    async def document_ids_with_status(self, status: RevisionStatus) -> list[str]:
        """Documents that have at least one revision in `status` (GET /documents filter)."""
        ids = await self._col.distinct("document_id", {"status": status})
        return [str(i) for i in ids]

    async def find_anchored_before(self, cutoff: dt.datetime) -> list[Revision]:
        return await self.find_many(
            {"anchor.status": "ANCHORED", "anchor.anchored_at": {"$lt": cutoff}},
            sort=[("anchor.anchored_at", 1)],
        )


def _claimable(stale_before: dt.datetime) -> list[dict[str, Any]]:
    return [
        {"anchor.status": "FAILED"},
        {"anchor.status": "ANCHORING", "anchor.attempted_at": None},
        {"anchor.status": "ANCHORING", "anchor.attempted_at": {"$lt": stale_before}},
    ]


def _own_claim(id_: str, claimed_at: dt.datetime) -> dict[str, Any]:
    return {
        "_id": id_,
        "status": "APPROVED",
        "anchor.status": "ANCHORING",
        "anchor.attempted_at": claimed_at,
    }
