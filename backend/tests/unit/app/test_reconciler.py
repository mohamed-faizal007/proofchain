"""Reconciler (P5-04): missing review / anchor events, anchor retries, stale pointers."""

import datetime as dt

import pytest

from app.models.revision import Anchor
from app.services.anchoring import CLAIM_STALE_AFTER, now_ms
from app.services.reconciler import GRACE
from tests.unit.app.anchor_harness import CONTRACT, SECRET, Harness

EVENT = {"APPROVED": "REVISION_APPROVED", "REJECTED": "REVISION_REJECTED"}
OLD = GRACE + dt.timedelta(seconds=1)


def anchored(version_no: int, at: dt.datetime | None = None) -> Anchor:
    return Anchor(
        status="ANCHORED",
        tx_hash="0x" + "ab" * 32,
        block_number=7 + version_no,
        chain_id=31337,
        contract=CONTRACT,
        anchored_at=at or now_ms() - OLD,
        attempts=1,
    )


# --- 1. reviewed revisions with no review event (P2-review finding) ---


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
async def test_missing_review_event_is_appended_once(hx: Harness, status: str) -> None:
    doc = await hx.document()
    extra = {"anchor": anchored(1), "version_no": 1} if status == "APPROVED" else {}
    rev = await hx.revision(doc, 1, status, reviewed_ago=OLD, **extra)
    await hx.events.append(doc.id, "DOCUMENT_CREATED", actor_id="issuer")

    report = await hx.reconciler().run_once()

    assert report.review_events == 1
    [event] = await hx.event_list(EVENT[status])
    assert (event["revision_id"], event["actor_id"]) == (rev.id, "approver-1")
    assert event["data"] == {"revision_no": 1, "comment": "ok", "reconciled": True}
    assert (await hx.events.verify_chain(doc.id)).ok
    # idempotent
    assert (await hx.reconciler().run_once()).review_events == 0
    assert len(await hx.event_list(EVENT[status])) == 1


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
async def test_present_review_event_is_left_alone(hx: Harness, status: str) -> None:
    doc = await hx.document()
    extra = {"anchor": anchored(1), "version_no": 1} if status == "APPROVED" else {}
    rev = await hx.revision(doc, 1, status, reviewed_ago=OLD, **extra)
    await hx.events.append(
        doc.id,
        EVENT[status],
        actor_id="approver-1",
        revision_id=rev.id,  # type: ignore[arg-type]
    )
    assert (await hx.reconciler().run_once()).review_events == 0
    assert len(await hx.event_list(EVENT[status])) == 1


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
async def test_review_inside_grace_window_is_skipped(hx: Harness, status: str) -> None:
    """A review whose event append may still be in flight is not recorded twice."""
    doc = await hx.document()
    extra = {"anchor": anchored(1), "version_no": 1} if status == "APPROVED" else {}
    await hx.revision(doc, 1, status, reviewed_ago=dt.timedelta(seconds=10), **extra)
    assert (await hx.reconciler().run_once()).review_events == 0
    assert await hx.event_list(EVENT[status]) == []


async def test_pending_revision_gets_no_review_event(hx: Harness) -> None:
    doc = await hx.document()
    await hx.revision(doc, 1, "PENDING")
    await hx.reconciler().run_once()
    assert await hx.event_list() == []


# --- 2. ANCHORED revisions with no VERSION_ANCHORED event (adjustment 5) ---


async def test_missing_anchor_event_is_appended_from_stored_anchor(hx: Harness) -> None:
    doc = await hx.document()
    await hx.events.append(doc.id, "DOCUMENT_CREATED", actor_id="issuer")
    rev = await hx.revision(doc, 1, anchor=anchored(3), version_no=3)
    await hx.events.append(doc.id, "REVISION_APPROVED", actor_id="approver-1", revision_id=rev.id)

    report = await hx.reconciler().run_once()

    assert report.anchor_events == 1
    [event] = await hx.event_list("VERSION_ANCHORED")
    assert (event["revision_id"], event["actor_id"]) == (rev.id, None)
    assert event["data"] == {
        "version_no": 3,
        "tx_hash": "0x" + "ab" * 32,
        "block_number": 10,
        "chain_id": 31337,
        "contract": CONTRACT,
        "reconciled": True,
    }
    assert (await hx.events.verify_chain(doc.id)).ok
    assert hx.client.anchor_calls == 0  # repair only, nothing re-sent
    assert (await hx.reconciler().run_once()).anchor_events == 0
    assert len(await hx.event_list("VERSION_ANCHORED")) == 1


