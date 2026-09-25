from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.chain import FakeRegistryClient, RegistryClient
from app.config import Settings
from app.deps import get_registry_client
from app.main import create_app


def _app(**kw: object) -> FastAPI:
    app = create_app(Settings(_env_file=None, app_env="test"), db=object(), storage=object(), **kw)  # type: ignore[arg-type]

    @app.get("/_chain")
    async def chain(c: RegistryClient = Depends(get_registry_client)) -> dict[str, bool]:
        return {"ok": (await c.health()).ok}

    return app


def test_injected_client_is_served() -> None:
    # db=object() makes ensure_indexes fail, so skip the lifespan and set state directly.
    app = _app(registry_client=FakeRegistryClient())
    app.state.registry_client = FakeRegistryClient()
    assert TestClient(app).get("/_chain").json() == {"ok": True}


def test_unconfigured_client_is_503_chain_unavailable() -> None:
    app = _app()
    app.state.registry_client = None
    r = TestClient(app).get("/_chain")
    assert r.status_code == 503 and r.json()["error"]["code"] == "CHAIN_UNAVAILABLE"
