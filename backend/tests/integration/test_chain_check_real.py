"""P6-03 chain cross-check against a real Hardhat node (same setup as test_chain_web3.py)."""

import uuid

import pytest

from app.chain.web3_client import Web3RegistryClient
from app.services.chain_check import ChainCheckService
from tests.integration.test_chain_web3 import client  # noqa: F401  (fixture)
from tests.unit.repositories.factories import make_revision

pytestmark = pytest.mark.chain


def _hex() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


async def test_cross_check_on_real_chain(client: Web3RegistryClient) -> None:  # noqa: F811
    doc, file_hash, text_root = _hex(), _hex(), _hex()
    receipt = await client.anchor_version(doc, file_hash, text_root, 2)
    rev = make_revision(
        "mongo-id",
        1,
        status="APPROVED",
        file_hash=file_hash,
        text_root=text_root,
        version_no=receipt.version_no,
        anchor={"status": "ANCHORED", "tx_hash": receipt.tx_hash},
    )
    svc = ChainCheckService(client)

    ok = await svc.check(rev, doc)
    assert ok.performed and ok.ok is True and ok.tx_hash == receipt.tx_hash

    edited = rev.model_copy(update={"text_root": _hex()})  # Mongo edited behind the chain's back
    bad = await svc.check(edited, doc)
    assert bad.ok is False and bad.mismatches == ("text_root",)

    await client.revoke_version(doc, receipt.version_no, "test")  # chain revoked, Mongo APPROVED
    assert (await svc.check(rev, doc)).mismatches == ("revoked",)
    revoked = rev.model_copy(update={"status": "REVOKED"})
    assert (await svc.check(revoked, doc)).ok is True
