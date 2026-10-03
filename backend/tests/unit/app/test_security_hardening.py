"""P10-01: security headers, per-IP rate limits, early body-size rejection, upload validation."""

import asyncio
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app.config import Settings
from app.main import _http_error_handler, create_app
from app.security.ratelimit import SlidingWindowLimiter
from tests.unit.app.docs_env import PDFS, PREFIX, Env, settings

LOGIN = f"{PREFIX}/auth/login"
VERIFY = f"{PREFIX}/verify"
BAD_LOGIN = {"email": "nobody@example.com", "password": "wrong-password"}


def _app_client(**overrides: object) -> TestClient:
    s = Settings(_env_file=None, app_env="test", **overrides)  # type: ignore[arg-type]
    return TestClient(create_app(s), raise_server_exceptions=False)


# --- limiter unit ---------------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_limit_then_reports_retry_after() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    assert [lim.hit("a", 3, 60) for _ in range(3)] == [None, None, None]
    clock.now += 10
    retry = lim.hit("a", 3, 60)
    assert retry == 50  # oldest hit (t=1000) leaves the window at t=1060


def test_limiter_window_expires() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    for _ in range(3):
        lim.hit("a", 3, 60)
    assert lim.hit("a", 3, 60) is not None
    clock.now += 61
    assert lim.hit("a", 3, 60) is None


def test_limiter_keys_are_independent() -> None:
    lim = SlidingWindowLimiter(Clock())
    for _ in range(3):
        lim.hit("a", 3, 60)
    assert lim.hit("a", 3, 60) is not None
    assert lim.hit("b", 3, 60) is None


def test_limiter_rejected_hits_do_not_extend_the_block() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    for _ in range(3):
        lim.hit("a", 3, 60)
    for _ in range(50):  # hammering while blocked
        clock.now += 1
        lim.hit("a", 3, 60)
    clock.now = 1061
    assert lim.hit("a", 3, 60) is None


def test_limiter_sweeps_idle_keys() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    for i in range(2000):
        lim.hit(f"ip{i}", 5, 60)
    clock.now += 120
    for i in range(2000, 2000 + 1100):  # crosses the sweep interval
        lim.hit(f"ip{i}", 5, 60)
    assert lim.size() < 1500


# --- routes ---------------------------------------------------------------------------------


def test_login_rate_limited_after_n_attempts_returns_429_envelope_with_retry_after() -> None:
    client = _app_client(login_rate_limit_per_min=3)
    codes = [client.post(LOGIN, json=BAD_LOGIN).status_code for _ in range(3)]
    assert 429 not in codes
    r = client.post(LOGIN, json=BAD_LOGIN)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert r.json()["error"]["details"] == {"retry_after_seconds": int(r.headers["retry-after"])}
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert r.headers["x-request-id"]  # still inside the request-id middleware


def test_verify_rate_limited() -> None:
    client = _app_client(verify_rate_limit_per_min=2)
    pdf = (PDFS / "not_a_pdf.pdf").read_bytes()
    files = {"file": ("x.pdf", pdf, "application/pdf")}
    first = [client.post(VERIFY, files=files).status_code for _ in range(2)]
    assert 429 not in first
    assert client.post(VERIFY, files=files).status_code == 429


def test_login_and_verify_use_separate_buckets() -> None:
    client = _app_client(login_rate_limit_per_min=1, verify_rate_limit_per_min=1)
    client.post(LOGIN, json=BAD_LOGIN)
    assert client.post(LOGIN, json=BAD_LOGIN).status_code == 429
    files = {"file": ("x.pdf", b"nope", "application/pdf")}
    assert client.post(VERIFY, files=files).status_code != 429


def test_other_routes_are_not_limited() -> None:
    client = _app_client(login_rate_limit_per_min=1, verify_rate_limit_per_min=1)
    assert all(client.get(f"{PREFIX}/health").status_code == 200 for _ in range(30))
    # only POST is limited: a GET on the same path is not counted
    assert all(client.get(LOGIN).status_code == 405 for _ in range(5))


def test_rate_limit_is_per_client_address() -> None:
    client = _app_client(login_rate_limit_per_min=1)
    client.post(LOGIN, json=BAD_LOGIN)
    assert client.post(LOGIN, json=BAD_LOGIN).status_code == 429
    other = TestClient(client.app, raise_server_exceptions=False, client=("203.0.113.9", 5000))
    assert other.post(LOGIN, json=BAD_LOGIN).status_code != 429


def test_x_forwarded_for_is_ignored_for_keying() -> None:
    """ADR-022: a spoofable header must not let a client choose its own bucket."""
    client = _app_client(login_rate_limit_per_min=1)
    client.post(LOGIN, json=BAD_LOGIN, headers={"X-Forwarded-For": "1.1.1.1"})
    r = client.post(LOGIN, json=BAD_LOGIN, headers={"X-Forwarded-For": "2.2.2.2"})
    assert r.status_code == 429


def test_rate_limit_can_be_disabled() -> None:
    client = _app_client(login_rate_limit_per_min=0, verify_rate_limit_per_min=0)
    assert all(client.post(LOGIN, json=BAD_LOGIN).status_code != 429 for _ in range(15))


def test_429_carries_cors_headers_so_the_browser_can_read_it() -> None:
    client = _app_client(login_rate_limit_per_min=1)
    origin = {"Origin": "http://localhost:5173"}
    client.post(LOGIN, json=BAD_LOGIN, headers=origin)
    r = client.post(LOGIN, json=BAD_LOGIN, headers=origin)
    assert r.status_code == 429
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- headers --------------------------------------------------------------------------------


