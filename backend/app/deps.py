"""FastAPI dependencies. Tests swap implementations via `app.dependency_overrides`."""

from fastapi import Request

from app.db import MongoDatabase
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.repositories.users import UserRepository
from app.repositories.verifications import VerificationRepository
from app.storage import S3Storage


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
