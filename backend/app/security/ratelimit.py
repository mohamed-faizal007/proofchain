"""In-process sliding-window rate limiter and the ASGI middleware that applies it (ADR-022)."""

import json
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from starlette.types import ASGIApp, Receive, Scope, Send

SWEEP_EVERY = 1024  # hits between full sweeps of idle keys


class SlidingWindowLimiter:
    """At most `limit` hits per `window` seconds per key. Rejected hits are not recorded, so
    hammering a blocked key cannot extend its own block. Single process, not shared."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._since_sweep = 0

    def hit(self, key: str, limit: int, window: float) -> int | None:
        """Record a hit. Returns None if allowed, else whole seconds until a slot frees."""
        now = self._clock()
        self._maybe_sweep(now, window)
        q = self._hits.setdefault(key, deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return max(1, math.ceil(q[0] + window - now))
        q.append(now)
        return None

    def size(self) -> int:
        return len(self._hits)

    def _maybe_sweep(self, now: float, window: float) -> None:
        self._since_sweep += 1
        if self._since_sweep < SWEEP_EVERY:
            return
        self._since_sweep = 0
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= now - window]:
            del self._hits[key]


def route_path(scope: Scope) -> str:
    """The request path without the mount prefix, as Starlette routes it: newer ASGI servers
    put `root_path` inside `path`, so matching the raw path would silently skip the rules."""
    path: str = scope.get("path", "")
    root: str = scope.get("root_path", "")
    if root and path.startswith(root.rstrip("/") + "/"):
        return path[len(root.rstrip("/")) :]
    return path


@dataclass(frozen=True)
class Rule:
    method: str
    path: str
    name: str
    limit: int  # per window; <= 0 disables the rule


class RateLimitMiddleware:
    """Per-client-address limits on selected POST routes.

    Keyed by the TCP peer (`scope["client"]`) only: X-Forwarded-For is client-controlled and
    must not pick its own bucket. Behind a reverse proxy every request shares the proxy's
    address, see ADR-022 / PROGRESS (P10-03).
    """

    WINDOW_SECONDS = 60.0

    def __init__(
        self,
        app: ASGIApp,
        rules: list[Rule],
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        self.app = app
        self._rules = {(r.method, r.path): r for r in rules if r.limit > 0}
        self._limiter = limiter or SlidingWindowLimiter()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rule = self._rules.get((scope.get("method", ""), route_path(scope)))
        if rule is None:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = f"{rule.name}:{client[0] if client else 'unknown'}"
        retry = self._limiter.hit(key, rule.limit, self.WINDOW_SECONDS)
        if retry is None:
            await self.app(scope, receive, send)
            return
        body = json.dumps(
            {
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests, retry later",
                    "details": {"retry_after_seconds": retry},
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(retry).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
