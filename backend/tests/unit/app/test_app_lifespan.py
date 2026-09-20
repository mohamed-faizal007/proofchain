from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings
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
