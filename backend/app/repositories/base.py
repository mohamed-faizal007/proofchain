"""Generic repository helpers. Subclasses set `collection_name` and `model`."""

from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.db import MongoCollection, MongoDatabase
from app.errors import ConflictError

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    collection_name: ClassVar[str]
    model: ClassVar[type[BaseModel]]

    def __init__(self, db: MongoDatabase) -> None:
        self._col: MongoCollection = db[self.collection_name]

    def _to_model(self, doc: dict[str, Any]) -> T:
        return self.model.model_validate(doc)  # type: ignore[return-value]

    async def insert(self, obj: T) -> T:
        try:
            await self._col.insert_one(obj.model_dump(by_alias=True))
        except DuplicateKeyError as exc:
            raise ConflictError(
                f"Duplicate value in {self.collection_name}",
                details={"collection": self.collection_name},
            ) from exc
        return obj

    async def get(self, id_: str) -> T | None:
        return await self.find_one({"_id": id_})

    async def find_one(self, filter_: dict[str, Any]) -> T | None:
        doc = await self._col.find_one(filter_)
        return self._to_model(doc) if doc else None

    async def find_many(
        self,
        filter_: dict[str, Any] | None = None,
        *,
        sort: list[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 0,
    ) -> list[T]:
        cursor = self._col.find(filter_ or {})
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return [self._to_model(d) async for d in cursor]

    async def update_one(self, id_: str, update: dict[str, Any]) -> bool:
        """Apply a Mongo update document to `_id`; True if a document was modified."""
        try:
            result = await self._col.update_one({"_id": id_}, update)
        except DuplicateKeyError as exc:
            raise ConflictError(
                f"Duplicate value in {self.collection_name}",
                details={"collection": self.collection_name},
            ) from exc
        return result.modified_count > 0

    async def delete(self, id_: str) -> bool:
        result = await self._col.delete_one({"_id": id_})
        return result.deleted_count > 0