def test_security_headers_on_every_response() -> None:
    client = _app_client()
    for r in (
        client.get(f"{PREFIX}/health"),
        client.get(f"{PREFIX}/does-not-exist"),  # error envelope
        client.post(LOGIN, json={"email": "not-an-email"}),  # 422
    ):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_security_headers_on_cors_preflight() -> None:
    client = _app_client()
    r = client.options(
        LOGIN,
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers["x-content-type-options"] == "nosniff"


def test_api_docs_page_is_not_broken_by_the_csp() -> None:
    client = _app_client()
    r = client.get("/docs")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in r.headers


def test_auth_responses_are_not_cacheable() -> None:
    client = _app_client()
    r = client.post(LOGIN, json=BAD_LOGIN)
    assert r.headers["cache-control"] == "no-store"
    assert "cache-control" not in client.get(f"{PREFIX}/health").headers


# --- body size / upload validation ----------------------------------------------------------


def test_oversized_content_length_rejected_before_the_body_is_read() -> None:
    client = _app_client(max_upload_mb=1)
    r = client.post(
        VERIFY, content=b"x" * (3 * 1024 * 1024), headers={"Content-Type": "text/plain"}
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert r.json()["error"]["details"]["max_bytes"] == 1024 * 1024


def test_body_at_the_limit_still_reaches_the_route_check(env: Env) -> None:
    r = env.post_pdf(env.issuer(), b"%PDF-1.7" + b"0" * (1024 * 1024 - 8))
    assert r.status_code == 422  # passes the size gate, fails PDF parsing


def test_http_413_maps_to_file_too_large_code() -> None:
    resp = asyncio.run(_http_error_handler(None, HTTPException(413, "too big")))  # type: ignore[arg-type]
    assert resp.status_code == 413
    assert b"FILE_TOO_LARGE" in bytes(resp.body)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\n" * 2000 + b"%PDF-1.7\n" + b"x" * 100, id="magic-beyond-1024-bytes"),
        pytest.param((PDFS / "one_page.pdf").read_bytes()[:200], id="truncated"),
        pytest.param(b"<html>%PDF-1.4</html>" + b"<script>x</script>" * 20, id="html-with-magic"),
    ],
)
def test_malformed_uploads_are_invalid_pdf_and_leave_no_trace(
    env_factory: Callable[..., Env], data: bytes
) -> None:
    env = env_factory(settings())
    r = env.post_pdf(env.issuer(), data)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "INVALID_PDF")
    assert env.count("documents") == 0
    assert env.s3_keys() == []


# --- download hardening ---------------------------------------------------------------------


def test_download_forces_pdf_type_attachment_and_nosniff(env: Env) -> None:
    issuer = env.issuer()
    rev_id = env.post_pdf(issuer).json()["revision"]["id"]
    # a hostile stored content type must not be reflected back
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["revisions"].update_one,
        {"_id": rev_id},
        {"$set": {"file.content_type": "text/html"}},
    )
    r = env.client.get(f"{PREFIX}/revisions/{rev_id}/download", headers=issuer)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["x-content-type-options"] == "nosniff"


# --- review follow-ups ----------------------------------------------------------------------


def test_unhandled_500_still_carries_security_headers_cors_and_request_id() -> None:
    from fastapi import APIRouter

    app = create_app(Settings(_env_file=None, app_env="test"))  # type: ignore[arg-type]
    router = APIRouter()

    @router.get("/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    app.include_router(router, prefix=PREFIX)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get(f"{PREFIX}/_boom", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 500
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers["x-request-id"]


def test_rate_limit_applies_when_the_server_puts_root_path_inside_path() -> None:
    """Newer ASGI servers report /x/api/v1/... with root_path=/x; the rules must still match."""
    from app.security.ratelimit import RateLimitMiddleware, Rule

    sent: list[int] = []

    async def inner(scope, receive, send):  # type: ignore[no-untyped-def]
        sent.append(200)

    async def send(message):  # type: ignore[no-untyped-def]
        if message["type"] == "http.response.start":
            sent.append(message["status"])

    mw = RateLimitMiddleware(inner, [Rule("POST", "/api/v1/auth/login", "login", 1)])
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/x/api/v1/auth/login",
        "root_path": "/x",
        "client": ("198.51.100.7", 1),
    }
    asyncio.run(mw(scope, None, send))  # type: ignore[arg-type]
    asyncio.run(mw(scope, None, send))  # type: ignore[arg-type]
    assert sent == [200, 429]


def test_rate_limit_ignores_websocket_scopes() -> None:
    from app.security.ratelimit import RateLimitMiddleware, Rule

    seen: list[str] = []

    async def inner(scope, receive, send):  # type: ignore[no-untyped-def]
        seen.append(scope["type"])

    mw = RateLimitMiddleware(inner, [Rule("POST", "/p", "p", 1)])
    asyncio.run(mw({"type": "websocket", "path": "/p"}, None, None))  # type: ignore[arg-type]
    assert seen == ["websocket"]


def test_download_filename_with_quotes_and_non_ascii_cannot_break_the_header(env: Env) -> None:
    issuer = env.issuer()
    rev_id = env.post_pdf(issuer).json()["revision"]["id"]
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["revisions"].update_one,
        {"_id": rev_id},
        {"$set": {"file.original_filename": 'a"b\u00e9\r\nX-Evil: 1.pdf'}},
    )
    r = env.client.get(f"{PREFIX}/revisions/{rev_id}/download", headers=issuer)
    assert r.status_code == 200
    assert "x-evil" not in r.headers
    assert r.headers["content-disposition"].count('"') == 2
