"""FastAPI app factory: CORS, request-id middleware, error envelope handlers."""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import router as v1_router
from app.config import Settings, get_settings
from app.db import MongoDatabase, create_client, ensure_indexes, get_database
from app.errors import DomainError
from app.logging import configure_logging, request_id_var
from app.storage import S3Storage

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def _envelope(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status_code, content=body)


def _with_request_id(response: Response) -> Response:
    rid = request_id_var.get()
    if rid and REQUEST_ID_HEADER.lower() not in response.headers:
        response.headers[REQUEST_ID_HEADER] = rid
    return response


async def _domain_error_handler(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, DomainError)
    return _with_request_id(_envelope(exc.status_code, exc.code, exc.message, exc.details))


async def _validation_error_handler(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    errors = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    for err in errors:
        err.pop("input", None)  # would echo submitted values, e.g. passwords
    return _with_request_id(
        _envelope(422, "VALIDATION_ERROR", "Request validation failed", {"errors": errors})
    )


async def _http_error_handler(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    codes = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    code = codes.get(exc.status_code, "HTTP_ERROR")
    return _with_request_id(_envelope(exc.status_code, code, str(exc.detail)))


def create_app(
    settings: Settings | None = None,
    db: MongoDatabase | None = None,
    storage: S3Storage | None = None,
) -> FastAPI:
    """Build the app. `db`/`storage` inject test doubles; otherwise the lifespan builds them."""
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = None
        if db is None:
            client = create_client(settings)
            app.state.db = get_database(client, settings)
        else:
            app.state.db = db
        app.state.storage = storage or S3Storage.from_settings(settings)
        try:
            await ensure_indexes(app.state.db)
            yield
        finally:
            if client is not None:
                client.close()

    app = FastAPI(title="ProofChain API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            try:
                response = await call_next(request)
            except Exception:
                # Handled here (not via an Exception handler) so the request id is still set.
                logger.exception("unhandled exception")
                response = _envelope(500, "INTERNAL_ERROR", "Internal server error")
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(v1_router, prefix=settings.api_prefix)
    return app


app = create_app()
