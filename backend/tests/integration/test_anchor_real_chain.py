"""Full approve -> ANCHORED path on a real Hardhat node and real MongoDB (P5-04).

Needs (see test_chain_web3.py): `npx hardhat node`, `npm run deploy:local`, and MongoDB up
(`docker compose -f infra/docker-compose.yml up -d mongo`). S3 is moto. Run with:

    python -m pytest -m chain tests/integration/test_anchor_real_chain.py
"""

import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pymongo import MongoClient

from app.chain.web3_client import Web3RegistryClient
from app.config import Settings
from app.main import create_app
from app.storage import S3Storage
from tests.unit.app.docs_env import BUCKET, PREFIX, SECRET, Env

pytestmark = [pytest.mark.chain, pytest.mark.mongo]

DEPLOYMENT = Path(__file__).parents[3] / "contracts" / "deployments" / "localhost.json"
HARDHAT_ACCOUNT_0_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")


def _settings(db_name: str) -> Settings:
    address = os.environ.get("REGISTRY_ADDRESS") or json.loads(DEPLOYMENT.read_text())["address"]
    return Settings(  # type: ignore[arg-type]
        app_env="test",
        jwt_secret=SECRET,
        mongo_uri=MONGO_URI,
        mongo_db=db_name,
        chain_rpc_url=os.environ.get("CHAIN_RPC_URL", "http://127.0.0.1:8545"),
        chain_id=int(os.environ.get("CHAIN_ID", "31337")),
        registry_address=address,
        anchor_private_key=os.environ.get("ANCHOR_PRIVATE_KEY") or HARDHAT_ACCOUNT_0_KEY,
        s3_bucket=BUCKET,
        s3_region="ap-south-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


@pytest.fixture
def real_env() -> Iterator[Env]:
    db_name = f"proofchain_chain_{uuid.uuid4().hex[:8]}"
    settings = _settings(db_name)
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
        storage = S3Storage.from_settings(settings)
        app = create_app(settings, storage=storage)  # real Mongo + Web3 client from settings
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                assert isinstance(app.state.registry_client, Web3RegistryClient)
                yield Env(client, app.state.db, raw, storage)
        finally:
            MongoClient(MONGO_URI).drop_database(db_name)


def test_approve_anchors_on_real_chain_in_revision_order(real_env: Env) -> None:
    env = real_env
    issuer, approver = env.issuer(), env.approver()
    admin = env.auth(env.user(["ADMIN"], "admin@example.com"))
    reg = env.post_pdf(issuer).json()
    v1, doc_id = reg["revision"]["id"], reg["document"]["id"]

    r = env.review(approver, v1, "approve")
    assert (r.status_code, r.json()["anchor"]["status"]) == (202, "ANCHORING")

    stored = env.revision(v1)
    anchor = stored["anchor"]
    assert (stored["status"], anchor["status"], stored["version_no"]) == ("APPROVED", "ANCHORED", 1)
    assert anchor["tx_hash"].startswith("0x") and len(anchor["tx_hash"]) == 66
    assert anchor["block_number"] > 0 and anchor["chain_id"] == 31337
    assert (anchor["error"], anchor["attempts"]) == (None, 1)
    [event] = env.events("VERSION_ANCHORED")
    assert (event["data"]["tx_hash"], event["data"]["version_no"]) == (anchor["tx_hash"], 1)
    doc = env.document(doc_id)
    assert (doc["latest_approved_revision_id"], doc["latest_approved_version_no"]) == (v1, 1)

    chain = env.client.app.state.registry_client  # type: ignore[attr-defined]
    on_chain = env.client.portal.call(chain.get_version, doc["chain_doc_id"], 1)  # type: ignore[union-attr]
    assert (on_chain.file_hash, on_chain.text_root) == (stored["file_hash"], stored["text_root"])

    # second revision links to the first on-chain
    v2 = env.submit(issuer, doc_id).json()["revision"]["id"]
    assert env.review(approver, v2, "approve").status_code == 202
    stored2 = env.revision(v2)
    assert (stored2["anchor"]["status"], stored2["version_no"]) == ("ANCHORED", 2)
    on_chain2 = env.client.portal.call(chain.get_version, doc["chain_doc_id"], 2)  # type: ignore[union-attr]
    assert on_chain2.prev_text_root == stored["text_root"]
    assert env.document(doc_id)["latest_approved_version_no"] == 2

    # admin retry on an ANCHORED revision is a 200 no-op: no new tx
    r = env.client.post(f"{PREFIX}/revisions/{v2}/retry-anchor", headers=admin)
    assert (r.status_code, r.json()["anchor"]["tx_hash"]) == (200, stored2["anchor"]["tx_hash"])
    count = env.client.portal.call(chain.version_count, doc["chain_doc_id"])  # type: ignore[union-attr]
    assert count == 2


def test_revoke_on_real_chain(real_env: Env) -> None:
    """P5-05: approve -> ANCHORED -> revoke sends revokeVersion and marks the revision REVOKED."""
    env = real_env
    issuer, approver = env.issuer(), env.approver()
    reg = env.post_pdf(issuer).json()
    v1, doc_id = reg["revision"]["id"], reg["document"]["id"]
    assert env.review(approver, v1, "approve").status_code == 202
    assert env.revision(v1)["anchor"]["status"] == "ANCHORED"

    r = env.client.post(
        f"{PREFIX}/revisions/{v1}/revoke", headers=approver, json={"reason": "issued in error"}
    )

    assert r.status_code == 200, r.text
    revocation = r.json()["revocation"]
    assert revocation["tx_hash"].startswith("0x") and len(revocation["tx_hash"]) == 66
    assert revocation["block_number"] > env.revision(v1)["anchor"]["block_number"]
    chain = env.client.app.state.registry_client  # type: ignore[attr-defined]
    chain_doc_id = env.document(doc_id)["chain_doc_id"]
    on_chain = env.client.portal.call(chain.get_version, chain_doc_id, 1)  # type: ignore[union-attr]
    assert on_chain.revoked is True
    [event] = env.events("VERSION_REVOKED")
    assert (event["data"]["tx_hash"], event["data"]["already_revoked"]) == (
        revocation["tx_hash"],
        False,
    )
    doc = env.document(doc_id)
    assert (doc["latest_approved_revision_id"], doc["latest_approved_version_no"]) == (None, None)

    # a second revoke is a clean 409, no tx
    r = env.client.post(f"{PREFIX}/revisions/{v1}/revoke", headers=approver, json={"reason": "x"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "REVISION_NOT_APPROVED")
