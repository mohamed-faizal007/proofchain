"""users collection (03_DATA_MODEL)."""

import datetime as dt
from typing import Literal

from pydantic import Field

from app.models.base import MongoModel, new_id

Role = Literal["ISSUER", "APPROVER", "VERIFIER", "ADMIN"]


class User(MongoModel):
    id: str = Field(default_factory=new_id, alias="_id")
    email: str
    full_name: str
    password_hash: str
    roles: list[Role]
    is_active: bool = True
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
