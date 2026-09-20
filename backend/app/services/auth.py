"""Register / login / role changes (04_API_SPEC Auth, ADR-014)."""

import anyio

from app.config import Settings
from app.errors import ConflictError, NotFoundError, UnauthorizedError
from app.models.user import Role, User
from app.repositories.users import UserRepository
from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password

# A real bcrypt hash at the production cost factor. Login verifies against it when the email is
# unknown, so both failure paths do one genuine bcrypt verify (no sleep, no timing shortcut).
_DUMMY_HASH = hash_password("dummy-not-a-real-password")

_BAD_CREDENTIALS = "Invalid email or password"


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, users: UserRepository, settings: Settings) -> None:
        self._users = users
        self._settings = settings

    async def register(self, email: str, password: str, full_name: str) -> User:
        password_hash = await anyio.to_thread.run_sync(hash_password, password)
        user = User(
            email=normalize_email(email),
            full_name=full_name.strip(),
            password_hash=password_hash,
            roles=["VERIFIER"],
        )
        return await self._users.insert(user)  # duplicate email -> ConflictError (409)

    async def login(self, email: str, password: str) -> tuple[str, User]:
        user = await self._users.get_by_email(normalize_email(email))
        target = user.password_hash if user else _DUMMY_HASH
        password_ok = await anyio.to_thread.run_sync(verify_password, password, target)
        if user is None or not password_ok or not user.is_active:
            raise UnauthorizedError(_BAD_CREDENTIALS)
        return create_access_token(user.id, user.roles, self._settings), user

    async def set_roles(self, user_id: str, roles: list[Role]) -> User:
        current = await self._users.get(user_id)
        if current is None:
            raise NotFoundError("User not found", details={"user_id": user_id})
        # Last-admin guard. Check-then-write, so not atomic: see PROGRESS follow-ups.
        if (
            "ADMIN" in current.roles
            and "ADMIN" not in roles
            and current.is_active
            and await self._users.count_active_with_role("ADMIN", exclude_id=user_id) == 0
        ):
            raise ConflictError("Cannot remove ADMIN from the last active administrator")
        await self._users.update_one(user_id, {"$set": {"roles": sorted(set(roles))}})
        updated = await self._users.get(user_id)
        if updated is None:  # deleted between the two reads
            raise NotFoundError("User not found", details={"user_id": user_id})
        return updated
