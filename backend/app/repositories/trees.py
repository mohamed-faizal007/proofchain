"""integrity_trees repository: one tree per revision, `_id` = revision id."""

from app.models.integrity_tree import IntegrityTreeDoc
from app.repositories.base import BaseRepository


class TreeRepository(BaseRepository[IntegrityTreeDoc]):
    collection_name = "integrity_trees"
    model = IntegrityTreeDoc

    async def upsert(self, tree: IntegrityTreeDoc) -> IntegrityTreeDoc:
        await self._col.replace_one({"_id": tree.id}, tree.model_dump(by_alias=True), upsert=True)
        return tree
