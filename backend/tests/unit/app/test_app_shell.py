import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import NoContentChangeError, NotFoundError
from app.main import create_app

PREFIX = "/api/v1"


def _make_app() -> FastAPI:
    app = create_app(Settings(app_env="test"))
    router = APIRouter()

    @router.get("/_boom_domain")
    async def boom_domain() -> None:
        raise NotFoundError("Document not found", details={"document_id": "abc"})

    @router.get("/_boom_no_change")
    async def boom_no_change() -> None:
        raise NoContentChangeError("Revision text is identical to its parent")

    @router.get("/_boom_unhandled")
    async def boom_unhandled() -> None:
        raise RuntimeError("secret internal detail")

    @router.get("/_needs_int")
    async def needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    app.include_router(router, prefix=PREFIX)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


def test_health_ok(client: TestClient) -> None:
    r = client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_docs_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    generated = client.get(f"{PREFIX}/health").headers["x-request-id"]
    assert len(generated) >= 32
    echoed = client.get(f"{PREFIX}/health", headers={"X-Request-ID": "req-123"})
    assert echoed.headers["x-request-id"] == "req-123"


def test_domain_error_envelope(client: TestClient) -> None:
    r = client.get(f"{PREFIX}/_boom_domain")
    assert r.status_code == 404
    assert r.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Document not found",
            "details": {"document_id": "abc"},
        }
    }
    assert "x-request-id" in r.headers


def test_no_content_change_is_422(client: TestClient) -> None:
    # 04_API_SPEC.md: 422 if text_root equals parent (no change)
    r = client.get(f"{PREFIX}/_boom_no_change")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "NO_CONTENT_CHANGE"


def test_validation_error_envelope(client: TestClient) -> None:
    r = client.get(f"{PREFIX}/_needs_int", params={"n": "x"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], dict)
    assert body["error"]["details"]["errors"]


def test_unhandled_error_envelope(client: TestClient) -> None:
    r = client.get(f"{PREFIX}/_boom_unhandled")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in r.text
    assert "x-request-id" in r.headers


def test_unknown_route_envelope(client: TestClient) -> None:
    r = client.get(f"{PREFIX}/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_cors_allows_configured_origin() -> None:
    app = create_app(Settings(app_env="test", cors_origins="http://a.test,http://b.test"))
    c = TestClient(app)
    r = c.get(f"{PREFIX}/health", headers={"Origin": "http://b.test"})
    assert r.headers["access-control-allow-origin"] == "http://b.test"
    r = c.get(f"{PREFIX}/health", headers={"Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in r.headers


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.api_prefix == "/api/v1"
    assert s.max_upload_mb == 25
    assert s.public_verify is True
    assert s.cors_origin_list == ["http://localhost:5173"]


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "5")
    monkeypatch.setenv("APP_ENV", "test")
    s = Settings(_env_file=None)
    assert s.max_upload_mb == 5
    assert s.app_env == "test"
