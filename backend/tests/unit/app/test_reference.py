"""P6-02 closest approved version + localization (02 §9-10)."""

import hashlib

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import ensure_indexes
from app.errors import NotFoundError
from app.models.document import Document
from app.models.revision import Revision
from app.repositories.documents import DocumentRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.services import reference as reference_mod
from app.services.reference import CANON_MISMATCH, NO_APPROVED, ReferenceService
from app.services.tree_mapping import tree_to_doc
from proofchain_core.types import BBox, Chunk, IntegrityTree, LocalizationStatus, Page
from tests.unit.repositories.factories import make_document, make_revision

CANON = 2


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def tree(texts: list[str], canon_version: int = CANON) -> IntegrityTree:
    """One-page tree; chunk words are unique so equality is decided by the leaf hash."""
    chunks = tuple(
        Chunk(f"c{i}", 0, i, t, BBox(0.0, float(i), 1.0, i + 1.0), sha(t))
        for i, t in enumerate(texts)
    )
    root = sha("".join(c.leaf_hash for c in chunks))
    return IntegrityTree(canon_version, sha("f" + root), root, 1, (Page(0, root, chunks),), ())


def words(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i:03d} lorem ipsum dolor sit amet {prefix}{i:03d}" for i in range(n)]


class Env:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.docs = DocumentRepository(db)
        self.revs = RevisionRepository(db)
        self.trees = TreeRepository(db)
        self.svc = ReferenceService(self.revs, self.trees)

    async def doc(self) -> Document:
        return await self.docs.insert(make_document())

    async def rev(
        self, doc: Document, no: int, t: IntegrityTree, status: str = "APPROVED"
    ) -> Revision:
        rev = await self.revs.insert(
            make_revision(
                doc.id,
                no,
                status=status,
                file_hash=t.file_hash,
                text_root=t.text_root,
                canon_version=t.canon_version,
            )
        )
        await self.trees.upsert(tree_to_doc(t, rev.id, doc.id))
        return rev


@pytest.fixture
async def env(mongo_db: AsyncIOMotorDatabase) -> Env:
    await ensure_indexes(mongo_db)
    return Env(mongo_db)


async def test_picks_version_with_most_equal_chunks(env: Env) -> None:
    d = await env.doc()
    base = words("a", 10)
    v1 = await env.rev(d, 1, tree(base))
    await env.rev(d, 2, tree(words("z", 10)))  # latest, but nothing in common
    cand = tree(base[:9] + [base[9].replace("dolor", "DOLOR")])

    got = await env.svc.localize_against(cand, d.id)

    assert got.reference is not None and got.reference.id == v1.id
    assert got.localization is not None
    assert got.localization.status is LocalizationStatus.CHANGED
    assert got.localization.stats["modified"] == 1
    assert got.no_localization_reason is None


async def test_tie_prefers_latest_approved(env: Env) -> None:
    d = await env.doc()
    base = words("a", 5)
    await env.rev(d, 1, tree(base))
    v2 = await env.rev(d, 2, tree(base + ["extra qqqq"]))  # same equal count as v1
    cand = tree(base)
    # v1 is IDENTICAL, v2 has 5 equal too: 5 == 5
    got = await env.svc.localize_against(cand, d.id)
    assert got.reference is not None and got.reference.id == v2.id


async def test_absolute_equal_count_favours_longer_reference(env: Env) -> None:
    """INTERPRETATION pinned (02 §10 "most equal chunks", absolute, not a ratio): a longer
    reference with more equal chunks beats a shorter, proportionally closer one."""
    d = await env.doc()
    cand_texts = words("a", 10)
    long_ref = await env.rev(d, 1, tree(cand_texts[:9] + words("l", 11)))  # 20 chunks, 9 equal
    await env.rev(d, 2, tree(cand_texts[:8] + ["short qqqq"]))  # 9 chunks, 8 equal
    got = await env.svc.localize_against(tree(cand_texts), d.id)
    assert got.reference is not None and got.reference.id == long_ref.id


async def test_ignores_non_approved_and_revoked(env: Env) -> None:
    d = await env.doc()
    base = words("a", 6)
    far = await env.rev(d, 1, tree(words("z", 6)))
    for no, status in enumerate(["PENDING", "REJECTED", "REVOKED"], start=2):
        await env.rev(d, no, tree(base), status=status)  # exact match, never a reference
    got = await env.svc.localize_against(tree(base), d.id)
    assert got.reference is not None and got.reference.id == far.id


async def test_skips_other_canon_version_tree(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    d = await env.doc()
    base = words("a", 6)
    await env.rev(d, 1, tree(base, canon_version=CANON - 1))  # would be IDENTICAL-ish
    ok = await env.rev(d, 2, tree(words("z", 6)))
    seen: list[int] = []
    real = reference_mod.localize

    def spy(ref: IntegrityTree, cand: IntegrityTree):  # type: ignore[no-untyped-def]
        seen.append(ref.canon_version)
        return real(ref, cand)

    monkeypatch.setattr(reference_mod, "localize", spy)
    got = await env.svc.localize_against(tree(base), d.id)
    assert seen == [CANON]
    assert got.reference is not None and got.reference.id == ok.id


async def test_all_other_canon_returns_no_localization_with_reason(env: Env) -> None:
    d = await env.doc()
    await env.rev(d, 1, tree(words("a", 4), canon_version=CANON - 1))
    got = await env.svc.localize_against(tree(words("a", 4)), d.id)
    assert (got.reference, got.localization) == (None, None)
    assert got.no_localization_reason == CANON_MISMATCH


async def test_no_approved_revisions_returns_none(env: Env) -> None:
    d = await env.doc()
    await env.rev(d, 1, tree(words("a", 4)), status="PENDING")
    got = await env.svc.localize_against(tree(words("a", 4)), d.id)
    assert (got.reference, got.localization) == (None, None)
    assert got.no_localization_reason == NO_APPROVED


async def test_identical_reference_scores_all_chunks(env: Env) -> None:
    d = await env.doc()
    base = words("a", 4)
    v1 = await env.rev(d, 1, tree(base))
    got = await env.svc.localize_against(tree(base), d.id)
    assert got.reference is not None and got.reference.id == v1.id
    assert got.localization is not None
    assert got.localization.status is LocalizationStatus.IDENTICAL


async def test_missing_stored_tree_raises_not_found(
    env: Env, mongo_db: AsyncIOMotorDatabase
) -> None:
    d = await env.doc()
    v1 = await env.rev(d, 1, tree(words("a", 4)))
    await mongo_db["integrity_trees"].delete_one({"_id": v1.id})
    with pytest.raises(NotFoundError):
        await env.svc.localize_against(tree(words("a", 4)), d.id)
