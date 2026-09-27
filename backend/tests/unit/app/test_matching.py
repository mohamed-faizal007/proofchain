"""P6-01 candidate matching (02 §11)."""

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import ensure_indexes
from app.errors import NotFoundError
from app.models.document import Document
from app.models.revision import Revision
from app.repositories.documents import DocumentRepository
from app.repositories.revisions import RevisionRepository
from app.services.matching import MatchingService
from proofchain_core.types import IntegrityTree
from tests.unit.repositories.factories import make_document, make_revision, now_ms

FH = "a" * 64
TR = "b" * 64


def cand(file_hash: str = FH, text_root: str = TR, canon_version: int = 2) -> IntegrityTree:
    return IntegrityTree(canon_version, file_hash, text_root, 1, (), ())


class Env:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.docs = DocumentRepository(db)
        self.revs = RevisionRepository(db)
        self.svc = MatchingService(self.docs, self.revs)

    async def doc(self, chain_doc_id: str = "aa") -> Document:
        return await self.docs.insert(make_document(chain_doc_id))

    async def rev(self, doc: Document, no: int, **kw: object) -> Revision:
        return await self.revs.insert(make_revision(doc.id, no, **kw))

    async def latest(self, doc: Document, rev: Revision) -> None:
        await self.docs.set_latest_approved(doc.id, rev.id, now_ms())


@pytest.fixture
async def env(mongo_db: AsyncIOMotorDatabase) -> Env:
    await ensure_indexes(mongo_db)
    return Env(mongo_db)


async def test_file_hash_matches_latest_approved(env: Env) -> None:
    d = await env.doc()
    r = await env.rev(d, 1, status="APPROVED")
    await env.latest(d, r)
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.id == r.id
    assert got.match_kind == "FILE_HASH"
    assert got.document is not None and got.document.id == d.id
    assert got.is_latest_approved is True


async def test_file_hash_matches_older_approved_is_not_latest(env: Env) -> None:
    d = await env.doc()
    old = await env.rev(d, 1, status="APPROVED")
    new = await env.rev(d, 2, status="APPROVED", file_hash="c" * 64, text_root="d" * 64)
    await env.latest(d, new)
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.id == old.id
    assert got.is_latest_approved is False


async def test_text_root_match_when_file_hash_differs(env: Env) -> None:
    d = await env.doc()
    r = await env.rev(d, 1, status="APPROVED")
    await env.latest(d, r)
    got = await env.svc.match(cand(file_hash="e" * 64))
    assert got.match is not None and got.match.id == r.id
    assert got.match_kind == "TEXT_ROOT"
    assert got.is_latest_approved is True


async def test_text_root_match_ignores_other_canon_version(env: Env) -> None:
    d = await env.doc()
    await env.rev(d, 1, status="APPROVED", canon_version=1)
    got = await env.svc.match(cand(file_hash="e" * 64, canon_version=2))
    assert got.match is None
    assert got.document is None


async def test_file_hash_takes_precedence_over_text_root(env: Env) -> None:
    d = await env.doc()
    by_text = await env.rev(d, 1, status="APPROVED", file_hash="c" * 64)
    by_file = await env.rev(d, 2, status="REJECTED", text_root="d" * 64)
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.id == by_file.id != by_text.id
    assert got.match_kind == "FILE_HASH"


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "REVOKED"])
async def test_non_approved_match_keeps_its_status(env: Env, status: str) -> None:
    d = await env.doc()
    await env.rev(d, 1, status=status)
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.status == status
    assert got.is_latest_approved is False


async def test_revoked_match_keeps_revocation_details(env: Env) -> None:
    d = await env.doc()
    await env.rev(
        d,
        1,
        status="REVOKED",
        revocation={"by": "u2", "at": now_ms(), "reason": "superseded by error"},
    )
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.revocation is not None
    assert got.match.revocation.reason == "superseded by error"


async def test_no_match_with_document_id_returns_the_document(env: Env) -> None:
    d = await env.doc()
    got = await env.svc.match(cand(), d.id)
    assert got.match is None and got.match_kind is None
    assert got.document is not None and got.document.id == d.id
    assert got.is_latest_approved is False


async def test_no_match_without_document_id_is_unknown(env: Env) -> None:
    await env.doc()
    got = await env.svc.match(cand())
    assert got.document is None and got.match is None


async def test_document_id_scopes_the_lookup(env: Env) -> None:
    d1 = await env.doc("aa")
    d2 = await env.doc("bb")
    await env.rev(d1, 1, status="APPROVED")
    got = await env.svc.match(cand(), d2.id)
    assert got.match is None
    assert got.document is not None and got.document.id == d2.id


async def test_unknown_document_id_is_not_found(env: Env) -> None:
    with pytest.raises(NotFoundError):
        await env.svc.match(cand(), "no-such-doc")


async def test_duplicate_hash_prefers_approved_over_rejected_copy(env: Env) -> None:
    d = await env.doc()
    approved = await env.rev(d, 1, status="APPROVED")
    await env.rev(d, 2, status="REJECTED")  # same bytes resubmitted later
    await env.latest(d, approved)
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.id == approved.id
    assert got.is_latest_approved is True


async def test_duplicate_hash_among_equals_takes_highest_revision_no(env: Env) -> None:
    d = await env.doc()
    await env.rev(d, 1, status="REVOKED")
    later = await env.rev(d, 2, status="REJECTED")
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.id == later.id


async def test_unscoped_match_resolves_the_owning_document(env: Env) -> None:
    await env.doc("aa")
    d2 = await env.doc("bb")
    r = await env.rev(d2, 1, status="APPROVED")
    await env.latest(d2, r)
    got = await env.svc.match(cand())
    assert got.document is not None and got.document.id == d2.id


async def test_stale_pointer_at_revoked_revision_is_not_latest_approved(env: Env) -> None:
    d = await env.doc()
    r = await env.rev(d, 1, status="REVOKED")
    await env.latest(d, r)  # pointer left behind after a failed repair
    got = await env.svc.match(cand())
    assert got.match is not None and got.match.status == "REVOKED"
    assert got.is_latest_approved is False
