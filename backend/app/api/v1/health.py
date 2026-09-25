from fastapi import APIRouter, Request

from app.services.health import DEFAULT_TIMEOUT_SECONDS, HealthReport, check_health

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request) -> HealthReport:
    # Always HTTP 200; degraded state is reported in the body (503 decision deferred to P10).
    state = request.app.state
    return await check_health(
        getattr(state, "db", None),
        getattr(state, "storage", None),
        getattr(state, "registry_client", None),
        timeout=getattr(state, "health_timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
    )
