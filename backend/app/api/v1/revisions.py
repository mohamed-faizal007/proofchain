"""/revisions routes (04_API_SPEC Documents & revisions): read, review, anchor, revoke."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Response

from app.deps import (
    get_anchor_service,
    get_current_user,
    get_query_service,
    get_review_service,
    get_revocation_service,
    require_roles,
)
from app.models.user import User
from app.schemas.documents import RevisionOut
from app.schemas.queries import FileUrlOut, TreeOut
from app.schemas.revisions import ApproveRequest, RejectRequest, RevokeRequest
from app.services.anchoring import AnchorService, run_anchor_job
from app.services.queries import QueryService
from app.services.reviews import ReviewService
from app.services.revocation import RevocationService

router = APIRouter(prefix="/revisions", tags=["revisions"])
_approver = require_roles("APPROVER")
_admin = require_roles("ADMIN")


@router.get("/{revision_id}", response_model=RevisionOut)
async def get_revision(
    revision_id: str,
    _: User = Depends(get_current_user),
    queries: QueryService = Depends(get_query_service),
) -> RevisionOut:
    return RevisionOut.from_revision(await queries.get_revision(revision_id))


@router.get("/{revision_id}/tree", response_model=TreeOut)
async def get_tree(
    revision_id: str,
    _: User = Depends(get_current_user),
    queries: QueryService = Depends(get_query_service),
) -> TreeOut:
    return TreeOut.from_tree(await queries.get_tree(revision_id))


@router.get("/{revision_id}/file", response_model=FileUrlOut)
async def get_file_url(
    revision_id: str,
    _: User = Depends(get_current_user),
    queries: QueryService = Depends(get_query_service),
) -> FileUrlOut:
    url, expires_in = await queries.presign_file(revision_id)
    return FileUrlOut(url=url, expires_in=expires_in)


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


@router.post("/{revision_id}/revoke", response_model=RevisionOut)
async def revoke_revision(
    revision_id: str,
    body: Annotated[RevokeRequest | None, Body()] = None,
    user: User = Depends(_approver),
    service: RevocationService = Depends(get_revocation_service),
) -> RevisionOut:
    """Synchronous: the on-chain revoke is sent (and confirmed) before the response."""
    reason = body.reason if body else None
    return RevisionOut.from_revision(await service.revoke(user, revision_id, reason))
