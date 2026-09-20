"""FastAPI dependencies. Tests swap implementations via `app.dependency_overrides`."""

from fastapi import Request

from app.db import MongoDatabase


def get_db(request: Request) -> MongoDatabase:
    db: MongoDatabase = request.app.state.db
    return db
