"""Security response headers and early request-size rejection (pure ASGI middleware)."""

import json
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.security.ratelimit import route_path

# Multipart framing plus the non-file form fields; the route still enforces the exact file cap.
BODY_SLACK_BYTES = 64 * 1024


class SecurityHeadersMiddleware:
    """Adds nosniff / frame / referrer headers to every response. The API-only CSP is limited
    to `api_prefix` so the Swagger UI at /docs (CDN scripts) keeps working; `/auth/*` responses
    carry tokens, so they are `no-store`. Handler-set headers are never overridden."""

    def __init__(self, app: ASGIApp, api_prefix: str) -> None:
        self.app = app
        self._api = api_prefix.rstrip("/") + "/"
        self._auth = self._api + "auth/"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = route_path(scope)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra: dict[bytes, bytes] = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                }
                if path.startswith(self._api):
                    extra[b"content-security-policy"] = (
                        b"default-src 'none'; frame-ancestors 'none'"
                    )
                if path.startswith(self._auth):
                    extra[b"cache-control"] = b"no-store"
                headers.extend((k, v) for k, v in extra.items() if k not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Rejects a request whose declared Content-Length exceeds the upload cap (plus form
    overhead) before the body is read or spooled to disk. Chunked bodies without a length are
    still capped by the routes' `read(max + 1)`."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            raw: Any = dict(scope.get("headers", [])).get(b"content-length")
            if raw is not None and raw.isdigit() and int(raw) > self._max + BODY_SLACK_BYTES:
                body = json.dumps(
                    {
                        "error": {
                            "code": "FILE_TOO_LARGE",
                            "message": "Request body exceeds the upload limit",
                            "details": {"max_bytes": self._max},
                        }
                    }
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
