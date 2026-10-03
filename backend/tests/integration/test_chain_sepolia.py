"""Round trip against the deployed Sepolia registry (spends a little test ETH; opt-in).

    $env:SEPOLIA_ROUNDTRIP = "1"; $env:CHAIN_RPC_URL = "<sepolia rpc>"
    $env:ANCHOR_PRIVATE_KEY = "<key with ANCHOR_ROLE>"
    cd backend; python -m pytest -m chain tests/integration/test_chain_sepolia.py -s

The registry address comes from contracts/deployments/sepolia.json (or REGISTRY_ADDRESS).
"""

import json
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.chain.web3_client import Web3RegistryClient

pytestmark = [
    pytest.mark.chain,
    pytest.mark.skipif(
        os.environ.get("SEPOLIA_ROUNDTRIP") != "1", reason="set SEPOLIA_ROUNDTRIP=1 to spend gas"
    ),
]

DEPLOYMENT = Path(__file__).parents[3] / "contracts" / "deployments" / "sepolia.json"
SEPOLIA_CHAIN_ID = 11155111


def _hex() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


@pytest.fixture
async def client() -> AsyncIterator[Web3RegistryClient]:
    address = os.environ.get("REGISTRY_ADDRESS") or json.loads(DEPLOYMENT.read_text())["address"]
    c = Web3RegistryClient(
        os.environ["CHAIN_RPC_URL"],
        SEPOLIA_CHAIN_ID,
        address,
        os.environ["ANCHOR_PRIVATE_KEY"],
        confirmations=2,
    )
    yield c
    await c.aclose()


async def test_sepolia_anchor_read_back_and_link(client: Web3RegistryClient) -> None:
    h = await client.health()
    assert h.ok is True and h.chain_id == SEPOLIA_CHAIN_ID

    doc, f1, r1, f2, r2 = _hex(), _hex(), _hex(), _hex(), _hex()
    a1 = await client.anchor_version(doc, f1, r1, 1)
    assert (a1.version_no, a1.already_anchored) == (1, False)
    assert a1.tx_hash is not None and len(a1.tx_hash) == 66
    print(f"v1 tx {a1.tx_hash} block {a1.block_number}")

    v1 = await client.get_version(doc, 1)
    assert v1 is not None and v1.file_hash == f1 and v1.text_root == r1
    assert await client.version_count(doc) == 1

    again = await client.anchor_version(doc, f1, r1, 1)  # idempotent: no second tx
    assert again.already_anchored is True

    a2 = await client.anchor_version(doc, f2, r2, 2)
    assert a2.version_no == 2
    v2 = await client.get_version(doc, 2)
    assert v2 is not None and v2.prev_text_root == r1 and v2.text_root == r2
    assert await client.version_count(doc) == 2