async def test_recovered_anchor_with_null_tx_hash_is_repaired_too(hx: Harness) -> None:
    doc = await hx.document()
    anchor = anchored(1).model_copy(update={"tx_hash": None, "block_number": None})
    await hx.revision(doc, 1, anchor=anchor, version_no=1)
    await hx.reconciler().run_once()
    [event] = await hx.event_list("VERSION_ANCHORED")
    assert (event["data"]["tx_hash"], event["data"]["block_number"]) == (None, None)


async def test_present_anchor_event_is_left_alone(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1, anchor=anchored(1), version_no=1)
    await hx.events.append(doc.id, "VERSION_ANCHORED", revision_id=rev.id, data={"x": 1})
    assert (await hx.reconciler().run_once()).anchor_events == 0
    assert len(await hx.event_list("VERSION_ANCHORED")) == 1


async def test_anchor_inside_grace_window_is_skipped(hx: Harness) -> None:
    doc = await hx.document()
    fresh = anchored(1, at=now_ms() - dt.timedelta(seconds=5))
    await hx.revision(doc, 1, anchor=fresh, version_no=1)
    assert (await hx.reconciler().run_once()).anchor_events == 0
    assert await hx.event_list("VERSION_ANCHORED") == []


async def test_anchor_whose_event_append_failed_is_repaired_end_to_end(
    hx: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    real_append = hx.events.append

    async def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(hx.events, "append", broken)
    assert await hx.service().anchor(rev.id) == "ANCHORED"
    monkeypatch.setattr(hx.events, "append", real_append)
    assert await hx.event_list("VERSION_ANCHORED") == []

    later = now_ms() + OLD
    assert (await hx.reconciler().run_once(now=later)).anchor_events == 1
    [event] = await hx.event_list("VERSION_ANCHORED")
    got = await hx.get(rev)
    assert event["data"]["tx_hash"] == got.anchor.tx_hash and event["data"]["version_no"] == 1
    assert hx.client.anchor_calls == 1
    assert (await hx.events.verify_chain(doc.id)).ok


async def test_failed_anchor_missing_its_event_is_not_backfilled(hx: Harness) -> None:
    """Deliberate: the retry supersedes the lost ANCHOR_FAILED and writes its own events."""
    doc = await hx.document()
    rev = await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="CHAIN_UNAVAILABLE"))
    hx.client.failures = [AssertionError("still failing")]
    await hx.reconciler().run_once()
    [event] = await hx.event_list("ANCHOR_FAILED")  # only the retry's own event
    assert event["data"]["trigger"] == "reconcile" and event["data"]["error"] == "UNEXPECTED_ERROR"
    assert event["revision_id"] == rev.id


# --- 3. anchor retries ---


async def test_failed_queued_and_stuck_anchors_are_resent(hx: Harness) -> None:
    stale = now_ms() - CLAIM_STALE_AFTER - dt.timedelta(seconds=1)
    a, b, c = await hx.document("a"), await hx.document("b"), await hx.document("c")
    failed = await hx.revision(a, 1, anchor=Anchor(status="FAILED", error="CHAIN_UNAVAILABLE"))
    queued = await hx.revision(b, 1)
    stuck = await hx.revision(c, 1, anchor=Anchor(status="ANCHORING", attempted_at=stale))

    report = await hx.reconciler().run_once()

    assert report.anchors_attempted == 3
    for rev in (failed, queued, stuck):
        got = await hx.get(rev)
        assert (got.anchor.status, got.version_no) == ("ANCHORED", 1)
    triggers = {e["data"]["trigger"] for e in await hx.event_list("VERSION_ANCHORED")}
    assert triggers == {"reconcile"}


