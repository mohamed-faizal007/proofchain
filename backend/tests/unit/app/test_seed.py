"""Demo-user seed script (P3-03): idempotency, lockout recovery, prod password guard."""

from typing import Any

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings
from app.errors import UnauthorizedError
from app.models.user import Role, User
from app.repositories.users import UserRepository
from app.schemas.auth import RegisterIn
from app.scripts import seed
from app.security.passwords import hash_password
from app.services.auth import AuthService

SECRET = "test-secret-" + "x" * 32
PASSWORD = "seed-password-1"
OTHER_HASH = hash_password("some other password")
ADMIN_EMAIL = "admin@proofchain.local"


def _settings(env: str = "test", **kw: Any) -> Settings:
    return Settings(  # type: ignore[arg-type]
        app_env=env,
        jwt_secret=SECRET,
        anchor_private_key="0x" + "1" * 64,
        registry_address="0x" + "2" * 40,
        **kw,
    )


def _auth(repo: UserRepository) -> AuthService:
    return AuthService(repo, _settings())


async def _admin(repo: UserRepository) -> User:
    user = await repo.get_by_email(ADMIN_EMAIL)
    assert user is not None
    return user


async def _extra_user(repo: UserRepository, email: str, roles: list[Role], *, active: bool) -> None:
    await repo.insert(
        User(
            email=email, full_name="Extra", password_hash=OTHER_HASH, roles=roles, is_active=active
        )
    )


@pytest.fixture
def repo(mongo_db: AsyncIOMotorDatabase) -> UserRepository:
    return UserRepository(mongo_db)


async def test_seed_creates_three_users_with_expected_roles(repo: UserRepository) -> None:
    await seed.seed_users(repo, PASSWORD)
    got = {u.email: u.roles for u in await repo.find_many()}
    assert got == {
        "admin@proofchain.local": ["ADMIN"],
        "issuer@proofchain.local": ["ISSUER"],
        "approver@proofchain.local": ["APPROVER"],
    }


async def test_seed_hashes_password_and_can_log_in(repo: UserRepository) -> None:
    await seed.seed_users(repo, PASSWORD)
    user = await _admin(repo)
    assert PASSWORD not in user.password_hash
    _, logged_in = await _auth(repo).login(ADMIN_EMAIL, PASSWORD)
    assert logged_in.id == user.id


async def test_seed_is_idempotent(repo: UserRepository) -> None:
    await seed.seed_users(repo, PASSWORD)
    before = {u.id: u.password_hash for u in await repo.find_many()}
    await seed.seed_users(repo, PASSWORD)
    after = {u.id: u.password_hash for u in await repo.find_many()}
    assert len(after) == 3
    assert after == before


async def test_rerun_does_not_reset_changed_password_or_name(repo: UserRepository) -> None:
    await seed.seed_users(repo, PASSWORD)
    admin = await _admin(repo)
    await repo.update_one(admin.id, {"$set": {"password_hash": OTHER_HASH, "full_name": "Renamed"}})
    await seed.seed_users(repo, PASSWORD)
    again = await _admin(repo)
    assert again.password_hash == OTHER_HASH
    assert again.full_name == "Renamed"


def test_seed_emails_match_register_pattern() -> None:
    for demo in seed.DEMO_USERS:
        parsed = RegisterIn(email=demo.email, password=PASSWORD, full_name=demo.full_name)
        assert parsed.email == demo.email
        assert demo.email == demo.email.strip().lower()


