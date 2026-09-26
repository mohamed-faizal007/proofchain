"""Approve/reject fault injection (P5-03).

Forward order: `set_review` (conditional on PENDING) -> event append -> (approve only) document
pointer. The event is the commit point:
- before it is known to be written, a failure reverts the revision to PENDING and the caller sees
  the original error (500, no exception text);
- if the revert itself fails, or it is unknown whether the event was written, the revision is left
  reviewed with no event: the state the P5-04 reconciler repairs by appending the missing event.
  It is never reverted blindly, since an event pointing at a PENDING revision could not be repaired;
- after the event is written the review has happened: a pointer failure is logged, not rolled back.
"""

import logging
from typing import Any

import pytest

from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from tests.unit.app.docs_env import Env

SECRET = "SECRET-INTERNAL-DETAIL-hunter2"
EVENT = {"approve": "REVISION_APPROVED", "reject": "REVISION_REJECTED"}
FINAL = {"approve": "APPROVED", "reject": "REJECTED"}
OK = {"approve": 202, "reject": 200}


def pending(env: Env) -> tuple[str, str]:
    reg = env.post_pdf(env.issuer()).json()
    return reg["revision"]["id"], reg["document"]["id"]


def fail(mp: pytest.MonkeyPatch, cls: type, name: str, mode: str = "before") -> None:
    original = getattr(cls, name)

    async def faulty(self: Any, *args: Any, **kwargs: Any) -> Any:
        if mode == "after":
            await original(self, *args, **kwargs)
        raise RuntimeError(SECRET)

    mp.setattr(cls, name, faulty)


def assert_pending_and_clean(env: Env, rev_id: str, doc_id: str, action: str) -> None:
    rev = env.revision(rev_id)
    assert (rev["status"], rev["reviewed_by"], rev["reviewed_at"], rev["review_comment"]) == (
        "PENDING",
        None,
        None,
        None,
    )
    assert rev["anchor"]["status"] == "NOT_REQUESTED"
    assert env.events(EVENT[action]) == []
    assert env.document(doc_id)["latest_approved_revision_id"] is None


def assert_500_without_secret(r: Any, caplog: pytest.LogCaptureFixture) -> None:
    assert (r.status_code, r.json()["error"]["code"]) == (500, "INTERNAL_ERROR")
    assert SECRET not in r.text
    assert SECRET not in "\n".join(
        rec.getMessage() for rec in caplog.records if rec.name.startswith("app.services")
    )


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize(
    ("step", "mode"),
    # an event that commits then raises is not "before the event": see the next test
    [("set_review", "before"), ("set_review", "after"), ("event", "before")],
)
def test_failure_before_the_event_is_written_reverts_to_pending(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    action: str,
    mode: str,
    step: str,
) -> None:
    rev_id, doc_id = pending(env)
    if step == "set_review":
        fail(monkeypatch, RevisionRepository, "set_review", mode)
    else:
        fail(monkeypatch, EventRepository, "append", mode)
    r = env.review(env.approver(), rev_id, action)
    monkeypatch.undo()

    assert_500_without_secret(r, caplog)
    assert_pending_and_clean(env, rev_id, doc_id, action)
    # nothing stuck: a retry by the same approver succeeds
    retry = env.review(env.auth(env.user(["APPROVER"], "a2@example.com")), rev_id, action)
    assert retry.status_code == OK[action], retry.text
    assert len(env.events(EVENT[action])) == 1


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_event_that_commits_then_raises_counts_as_reviewed(
    env: Env, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    rev_id, doc_id = pending(env)
    fail(monkeypatch, EventRepository, "append", "after")
    r = env.review(env.approver(), rev_id, action)
    monkeypatch.undo()

    assert r.status_code == OK[action], r.text
    assert env.revision(rev_id)["status"] == FINAL[action]
    assert len(env.events(EVENT[action])) == 1
    if action == "approve":
        assert env.document(doc_id)["latest_approved_revision_id"] == rev_id
    assert env.client.portal.call(EventRepository(env.db).verify_chain, doc_id).ok  # type: ignore[union-attr]


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_event_and_revert_both_fail_leaves_review_for_the_reconciler(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, action: str
) -> None:
    """Double failure: caller sees the ORIGINAL error (500 INTERNAL_ERROR, no exception text).

    The revision stays APPROVED/REJECTED with no event and no pointer move; the log names the
    ids so the P5-04 reconciler (TASKS.md Accept line) can append the missing event.
    """
    rev_id, doc_id = pending(env)
    approver = env.user(["APPROVER"], "approver@example.com")
    fail(monkeypatch, EventRepository, "append")
    fail(monkeypatch, RevisionRepository, "revert_review")
    caplog.set_level(logging.ERROR, logger="app.services.reviews")
    r = env.review(env.auth(approver), rev_id, action)
    monkeypatch.undo()

    assert_500_without_secret(r, caplog)
    rev = env.revision(rev_id)
    assert (rev["status"], rev["reviewed_by"]) == (FINAL[action], approver.id)
    assert rev["anchor"]["status"] == ("ANCHORING" if action == "approve" else "NOT_REQUESTED")
    assert env.events(EVENT[action]) == []
    assert env.document(doc_id)["latest_approved_revision_id"] is None
    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "without its provenance event" in logged and rev_id in logged and doc_id in logged
    # the review stands: a retry is refused rather than producing a second decision
    retry = env.review(env.approver("a2@example.com"), rev_id, action)
    assert (retry.status_code, retry.json()["error"]["code"]) == (409, "REVISION_NOT_PENDING")


def test_unknown_event_outcome_is_not_reverted(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Append fails and the follow-up lookup fails too: the event may exist, so never revert."""
    rev_id, _ = pending(env)
    fail(monkeypatch, EventRepository, "append")
    fail(monkeypatch, EventRepository, "list_by_document")
    reverts: list[str] = []
    monkeypatch.setattr(
        RevisionRepository,
        "revert_review",
        lambda *a, **k: reverts.append("x"),  # type: ignore[arg-type,return-value]
    )
    r = env.review(env.approver(), rev_id, "approve")
    monkeypatch.undo()

    assert_500_without_secret(r, caplog)
    assert reverts == []
    assert env.revision(rev_id)["status"] == "APPROVED"


def test_pointer_failure_after_the_event_is_logged_not_rolled_back(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rev_id, doc_id = pending(env)
    fail(monkeypatch, DocumentRepository, "set_latest_approved")
    caplog.set_level(logging.ERROR, logger="app.services.reviews")
    r = env.review(env.approver(), rev_id, "approve")
    monkeypatch.undo()

    assert r.status_code == 202, r.text
    assert env.revision(rev_id)["status"] == "APPROVED"
    assert len(env.events("REVISION_APPROVED")) == 1
    assert env.document(doc_id)["latest_approved_revision_id"] is None  # stale, logged
    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "latest_approved_revision_id not updated" in logged and doc_id in logged
    assert SECRET not in logged
