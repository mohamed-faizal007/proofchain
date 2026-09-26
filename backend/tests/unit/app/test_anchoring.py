"""AnchorService (P5-04): invariant, success/failure writes, retries, ordering, claims, pointer."""

import logging

import pytest

from app.errors import (
    AnchorFailedError,
    ChainUnavailableError,
    NotFoundError,
    RevisionNotApprovedError,
)
from app.models.revision import Anchor
from app.services import anchoring
from app.services.anchoring import now_ms, run_anchor_job
from tests.unit.app.anchor_harness import CONTRACT, SECRET, Harness

UNREACHABLE = ChainUnavailableError("Blockchain node unreachable or timed out")
REVERT = AnchorFailedError("Contract rejected the transaction")


# --- invariant: only APPROVED revisions are anchored ---


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "REVOKED"])
async def test_direct_call_on_non_approved_revision_raises_and_writes_nothing(
    hx: Harness, status: str
) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1, status, anchor=Anchor(status="FAILED"))
    with pytest.raises(RevisionNotApprovedError) as info:
        await hx.service().anchor(rev.id)
    assert (info.value.code, info.value.status_code) == ("REVISION_NOT_APPROVED", 409)
    assert hx.client.anchor_calls == 0
    assert (await hx.get(rev)).anchor == Anchor(status="FAILED")
    assert await hx.event_list() == []


async def test_missing_revision_is_not_found(hx: Harness) -> None:
    with pytest.raises(NotFoundError):
        await hx.service().anchor("nope")


# --- success path ---


