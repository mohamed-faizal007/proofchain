"""/documents routes (04_API_SPEC Documents & revisions)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.config import Settings
from app.deps import (
    get_app_settings,
    get_current_user,
    get_document_service,
    get_query_service,
    require_roles,
)
from app.models.document import DocType
from app.models.revision import RevisionStatus
from app.models.user import User
from app.schemas.documents import DocumentOut, RegisterResponse, RevisionOut
from app.schemas.queries import DocumentDetailOut, DocumentListOut, ProvenanceOut
from app.services.documents import DocumentService
from app.services.queries import QueryService

router = APIRouter(prefix="/documents", tags=["documents"])
_issuer = require_roles("ISSUER")
MAX_PAGE_SIZE = 100


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


@router.get("", response_model=DocumentListOut)
async def list_documents(
    q: Annotated[str | None, Query(max_length=200)] = None,
    doc_type: DocType | None = None,
    status: RevisionStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    _: User = Depends(get_current_user),
    queries: QueryService = Depends(get_query_service),
) -> DocumentListOut:
    result = await queries.list_documents(
        q=q, doc_type=doc_type, status=status, page=page, page_size=page_size
    )
    return DocumentListOut.from_page(result)


@router.get("/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    document_id: str,
    _: User = Depends(get_current_user),
    queries: QueryService = Depends(get_query_service),
) -> DocumentDetailOut:
    document, latest = await queries.get_document(document_id)
    return DocumentDetailOut(
        document=DocumentOut.from_document(document),
        latest_approved_revision=RevisionOut.from_revision(latest) if latest else None,
    )


@router.get("/{document_id}/revisions", response_model=list[RevisionOut])
async def list_revisions(
    document_id: str,
    _: User = Depends(get_current_user),
    queries: QueryService = Depends(get_query_service),
) -> list[RevisionOut]:
    return [RevisionOut.from_revision(r) for r in await queries.list_revisions(document_id)]


@router.get("/{document_id}/provenance", response_model=ProvenanceOut)
async def get_provenance(
    document_id: str,
    _: User = Depends(get_current_user),
    queries: QueryService = Depends(get_query_service),
) -> ProvenanceOut:
    return ProvenanceOut.from_provenance(await queries.provenance(document_id))