async def test_in_flight_claim_is_not_resent(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1, anchor=Anchor(status="ANCHORING", attempted_at=now_ms()))
    assert (await hx.reconciler().run_once()).anchors_attempted == 0
    assert hx.client.anchor_calls == 0
    assert (await hx.get(rev)).anchor.status == "ANCHORING"


async def test_resend_keeps_revision_order(hx: Harness) -> None:
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="CHAIN_UNAVAILABLE"))
    v2 = await hx.revision(doc, 2)
    v3 = await hx.revision(doc, 3, anchor=Anchor(status="FAILED", error="CHAIN_UNAVAILABLE"))
    await hx.reconciler().run_once()
    assert [(await hx.get(r)).version_no for r in (v1, v2, v3)] == [1, 2, 3]


@pytest.mark.parametrize("status", ["PENDING", "REJECTED"])
async def test_reconciler_path_refuses_non_approved_revision(
    hx: Harness, status: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Invariant via the reconciler: a corrupt FAILED anchor on a non-APPROVED revision."""
    doc = await hx.document()
    rev = await hx.revision(doc, 1, status, anchor=Anchor(status="FAILED"))
    report = await hx.reconciler().run_once()
    assert (report.anchors_attempted, report.errors) == (1, 1)
    assert "reconcile anchor skipped (REVISION_NOT_APPROVED)" in caplog.text
    assert hx.client.anchor_calls == 0
    assert (await hx.get(rev)).anchor == Anchor(status="FAILED")


# --- 4. stale pointer (P5-03 pointer Accept line) ---


async def test_stale_pointer_is_repaired(hx: Harness) -> None:
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=anchored(1), version_no=1, reviewed_ago=2 * OLD)
    v2 = await hx.revision(doc, 2, anchor=anchored(2), version_no=2, reviewed_ago=OLD)
    await hx.documents.set_latest_approved(doc.id, v1.id, now_ms())  # v2's pointer write lost

    assert (await hx.reconciler().run_once()).pointers == 1
    stored = await hx.documents.get(doc.id)
    assert stored is not None
    assert (stored.latest_approved_revision_id, stored.latest_approved_version_no) == (v2.id, 2)
    assert (await hx.reconciler().run_once()).pointers == 0


async def test_stale_version_no_is_repaired(hx: Harness) -> None:
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=anchored(1), version_no=1, reviewed_ago=OLD)
    await hx.documents.set_latest_approved(doc.id, v1.id, now_ms())  # version_no left null
    assert (await hx.reconciler().run_once()).pointers == 1
    stored = await hx.documents.get(doc.id)
    assert stored is not None and stored.latest_approved_version_no == 1


async def test_correct_pointer_is_untouched(hx: Harness) -> None:
    doc = await hx.document()
    v1 = await hx.revision(doc, 1, anchor=anchored(1), version_no=1, reviewed_ago=OLD)
    await hx.documents.set_latest_approved(doc.id, v1.id, now_ms())
    await hx.documents.set_latest_version_no(doc.id, v1.id, 1, now_ms())
    before = await hx.documents.get(doc.id)
    assert (await hx.reconciler().run_once()).pointers == 0
    assert await hx.documents.get(doc.id) == before


async def test_pointer_of_approval_inside_grace_window_is_left_alone(hx: Harness) -> None:
    doc = await hx.document()
    await hx.revision(doc, 1, reviewed_ago=dt.timedelta(seconds=5))
    assert (await hx.reconciler(chain=False).run_once()).pointers == 0
    stored = await hx.documents.get(doc.id)
    assert stored is not None and stored.latest_approved_revision_id is None


# --- pass isolation ---


async def test_a_failing_step_does_not_stop_the_others(
    hx: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="CHAIN_UNAVAILABLE"))

    async def broken(*args: object, **kwargs: object) -> set[str]:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(hx.events, "revision_ids_with_event", broken)
    report = await hx.reconciler().run_once()
    assert report.errors == 2  # review-event and anchor-event steps
    assert (await hx.get(rev)).anchor.status == "ANCHORED"
    assert SECRET not in caplog.text
