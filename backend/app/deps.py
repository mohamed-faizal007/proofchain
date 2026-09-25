"""FastAPI dependencies. Tests swap implementations via `app.dependency_overrides`."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.chain import RegistryClient
from app.config import Settings
from app.db import MongoDatabase
from app.errors import ChainUnavailableError, ForbiddenError, UnauthorizedError
from app.models.user import Role, User
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.repositories.users import UserRepository
from app.repositories.verifications import VerificationRepository
from app.security.jwt import decode_access_token
from app.services.auth import AuthService
from app.storage import S3Storage

_bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> MongoDatabase:
    db: MongoDatabase = request.app.state.db
    return db


def get_user_repo(request: Request) -> UserRepository:
    return UserRepository(get_db(request))


def get_document_repo(request: Request) -> DocumentRepository:
    return DocumentRepository(get_db(request))


def get_revision_repo(request: Request) -> RevisionRepository:
    return RevisionRepository(get_db(request))


def get_tree_repo(request: Request) -> TreeRepository:
    return TreeRepository(get_db(request))


def get_event_repo(request: Request) -> EventRepository:
    return EventRepository(get_db(request))


def get_verification_repo(request: Request) -> VerificationRepository:
    return VerificationRepository(get_db(request))


def get_storage(request: Request) -> S3Storage:
    storage: S3Storage = request.app.state.storage
    return storage


def get_registry_client(request: Request) -> RegistryClient:
    client: RegistryClient | None = getattr(request.app.state, "registry_client", None)
    if client is None:
        raise ChainUnavailableError("Blockchain registry is not configured")
    return client


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_auth_service(
    users: UserRepository = Depends(get_user_repo),
    settings: Settings = Depends(get_app_settings),
) -> AuthService:
    return AuthService(users, settings)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    users: UserRepository = Depends(get_user_repo),
    settings: Settings = Depends(get_app_settings),
) -> User | None:
    """None when no bearer token is sent; 401 when one is sent but is not valid.

    Roles and `is_active` come from the DB on every request, not from the JWT `roles` claim, so
    role changes and deactivation apply immediately (see PROGRESS follow-ups).
    """
    if credentials is None:
        return None
    claims = decode_access_token(credentials.credentials, settings)
    user = await users.get(claims.sub)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired token")
    return user


async def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise UnauthorizedError("Authentication required")
    return user


def require_roles(*roles: Role) -> Callable[..., Awaitable[User]]:
    """Dependency factory: the current user must hold at least one of `roles` (else 403)."""

    async def guard(user: User = Depends(get_current_user)) -> User:
        if not set(roles) & set(user.roles):
            raise ForbiddenError("Insufficient role", details={"required_any_of": list(roles)})
        return user

    return guard


async def require_register_access(
    user: User | None = Depends(get_optional_user),
    settings: Settings = Depends(get_app_settings),
) -> None:
    """Registration is public in dev/test and ADMIN-only in prod (04_API_SPEC Auth)."""
    if settings.app_env != "prod":
        return
    if user is None:
        raise UnauthorizedError("Authentication required")
    if "ADMIN" not in user.roles:
        raise ForbiddenError("Insufficient role", details={"required_any_of": ["ADMIN"]})
