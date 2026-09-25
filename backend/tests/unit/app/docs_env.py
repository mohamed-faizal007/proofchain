"""Shared harness for document route tests: mongomock + moto S3 + fake chain + real app."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.chain import FakeRegistryClient
from app.config import Settings
from app.main import create_app
from app.models.user import Role, User
from app.repositories.users import UserRepository
from app.security.jwt import create_access_token
from app.storage import S3Storage

PREFIX = "/api/v1"
BUCKET = "proofchain-test"
SECRET = "test-secret-" + "x" * 32
PDFS = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs"


def settings() -> Settings:
    return Settings(  # type: ignore[arg-type]
        app_env="test",
        jwt_secret=SECRET,
        anchor_private_key="0x" + "1" * 64,
        registry_address="0x" + "2" * 40,
        s3_bucket=BUCKET,
        s3_region="ap-south-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        max_upload_mb=1,
    )


@dataclass
class Env:
    client: TestClient
    db: AsyncIOMotorDatabase
    s3: Any  # raw boto3 client for inspecting the bucket
    storage: S3Storage

    def user(self, roles: list[Role], email: str = "u@example.com") -> User:
        user = User(email=email, full_name="U", password_hash="x", roles=roles)
        repo = UserRepository(self.db)
        self.client.portal.call(repo.insert, user)  # type: ignore[union-attr]
        return user

    def auth(self, user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id, user.roles, settings())}"}

    def issuer(self) -> dict[str, str]:
        return self.auth(self.user(["ISSUER"], "issuer@example.com"))

    def count(self, collection: str) -> int:
        return self.client.portal.call(self.db[collection].count_documents, {})  # type: ignore[union-attr]

    def s3_keys(self) -> list[str]:
        resp = self.s3.list_object_versions(Bucket=BUCKET)
        return [v["Key"] for v in resp.get("Versions", [])]

    def post_pdf(
        self,
        headers: dict[str, str],
        pdf: bytes | str = "contract_3page.pdf",
        **form: str,
    ) -> Any:
        data = (PDFS / pdf).read_bytes() if isinstance(pdf, str) else pdf
        fields = {"title": "Lease", "doc_type": "CONTRACT", **form}
        return self.client.post(
            f"{PREFIX}/documents",
            headers=headers,
            files={"file": ("lease.pdf", data, "application/pdf")},
            data=fields,
        )

    def submit(
        self,
        headers: dict[str, str],
        document_id: str,
        pdf: bytes | str = "one_page.pdf",
        **form: str,
    ) -> Any:
        data = (PDFS / pdf).read_bytes() if isinstance(pdf, str) else pdf
        return self.client.post(
            f"{PREFIX}/documents/{document_id}/revisions",
            headers=headers,
            files={"file": ("lease_v2.pdf", data, "application/pdf")},
            data={"change_note": "updated", **form},
        )

    def set_status(self, revision_id: str, status: str) -> None:
        """Stand-in for approve/reject (P5-03): force a revision's status directly."""
        self.client.portal.call(  # type: ignore[union-attr]
            self.db["revisions"].update_one, {"_id": revision_id}, {"$set": {"status": status}}
        )


@pytest.fixture
def env(mongo_db: AsyncIOMotorDatabase) -> Iterator[Env]:
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
        storage = S3Storage.from_settings(settings())
        app = create_app(
            settings(), db=mongo_db, storage=storage, registry_client=FakeRegistryClient()
        )
        # raise_server_exceptions=False exercises the real 500 middleware.
        with TestClient(app, raise_server_exceptions=False) as client:
            yield Env(client, mongo_db, raw, storage)
