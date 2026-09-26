"""Approve -> background anchoring and POST /revisions/{id}/retry-anchor (P5-04)."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.chain import FakeRegistryClient
from app.errors import AnchorFailedError
from app.main import create_app
from app.models.revision import Anchor
from app.services.anchoring import now_ms
from tests.unit.app.anchor_harness import ScriptedRegistryClient
from tests.unit.app.docs_env import PREFIX, Env, settings

REVERT = AnchorFailedError("Contract rejected the transaction")
PDFS = ["contract_3page.pdf", "one_page.pdf", "unicode_variants.pdf"]


def scripted(env: Env) -> ScriptedRegistryClient:
    client = ScriptedRegistryClient()
    env.client.app.state.registry_client = client  # type: ignore[attr-defined]
    return client


def retry(env: Env, headers: dict[str, str], revision_id: str) -> Any:
    return env.client.post(f"{PREFIX}/revisions/{revision_id}/retry-anchor", headers=headers)


def admin(env: Env) -> dict[str, str]:
    return env.auth(env.user(["ADMIN"], "admin@example.com"))


def first_revision(env: Env) -> tuple[dict[str, str], str, str]:
    issuer = env.issuer()
    reg = env.post_pdf(issuer).json()
    return issuer, reg["revision"]["id"], reg["document"]["id"]


def approve(env: Env, headers: dict[str, str], rev_id: str) -> None:
    r = env.review(headers, rev_id, "approve")
    assert r.status_code == 202, r.text


def next_revision(env: Env, issuer: dict[str, str], doc_id: str, pdf: str) -> str:
    r = env.submit(issuer, doc_id, pdf)
    assert r.status_code == 201, r.text
    return str(r.json()["revision"]["id"])


def test_approve_anchors_in_background(env: Env) -> None:
    client = scripted(env)
    _, rev_id, doc_id = first_revision(env)
    r = env.review(env.approver(), rev_id, "approve")
    assert (r.status_code, r.json()["anchor"]["status"]) == (202, "ANCHORING")
    stored = env.revision(rev_id)
    assert (stored["anchor"]["status"], stored["version_no"]) == ("ANCHORED", 1)
    assert env.document(doc_id)["latest_approved_version_no"] == 1
    assert [e["type"] for e in env.events()][-2:] == ["REVISION_APPROVED", "VERSION_ANCHORED"]
    assert client.anchor_calls == 1


def test_reject_does_not_anchor(env: Env) -> None:
    client = scripted(env)
    _, rev_id, _ = first_revision(env)
    env.review(env.approver(), rev_id, "reject", "no")
    assert client.anchor_calls == 0
    assert env.revision(rev_id)["anchor"]["status"] == "NOT_REQUESTED"


def test_approve_without_chain_configured_records_failed_anchor(env: Env) -> None:
    """Adjustment 4: approval still succeeds (202); the anchor is FAILED, not a 503."""
    env.client.app.state.registry_client = None  # type: ignore[attr-defined]
    _, rev_id, _ = first_revision(env)
    approve(env, env.approver(), rev_id)
    stored = env.revision(rev_id)
    assert (stored["status"], stored["anchor"]["status"], stored["anchor"]["error"]) == (
        "APPROVED",
        "FAILED",
        "CHAIN_NOT_CONFIGURED",
    )
    [event] = env.events("ANCHOR_FAILED")
    assert event["data"]["error"] == "CHAIN_NOT_CONFIGURED"


def test_v2_failure_does_not_let_v3_take_its_chain_slot(env: Env) -> None:
    """Adjustment 1. The old bug: v2 FAILED, v3 anchored as chain version 2, then an admin retry
    of v2 anchored it as version 3, out of order and with a wrong prevTextRoot link."""
    client = scripted(env)
    approver = env.approver()
    issuer, v1, doc_id = first_revision(env)
    approve(env, approver, v1)

    v2 = next_revision(env, issuer, doc_id, PDFS[1])
    client.failures = [REVERT]
    approve(env, approver, v2)
    assert env.revision(v2)["anchor"]["status"] == "FAILED"

    v3 = next_revision(env, issuer, doc_id, PDFS[2])
    approve(env, approver, v3)  # approval is not blocked by v2
    stored_v3 = env.revision(v3)
    assert (stored_v3["status"], stored_v3["anchor"]["status"]) == ("APPROVED", "ANCHORING")
    assert stored_v3["anchor"]["attempted_at"] is None and stored_v3["version_no"] is None
    assert env.document(doc_id)["latest_approved_revision_id"] == v3
    assert env.document(doc_id)["latest_approved_version_no"] is None  # adjustment 8
    assert client.anchor_calls == 2  # v1 + failed v2; v3 never sent

    r = retry(env, admin(env), v2)
    assert r.status_code == 202, r.text

    versions = [env.revision(v)["version_no"] for v in (v1, v2, v3)]
    assert versions == [1, 2, 3]
    chain_doc_id = env.document(doc_id)["chain_doc_id"]
    on_chain = [
        env.client.portal.call(client.get_version, chain_doc_id, n)  # type: ignore[union-attr]
        for n in (1, 2, 3)
    ]
    roots = [env.revision(v)["text_root"] for v in (v1, v2, v3)]
    assert [v.text_root for v in on_chain] == roots  # type: ignore[union-attr]
    assert on_chain[2].prev_text_root == roots[1]  # type: ignore[union-attr]
    doc = env.document(doc_id)
    assert (doc["latest_approved_revision_id"], doc["latest_approved_version_no"]) == (v3, 3)


def test_retry_failed_returns_202_and_anchors(env: Env) -> None:
    client = scripted(env)
    _, rev_id, _ = first_revision(env)
    client.failures = [REVERT]
    approve(env, env.approver(), rev_id)

    r = retry(env, admin(env), rev_id)

    assert r.status_code == 202, r.text
    assert (r.json()["anchor"]["status"], r.json()["anchor"]["attempted_at"]) == ("ANCHORING", None)
    stored = env.revision(rev_id)
    assert (stored["anchor"]["status"], stored["anchor"]["attempts"]) == ("ANCHORED", 2)
    assert env.events("VERSION_ANCHORED")[0]["data"]["trigger"] == "retry"


def test_retry_anchored_is_200_no_op(env: Env) -> None:
    client = scripted(env)
    _, rev_id, _ = first_revision(env)
    approve(env, env.approver(), rev_id)
    before = env.revision(rev_id)
    r = retry(env, admin(env), rev_id)
    assert (r.status_code, r.json()["anchor"]["status"]) == (200, "ANCHORED")
    assert env.revision(rev_id) == before and client.anchor_calls == 1


@pytest.mark.parametrize("action", [None, "reject"], ids=["PENDING", "REJECTED"])
def test_retry_non_approved_is_409_revision_not_approved(env: Env, action: str | None) -> None:
    client = scripted(env)
    _, rev_id, _ = first_revision(env)
    if action:
        env.review(env.approver(), rev_id, action, "no")
    r = retry(env, admin(env), rev_id)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "REVISION_NOT_APPROVED")
    assert client.anchor_calls == 0


def test_retry_while_anchoring_is_409_conflict(env: Env) -> None:
    env.client.app.state.registry_client = FakeRegistryClient()  # type: ignore[attr-defined]
    _, rev_id, _ = first_revision(env)
    approve(env, env.approver(), rev_id)
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["revisions"].update_one,
        {"_id": rev_id},
        {"$set": {"anchor": Anchor(status="ANCHORING", attempted_at=now_ms()).model_dump()}},
    )
    r = retry(env, admin(env), rev_id)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "CONFLICT")


def test_retry_authz(env: Env) -> None:
    _, rev_id, _ = first_revision(env)
    assert retry(env, {}, rev_id).status_code == 401
    r = retry(env, env.approver(), rev_id)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
    r = retry(env, admin(env), "missing")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_startup_reconciler_runs_in_background(env: Env) -> None:
    """A FAILED anchor left from before a restart is re-sent by the startup pass."""
    _, rev_id, _ = first_revision(env)
    env.client.app.state.registry_client = None  # type: ignore[attr-defined]
    approve(env, env.approver(), rev_id)
    assert env.revision(rev_id)["anchor"]["status"] == "FAILED"

    app = create_app(
        settings(),
        db=env.db,
        storage=env.storage,
        registry_client=FakeRegistryClient(),
        reconcile_on_startup=True,
    )
    with TestClient(app) as restarted:
        assert restarted.get(f"{PREFIX}/health").status_code == 200
        for _ in range(200):
            doc = restarted.portal.call(env.db["revisions"].find_one, {"_id": rev_id})  # type: ignore[union-attr]
            if doc["anchor"]["status"] == "ANCHORED":
                break
            restarted.portal.call(_tick)  # type: ignore[union-attr]
    assert doc["anchor"]["status"] == "ANCHORED"
    assert env.events("VERSION_ANCHORED")[0]["data"]["trigger"] == "reconcile"


async def _tick() -> None:
    await asyncio.sleep(0.01)
