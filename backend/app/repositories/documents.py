"""documents repository."""

import datetime as dt
from typing import Any

from app.models.document import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    collection_name = "documents"
    model = Document

    async def get_by_chain_doc_id(self, chain_doc_id: str) -> Document | None:
        return await self.find_one({"chain_doc_id": chain_doc_id})

    async def bump_revision_count(self, id_: str, at: dt.datetime, delta: int = 1) -> bool:
        """Atomic server-side `$inc`; never read-then-write. False if the document is missing."""
        result = await self._col.update_one(
            {"_id": id_}, {"$inc": {"revision_count": delta}, "$set": {"updated_at": at}}
        )
        return result.matched_count > 0

    async def set_latest_approved(self, id_: str, revision_id: str, at: dt.datetime) -> bool:
        """Point the document at its newest APPROVED revision. False if the document is missing.

        A just-approved revision is not anchored yet, so `latest_approved_version_no` is reset to
        null until anchoring sets it (03_DATA_MODEL).
        """
        result = await self._col.update_one(
            {"_id": id_},
            {
                "$set": {
                    "latest_approved_revision_id": revision_id,
                    "latest_approved_version_no": None,
                    "updated_at": at,
                }
            },
        )
        return result.matched_count > 0

    async def set_latest_version_no(
        self, id_: str, revision_id: str, version_no: int, at: dt.datetime
    ) -> bool:
        """Set the on-chain version, only while the document still points at `revision_id`."""
        result = await self._col.update_one(
            {"_id": id_, "latest_approved_revision_id": revision_id},
            {"$set": {"latest_approved_version_no": version_no, "updated_at": at}},
        )
        return result.matched_count > 0

    async def repair_pointer(
        self,
        id_: str,
        seen: tuple[str | None, int | None],
        new: tuple[str | None, int | None],
        at: dt.datetime,
    ) -> bool:
        """Compare-and-set both pointer fields: no-op if they changed since they were read."""
        result = await self._col.update_one(
            {
                "_id": id_,
                "latest_approved_revision_id": seen[0],
                "latest_approved_version_no": seen[1],
            },
            {
                "$set": {
                    "latest_approved_revision_id": new[0],
                    "latest_approved_version_no": new[1],
                    "updated_at": at,
                }
            },
        )
        return result.modified_count > 0

    async def list_by_owner(self, owner_id: str) -> list[Document]:
        return await self.find_many({"owner_id": owner_id}, sort=[("created_at", -1)])

    async def page(
        self, filter_: dict[str, Any], skip: int, limit: int
    ) -> tuple[list[Document], int]:
        """One page, newest activity first (`_id` breaks ties), plus the total match count."""
        total = await self._col.count_documents(filter_)
        items = await self.find_many(
            filter_, sort=[("updated_at", -1), ("_id", 1)], skip=skip, limit=limit
        )
        return items, total
