"""/documents routes (04_API_SPEC Documents & revisions)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.config import Settings
from app.deps import get_app_settings, get_document_service, require_roles
from app.models.document import DocType
from app.models.user import User
from app.schemas.documents import DocumentOut, RegisterResponse, RevisionOut
from app.services.documents import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])
_issuer = require_roles("ISSUER")


@router.post("", status_code=201, response_model=RegisterResponse)
async def register_document(
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    doc_type: Annotated[DocType, Form()],
    change_note: Annotated[str | None, Form()] = None,
    user: User = Depends(_issuer),
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_app_settings),
) -> RegisterResponse:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    document, revision = await service.register(
        user,
        data=data,
        filename=file.filename,
        title=title,
        doc_type=doc_type,
        change_note=change_note,
    )
    return RegisterResponse(
        document=DocumentOut.from_document(document),
        revision=RevisionOut.from_revision(revision),
    )


@router.post("/{document_id}/revisions", status_code=201, response_model=RegisterResponse)
async def submit_revision(
    document_id: str,
    file: Annotated[UploadFile, File()],
    change_note: Annotated[str, Form()],
    user: User = Depends(_issuer),
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_app_settings),
) -> RegisterResponse:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    document, revision = await service.submit_revision(
        user,
        document_id,
        data=data,
        filename=file.filename,
        change_note=change_note,
    )
    return RegisterResponse(
        document=DocumentOut.from_document(document),
        revision=RevisionOut.from_revision(revision),
    )
