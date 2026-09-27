"""/verify and /verifications routes (04_API_SPEC Verification)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.config import Settings
from app.deps import (
    get_app_settings,
    get_current_user,
    get_optional_user,
    get_verification_service,
)
from app.errors import UnauthorizedError
from app.models.user import User
from app.schemas.verification import VerificationListOut, VerificationReportOut
from app.services.verification import VerificationService

router = APIRouter(tags=["verification"])
MAX_PAGE_SIZE = 100


@router.post("/verify", response_model=VerificationReportOut)
async def verify(
    file: Annotated[UploadFile, File()],
    document_id: Annotated[str | None, Form(max_length=64)] = None,
    include_nlp: Annotated[bool, Form()] = True,
    user: User | None = Depends(get_optional_user),
    service: VerificationService = Depends(get_verification_service),
    settings: Settings = Depends(get_app_settings),
) -> VerificationReportOut:
    """Public when `PUBLIC_VERIFY=true`, otherwise any authenticated user."""
    if user is None and not settings.public_verify:
        raise UnauthorizedError("Authentication required")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    record = await service.verify(
        user,
        data=data,
        filename=file.filename,
        document_id=document_id or None,
        include_nlp=include_nlp,
    )
    return VerificationReportOut.from_verification(record)


@router.get("/verifications", response_model=VerificationListOut)
async def list_verifications(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    user: User = Depends(get_current_user),
    service: VerificationService = Depends(get_verification_service),
) -> VerificationListOut:
    items, total = await service.history(user, page, page_size)
    return VerificationListOut.build(items, page, page_size, total)


@router.get("/verifications/{verification_id}", response_model=VerificationReportOut)
async def get_verification(
    verification_id: str,
    user: User = Depends(get_current_user),
    service: VerificationService = Depends(get_verification_service),
) -> VerificationReportOut:
    return VerificationReportOut.from_verification(await service.get(user, verification_id))
