"""Seed demo users: `python -m app.scripts.seed` (04_API_SPEC Auth).

Idempotent. A rerun repairs each demo user's roles and `is_active` and never touches an existing
password or name, so it doubles as recovery when no active ADMIN is left. The repair writes through
the repository, deliberately bypassing the last-admin guard in AuthService.set_roles.
"""

import asyncio
import sys
from dataclasses import dataclass

import anyio

from app.config import Settings, get_settings
from app.db import MongoDatabase, create_client, ensure_indexes, get_database
from app.models.user import Role, User
from app.repositories.users import UserRepository
from app.schemas.auth import RegisterIn
from app.security.passwords import hash_password

DEV_DEFAULT_PASSWORD = "proofchain-demo-1"


class SeedConfigError(Exception):
    pass


@dataclass(frozen=True)
class DemoUser:
    email: str
    full_name: str
    roles: tuple[Role, ...]


DEMO_USERS = (
    DemoUser("admin@proofchain.local", "Demo Admin", ("ADMIN",)),
    DemoUser("issuer@proofchain.local", "Demo Issuer", ("ISSUER",)),
    DemoUser("approver@proofchain.local", "Demo Approver", ("APPROVER",)),
)


def resolve_seed_password(settings: Settings) -> str:
    password = (settings.seed_password or "").strip()
    if password:
        return settings.seed_password  # type: ignore[return-value]
    if settings.app_env == "prod":
        raise SeedConfigError("SEED_PASSWORD must be set when APP_ENV=prod; nothing was written")
    return DEV_DEFAULT_PASSWORD


async def seed_users(users: UserRepository, password: str) -> dict[str, str]:
    """Create or repair every demo user. Returns {email: "created" | "repaired"}."""
    password_hash: str | None = None
    outcome: dict[str, str] = {}
    for demo in DEMO_USERS:
        # Validate exactly as register would (lightweight email pattern, password length).
        parsed = RegisterIn(email=demo.email, password=password, full_name=demo.full_name)
        roles = sorted(demo.roles)
        existing = await users.get_by_email(parsed.email)
        if existing is None:
            if password_hash is None:
                password_hash = await anyio.to_thread.run_sync(hash_password, password)
            await users.insert(
                User(
                    email=parsed.email,
                    full_name=parsed.full_name,
                    password_hash=password_hash,
                    roles=roles,
                )
            )
            outcome[parsed.email] = "created"
        else:
            await users.update_one(existing.id, {"$set": {"roles": roles, "is_active": True}})
            outcome[parsed.email] = "repaired"
    return outcome


async def run(settings: Settings, db: MongoDatabase | None = None) -> dict[str, str]:
    password = resolve_seed_password(settings)  # before any connection or write
    if db is None:
        db = get_database(create_client(settings), settings)
    await ensure_indexes(db)
    return await seed_users(UserRepository(db), password)


def main(settings: Settings | None = None) -> int:
    try:
        outcome = asyncio.run(run(settings or get_settings()))
    except SeedConfigError as exc:
        print(f"seed: {exc}", file=sys.stderr)
        return 1
    for email, what in outcome.items():
        print(f"seed: {what} {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