@pytest.mark.parametrize("scenario", ["demoted", "deactivated", "both", "deleted"])
async def test_rerun_recovers_from_total_admin_lockout(repo: UserRepository, scenario: str) -> None:
    await seed.seed_users(repo, PASSWORD)
    admin = await _admin(repo)
    if scenario == "demoted":
        await repo.update_one(admin.id, {"$set": {"roles": ["VERIFIER"]}})
    elif scenario == "deactivated":
        await repo.update_one(admin.id, {"$set": {"is_active": False}})
    elif scenario == "both":
        await repo.update_one(admin.id, {"$set": {"roles": ["ISSUER"], "is_active": False}})
    else:
        await repo.delete(admin.id)
    # Other admins exist but are inactive, so there is no usable admin anywhere.
    await _extra_user(repo, "old-admin@example.com", ["ADMIN"], active=False)
    await _extra_user(repo, "ex-admin@example.com", ["ADMIN", "ISSUER"], active=False)

    # Precondition: this really is a lockout.
    assert await repo.count_active_with_role("ADMIN") == 0
    # A deactivated demo admin cannot log in, so the API offers no way out of the lockout.
    if scenario in ("deactivated", "both"):
        with pytest.raises(UnauthorizedError):
            await _auth(repo).login(ADMIN_EMAIL, PASSWORD)

    await seed.seed_users(repo, PASSWORD)

    recovered = await _admin(repo)
    assert recovered.roles == ["ADMIN"]
    assert recovered.is_active is True
    assert await repo.count_active_with_role("ADMIN") == 1
    # Restored user can actually log in (original seed password in every scenario).
    _, user = await _auth(repo).login(ADMIN_EMAIL, PASSWORD)
    assert user.id == recovered.id and user.roles == ["ADMIN"]
    # Unrelated users are untouched.
    old = await repo.get_by_email("old-admin@example.com")
    assert old is not None and old.is_active is False


async def test_healthy_rerun_leaves_last_admin_unchanged(repo: UserRepository) -> None:
    await seed.seed_users(repo, PASSWORD)
    before = await _admin(repo)
    await seed.seed_users(repo, PASSWORD)
    assert await _admin(repo) == before


def test_dev_uses_default_password_when_unset() -> None:
    assert seed.resolve_seed_password(_settings("dev")) == seed.DEV_DEFAULT_PASSWORD
    assert len(seed.DEV_DEFAULT_PASSWORD) >= 8


def test_explicit_seed_password_wins_in_any_env() -> None:
    assert seed.resolve_seed_password(_settings("prod", seed_password="prod-pass-123")) == (
        "prod-pass-123"
    )


@pytest.mark.parametrize("value", [None, "", "   "])
def test_prod_requires_explicit_seed_password(value: str | None) -> None:
    kw: dict[str, Any] = {} if value is None else {"seed_password": value}
    with pytest.raises(seed.SeedConfigError, match="SEED_PASSWORD"):
        seed.resolve_seed_password(_settings("prod", **kw))


@pytest.mark.parametrize("value", [None, "", "   "])
async def test_prod_without_password_writes_nothing(
    mongo_db: AsyncIOMotorDatabase, repo: UserRepository, value: str | None
) -> None:
    await _extra_user(repo, ADMIN_EMAIL, ["VERIFIER"], active=False)
    before = await mongo_db["users"].find_one({"email": ADMIN_EMAIL})
    kw: dict[str, Any] = {} if value is None else {"seed_password": value}

    with pytest.raises(seed.SeedConfigError):
        await seed.run(_settings("prod", **kw), db=mongo_db)

    assert await mongo_db["users"].count_documents({}) == 1
    assert await mongo_db["users"].find_one({"email": ADMIN_EMAIL}) == before


@pytest.mark.parametrize("value", [None, "  "])
def test_prod_without_password_never_connects_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], value: str | None
) -> None:
    def boom(*_: object, **__: object) -> None:
        raise AssertionError("must not connect to Mongo before the password check")

    monkeypatch.setattr(seed, "create_client", boom)
    kw: dict[str, Any] = {} if value is None else {"seed_password": value}

    code = seed.main(_settings("prod", **kw))

    assert code != 0
    err = capsys.readouterr().err
    assert "SEED_PASSWORD" in err
    assert "Traceback" not in err
    assert "nothing was written" in err


@pytest.mark.parametrize("bad", ["short", "x" * 257, "é" * 40])
def test_invalid_seed_password_is_rejected_without_leaking_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    def boom(*_: object, **__: object) -> None:
        raise AssertionError("must not connect to Mongo")

    monkeypatch.setattr(seed, "create_client", boom)

    code = seed.main(_settings("dev", seed_password=bad))

    assert code != 0
    captured = capsys.readouterr()
    assert bad not in captured.err + captured.out
    assert "Traceback" not in captured.err
    assert "SEED_PASSWORD" in captured.err
