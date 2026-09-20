"""JWT access tokens: HS256, claims `sub`, `roles`, `exp` (04_API_SPEC Auth, ADR-014)."""

import datetime as dt
from collections.abc import Sequence

import jwt as pyjwt
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.errors import UnauthorizedError
from app.models.user import Role

ALGORITHM = "HS256"


class TokenClaims(BaseModel):
    sub: str
    roles: list[Role]
    exp: int


def create_access_token(
    user_id: str,
    roles: Sequence[str],
    settings: Settings,
    now: dt.datetime | None = None,
) -> str:
    issued = now or dt.datetime.now(dt.UTC)
    expires = issued + dt.timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "roles": list(roles), "exp": int(expires.timestamp())}
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "roles", "exp"]},
        )
        claims = TokenClaims.model_validate(payload, strict=True)
    except (pyjwt.PyJWTError, ValidationError) as exc:
        raise UnauthorizedError("Invalid or expired token") from exc
    if not claims.sub:
        raise UnauthorizedError("Invalid or expired token")
    return claims


__all__ = ["ALGORITHM", "TokenClaims", "create_access_token", "decode_access_token"]
