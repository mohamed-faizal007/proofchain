from collections.abc import AsyncIterator

import pytest
from mongomock_motor import AsyncMongoMockClient
from motor.motor_asyncio import AsyncIOMotorDatabase


@pytest.fixture
async def mongo_db() -> AsyncIterator[AsyncIOMotorDatabase]:
    # tz_aware=True mirrors app.db.create_client (see PROGRESS.md, datetimes note).
    client = AsyncMongoMockClient(tz_aware=True)
    yield client["proofchain_test"]
    client.close()
