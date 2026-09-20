"""users repository."""

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    collection_name = "users"
    model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self.find_one({"email": email})

    async def count_active_with_role(self, role: str, *, exclude_id: str | None = None) -> int:
        filter_: dict[str, object] = {"roles": role, "is_active": True}
        if exclude_id is not None:
            filter_["_id"] = {"$ne": exclude_id}
        return await self._col.count_documents(filter_)
