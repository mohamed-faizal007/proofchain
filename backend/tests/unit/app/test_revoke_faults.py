"""Revoke failure paths and concurrency (P5-05): chain first, idempotent retry, one tx."""

import asyncio
import contextlib
import logging

import pytest

from app.chain import OnChainVersion
from app.errors import AnchorFailedError, ChainUnavailableError, RevisionNotApprovedError
from app.models.revision import Anchor
from app.models.user import User
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.services.revocation import RevocationService
from tests.unit.app.anchor_harness import SECRET, Harness
from tests.unit.app.docs_env import Env
from tests.unit.app.revoke_helpers import RevokeClient, anchored_doc, install, on_chain, revoke


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ChainUnavailableError("down"), 503, "CHAIN_UNAVAILABLE"),
        (AnchorFailedError("Contract rejected the transaction"), 502, "ANCHOR_FAILED"),
    ],
)
def test_chain_failure_writes_nothing(env: Env, exc: Exception, status: int, code: str) -> None:
    client = install(env)
    _, approver, doc_id, rev_id = anchored_doc(env)
    client.revoke_failures.append(exc)

    r = revoke(env, approver, rev_id)

    assert (r.status_code, r.json()["error"]["code"]) == (status, code)
    stored = env.revision(rev_id)
    assert (stored["status"], stored["revocation"]) == ("APPROVED", None)
    assert env.events("VERSION_REVOKED") == []
    assert on_chain(env, doc_id, 1).revoked is False
    assert revoke(env, approver, rev_id).status_code == 200  # a plain retry works


def test_version_missing_on_chain_is_502_without_a_tx(env: Env) -> None:
    client = install(env)
    _, approver, _, rev_id = anchored_doc(env)
    client.missing_versions = True
    r = revoke(env, approver, rev_id)
    assert (r.status_code, r.json()["error"]["code"]) == (502, "ANCHOR_FAILED")
    assert client.revoke_calls == 0
    assert env.revision(rev_id)["status"] == "APPROVED"


def test_db_failure_after_chain_revoke_is_finished_by_a_retry_without_a_second_tx(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = install(env)
    _, approver, doc_id, rev_id = anchored_doc(env)
    real = RevisionRepository.mark_revoked
    calls = {"n": 0}

    async def flaky(self: RevisionRepository, *args: object, **kwargs: object) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(SECRET)
        return await real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(RevisionRepository, "mark_revoked", flaky)
    caplog.set_level(logging.ERROR)

    r = revoke(env, approver, rev_id)
    assert (r.status_code, r.json()["error"]["code"]) == (500, "INTERNAL_ERROR")
    assert SECRET not in r.text
    assert on_chain(env, doc_id, 1).revoked is True  # chain went first
    assert env.revision(rev_id)["status"] == "APPROVED"
    assert "retry the revoke" in caplog.text

    r = revoke(env, approver, rev_id)

    assert r.status_code == 200, r.text
    assert client.revoke_calls == 1  # found already revoked on-chain: no second tx
    assert r.json()["revocation"]["tx_hash"] is None
    [event] = env.events("VERSION_REVOKED")
    assert (event["data"]["already_revoked"], event["data"]["tx_hash"]) == (True, None)


def test_event_failure_still_returns_200_and_is_logged(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install(env)
    _, approver, _, rev_id = anchored_doc(env)
    real = EventRepository.append

    async def append(self: EventRepository, document_id: str, type_: str, **kw: object) -> object:
        if type_ == "VERSION_REVOKED":
            raise RuntimeError(SECRET)
        return await real(self, document_id, type_, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(EventRepository, "append", append)
    caplog.set_level(logging.ERROR)

    r = revoke(env, approver, rev_id)

    assert r.status_code == 200
    assert env.revision(rev_id)["status"] == "REVOKED"
    assert env.events("VERSION_REVOKED") == []  # the reconciler appends it (test_reconciler_revoke)
    assert "VERSION_REVOKED event not written (RuntimeError)" in caplog.text
    assert SECRET not in caplog.text


def test_pointer_failure_still_returns_200_and_is_logged(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install(env)
    _, approver, doc_id, rev_id = anchored_doc(env)

    async def broken(*args: object, **kwargs: object) -> bool:
        raise RuntimeError(SECRET)

    monkeypatch.setattr("app.repositories.documents.DocumentRepository.repair_pointer", broken)
    caplog.set_level(logging.ERROR)

    assert revoke(env, approver, rev_id).status_code == 200
    assert env.document(doc_id)["latest_approved_revision_id"] == rev_id  # stale, repaired later
    assert "pointer update failed (RuntimeError)" in caplog.text
    assert SECRET not in caplog.text


class SlowRevokeClient(RevokeClient):
    """Holds every get_version at a barrier so two revokes both pass their pre-checks."""

    def __init__(self) -> None:
        super().__init__()
        self.reads = 0
        self.both_read = asyncio.Event()

    async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None:
        # Read first, then wait: without the service lock both callers hold a stale
        # "not revoked" view and both send a tx (the second reverts AlreadyRevoked -> 502).
        seen = await super().get_version(doc_id, version_no)
        self.reads += 1
        if self.reads >= 2:
            self.both_read.set()
        # Serialized by the service lock, the second read never comes while we wait.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.both_read.wait(), timeout=0.2)
        return seen


async def test_concurrent_revokes_send_one_tx_and_one_event(hx: Harness) -> None:
    client = SlowRevokeClient()
    doc = await hx.document()
    anchor = Anchor(status="ANCHORED", tx_hash="0x" + "ab" * 32, block_number=1)
    await client.anchor_version(doc.chain_doc_id, "a" * 64, "b" * 64, 2)
    rev = await hx.revision(doc, 1, anchor=anchor, version_no=1)
    service = RevocationService(hx.documents, hx.revisions, hx.events, client)
    users = [
        User(email=f"a{i}@x.com", full_name="A", password_hash="x", roles=["APPROVER"])
        for i in range(2)
    ]

    results = await asyncio.gather(
        *(service.revoke(u, rev.id, "dup") for u in users), return_exceptions=True
    )

    winners = [r for r in results if not isinstance(r, BaseException)]
    losers = [r for r in results if isinstance(r, BaseException)]
    assert len(winners) == 1
    assert len(losers) == 1 and isinstance(losers[0], RevisionNotApprovedError)
    assert losers[0].details == {"status": "REVOKED"}
    assert client.revoke_calls == 1
    assert len(await hx.event_list("VERSION_REVOKED")) == 1
    assert (await hx.get(rev)).status == "REVOKED"
