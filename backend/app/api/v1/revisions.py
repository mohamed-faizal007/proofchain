"""/revisions routes (04_API_SPEC Documents & revisions): maker-checker review."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Response

from app.deps import get_anchor_service, get_review_service, require_roles
from app.models.user import User
from app.schemas.documents import RevisionOut
from app.schemas.revisions import ApproveRequest, RejectRequest
from app.services.anchoring import AnchorService, run_anchor_job
from app.services.reviews import ReviewService

router = APIRouter(prefix="/revisions", tags=["revisions"])
_approver = require_roles("APPROVER")
_admin = require_roles("ADMIN")


@router.post("/{revision_id}/approve", status_code=202, response_model=RevisionOut)
async def approve_revision(
    revision_id: str,
    background: BackgroundTasks,
    body: Annotated[ApproveRequest | None, Body()] = None,
    user: User = Depends(_approver),
    service: ReviewService = Depends(get_review_service),
    anchoring: AnchorService = Depends(get_anchor_service),
) -> RevisionOut:
    # 202: anchoring runs after the response (ADR-012).
    comment = body.comment if body else None
    revision = await service.approve(user, revision_id, comment)
    background.add_task(run_anchor_job, anchoring, revision_id, "approve")
    return RevisionOut.from_revision(revision)


@router.post("/{revision_id}/reject", response_model=RevisionOut)
async def reject_revision(
    revision_id: str,
    body: Annotated[RejectRequest | None, Body()] = None,
    user: User = Depends(_approver),
    service: ReviewService = Depends(get_review_service),
) -> RevisionOut:
    comment = body.comment if body else None
    return RevisionOut.from_revision(await service.reject(user, revision_id, comment))


@router.post("/{revision_id}/retry-anchor", status_code=200, response_model=RevisionOut)
async def retry_anchor(
    revision_id: str,
    response: Response,
    background: BackgroundTasks,
    user: User = Depends(_admin),
    anchoring: AnchorService = Depends(get_anchor_service),
) -> RevisionOut:
    """FAILED -> 202 and a new attempt in the background; ANCHORED -> 200, no-op."""
    revision, scheduled = await anchoring.request_retry(revision_id)
    if scheduled:
        response.status_code = 202
        background.add_task(run_anchor_job, anchoring, revision_id, "retry")
    return RevisionOut.from_revision(revision)
