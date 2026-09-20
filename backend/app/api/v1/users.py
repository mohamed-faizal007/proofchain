"""/users routes (ADMIN only)."""

from fastapi import APIRouter, Depends

from app.deps import get_auth_service, require_roles
from app.schemas.auth import RolesIn, UserOut
from app.services.auth import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.patch(
    "/{user_id}/roles",
    response_model=UserOut,
    dependencies=[Depends(require_roles("ADMIN"))],
)
async def set_roles(
    user_id: str, body: RolesIn, service: AuthService = Depends(get_auth_service)
) -> UserOut:
    return UserOut.from_user(await service.set_roles(user_id, body.roles))
