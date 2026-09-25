"""/health real dependency checks (P2-04). Degraded is still HTTP 200 (see PROGRESS follow-ups)."""

import asyncio
import time
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.chain import ChainHealth, FakeRegistryClient
from app.chain.web3_client import Web3RegistryClient
from app.config import Settings
from app.main import create_app
from app.storage import S3Storage
from proofchain_core import CANON_VERSION

URL = "/api/v1/health"
BUCKET = "proofchain-test"
SECRET = "super-secret-connection-detail"


def _settings() -> Settings:
    return Settings(
        app_env="test",
        s3_bucket=BUCKET,
        s3_region="ap-south-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


@pytest.fixture
def storage() -> Iterator[S3Storage]:
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
        yield S3Storage.from_settings(_settings())


class _BrokenDb:
    async def command(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(SECRET)


class _HangingDb:
    async def command(self, *args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(60)


class _BrokenStorage:
    async def head_bucket(self) -> bool:
        raise RuntimeError(SECRET)


class _MissingBucketStorage:
    async def head_bucket(self) -> bool:
        return False


class _DownChain(FakeRegistryClient):
    async def health(self) -> ChainHealth:
        return ChainHealth(ok=False)


class _BrokenChain(FakeRegistryClient):
    async def health(self) -> ChainHealth:
        raise RuntimeError(SECRET)


class _HangingChain(FakeRegistryClient):
    async def health(self) -> ChainHealth:
        await asyncio.sleep(60)
        return ChainHealth(ok=True)


class _SlowDb:
    async def command(self, *args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(0.3)


class _SlowChain(FakeRegistryClient):
    async def health(self) -> ChainHealth:
        await asyncio.sleep(0.3)
        return ChainHealth(ok=True)


class _SlowStorage:
    async def head_bucket(self) -> bool:
        await asyncio.sleep(0.3)
        return True


def _get(db: Any, storage: Any, chain: Any = None, timeout: float | None = None) -> Any:
    app = create_app(_settings(), db=db, storage=storage, registry_client=chain)
    if timeout is not None:
        app.state.health_timeout_seconds = timeout
    with TestClient(app) as client:
        return client.get(URL)


def test_health_all_ok(mongo_db: AsyncIOMotorDatabase, storage: S3Storage) -> None:
    r = _get(mongo_db, storage)
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "mongo": "ok",
        "s3": "ok",
        "chain": "not_configured",
        "nlp": "not_configured",
        "canon_version": CANON_VERSION,
    }


def test_health_mongo_down_is_degraded_but_200(storage: S3Storage) -> None:
    app = create_app(_settings(), db=_BrokenDb(), storage=storage)  # type: ignore[arg-type]
    app.router.lifespan_context = _no_index_lifespan(app, _BrokenDb(), storage)
    with TestClient(app) as client:
        r = client.get(URL)
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["mongo"] == "down"
    assert r.json()["s3"] == "ok"


def test_health_s3_bucket_missing_is_degraded_but_200(mongo_db: AsyncIOMotorDatabase) -> None:
    r = _get(mongo_db, _MissingBucketStorage())
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["s3"] == "down"
    assert r.json()["mongo"] == "ok"


def test_health_s3_raising_is_degraded_but_200(mongo_db: AsyncIOMotorDatabase) -> None:
    r = _get(mongo_db, _BrokenStorage())
    assert r.status_code == 200
    assert r.json()["s3"] == "down"
    assert r.json()["status"] == "degraded"


def test_health_never_leaks_exception_text(storage: S3Storage) -> None:
    app = create_app(_settings(), db=_BrokenDb(), storage=_BrokenStorage())  # type: ignore[arg-type]
    app.router.lifespan_context = _no_index_lifespan(app, _BrokenDb(), _BrokenStorage())
    with TestClient(app) as client:
        r = client.get(URL)
    assert SECRET not in r.text
    assert r.json()["mongo"] == "down"
    assert r.json()["s3"] == "down"


def test_health_hung_dependency_times_out(storage: S3Storage) -> None:
    app = create_app(_settings(), db=_HangingDb(), storage=storage)  # type: ignore[arg-type]
    app.router.lifespan_context = _no_index_lifespan(app, _HangingDb(), storage)
    app.state.health_timeout_seconds = 0.05
    with TestClient(app) as client:
        r = client.get(URL)
    assert r.status_code == 200
    assert r.json()["mongo"] == "down"


def test_health_is_public_and_works_without_lifespan() -> None:
    # No startup ran, so app.state has no db/storage: report down instead of a 500.
    r = TestClient(create_app(_settings())).get(URL)
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["mongo"] == "down"
    assert r.json()["s3"] == "down"


def _no_index_lifespan(app: Any, db: Any, storage: Any) -> Any:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_: Any) -> Any:
        app.state.db = db
        app.state.storage = storage
        yield

    return lifespan


def test_health_chain_ok(mongo_db: AsyncIOMotorDatabase, storage: S3Storage) -> None:
    r = _get(mongo_db, storage, FakeRegistryClient())
    assert r.status_code == 200
    assert r.json()["chain"] == "ok"
    assert r.json()["status"] == "ok"


def test_health_chain_reporting_down_is_degraded_but_200(
    mongo_db: AsyncIOMotorDatabase, storage: S3Storage
) -> None:
    r = _get(mongo_db, storage, _DownChain())
    assert r.status_code == 200
    assert r.json()["chain"] == "down"
    assert r.json()["status"] == "degraded"
    assert r.json()["mongo"] == "ok" and r.json()["s3"] == "ok"


def test_health_chain_raising_is_down_and_never_leaks(
    mongo_db: AsyncIOMotorDatabase, storage: S3Storage
) -> None:
    r = _get(mongo_db, storage, _BrokenChain())
    assert r.json()["chain"] == "down"
    assert r.json()["status"] == "degraded"
    assert SECRET not in r.text


def test_health_hung_chain_times_out(mongo_db: AsyncIOMotorDatabase, storage: S3Storage) -> None:
    r = _get(mongo_db, storage, _HangingChain(), timeout=0.05)
    assert r.status_code == 200
    assert r.json()["chain"] == "down"
    assert r.json()["mongo"] == "ok"


def test_health_unreachable_real_chain_client_is_down(
    mongo_db: AsyncIOMotorDatabase, storage: S3Storage
) -> None:
    chain = Web3RegistryClient(
        "http://127.0.0.1:9", 31337, "0x" + "2" * 40, "0x" + "1" * 64, rpc_timeout=0.3
    )
    r = _get(mongo_db, storage, chain, timeout=3.0)
    assert r.status_code == 200
    assert r.json()["chain"] == "down"
    assert r.json()["status"] == "degraded"
    assert "127.0.0.1" not in r.text


def test_health_checks_run_concurrently() -> None:
    db, storage, chain = _SlowDb(), _SlowStorage(), _SlowChain()
    app = create_app(_settings(), db=db, storage=storage, registry_client=chain)  # type: ignore[arg-type]
    app.router.lifespan_context = _no_index_lifespan(app, db, storage)
    app.state.registry_client = chain
    app.state.health_timeout_seconds = 2.0
    started = time.perf_counter()
    with TestClient(app) as client:
        r = client.get(URL)
    elapsed = time.perf_counter() - started
    assert r.json()["chain"] == "ok" and r.json()["status"] == "ok"
    assert elapsed < 0.8  # three 0.3s probes: sequential would be >= 0.9s
