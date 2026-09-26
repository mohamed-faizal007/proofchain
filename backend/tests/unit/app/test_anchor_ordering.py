"""AnchorService ordering (adjustment 1) and claims (adjustment 9), P5-04."""

import datetime as dt

import pytest

from app.errors import AnchorFailedError
from app.models.revision import Anchor
from app.services.anchoring import CLAIM_STALE_AFTER, now_ms
from tests.unit.app.anchor_harness import Harness

# --- ordering (adjustment 1) ---


async def test_newer_revision_waits_while_older_approved_is_unanchored(hx: Harness) -> None:
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="CHAIN_UNAVAILABLE"))
    v2 = await hx.revision(doc, 2)

    assert await hx.service().anchor(v2.id) == "QUEUED"
    assert hx.client.anchor_calls == 0
    got = await hx.get(v2)
    assert (got.anchor.status, got.anchor.attempted_at, got.anchor.attempts) == (
        "ANCHORING",
        None,
        0,
    )
    assert (await hx.get(v1)).anchor.status == "FAILED"


async def test_anchoring_the_predecessor_drains_queued_successors_in_order(hx: Harness) -> None:
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="ANCHOR_FAILED"))
    v2 = await hx.revision(doc, 2)
    v3 = await hx.revision(doc, 3)
    svc = hx.service()
    assert await svc.anchor(v3.id) == "QUEUED"

    assert await svc.anchor(v1.id, "retry") == "ANCHORED"

    assert [(await hx.get(r)).version_no for r in (v1, v2, v3)] == [1, 2, 3]
    v3_chain = await hx.client.get_version(doc.chain_doc_id, 3)
    assert v3_chain is not None and v3_chain.prev_text_root == v2.text_root
    triggers = [e["data"]["trigger"] for e in await hx.event_list("VERSION_ANCHORED")]
    assert triggers == ["retry", "successor", "successor"]


async def test_rejected_or_pending_older_revisions_do_not_block(hx: Harness) -> None:
    doc = await hx.document()
    await hx.revision(doc, 1, "REJECTED")
    v2 = await hx.revision(doc, 2)
    await hx.revision(doc, 3, "PENDING")
    assert await hx.service().anchor(v2.id) == "ANCHORED"


async def test_blocked_failed_revision_is_requeued_for_its_predecessor(hx: Harness) -> None:
    doc = await hx.document()
    await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="ANCHOR_FAILED"))
    v2 = await hx.revision(doc, 2, anchor=Anchor(status="FAILED", error="ANCHOR_FAILED"))
    assert await hx.service().anchor(v2.id, "reconcile") == "QUEUED"
    got = await hx.get(v2)
    assert (got.anchor.status, got.anchor.attempted_at) == ("ANCHORING", None)


async def test_blocked_failed_revision_proceeds_if_predecessor_anchored_meanwhile(
    hx: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Race: the predecessor anchors (and drains) between our check and our requeue."""
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=Anchor(status="ANCHORED"), version_no=1)
    v2 = await hx.revision(doc, 2, anchor=Anchor(status="FAILED", error="ANCHOR_FAILED"))
    await hx.client.anchor_version(doc.chain_doc_id, v1.file_hash, v1.text_root, 2)
    real = hx.revisions.find_unanchored_predecessor
    answers = [v1]  # first check still sees v1 unanchored

    async def racy(document_id: str, revision_no: int):  # type: ignore[no-untyped-def]
        return answers.pop(0) if answers else await real(document_id, revision_no)

    monkeypatch.setattr(hx.revisions, "find_unanchored_predecessor", racy)
    assert await hx.service().anchor(v2.id, "reconcile") == "ANCHORED"
    assert (await hx.get(v2)).version_no == 2


# --- claims (adjustment 9) ---


async def test_in_flight_claim_is_not_taken(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1, anchor=Anchor(status="ANCHORING", attempted_at=now_ms()))
    assert await hx.service().anchor(rev.id, "reconcile") == "SKIPPED"
    assert hx.client.anchor_calls == 0


async def test_stuck_claim_is_taken_over(hx: Harness) -> None:
    doc = await hx.document()
    old = now_ms() - CLAIM_STALE_AFTER - dt.timedelta(seconds=1)
    rev = await hx.revision(doc, 1, anchor=Anchor(status="ANCHORING", attempted_at=old, attempts=1))
    assert await hx.service().anchor(rev.id, "reconcile") == "ANCHORED"
    got = await hx.get(rev)
    assert got.anchor.attempts == 2 and got.anchor.attempted_at is not None
    assert got.anchor.attempted_at > old


async def test_failure_mid_drain_leaves_later_revisions_queued(hx: Harness) -> None:
    """3-deep queue: v1 retry drains v2, then v3 FAILS; v4 (behind v3) stays queued, unsent."""
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="CHAIN_UNAVAILABLE"))
    v2, v3, v4 = [await hx.revision(doc, n) for n in (2, 3, 4)]  # queued behind v1
    svc = hx.service()
    real = hx.client.anchor_version
    sent: list[str] = []

    async def v3_rejected(doc_id: str, file_hash: str, text_root: str, canon: int):  # type: ignore[no-untyped-def]
        sent.append(text_root)
        if text_root == v3.text_root:
            raise AnchorFailedError("Contract rejected the transaction")
        return await real(doc_id, file_hash, text_root, canon)

    hx.client.anchor_version = v3_rejected  # type: ignore[method-assign]
    assert await svc.anchor(v1.id, "retry") == "ANCHORED"

    assert sent == [v1.text_root, v2.text_root, v3.text_root]  # v4 never sent
    got = [await hx.get(r) for r in (v1, v2, v3, v4)]
    assert [g.version_no for g in got] == [1, 2, None, None]
    assert (got[2].anchor.status, got[2].anchor.error) == ("FAILED", "ANCHOR_FAILED")
    assert (got[3].anchor.status, got[3].anchor.attempted_at, got[3].anchor.attempts) == (
        "ANCHORING",
        None,
        0,
    )
    assert await hx.client.version_count(doc.chain_doc_id) == 2

    # Retrying v3 anchors it and then drains v4, in order.
    hx.client.anchor_version = real  # type: ignore[method-assign]
    await svc.request_retry(v3.id)
    assert await svc.anchor(v3.id, "retry") == "ANCHORED"
    assert [(await hx.get(r)).version_no for r in (v1, v2, v3, v4)] == [1, 2, 3, 4]
