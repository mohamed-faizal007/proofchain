"""documents repository."""

from app.models.document import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    collection_name = "documents"
    model = Document

    async def get_by_chain_doc_id(self, chain_doc_id: str) -> Document | None:
        return await self.find_one({"chain_doc_id": chain_doc_id})

    async def list_by_owner(self, owner_id: str) -> list[Document]:
        return await self.find_many({"owner_id": owner_id}, sort=[("created_at", -1)])
