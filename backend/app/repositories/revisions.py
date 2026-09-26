"""revisions repository. State transitions are guarded in the query (03 state machine)."""

import datetime as dt
from typing import Literal

from app.models.revision import Anchor, Revision
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

    async def set_anchor(self, id_: str, anchor: Anchor, version_no: int | None = None) -> bool:
        fields: dict[str, object] = {"anchor": anchor.model_dump()}
        if version_no is not None:
            fields["version_no"] = version_no
        # Backstop for "only APPROVED revisions are anchored" (CLAUDE.md); the service enforces it
        # first (P5-04). matched_count so an identical retry still reads as True.
        result = await self._col.update_one({"_id": id_, "status": "APPROVED"}, {"$set": fields})
        return result.matched_count > 0