async def test_anchor_records_state_event_and_pointer(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    await hx.documents.set_latest_approved(doc.id, rev.id, now_ms())

    assert await hx.service().anchor(rev.id) == "ANCHORED"

    got = await hx.get(rev)
    assert (got.anchor.status, got.version_no, got.anchor.attempts) == ("ANCHORED", 1, 1)
    assert got.anchor.tx_hash is not None and got.anchor.tx_hash.startswith("0x")
    assert (got.anchor.chain_id, got.anchor.contract, got.anchor.error) == (31337, CONTRACT, None)
    assert got.anchor.anchored_at is not None and got.anchor.attempted_at is not None
    [event] = await hx.event_list("VERSION_ANCHORED")
    assert event["revision_id"] == rev.id and event["actor_id"] is None
    assert event["data"] == {
        "version_no": 1,
        "tx_hash": got.anchor.tx_hash,
        "block_number": got.anchor.block_number,
        "chain_id": 31337,
        "contract": CONTRACT,
        "already_anchored": False,
        "trigger": "approve",
    }
    stored_doc = await hx.documents.get(doc.id)
    assert stored_doc is not None
    assert (stored_doc.latest_approved_revision_id, stored_doc.latest_approved_version_no) == (
        rev.id,
        1,
    )
    on_chain = await hx.client.get_version(doc.chain_doc_id, 1)
    assert on_chain is not None and (on_chain.file_hash, on_chain.text_root) == (
        rev.file_hash,
        rev.text_root,
    )
    assert (await hx.events.verify_chain(doc.id)).ok


async def test_second_call_is_idempotent_no_new_tx_or_event(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    svc = hx.service()
    await svc.anchor(rev.id)
    before = await hx.get(rev)

    assert await svc.anchor(rev.id) == "ALREADY_ANCHORED"
    assert hx.client.anchor_calls == 1
    assert await hx.get(rev) == before
    assert len(await hx.event_list("VERSION_ANCHORED")) == 1
    assert await hx.client.version_count(doc.chain_doc_id) == 1


async def test_version_already_on_chain_is_recovered_with_null_tx_hash(hx: Harness) -> None:
    """Adjustment 3: e.g. a receipt timeout marked FAILED, but the tx was mined after all."""
    doc = await hx.document()
    rev = await hx.revision(doc, 1, anchor=Anchor(status="FAILED", error="ANCHOR_FAILED"))
    await hx.client.anchor_version(doc.chain_doc_id, rev.file_hash, rev.text_root, 2)

    assert await hx.service().anchor(rev.id, "retry") == "ANCHORED"

    got = await hx.get(rev)
    assert (got.anchor.status, got.version_no, got.anchor.tx_hash) == ("ANCHORED", 1, None)
    assert got.anchor.block_number is None
    [event] = await hx.event_list("VERSION_ANCHORED")
    assert (event["data"]["already_anchored"], event["data"]["tx_hash"]) == (True, None)
    assert await hx.client.version_count(doc.chain_doc_id) == 1


# --- failure paths and retries (adjustments 2 and 4) ---


async def test_failed_then_retry_then_anchored(hx: Harness) -> None:
    """TASKS Accept: FAILED -> retry -> ANCHORED with the fake client."""
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    hx.client.failures = [REVERT]
    svc = hx.service()
    assert await svc.anchor(rev.id) == "FAILED"
    assert (await hx.get(rev)).anchor.status == "FAILED"

    _, scheduled = await svc.request_retry(rev.id)
    assert scheduled is True
    assert await svc.anchor(rev.id, "retry") == "ANCHORED"
    got = await hx.get(rev)
    assert (got.anchor.status, got.anchor.attempts, got.anchor.error) == ("ANCHORED", 2, None)
    assert [e["type"] for e in await hx.event_list()] == ["ANCHOR_FAILED", "VERSION_ANCHORED"]


async def test_unreachable_chain_is_retried_with_1s_then_4s_backoff(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    hx.client.failures = [UNREACHABLE, UNREACHABLE]

    assert await hx.service().anchor(rev.id) == "ANCHORED"
    assert (hx.client.anchor_calls, hx.sleeps) == (3, [1.0, 4.0])
    assert (await hx.get(rev)).anchor.attempts == 1  # one claim, three chain calls
    assert await hx.event_list("ANCHOR_FAILED") == []


async def test_unreachable_chain_fails_after_three_attempts(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    hx.client.failures = [UNREACHABLE, UNREACHABLE, UNREACHABLE, UNREACHABLE]

    assert await hx.service().anchor(rev.id) == "FAILED"
    assert (hx.client.anchor_calls, hx.sleeps) == (3, [1.0, 4.0])
    got = await hx.get(rev)
    assert (got.anchor.status, got.anchor.error, got.version_no) == (
        "FAILED",
        "CHAIN_UNAVAILABLE",
        None,
    )
    [event] = await hx.event_list("ANCHOR_FAILED")
    assert event["data"] == {"error": "CHAIN_UNAVAILABLE", "attempts": 1, "trigger": "approve"}


async def test_contract_revert_is_not_retried(hx: Harness) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    hx.client.failures = [REVERT]

    assert await hx.service().anchor(rev.id) == "FAILED"
    assert (hx.client.anchor_calls, hx.sleeps) == (1, [])
    assert (await hx.get(rev)).anchor.error == "ANCHOR_FAILED"


async def test_unexpected_error_fails_with_code_only(
    hx: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    hx.client.failures = [RuntimeError(SECRET)]

    assert await hx.service().anchor(rev.id) == "FAILED"
    assert hx.client.anchor_calls == 1
    got = await hx.get(rev)
    assert got.anchor.error == "UNEXPECTED_ERROR"
    assert SECRET not in str(await hx.event_list())
    assert SECRET not in caplog.text


async def test_no_chain_configured_fails_with_code_and_event(hx: Harness) -> None:
    """Adjustment 4."""
    doc = await hx.document()
    rev = await hx.revision(doc, 1)

    assert await hx.service(chain=False).anchor(rev.id) == "FAILED"
    got = await hx.get(rev)
    assert (got.anchor.status, got.anchor.error, got.anchor.attempts) == (
        "FAILED",
        "CHAIN_NOT_CONFIGURED",
        1,
    )
    [event] = await hx.event_list("ANCHOR_FAILED")
    assert event["data"]["error"] == "CHAIN_NOT_CONFIGURED"


async def test_event_failure_after_chain_success_keeps_anchored_state(
    hx: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)

    async def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(hx.events, "append", broken)
    assert await hx.service().anchor(rev.id) == "ANCHORED"
    assert (await hx.get(rev)).anchor.status == "ANCHORED"
    assert "VERSION_ANCHORED event not written (RuntimeError)" in caplog.text
    assert SECRET not in caplog.text


async def test_pointer_failure_is_logged_not_raised(
    hx: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1)

    async def broken(*args: object, **kwargs: object) -> bool:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(hx.documents, "set_latest_version_no", broken)
    assert await hx.service().anchor(rev.id) == "ANCHORED"
    assert "pointer update failed (RuntimeError)" in caplog.text
    assert SECRET not in caplog.text


# --- document pointer (adjustment 8) ---


async def test_version_pointer_not_set_when_document_points_elsewhere(hx: Harness) -> None:
    doc = await hx.document()
    v1 = await hx.revision(doc, 1)
    v2 = await hx.revision(doc, 2, "PENDING")
    await hx.documents.set_latest_approved(doc.id, v2.id, now_ms())  # e.g. v2 approved meanwhile
    await hx.service().anchor(v1.id)
    stored = await hx.documents.get(doc.id)
    assert stored is not None
    assert (stored.latest_approved_revision_id, stored.latest_approved_version_no) == (
        v2.id,
        None,
    )


# --- admin retry request ---


@pytest.mark.parametrize("status", ["PENDING", "REJECTED"])
async def test_retry_request_on_non_approved_raises(hx: Harness, status: str) -> None:
    doc = await hx.document()
    rev = await hx.revision(doc, 1, status)
    with pytest.raises(RevisionNotApprovedError):
        await hx.service().request_retry(rev.id)


async def test_run_anchor_job_never_raises(
    hx: Harness, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.ERROR)
    await run_anchor_job(hx.service(), "nope", "approve")
    assert "anchoring job failed (NOT_FOUND)" in caplog.text
    monkeypatch.setattr(anchoring, "RETRY_BACKOFF_SECONDS", ())
    doc = await hx.document()
    rev = await hx.revision(doc, 1)
    hx.client.failures = [UNREACHABLE]
    await run_anchor_job(hx.service(), rev.id, "approve")
    assert (hx.client.anchor_calls, (await hx.get(rev)).anchor.error) == (1, "CHAIN_UNAVAILABLE")
