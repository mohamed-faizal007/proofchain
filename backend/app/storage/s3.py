"""S3 / MinIO client (ADR-002). boto3 is sync, so calls run in a worker thread."""

from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

import anyio.to_thread
import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from app.config import Settings
from app.errors import StorageError

T = TypeVar("T")

# The worker thread behind a call cannot be cancelled, so botocore's own timeouts are what bound it
# (asyncio.wait_for in /health only abandons the await). Connect stays under /health's 2s budget.
CONNECT_TIMEOUT_SECONDS = 1.0
READ_TIMEOUT_SECONDS = 5.0
TOTAL_MAX_ATTEMPTS = 2

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}


class StoredObject(BaseModel):
    key: str
    version_id: str | None
    size_bytes: int


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


class S3Storage:
    def __init__(self, client: BaseClient, bucket: str, presign_expiry_seconds: int) -> None:
        self._client = client
        self._bucket = bucket
        self._presign_expiry = presign_expiry_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3Storage":
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            # MinIO needs path-style addressing; it is also valid on AWS.
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                read_timeout=READ_TIMEOUT_SECONDS,
                retries={"total_max_attempts": TOTAL_MAX_ATTEMPTS},
            ),
        )
        return cls(client, settings.s3_bucket, settings.s3_presign_expiry_seconds)

    async def _run(self, fn: Callable[[], T]) -> T:
        return await anyio.to_thread.run_sync(fn)

    async def put(
        self, key: str, data: bytes, content_type: str = "application/pdf"
    ) -> StoredObject:
        try:
            resp = await self._run(
                partial(
                    self._client.put_object,
                    Bucket=self._bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"failed to store object {key}") from exc
        return StoredObject(key=key, version_id=resp.get("VersionId"), size_bytes=len(data))

    async def get(self, key: str, version_id: str | None = None) -> bytes:
        def read() -> bytes:
            resp = self._client.get_object(Bucket=self._bucket, Key=key, **_version(version_id))
            body: bytes = resp["Body"].read()
            return body

        try:
            return await self._run(read)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"failed to read object {key}") from exc

    async def head(self, key: str, version_id: str | None = None) -> StoredObject | None:
        """Metadata for the object, or None if it does not exist."""
        try:
            resp = await self._run(
                partial(
                    self._client.head_object, Bucket=self._bucket, Key=key, **_version(version_id)
                )
            )
        except ClientError as exc:
            if _error_code(exc) in _NOT_FOUND_CODES:
                return None
            raise StorageError(f"failed to head object {key}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"failed to head object {key}") from exc
        return StoredObject(
            key=key, version_id=resp.get("VersionId"), size_bytes=int(resp["ContentLength"])
        )

    async def presign_get(
        self, key: str, version_id: str | None = None, expires_seconds: int | None = None
    ) -> str:
        # KNOWN LIMITATION (PROGRESS.md Follow-ups, "Presigned URL host"): the URL is signed
        # against the internal S3_ENDPOINT_URL. That host is not browser-reachable once the
        # backend runs in Docker (minio vs localhost), and it cannot be rewritten after signing.
        # To be resolved by P8-03 / P10-03.
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key, **_version(version_id)}
        try:
            return await self._run(
                partial(
                    self._client.generate_presigned_url,
                    "get_object",
                    Params=params,
                    ExpiresIn=expires_seconds or self._presign_expiry,
                )
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"failed to presign object {key}") from exc

    async def head_bucket(self) -> bool:
        """True if the bucket exists and is reachable (used by /health, P2-04)."""
        try:
            await self._run(partial(self._client.head_bucket, Bucket=self._bucket))
        except (ClientError, BotoCoreError):
            return False
        return True


def _version(version_id: str | None) -> dict[str, str]:
    return {"VersionId": version_id} if version_id else {}
