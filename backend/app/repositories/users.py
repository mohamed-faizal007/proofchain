"""users repository."""

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    collection_name = "users"
    model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self.find_one({"email": email})
