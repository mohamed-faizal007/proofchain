from fastapi import APIRouter, Depends, Request

from app.deps import get_current_user
from app.models.user import User
from app.services.chain_status import ChainStatus, get_chain_status
from app.services.health import DEFAULT_TIMEOUT_SECONDS

router = APIRouter(tags=["system"])


@router.get("/chain/status")
async def chain_status(
    request: Request,
    _user: User = Depends(get_current_user),
) -> ChainStatus:
    # Always HTTP 200; an unreachable chain is reported as healthy=false (like /health).
    state = request.app.state
    return await get_chain_status(
        getattr(state, "registry_client", None),
        timeout=getattr(state, "health_timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
    )
