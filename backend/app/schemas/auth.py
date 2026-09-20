"""Request/response DTOs for auth and user routes (04_API_SPEC Auth)."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.user import Role, User

Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
]


class RegisterIn(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]
    password: str = Field(min_length=1, max_length=256)


class RolesIn(BaseModel):
    roles: list[Role] = Field(min_length=1)


class UserOut(BaseModel):
    """Public user shape: never carries `password_hash`."""

    id: str
    email: str
    full_name: str
    roles: list[Role]
    is_active: bool
    created_at: dt.datetime

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut
