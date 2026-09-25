"""Needs a Hardhat node with the contract deployed (from contracts/):

    npx hardhat node                                   # terminal 1
    npm run deploy:local                               # terminal 2
    cd ../backend; python -m pytest -m chain tests/integration/test_chain_web3.py

Reads the address from contracts/deployments/localhost.json (or REGISTRY_ADDRESS) and signs
with hardhat account #0 (or ANCHOR_PRIVATE_KEY), which deploy.ts grants ANCHOR_ROLE by default.
"""

import json
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.chain.types import ZERO_HASH
from app.chain.web3_client import Web3RegistryClient
from app.errors import AnchorFailedError

pytestmark = pytest.mark.chain

DEPLOYMENT = Path(__file__).parents[3] / "contracts" / "deployments" / "localhost.json"
HARDHAT_ACCOUNT_0_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def _hex() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


@pytest.fixture
async def client() -> AsyncIterator[Web3RegistryClient]:
    address = os.environ.get("REGISTRY_ADDRESS") or json.loads(DEPLOYMENT.read_text())["address"]
    c = Web3RegistryClient(
        os.environ.get("CHAIN_RPC_URL", "http://127.0.0.1:8545"),
        int(os.environ.get("CHAIN_ID", "31337")),
        address,
        os.environ.get("ANCHOR_PRIVATE_KEY") or HARDHAT_ACCOUNT_0_KEY,
        confirmations=1,
    )
    yield c
    await c.aclose()


async def test_health(client: Web3RegistryClient) -> None:
    h = await client.health()
    assert h.ok is True and h.chain_id == 31337 and h.block_number is not None


async def test_anchor_read_link_and_idempotency(client: Web3RegistryClient) -> None:
    doc, f1, r1, f2, r2 = _hex(), _hex(), _hex(), _hex(), _hex()
    assert await client.version_count(doc) == 0
    assert await client.get_version(doc, 1) is None

    a1 = await client.anchor_version(doc, f1, r1, 1)
    assert (a1.version_no, a1.already_anchored) == (1, False)
    assert a1.tx_hash is not None and a1.tx_hash.startswith("0x") and len(a1.tx_hash) == 66
    v1 = await client.get_version(doc, 1)
    assert v1 is not None
    assert (v1.file_hash, v1.text_root, v1.prev_text_root) == (f1, r1, ZERO_HASH)
    assert (v1.canon_version, v1.revoked) == (1, False) and v1.anchored_at > 0

    again = await client.anchor_version(doc, f1, r1, 1)
    assert (again.version_no, again.already_anchored, again.tx_hash) == (1, True, None)
    assert await client.version_count(doc) == 1

    a2 = await client.anchor_version(doc, f2, r2, 1)
    assert a2.version_no == 2
    v2 = await client.get_version(doc, 2)
    assert v2 is not None and v2.prev_text_root == r1
    assert await client.get_version(doc, 3) is None


async def test_revoke_then_reanchor_same_content_creates_new_version(
    client: Web3RegistryClient,
) -> None:
    doc, f1, r1 = _hex(), _hex(), _hex()
    a1 = await client.anchor_version(doc, f1, r1, 1)
    rev = await client.revoke_version(doc, 1, "mistake")
    assert rev.tx_hash.startswith("0x")
    v1 = await client.get_version(doc, 1)
    assert v1 is not None and v1.revoked is True and v1.file_hash == f1

    a2 = await client.anchor_version(doc, f1, r1, 1)
    assert (a2.version_no, a2.already_anchored) == (2, False)
    assert a2.tx_hash is not None and a2.tx_hash != a1.tx_hash
    v2 = await client.get_version(doc, 2)
    assert v2 is not None and v2.revoked is False and v2.prev_text_root == r1
    assert await client.version_count(doc) == 2


async def test_revert_maps_to_anchor_failed(client: Web3RegistryClient) -> None:
    doc = _hex()
    with pytest.raises(AnchorFailedError):
        await client.revoke_version(doc, 1, "no such version")
    with pytest.raises(AnchorFailedError):
        await client.anchor_version(doc, ZERO_HASH, _hex(), 1)
