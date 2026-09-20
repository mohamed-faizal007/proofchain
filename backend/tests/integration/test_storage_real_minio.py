"""Needs MinIO (`docker compose -f infra/docker-compose.yml up -d minio minio-init`).

Run with: python -m pytest -m minio tests/integration/test_storage_real_minio.py
Uses S3_ENDPOINT_URL (default http://localhost:9000), minioadmin creds, bucket proofchain-docs.
"""

import os
import uuid

import httpx
import pytest

from app.config import Settings
from app.storage import S3Storage, revision_key

pytestmark = pytest.mark.minio


@pytest.fixture
def storage() -> S3Storage:
    return S3Storage.from_settings(
        Settings(
            app_env="test",
            s3_endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        )
    )


async def test_put_get_versions_and_presign(storage: S3Storage) -> None:
    assert await storage.head_bucket() is True
    key = revision_key(f"it-{uuid.uuid4().hex[:8]}", "r1")
    v1 = await storage.put(key, b"one")
    v2 = await storage.put(key, b"two")
    assert v1.version_id and v1.version_id != v2.version_id
    assert await storage.get(key, version_id=v1.version_id) == b"one"

    url = await storage.presign_get(key, version_id=v1.version_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    assert resp.content == b"one"
