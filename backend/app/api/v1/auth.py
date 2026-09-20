"""/auth routes. Thin: validation and wiring only, logic lives in AuthService."""

from fastapi import APIRouter, Depends

from app.deps import get_auth_service, get_current_user, require_register_access
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=201,
    response_model=UserOut,
    dependencies=[Depends(require_register_access)],
)
async def register(body: RegisterIn, service: AuthService = Depends(get_auth_service)) -> UserOut:
    user = await service.register(body.email, body.password, body.full_name)
    return UserOut.from_user(user)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, service: AuthService = Depends(get_auth_service)) -> TokenOut:
    token, user = await service.login(body.email, body.password)
    return TokenOut(access_token=token, user=UserOut.from_user(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_user(user)
