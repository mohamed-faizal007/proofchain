"""Reconciler on REVOKED revisions (P5-05 Accept): missing revoke and approval events."""

import datetime as dt

from app.models.revision import Anchor, Revision, Revocation
from app.services.anchoring import now_ms
from app.services.reconciler import GRACE
from tests.unit.app.anchor_harness import CONTRACT, Harness

OLD = GRACE + dt.timedelta(seconds=1)


async def revoked(hx: Harness, revoked_ago: dt.timedelta = OLD) -> Revision:
    doc = await hx.document()
    anchor = Anchor(
        status="ANCHORED",
        tx_hash="0x" + "ab" * 32,
        block_number=8,
        chain_id=31337,
        contract=CONTRACT,
        anchored_at=now_ms() - OLD - dt.timedelta(minutes=1),
        attempts=1,
    )
    revocation = Revocation(
        by="approver-2",
        at=now_ms() - revoked_ago,
        reason="issued in error",
        tx_hash="0x" + "cd" * 32,
        block_number=9,
    )
    rev = await hx.revision(
        doc,
        1,
        "REVOKED",
        anchor=anchor,
        version_no=1,
        revocation=revocation,
        reviewed_ago=OLD + dt.timedelta(minutes=2),
    )
    for type_, actor in (("REVISION_APPROVED", "approver-1"), ("VERSION_ANCHORED", None)):
        await hx.events.append(doc.id, type_, actor_id=actor, revision_id=rev.id)  # type: ignore[arg-type]
    return rev


async def test_missing_version_revoked_event_is_appended_once(hx: Harness) -> None:
    rev = await revoked(hx)

    report = await hx.reconciler().run_once()

    assert report.revoke_events == 1
    [event] = await hx.event_list("VERSION_REVOKED")
    assert (event["revision_id"], event["actor_id"]) == (rev.id, "approver-2")
    assert event["data"] == {
        "version_no": 1,
        "reason": "issued in error",
        "tx_hash": "0x" + "cd" * 32,
        "block_number": 9,
        "already_revoked": False,
        "reconciled": True,
    }
    assert (await hx.events.verify_chain(rev.document_id)).ok
    assert (await hx.reconciler().run_once()).revoke_events == 0  # idempotent
    assert len(await hx.event_list("VERSION_REVOKED")) == 1


async def test_present_version_revoked_event_is_left_alone(hx: Harness) -> None:
    rev = await revoked(hx)
    await hx.events.append(
        rev.document_id,
        "VERSION_REVOKED",
        actor_id="approver-2",
        revision_id=rev.id,  # type: ignore[arg-type]
    )
    report = await hx.reconciler().run_once()
    assert (report.revoke_events, report.errors) == (0, 0)
    assert len(await hx.event_list("VERSION_REVOKED")) == 1


async def test_revocation_inside_grace_window_is_skipped(hx: Harness) -> None:
    await revoked(hx, revoked_ago=dt.timedelta(seconds=5))
    assert (await hx.reconciler().run_once()).revoke_events == 0
    assert await hx.event_list("VERSION_REVOKED") == []


async def test_revoked_revision_missing_its_approval_event_gets_it(hx: Harness) -> None:
    """A REVOKED revision was approved first; its REVISION_APPROVED event is repaired too."""
    rev = await revoked(hx)
    await hx.db["provenance_events"].delete_many({})  # rebuild the chain without the approval
    await hx.events.append(rev.document_id, "VERSION_REVOKED", revision_id=rev.id)  # type: ignore[arg-type]

    report = await hx.reconciler().run_once()

    assert report.review_events == 1
    [event] = await hx.event_list("REVISION_APPROVED")
    assert (event["revision_id"], event["actor_id"]) == (rev.id, "approver-1")


async def test_revoked_revision_is_never_re_anchored(hx: Harness) -> None:
    await revoked(hx)
    report = await hx.reconciler().run_once()
    assert (report.anchors_attempted, hx.client.anchor_calls) == (0, 0)


async def test_pointer_to_a_revoked_revision_is_cleared(hx: Harness) -> None:
    """The pointer repair treats a revoked revision as not approved (was unreachable pre-P5-05)."""
    rev = await revoked(hx)
    await hx.db["documents"].update_one(
        {"_id": rev.document_id},
        {"$set": {"latest_approved_revision_id": rev.id, "latest_approved_version_no": 1}},
    )
    report = await hx.reconciler().run_once()
    assert report.pointers == 1
    doc = await hx.documents.get(rev.document_id)
    assert doc is not None
    assert (doc.latest_approved_revision_id, doc.latest_approved_version_no) == (None, None)
