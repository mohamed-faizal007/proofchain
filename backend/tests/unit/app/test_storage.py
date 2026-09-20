"""S3Storage against moto (versioned bucket)."""

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from moto import mock_aws

from app.config import Settings
from app.errors import StorageError
from app.storage import S3Storage, revision_key

BUCKET = "proofchain-test"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        s3_bucket=BUCKET,
        s3_region="ap-south-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        s3_presign_expiry_seconds=123,
    )


@pytest.fixture
def storage(settings: Settings) -> Iterator[S3Storage]:
    with mock_aws():
        raw = boto3.client(
            "s3",
            region_name="ap-south-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        raw.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )
        raw.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        yield S3Storage.from_settings(settings)


def test_revision_key_layout() -> None:
    assert revision_key("d1", "r2") == "documents/d1/revisions/r2.pdf"


async def test_put_returns_version_id_and_size(storage: S3Storage) -> None:
    obj = await storage.put("k.pdf", b"hello")
    assert obj.key == "k.pdf"
    assert obj.size_bytes == 5
    assert obj.version_id


async def test_get_roundtrip_bytes(storage: S3Storage) -> None:
    await storage.put("k.pdf", b"\x00\x01payload")
    assert await storage.get("k.pdf") == b"\x00\x01payload"


async def test_overwrite_creates_new_version_and_old_version_readable(storage: S3Storage) -> None:
    v1 = await storage.put("k.pdf", b"one")
    v2 = await storage.put("k.pdf", b"two")
    assert v1.version_id != v2.version_id
    assert await storage.get("k.pdf", version_id=v1.version_id) == b"one"
    assert await storage.get("k.pdf") == b"two"


async def test_head_existing_and_missing(storage: S3Storage) -> None:
    put = await storage.put("k.pdf", b"abc")
    head = await storage.head("k.pdf")
    assert head is not None
    assert (head.size_bytes, head.version_id) == (3, put.version_id)
    assert await storage.head("nope.pdf") is None


async def test_get_missing_raises_storage_error(storage: S3Storage) -> None:
    with pytest.raises(StorageError):
        await storage.get("nope.pdf")


async def test_presign_pins_version_and_uses_configured_expiry(storage: S3Storage) -> None:
    put = await storage.put("k.pdf", b"abc")
    url = await storage.presign_get("k.pdf", version_id=put.version_id)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert "k.pdf" in parsed.path
    assert query["versionId"] == [put.version_id]
    assert query["X-Amz-Expires"] == ["123"]


async def test_presign_explicit_expiry_overrides_default(storage: S3Storage) -> None:
    url = await storage.presign_get("k.pdf", expires_seconds=60)
    assert parse_qs(urlparse(url).query)["X-Amz-Expires"] == ["60"]


async def test_head_bucket_ok(storage: S3Storage) -> None:
    assert await storage.head_bucket() is True


async def test_head_bucket_missing_returns_false(settings: Settings) -> None:
    with mock_aws():
        assert await S3Storage.from_settings(settings).head_bucket() is False
