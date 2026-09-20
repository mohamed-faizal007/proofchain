"""verifications repository (insert + history queries, newest first)."""

from app.models.verification import Verification
from app.repositories.base import BaseRepository


class VerificationRepository(BaseRepository[Verification]):
    collection_name = "verifications"
    model = Verification

    async def list_by_document(self, document_id: str, limit: int = 50) -> list[Verification]:
        return await self.find_many({"document_id": document_id}, sort=[("at", -1)], limit=limit)

    async def list_by_requester(self, requested_by: str, limit: int = 50) -> list[Verification]:
        return await self.find_many({"requested_by": requested_by}, sort=[("at", -1)], limit=limit)
