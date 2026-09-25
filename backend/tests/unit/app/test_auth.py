"""Auth routes, current-user dependency and role guard (P3-02)."""

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.chain import FakeRegistryClient
from app.config import Settings
from app.deps import require_roles
from app.main import create_app
from app.models.user import Role, User
from app.repositories.users import UserRepository
from app.security.jwt import create_access_token, decode_access_token
from app.security.passwords import hash_password
from app.services import auth as auth_service

PREFIX = "/api/v1"
PASSWORD = "correct horse battery"
PASSWORD_HASH = hash_password(PASSWORD)
_ISSUER_OR_APPROVER = require_roles("ISSUER", "APPROVER")
SECRET = "test-secret-" + "x" * 32


def _settings(env: str = "test") -> Settings:
    return Settings(  # type: ignore[arg-type]
        app_env=env,
        jwt_secret=SECRET,
        anchor_private_key="0x" + "1" * 64,
        registry_address="0x" + "2" * 40,
    )


def _make_client(db: AsyncIOMotorDatabase, env: str = "test") -> Iterator[TestClient]:
    app = create_app(  # type: ignore[arg-type]
        _settings(env), db=db, storage=object(), registry_client=FakeRegistryClient()
    )

    @app.get("/_guard")
    async def guard(user: User = Depends(_ISSUER_OR_APPROVER)) -> dict[str, str]:
        return {"id": user.id}

    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(mongo_db: AsyncIOMotorDatabase) -> Iterator[TestClient]:
    yield from _make_client(mongo_db)


@pytest.fixture
def prod_client(mongo_db: AsyncIOMotorDatabase) -> Iterator[TestClient]:
    yield from _make_client(mongo_db, env="prod")


def _seed(
    client: TestClient,
    email: str,
    roles: list[Role],
    *,
    active: bool = True,
) -> User:
    user = User(
        email=email,
        full_name="Seeded User",
        password_hash=PASSWORD_HASH,
        roles=roles,
        is_active=active,
    )
    repo = UserRepository(client.app.state.db)  # type: ignore[attr-defined]
    client.portal.call(repo.insert, user)  # type: ignore[union-attr]
    return user


def _bearer(user: User, now: dt.datetime | None = None) -> dict[str, str]:
    token = create_access_token(user.id, user.roles, _settings(), now=now)
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, **over: Any) -> Any:
    body = {"email": "new@example.com", "password": PASSWORD, "full_name": "New User"}
    return client.post(f"{PREFIX}/auth/register", json={**body, **over})


# --- register ---------------------------------------------------------------


def test_register_creates_verifier_without_password_hash(client: TestClient) -> None:
    r = _register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["roles"] == ["VERIFIER"]
    assert body["email"] == "new@example.com"
    assert body["is_active"] is True
    assert "password_hash" not in body
    assert "password" not in body


def test_register_cannot_choose_roles(client: TestClient) -> None:
    r = _register(client, roles=["ADMIN"])
    assert r.status_code == 201
    assert r.json()["roles"] == ["VERIFIER"]


def test_register_normalizes_email_and_duplicate_is_409(client: TestClient) -> None:
    assert _register(client, email="  Mixed@Example.COM ").json()["email"] == "mixed@example.com"
    r = _register(client, email="mixed@example.com")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


@pytest.mark.parametrize(
    "over",
    [{"email": "not-an-email"}, {"password": "pw-7chr"}, {"full_name": ""}],
)
def test_register_validation_errors_do_not_echo_input(
    client: TestClient, over: dict[str, str]
) -> None:
    r = _register(client, **over)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    for value in over.values():
        if value:
            assert value not in r.text


def test_register_overlong_password_is_422(client: TestClient) -> None:
    r = _register(client, password="p" * 73)
    assert r.status_code == 422


def test_prod_register_requires_admin(
    prod_client: TestClient,
) -> None:
    assert _register(prod_client).status_code == 401
    verifier = _seed(prod_client, "v@example.com", ["VERIFIER"])
    r = prod_client.post(
        f"{PREFIX}/auth/register",
        json={"email": "n@example.com", "password": PASSWORD, "full_name": "N"},
        headers=_bearer(verifier),
    )
    assert r.status_code == 403
    admin = _seed(prod_client, "a@example.com", ["ADMIN"])
    r = prod_client.post(
        f"{PREFIX}/auth/register",
        json={"email": "n@example.com", "password": PASSWORD, "full_name": "N"},
        headers=_bearer(admin),
    )
    assert r.status_code == 201


