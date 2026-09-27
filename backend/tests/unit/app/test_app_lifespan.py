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


async def test_startup_warms_nlp_models_when_explicitly_requested(
    mongo_db: AsyncIOMotorDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P7 phase review MEDIUM (06: "warmed at startup when NLP_ENABLED=true"): a spy on
    `warm_nlp_models` proves the lifespan actually calls it, not just that it's importable."""
    calls = []
    monkeypatch.setattr("app.main.warm_nlp_models", lambda settings: calls.append(settings))
    settings = Settings(app_env="test", nlp_enabled=True)
    app = create_app(settings, db=mongo_db, warm_nlp_on_startup=True)

    with TestClient(app):
        pass

    assert calls == [settings]


async def test_startup_does_not_warm_nlp_models_when_nlp_disabled(
    mongo_db: AsyncIOMotorDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr("app.main.warm_nlp_models", lambda settings: calls.append(settings))
    settings = Settings(app_env="test", nlp_enabled=False)
    app = create_app(settings, db=mongo_db, warm_nlp_on_startup=True)

    with TestClient(app):
        pass

    assert calls == []


async def test_default_app_env_test_never_warms_nlp_models(
    mongo_db: AsyncIOMotorDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`warm_nlp_on_startup` defaults to off under APP_ENV=test (mirrors
    `reconcile_on_startup`), so the ordinary fast test suite never triggers a real model load."""
    calls = []
    monkeypatch.setattr("app.main.warm_nlp_models", lambda settings: calls.append(settings))
    settings = Settings(app_env="test", nlp_enabled=True)
    app = create_app(settings, db=mongo_db)  # warm_nlp_on_startup left at its default

    with TestClient(app):
        pass

    assert calls == []
