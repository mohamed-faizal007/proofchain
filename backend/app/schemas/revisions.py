"""Request DTOs for revision review and revocation (04_API_SPEC Documents & revisions)."""

from pydantic import BaseModel


class ApproveRequest(BaseModel):
    comment: str | None = None


class RejectRequest(BaseModel):
    comment: str | None = None  # required; checked in the service so blank is 422 too


class RevokeRequest(BaseModel):
    reason: str | None = None  # required; checked in the service so blank is 422 too