# --- login ------------------------------------------------------------------


def test_login_returns_token_with_claims(client: TestClient) -> None:
    user = _seed(client, "issuer@example.com", ["ISSUER"])
    r = client.post(
        f"{PREFIX}/auth/login", json={"email": "Issuer@Example.com", "password": PASSWORD}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["id"] == user.id
    assert "password_hash" not in body["user"]
    claims = decode_access_token(body["access_token"], _settings())
    assert claims.sub == user.id
    assert claims.roles == ["ISSUER"]


def test_login_failures_are_indistinguishable(client: TestClient) -> None:
    _seed(client, "issuer@example.com", ["ISSUER"])
    _seed(client, "off@example.com", ["ISSUER"], active=False)
    responses = [
        client.post(f"{PREFIX}/auth/login", json={"email": e, "password": p})
        for e, p in [
            ("issuer@example.com", "wrong password"),
            ("nobody@example.com", PASSWORD),
            ("off@example.com", PASSWORD),
        ]
    ]
    assert {r.status_code for r in responses} == {401}
    assert len({r.text for r in responses}) == 1
    assert responses[0].json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("known_email", [True, False])
def test_login_always_does_one_real_bcrypt_verify(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, known_email: bool
) -> None:
    _seed(client, "issuer@example.com", ["ISSUER"])
    targets: list[str] = []
    real = auth_service.verify_password

    def spy(password: str, password_hash: str) -> bool:
        targets.append(password_hash)
        return real(password, password_hash)

    monkeypatch.setattr(auth_service, "verify_password", spy)
    email = "issuer@example.com" if known_email else "nobody@example.com"
    r = client.post(f"{PREFIX}/auth/login", json={"email": email, "password": "wrong password"})
    assert r.status_code == 401
    assert len(targets) == 1
    assert targets[0].startswith("$2b$") and len(targets[0]) == 60


# --- me ---------------------------------------------------------------------


def test_me_returns_current_user(client: TestClient) -> None:
    user = _seed(client, "approver@example.com", ["APPROVER"])
    r = client.get(f"{PREFIX}/auth/me", headers=_bearer(user))
    assert r.status_code == 200
    assert r.json()["id"] == user.id
    assert "password_hash" not in r.json()


def test_me_without_token_is_401(client: TestClient) -> None:
    r = client.get(f"{PREFIX}/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_rejects_bad_tokens(client: TestClient) -> None:
    user = _seed(client, "approver@example.com", ["APPROVER"])
    good = _bearer(user)["Authorization"]
    expired = _bearer(user, now=dt.datetime.now(dt.UTC) - dt.timedelta(days=1))["Authorization"]
    cases = {
        "garbage": "Bearer not.a.jwt",
        "expired": expired,
        "tampered": good[:-2] + ("aa" if not good.endswith("aa") else "bb"),
        "wrong scheme": good.replace("Bearer", "Basic"),
    }
    for name, header in cases.items():
        r = client.get(f"{PREFIX}/auth/me", headers={"Authorization": header})
        assert r.status_code == 401, name


def test_me_token_for_deleted_or_inactive_user_is_401(client: TestClient) -> None:
    ghost = User(email="g@example.com", full_name="G", password_hash="x", roles=["ISSUER"])
    assert client.get(f"{PREFIX}/auth/me", headers=_bearer(ghost)).status_code == 401
    off = _seed(client, "off@example.com", ["ISSUER"], active=False)
    assert client.get(f"{PREFIX}/auth/me", headers=_bearer(off)).status_code == 401


def test_roles_come_from_db_not_token_claim(client: TestClient) -> None:
    user = _seed(client, "v@example.com", ["VERIFIER"])
    forged = create_access_token(user.id, ["ADMIN"], _settings())
    r = client.get("/_guard", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 403


# --- role guard -------------------------------------------------------------


def test_guard_allows_any_listed_role(client: TestClient) -> None:
    for i, role in enumerate(["ISSUER", "APPROVER"]):
        user = _seed(client, f"u{i}@example.com", [role])  # type: ignore[list-item]
        assert client.get("/_guard", headers=_bearer(user)).status_code == 200


def test_guard_403_for_other_roles_and_401_when_anonymous(client: TestClient) -> None:
    user = _seed(client, "v@example.com", ["VERIFIER", "ADMIN"])
    r = client.get("/_guard", headers=_bearer(user))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    assert client.get("/_guard").status_code == 401


# --- PATCH /users/{id}/roles -------------------------------------------------


def _patch(client: TestClient, user_id: str, roles: Any, headers: dict[str, str]) -> Any:
    return client.patch(f"{PREFIX}/users/{user_id}/roles", json={"roles": roles}, headers=headers)


def test_admin_can_set_roles_and_change_is_immediate(client: TestClient) -> None:
    admin = _seed(client, "admin@example.com", ["ADMIN"])
    target = _seed(client, "t@example.com", ["VERIFIER"])
    assert client.get("/_guard", headers=_bearer(target)).status_code == 403
    r = _patch(client, target.id, ["APPROVER", "ISSUER", "ISSUER"], _bearer(admin))
    assert r.status_code == 200
    assert r.json()["roles"] == ["APPROVER", "ISSUER"]
    assert client.get("/_guard", headers=_bearer(target)).status_code == 200


@pytest.mark.parametrize("role", ["ISSUER", "APPROVER", "VERIFIER"])
def test_non_admin_cannot_set_roles(client: TestClient, role: Role) -> None:
    caller = _seed(client, "c@example.com", [role])
    target = _seed(client, "t@example.com", ["VERIFIER"])
    assert _patch(client, target.id, ["ADMIN"], _bearer(caller)).status_code == 403


def test_set_roles_anonymous_is_401(client: TestClient) -> None:
    assert _patch(client, "x", ["ADMIN"], {}).status_code == 401


def test_set_roles_validation_and_not_found(client: TestClient) -> None:
    admin = _seed(client, "admin@example.com", ["ADMIN"])
    target = _seed(client, "t@example.com", ["VERIFIER"])
    assert _patch(client, target.id, ["SUPERUSER"], _bearer(admin)).status_code == 422
    assert _patch(client, target.id, [], _bearer(admin)).status_code == 422
    r = _patch(client, "no-such-id", ["ISSUER"], _bearer(admin))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


# --- last-admin guard --------------------------------------------------------


def _roles_in_db(client: TestClient, user_id: str) -> list[str]:
    repo = UserRepository(client.app.state.db)  # type: ignore[attr-defined]
    user = client.portal.call(repo.get, user_id)  # type: ignore[union-attr]
    assert user is not None
    return list(user.roles)


def test_sole_admin_cannot_remove_own_admin_role(client: TestClient) -> None:
    admin = _seed(client, "admin@example.com", ["ADMIN"])
    r = _patch(client, admin.id, ["ISSUER"], _bearer(admin))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"
    assert _roles_in_db(client, admin.id) == ["ADMIN"]


def test_admin_can_be_demoted_when_another_active_admin_exists(client: TestClient) -> None:
    a1 = _seed(client, "a1@example.com", ["ADMIN"])
    a2 = _seed(client, "a2@example.com", ["ADMIN"])
    r = _patch(client, a2.id, ["VERIFIER"], _bearer(a1))
    assert r.status_code == 200
    assert _roles_in_db(client, a2.id) == ["VERIFIER"]
    # a1 is now the sole admin and is protected.
    assert _patch(client, a1.id, ["VERIFIER"], _bearer(a1)).status_code == 409


def test_inactive_admin_does_not_count_as_remaining_admin(client: TestClient) -> None:
    admin = _seed(client, "admin@example.com", ["ADMIN"])
    _seed(client, "off@example.com", ["ADMIN"], active=False)
    assert _patch(client, admin.id, ["ISSUER"], _bearer(admin)).status_code == 409


def test_sole_admin_can_gain_roles_while_keeping_admin(client: TestClient) -> None:
    admin = _seed(client, "admin@example.com", ["ADMIN"])
    r = _patch(client, admin.id, ["ADMIN", "ISSUER"], _bearer(admin))
    assert r.status_code == 200
    assert r.json()["roles"] == ["ADMIN", "ISSUER"]


def test_guard_does_not_affect_non_admin_targets(client: TestClient) -> None:
    admin = _seed(client, "admin@example.com", ["ADMIN"])
    target = _seed(client, "t@example.com", ["ISSUER"])
    assert _patch(client, target.id, ["VERIFIER"], _bearer(admin)).status_code == 200
