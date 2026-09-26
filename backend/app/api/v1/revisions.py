"""/revisions routes (04_API_SPEC Documents & revisions): maker-checker review."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.deps import get_review_service, require_roles
from app.models.user import User
from app.schemas.documents import RevisionOut
from app.schemas.revisions import ApproveRequest, RejectRequest
from app.services.reviews import ReviewService

router = APIRouter(prefix="/revisions", tags=["revisions"])
_approver = require_roles("APPROVER")


@router.post("/{revision_id}/approve", status_code=202, response_model=RevisionOut)
async def approve_revision(
    revision_id: str,
    body: Annotated[ApproveRequest | None, Body()] = None,
    user: User = Depends(_approver),
    service: ReviewService = Depends(get_review_service),
) -> RevisionOut:
    # 202: anchoring runs in the background (ADR-012, started in P5-04).
    comment = body.comment if body else None
    return RevisionOut.from_revision(await service.approve(user, revision_id, comment))


@router.post("/{revision_id}/reject", response_model=RevisionOut)
async def reject_revision(
    revision_id: str,
    body: Annotated[RejectRequest | None, Body()] = None,
    user: User = Depends(_approver),
    service: ReviewService = Depends(get_review_service),
) -> RevisionOut:
    comment = body.comment if body else None
    return RevisionOut.from_revision(await service.reject(user, revision_id, comment))
