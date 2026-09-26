"""POST /revisions/{id}/revoke (P5-05): happy path, pointer, state and authz rules."""

import pytest

from app.chain import FakeRegistryClient
from app.services.revocation import MAX_REASON_CHARS
from tests.unit.app.docs_env import PREFIX, Env
from tests.unit.app.revoke_helpers import (
    add_anchored,
    anchored_doc,
    install,
    on_chain,
    pointer,
    revoke,
)


def test_revoke_revokes_on_chain_then_records_state_and_event(env: Env) -> None:
    client = install(env)
    _, approver, doc_id, rev_id = anchored_doc(env)

    r = revoke(env, approver, rev_id, "  signed by mistake  ")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "REVOKED"
    revocation = body["revocation"]
    assert revocation["reason"] == "signed by mistake"
    assert revocation["tx_hash"].startswith("0x") and revocation["block_number"] > 0
    stored = env.revision(rev_id)
    assert (stored["status"], stored["revocation"]["tx_hash"]) == ("REVOKED", revocation["tx_hash"])
    assert stored["anchor"]["status"] == "ANCHORED"  # anchoring history is kept
    assert on_chain(env, doc_id, 1).revoked is True
    assert client.revoke_calls == 1

    [event] = env.events("VERSION_REVOKED")
    assert event["revision_id"] == rev_id
    assert event["actor_id"] == revocation["by"]
    assert event["data"] == {
        "version_no": 1,
        "reason": "signed by mistake",
        "tx_hash": revocation["tx_hash"],
        "block_number": revocation["block_number"],
        "already_revoked": False,
    }
    assert [e["type"] for e in env.events()][-2:] == ["VERSION_ANCHORED", "VERSION_REVOKED"]
    prov = env.client.get(f"{PREFIX}/documents/{doc_id}/provenance", headers=approver).json()
    assert prov["chain_valid"] is True


def test_revoking_the_latest_version_moves_the_pointer_back(env: Env) -> None:
    install(env)
    issuer, approver, doc_id, v1 = anchored_doc(env)
    v2 = add_anchored(env, issuer, approver, doc_id, "one_page.pdf")
    assert pointer(env, doc_id) == (v2, 2)

    assert revoke(env, approver, v2).status_code == 200

    assert pointer(env, doc_id) == (v1, 1)
    detail = env.client.get(f"{PREFIX}/documents/{doc_id}", headers=approver).json()
    assert detail["latest_approved_revision"]["id"] == v1


def test_revoking_the_only_approved_version_clears_the_pointer(env: Env) -> None:
    install(env)
    _, approver, doc_id, rev_id = anchored_doc(env)
    assert revoke(env, approver, rev_id).status_code == 200
    assert pointer(env, doc_id) == (None, None)


def test_revoking_an_older_version_leaves_the_pointer(env: Env) -> None:
    install(env)
    issuer, approver, doc_id, v1 = anchored_doc(env)
    v2 = add_anchored(env, issuer, approver, doc_id, "one_page.pdf")
    assert revoke(env, approver, v1).status_code == 200
    assert pointer(env, doc_id) == (v2, 2)
    assert on_chain(env, doc_id, 2).revoked is False


def test_any_approver_may_revoke_including_the_one_who_approved(env: Env) -> None:
    """Decision 3: maker != checker does not apply to revoke (PROGRESS.md, P5-05)."""
    install(env)
    _, approver, doc_id, rev_id = anchored_doc(env)
    # anchored_doc approved with `approver`; the same user revokes.
    r = revoke(env, approver, rev_id)
    assert r.status_code == 200
    assert r.json()["revocation"]["by"] == env.revision(rev_id)["reviewed_by"]


@pytest.mark.parametrize("status", ["PENDING", "REJECTED"])
def test_only_approved_revisions_can_be_revoked(env: Env, status: str) -> None:
    client = install(env)
    issuer, approver = env.issuer(), env.approver()
    rev_id = env.post_pdf(issuer).json()["revision"]["id"]
    if status == "REJECTED":
        env.review(approver, rev_id, "reject", "no")

    r = revoke(env, approver, rev_id)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REVISION_NOT_APPROVED"
    assert r.json()["error"]["details"] == {"status": status}
    assert client.revoke_calls == 0
    assert env.events("VERSION_REVOKED") == []


