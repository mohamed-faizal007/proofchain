"""GET /chain/status (04_API_SPEC, System): authenticated, no secrets, outage is a body flag."""

from typing import Any

from app.chain import ChainHealth, FakeRegistryClient
from tests.unit.app.docs_env import PREFIX, Env

URL = f"{PREFIX}/chain/status"
SECRET = "super-secret-rpc-detail"


class _Stub:
    async def aclose(self) -> None:  # the app lifespan closes the client on teardown
        return None


class _Down(_Stub):
    async def health(self) -> ChainHealth:
        return ChainHealth(ok=False)


class _Raises(_Stub):
    async def health(self) -> ChainHealth:
        raise RuntimeError(SECRET)


class _Real(_Stub):
    async def health(self) -> ChainHealth:
        return ChainHealth(
            ok=True, chain_id=31337, block_number=42, registry_address="0x" + "ab" * 20
        )


def _use(env: Env, client: Any) -> None:
    env.client.app.state.registry_client = client  # type: ignore[attr-defined]


def test_requires_authentication(env: Env) -> None:
    r = env.client.get(URL)
    assert r.status_code == 401


def test_any_authenticated_role_can_read(env: Env) -> None:
    _use(env, _Real())
    headers = env.auth(env.user(["VERIFIER"], "verifier@example.com"))
    assert env.client.get(URL, headers=headers).status_code == 200


def test_reports_chain_id_contract_and_block(env: Env) -> None:
    _use(env, _Real())
    r = env.client.get(URL, headers=env.issuer())
    assert r.status_code == 200
    assert r.json() == {
        "configured": True,
        "healthy": True,
        "chain_id": 31337,
        "contract": "0x" + "ab" * 20,
        "latest_block": 42,
    }


def test_fake_client_has_no_contract_address(env: Env) -> None:
    _use(env, FakeRegistryClient())
    body = env.client.get(URL, headers=env.issuer()).json()
    assert (body["configured"], body["healthy"]) == (True, True)
    assert body["contract"] is None
    assert body["chain_id"] == 31337


def test_not_configured_when_no_registry_client(env: Env) -> None:
    _use(env, None)
    body = env.client.get(URL, headers=env.issuer()).json()
    assert body == {
        "configured": False,
        "healthy": False,
        "chain_id": None,
        "contract": None,
        "latest_block": None,
    }


def test_unhealthy_chain_is_reported_in_the_body_with_http_200(env: Env) -> None:
    _use(env, _Down())
    r = env.client.get(URL, headers=env.issuer())
    assert r.status_code == 200
    assert (r.json()["configured"], r.json()["healthy"]) == (True, False)


def test_probe_exception_is_unhealthy_and_never_leaks_text(env: Env) -> None:
    _use(env, _Raises())
    r = env.client.get(URL, headers=env.issuer())
    assert r.status_code == 200
    assert r.json()["healthy"] is False
    assert SECRET not in r.text


def test_response_has_only_the_documented_keys(env: Env) -> None:
    _use(env, _Real())
    body = env.client.get(URL, headers=env.issuer()).json()
    assert set(body) == {"configured", "healthy", "chain_id", "contract", "latest_block"}
