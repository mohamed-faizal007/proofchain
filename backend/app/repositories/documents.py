"""documents repository."""

import datetime as dt

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
        """Point the document at its newest APPROVED revision. False if the document is missing."""
        result = await self._col.update_one(
            {"_id": id_},
            {"$set": {"latest_approved_revision_id": revision_id, "updated_at": at}},
        )
        return result.matched_count > 0

    async def list_by_owner(self, owner_id: str) -> list[Document]:
        return await self.find_many({"owner_id": owner_id}, sort=[("created_at", -1)])