def test_revoking_twice_is_409_and_sends_one_tx(env: Env) -> None:
    client = install(env)
    _, approver, _, rev_id = anchored_doc(env)
    assert revoke(env, approver, rev_id).status_code == 200

    r = revoke(env, approver, rev_id)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REVISION_NOT_APPROVED"
    assert r.json()["error"]["details"] == {"status": "REVOKED"}
    assert client.revoke_calls == 1
    assert len(env.events("VERSION_REVOKED")) == 1


@pytest.mark.parametrize("anchor_status", ["ANCHORING", "FAILED"])
def test_unanchored_approved_revision_cannot_be_revoked(env: Env, anchor_status: str) -> None:
    client = install(env)
    issuer, approver = env.issuer(), env.approver()
    rev_id = env.post_pdf(issuer).json()["revision"]["id"]
    env.client.app.state.registry_client = None  # type: ignore[attr-defined]
    env.review(approver, rev_id, "approve")  # -> FAILED (CHAIN_NOT_CONFIGURED)
    env.client.app.state.registry_client = client  # type: ignore[attr-defined]
    if anchor_status == "ANCHORING":
        env.client.portal.call(  # type: ignore[union-attr]
            env.db["revisions"].update_one,
            {"_id": rev_id},
            {"$set": {"anchor.status": "ANCHORING", "anchor.attempted_at": None}},
        )

    r = revoke(env, approver, rev_id)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"
    assert r.json()["error"]["details"] == {"anchor_status": anchor_status}
    assert env.revision(rev_id)["status"] == "APPROVED"
    assert client.revoke_calls == 0


@pytest.mark.parametrize("reason", [None, "", "   ", "x" * (MAX_REASON_CHARS + 1)])
def test_reason_is_required_and_bounded(env: Env, reason: str | None) -> None:
    client = install(env)
    _, approver, _, rev_id = anchored_doc(env)
    r = revoke(env, approver, rev_id, reason)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert env.revision(rev_id)["status"] == "APPROVED"
    assert client.revoke_calls == 0


def test_reason_at_the_limit_is_accepted(env: Env) -> None:
    install(env)
    _, approver, _, rev_id = anchored_doc(env)
    assert revoke(env, approver, rev_id, "x" * MAX_REASON_CHARS).status_code == 200


def test_revoke_authz(env: Env) -> None:
    install(env)
    issuer, _, _, rev_id = anchored_doc(env)
    assert revoke(env, {}, rev_id).status_code == 401
    assert revoke(env, issuer, rev_id).status_code == 403
    admin = env.auth(env.user(["ADMIN"], "admin@example.com"))
    assert revoke(env, admin, rev_id).status_code == 403
    r = revoke(env, env.approver("other@example.com"), "no-such-revision")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert env.revision(rev_id)["status"] == "APPROVED"


def test_unconfigured_chain_is_503_and_writes_nothing(env: Env) -> None:
    _, approver, _, rev_id = anchored_doc(env)  # anchored with the default fake client
    env.client.app.state.registry_client = None  # type: ignore[attr-defined]
    r = revoke(env, approver, rev_id)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "CHAIN_UNAVAILABLE")
    assert env.revision(rev_id)["status"] == "APPROVED"
    assert env.events("VERSION_REVOKED") == []


def test_reanchoring_same_content_after_revoke_is_a_new_version(env: Env) -> None:
    """Revoked versions stay revoked; resubmitting the same text anchors a fresh version."""
    assert isinstance(env.client.app.state.registry_client, FakeRegistryClient)  # type: ignore[attr-defined]
    issuer, approver, doc_id, v1 = anchored_doc(env)
    assert revoke(env, approver, v1).status_code == 200
    v2 = add_anchored(env, issuer, approver, doc_id, "contract_3page.pdf")
    assert env.revision(v2)["version_no"] == 2
    assert on_chain(env, doc_id, 1).revoked is True
    assert on_chain(env, doc_id, 2).revoked is False
    assert pointer(env, doc_id) == (v2, 2)
