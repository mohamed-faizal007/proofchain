"""Dependency health checks for GET /health (docs/04_API_SPEC.md, System)."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel

from proofchain_core import CANON_VERSION

DEFAULT_TIMEOUT_SECONDS = 2.0

Probe = Literal["ok", "down"]


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    mongo: Probe
    s3: Probe
    chain: Literal["not_configured"]
    nlp: Literal["not_configured"]
    canon_version: int


async def _probe(check: Callable[[], Awaitable[bool]] | None, timeout: float) -> Probe:
    """Run one check; any failure or timeout is 'down'. Never surfaces exception text."""
    if check is None:
        return "down"
    try:
        ok = await asyncio.wait_for(check(), timeout)
    except Exception:
        return "down"
    return "ok" if ok else "down"


async def check_health(
    db: Any | None, storage: Any | None, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> HealthReport:
    async def ping_mongo() -> bool:
        assert db is not None
        await db.command("ping")
        return True

    mongo, s3 = await asyncio.gather(
        _probe(ping_mongo if db is not None else None, timeout),
        _probe(storage.head_bucket if storage is not None else None, timeout),
    )
    return HealthReport(
        status="ok" if mongo == "ok" and s3 == "ok" else "degraded",
        mongo=mongo,
        s3=s3,
        chain="not_configured",  # P4 (chain client)
        nlp="not_configured",  # P7 (NLP pipeline)
        canon_version=CANON_VERSION,
    )
