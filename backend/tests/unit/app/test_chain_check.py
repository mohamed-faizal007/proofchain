"""P6-03 chain cross-check (02 §11, ADR-020): Mongo record vs the on-chain version."""

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.chain import FakeRegistryClient
from app.chain.types import OnChainVersion
from app.db import ensure_indexes
from app.errors import ChainUnavailableError
from app.models.revision import Revision
from app.repositories.documents import DocumentRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.services.chain_check import (
    MISSING_ON_CHAIN,
    NOT_ANCHORED,
    NOT_CONFIGURED,
    UNAVAILABLE,
    ChainCheckService,
)
from app.services.reference import ReferenceService
from app.services.tree_mapping import tree_to_doc
from tests.unit.app.test_reference import tree, words
from tests.unit.repositories.factories import make_document, make_revision

DOC = "d" * 64


async def anchored(
    client: FakeRegistryClient, *, no: int = 1, status: str = "APPROVED", seed: str = "1"
) -> Revision:
    """A Mongo revision plus its matching on-chain version (anchored through the fake)."""
    file_hash, text_root = seed * 64, chr(ord(seed) + 1) * 64
    receipt = await client.anchor_version(DOC, file_hash, text_root, 2)
    return make_revision(
        DOC,
        no,
        status=status,
        file_hash=file_hash,
        text_root=text_root,
        version_no=receipt.version_no,
        anchor={"status": "ANCHORED", "tx_hash": receipt.tx_hash},
    )


async def test_matching_record_is_ok() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client)

    got = await ChainCheckService(client).check(rev, DOC)

    assert got.performed and got.ok is True
    assert got.mismatches == () and got.reason is None
    assert got.tx_hash == rev.anchor.tx_hash


async def test_mongo_text_root_edited_directly_is_mismatch() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client)
    tampered = rev.model_copy(update={"text_root": "e" * 64})

    got = await ChainCheckService(client).check(tampered, DOC)

    assert got.performed and got.ok is False
    assert got.mismatches == ("text_root",)


async def test_mongo_file_hash_edited_is_mismatch() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client)

    got = await ChainCheckService(client).check(rev.model_copy(update={"file_hash": "e" * 64}), DOC)

    assert got.ok is False and got.mismatches == ("file_hash",)


async def test_canon_version_differs_is_mismatch() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client)

    got = await ChainCheckService(client).check(rev.model_copy(update={"canon_version": 3}), DOC)

    assert got.ok is False and got.mismatches == ("canon_version",)


async def test_several_fields_are_all_reported() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client)
    bad = rev.model_copy(update={"text_root": "e" * 64, "file_hash": "f" * 64})

    got = await ChainCheckService(client).check(bad, DOC)

    assert got.mismatches == ("file_hash", "text_root")


async def test_chain_revoked_but_mongo_approved_is_mismatch() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client)
    await client.revoke_version(DOC, 1, "oops")

    got = await ChainCheckService(client).check(rev, DOC)

    assert got.ok is False and got.mismatches == ("revoked",)


async def test_mongo_revoked_but_chain_active_is_mismatch() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client, status="REVOKED")

    got = await ChainCheckService(client).check(rev, DOC)

    assert got.ok is False and got.mismatches == ("revoked",)


async def test_revoked_on_both_sides_is_ok() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client, status="REVOKED")
    await client.revoke_version(DOC, 1, "oops")

    got = await ChainCheckService(client).check(rev, DOC)

    assert got.performed and got.ok is True


async def test_version_missing_on_chain_is_mismatch() -> None:
    client = FakeRegistryClient()
    rev = (await anchored(client)).model_copy(update={"version_no": 5})

    got = await ChainCheckService(client).check(rev, DOC)

    assert got.performed and got.ok is False
    assert got.reason == MISSING_ON_CHAIN and got.mismatches == (MISSING_ON_CHAIN,)


@pytest.mark.parametrize("status", ["NOT_REQUESTED", "ANCHORING", "FAILED"])
async def test_unanchored_revision_is_not_performed_and_reads_nothing(status: str) -> None:
    class Boom(FakeRegistryClient):
        async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None:
            raise AssertionError("must not read the chain")

    rev = make_revision(DOC, 1, status="APPROVED", version_no=1, anchor={"status": status})

    got = await ChainCheckService(Boom()).check(rev, DOC)

    assert (got.performed, got.ok, got.reason) == (False, None, NOT_ANCHORED)


async def test_anchored_without_version_no_is_not_performed() -> None:
    rev = make_revision(DOC, 1, anchor={"status": "ANCHORED"})

    got = await ChainCheckService(FakeRegistryClient()).check(rev, DOC)

    assert (got.performed, got.reason) == (False, NOT_ANCHORED)


async def test_no_registry_configured_is_not_performed() -> None:
    client = FakeRegistryClient()
    rev = await anchored(client)

    got = await ChainCheckService(None).check(rev, DOC)

    assert (got.performed, got.ok, got.reason) == (False, None, NOT_CONFIGURED)


async def test_chain_unavailable_is_not_a_mismatch() -> None:
    """Availability over guarantee: an outage never becomes a false RECORD_MISMATCH."""

    class Down(FakeRegistryClient):
        async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None:
            raise ChainUnavailableError("node down: secret-internal-host")

    rev = await anchored(FakeRegistryClient())

    got = await ChainCheckService(Down()).check(rev, DOC)

    assert (got.performed, got.ok, got.reason) == (False, None, UNAVAILABLE)
    assert "secret" not in repr(got)


async def test_tampered_reference_revision_is_checked_and_detected(
    mongo_db: AsyncIOMotorDatabase,
) -> None:
    """TAMPERED path: the chain check runs on the reference chosen by ReferenceService (a
    superseded APPROVED revision here), not on the candidate; editing its Mongo root is caught."""
    await ensure_indexes(mongo_db)
    client = FakeRegistryClient()
    revs, trees = RevisionRepository(mongo_db), TreeRepository(mongo_db)
    doc = await DocumentRepository(mongo_db).insert(make_document(DOC))
    base = words("a", 10)
    stored: dict[int, Revision] = {}
    for no, texts in ((1, base), (2, words("z", 10))):
        t = tree(texts)
        receipt = await client.anchor_version(
            doc.chain_doc_id, t.file_hash, t.text_root, t.canon_version
        )
        rev = await revs.insert(
            make_revision(
                doc.id,
                no,
                status="APPROVED",
                file_hash=t.file_hash,
                text_root=t.text_root,
                version_no=receipt.version_no,
                anchor={"status": "ANCHORED", "tx_hash": receipt.tx_hash},
            )
        )
        await trees.upsert(tree_to_doc(t, rev.id, doc.id))
        stored[no] = rev
    cand = tree(base[:9] + [base[9].replace("dolor", "DOLOR")])  # tampered copy of v1

    ref = (await ReferenceService(revs, trees).localize_against(cand, doc.id)).reference
    assert ref is not None and ref.id == stored[1].id  # superseded, not the latest
    svc = ChainCheckService(client)
    assert (await svc.check(ref, doc.chain_doc_id)).ok is True

    await mongo_db["revisions"].update_one({"_id": ref.id}, {"$set": {"text_root": "e" * 64}})
    edited = await revs.get(ref.id)
    assert edited is not None
    got = await svc.check(edited, doc.chain_doc_id)

    assert got.ok is False and got.mismatches == ("text_root",)
