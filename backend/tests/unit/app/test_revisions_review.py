"""POST /revisions/{id}/approve|reject (P5-03): maker-checker review and provenance events."""

from typing import Any

import pytest

from app.repositories.events import EventRepository
from tests.unit.app.docs_env import Env


def registered(env: Env, email: str = "issuer@example.com") -> tuple[dict[str, str], Any]:
    headers = env.auth(env.user(["ISSUER"], email))
    r = env.post_pdf(headers)
    assert r.status_code == 201, r.text
    return headers, r.json()


def chain_ok(env: Env, document_id: str) -> bool:
    repo = EventRepository(env.db)
    return bool(env.client.portal.call(repo.verify_chain, document_id).ok)  # type: ignore[union-attr]


def test_approve_returns_202_and_records_state_pointer_and_event(env: Env) -> None:
    _, reg = registered(env)
    rev_id, doc_id = reg["revision"]["id"], reg["document"]["id"]
    approver = env.user(["APPROVER"], "approver@example.com")

    r = env.review(env.auth(approver), rev_id, "approve", "looks right")

    assert r.status_code == 202, r.text
    body = r.json()
    assert (body["id"], body["status"], body["anchor"]["status"]) == (
        rev_id,
        "APPROVED",
        "ANCHORING",
    )
    assert (body["reviewed_by"], body["review_comment"]) == (approver.id, "looks right")
    stored = env.revision(rev_id)
    assert (stored["status"], stored["reviewed_by"], stored["anchor"]["status"]) == (
        "APPROVED",
        approver.id,
        "ANCHORING",
    )
    doc = env.document(doc_id)
    assert doc["latest_approved_revision_id"] == rev_id
    assert doc["latest_approved_version_no"] is None  # set when anchored (P5-04)
    [event] = env.events("REVISION_APPROVED")
    assert (event["revision_id"], event["actor_id"]) == (rev_id, approver.id)
    assert event["data"] == {"revision_no": 1, "comment": "looks right"}
    assert event["at"] == stored["reviewed_at"]
    assert chain_ok(env, doc_id)


def test_approve_comment_is_optional(env: Env) -> None:
    _, reg = registered(env)
    r = env.review(env.approver(), reg["revision"]["id"], "approve", comment=None)
    assert r.status_code == 202, r.text
    assert r.json()["review_comment"] is None
    assert env.events("REVISION_APPROVED")[0]["data"]["comment"] is None


def test_reject_returns_200_and_records_state_and_event_without_pointer(env: Env) -> None:
    _, reg = registered(env)
    rev_id, doc_id = reg["revision"]["id"], reg["document"]["id"]
    r = env.review(env.approver(), rev_id, "reject", "  wrong annex  ")
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["review_comment"]) == ("REJECTED", "wrong annex")
    assert r.json()["anchor"]["status"] == "NOT_REQUESTED"
    assert env.revision(rev_id)["status"] == "REJECTED"
    assert env.document(doc_id)["latest_approved_revision_id"] is None
    [event] = env.events("REVISION_REJECTED")
    assert event["data"] == {"revision_no": 1, "comment": "wrong annex"}
    assert env.events("REVISION_APPROVED") == []
    assert chain_ok(env, doc_id)


@pytest.mark.parametrize(
    "comment", [None, "", "   ", "x" * 2001], ids=["missing", "empty", "blank", "too_long"]
)
def test_reject_needs_a_valid_comment(env: Env, comment: str | None) -> None:
    _, reg = registered(env)
    rev_id = reg["revision"]["id"]
    r = env.review(env.approver(), rev_id, "reject", comment)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert env.revision(rev_id)["status"] == "PENDING"
    assert env.events("REVISION_REJECTED") == []


def test_approve_comment_too_long_is_422(env: Env) -> None:
    _, reg = registered(env)
    r = env.review(env.approver(), reg["revision"]["id"], "approve", "x" * 2001)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert env.revision(reg["revision"]["id"])["status"] == "PENDING"


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_submitter_cannot_review_own_revision(env: Env, action: str) -> None:
    both = env.user(["ISSUER", "APPROVER"], "both@example.com")
    reg = env.post_pdf(env.auth(both)).json()
    rev_id = reg["revision"]["id"]
    r = env.review(env.auth(both), rev_id, action)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "SELF_APPROVAL_FORBIDDEN")
    assert env.revision(rev_id)["status"] == "PENDING"
    assert len(env.events()) == 2  # DOCUMENT_CREATED + REVISION_SUBMITTED only


def test_unrelated_approver_can_approve_other_issuers_revisions(env: Env) -> None:
    """Only maker != checker: no ownership, team or prior-contact rule for the approver."""
    _, reg_a = registered(env, "issuer-a@example.com")
    _, reg_b = registered(env, "issuer-b@example.com")
    stranger = env.user(["APPROVER"], "stranger@example.com")  # never touched either document
    assert stranger.id not in {reg_a["document"]["owner_id"], reg_b["document"]["owner_id"]}
    for reg in (reg_a, reg_b):
        r = env.review(env.auth(stranger), reg["revision"]["id"], "approve")
        assert r.status_code == 202, r.text
        assert r.json()["reviewed_by"] == stranger.id


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_review_authz(env: Env, action: str) -> None:
    issuer_headers, reg = registered(env)
    rev_id = reg["revision"]["id"]
    assert env.review({}, rev_id, action).status_code == 401
    verifier = env.auth(env.user(["VERIFIER"], "v@example.com"))
    for headers in (issuer_headers, verifier):  # the owner without APPROVER is still refused
        r = env.review(headers, rev_id, action)
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
    r = env.review(env.approver(), "no-such-revision", action)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert env.revision(rev_id)["status"] == "PENDING"


def test_approved_revision_becomes_parent_of_next_submission(env: Env) -> None:
    headers, reg = registered(env)
    approver = env.approver()
    env.review(approver, reg["revision"]["id"], "approve")
    r = env.submit(headers, reg["document"]["id"])
    assert r.status_code == 201, r.text
    v2 = r.json()["revision"]
    assert v2["parent_revision_id"] == reg["revision"]["id"]
    assert env.review(approver, v2["id"], "approve").status_code == 202
    assert env.document(reg["document"]["id"])["latest_approved_revision_id"] == v2["id"]
    assert chain_ok(env, reg["document"]["id"])


def test_rejection_frees_the_pending_slot_and_keeps_the_old_parent(env: Env) -> None:
    headers, reg = registered(env)
    approver = env.approver()
    env.review(approver, reg["revision"]["id"], "approve")
    v2 = env.submit(headers, reg["document"]["id"]).json()["revision"]
    assert env.review(approver, v2["id"], "reject", "no").status_code == 200
    v3 = env.submit(headers, reg["document"]["id"])
    assert v3.status_code == 201, v3.text
    assert v3.json()["revision"]["parent_revision_id"] == reg["revision"]["id"]
    assert (
        env.document(reg["document"]["id"])["latest_approved_revision_id"] == reg["revision"]["id"]
    )
