import logging

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import DEFAULT_JWT_SECRET, Settings
from app.main import create_app


async def test_lifespan_creates_indexes_on_injected_db(mongo_db: AsyncIOMotorDatabase) -> None:
    app = create_app(Settings(app_env="test"), db=mongo_db)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert app.state.db is mongo_db
    assert "email_1" in await mongo_db.users.index_information()


def test_app_without_lifespan_does_not_touch_mongo() -> None:
    # Plain TestClient (no context manager) never runs startup, so no Mongo is required.
    client = TestClient(create_app(Settings(app_env="test")))
    assert client.get("/api/v1/health").status_code == 200


def _startup_warnings(
    caplog: pytest.LogCaptureFixture, db: AsyncIOMotorDatabase, settings: Settings
) -> list[str]:
    app = create_app(settings, db=db)
    # create_app -> configure_logging() replaces root handlers, so re-attach caplog's.
    logging.getLogger().addHandler(caplog.handler)
    caplog.set_level(logging.WARNING)
    with TestClient(app):
        pass
    return [r.getMessage() for r in caplog.records if "JWT_SECRET" in r.getMessage()]


async def test_default_jwt_secret_outside_prod_warns_at_startup(
    caplog: pytest.LogCaptureFixture, mongo_db: AsyncIOMotorDatabase
) -> None:
    msgs = _startup_warnings(caplog, mongo_db, Settings(app_env="dev"))
    assert len(msgs) == 1
    assert "APP_ENV" in msgs[0]
    assert DEFAULT_JWT_SECRET not in msgs[0]
    assert [r.levelno for r in caplog.records if "JWT_SECRET" in r.getMessage()] == [
        logging.WARNING
    ]


async def test_default_jwt_secret_in_test_env_is_silent(
    caplog: pytest.LogCaptureFixture, mongo_db: AsyncIOMotorDatabase
) -> None:
    assert _startup_warnings(caplog, mongo_db, Settings(app_env="test")) == []


async def test_custom_jwt_secret_is_silent(
    caplog: pytest.LogCaptureFixture, mongo_db: AsyncIOMotorDatabase
) -> None:
    settings = Settings(app_env="dev", jwt_secret="a-real-secret-" + "x" * 32)
    assert _startup_warnings(caplog, mongo_db, settings) == []
