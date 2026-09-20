"""Shared fixture for real-MongoDB tests (`-m mongo`); uses MONGO_URI and a throwaway database."""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


@pytest.fixture
async def real_db() -> AsyncIterator[AsyncIOMotorDatabase]:
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client: AsyncIOMotorClient = AsyncIOMotorClient(
        uri, tz_aware=True, serverSelectionTimeoutMS=3000
    )
    name = f"proofchain_it_{uuid.uuid4().hex[:8]}"
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        client.close()
        pytest.fail(f"MongoDB not reachable at {uri}: {exc}")
    try:
        yield client[name]
    finally:
        await client.drop_database(name)
        client.close()
