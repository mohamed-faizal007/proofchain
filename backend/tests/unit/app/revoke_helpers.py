"""Helpers for revoke tests (P5-05): a chain client that counts and scripts revoke calls."""

from typing import Any

from app.chain import OnChainVersion, TxReceipt
from tests.unit.app.anchor_harness import ScriptedRegistryClient
from tests.unit.app.docs_env import PREFIX, Env


class RevokeClient(ScriptedRegistryClient):
    """Counts revoke txs; raises queued `revoke_failures` first, one per revoke call."""

    def __init__(self) -> None:
        super().__init__()
        self.revoke_calls = 0
        self.revoke_failures: list[BaseException] = []
        self.missing_versions = False

    async def revoke_version(self, doc_id: str, version_no: int, reason: str) -> TxReceipt:
        self.revoke_calls += 1
        if self.revoke_failures:
            raise self.revoke_failures.pop(0)
        return await super().revoke_version(doc_id, version_no, reason)

    async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None:
        if self.missing_versions:
            return None
        return await super().get_version(doc_id, version_no)


def install(env: Env) -> RevokeClient:
    client = RevokeClient()
    env.client.app.state.registry_client = client  # type: ignore[attr-defined]
    return client


def revoke(
    env: Env, headers: dict[str, str], revision_id: str, reason: str | None = "wrong"
) -> Any:
    body = None if reason is None else {"reason": reason}
    return env.client.post(f"{PREFIX}/revisions/{revision_id}/revoke", headers=headers, json=body)


def anchored_doc(env: Env) -> tuple[dict[str, str], dict[str, str], str, str]:
    """(issuer, approver, document_id, revision_id) with revision 1 APPROVED + ANCHORED."""
    issuer, approver = env.issuer(), env.approver()
    reg = env.post_pdf(issuer).json()
    rev_id, doc_id = reg["revision"]["id"], reg["document"]["id"]
    assert env.review(approver, rev_id, "approve").status_code == 202
    assert env.revision(rev_id)["anchor"]["status"] == "ANCHORED"
    return issuer, approver, doc_id, rev_id


def add_anchored(
    env: Env, issuer: dict[str, str], approver: dict[str, str], doc_id: str, pdf: str
) -> str:
    r = env.submit(issuer, doc_id, pdf)
    assert r.status_code == 201, r.text
    rev_id = str(r.json()["revision"]["id"])
    assert env.review(approver, rev_id, "approve").status_code == 202
    assert env.revision(rev_id)["anchor"]["status"] == "ANCHORED"
    return rev_id


def on_chain(env: Env, doc_id: str, version_no: int) -> OnChainVersion:
    client = env.client.app.state.registry_client  # type: ignore[attr-defined]
    chain_doc_id = env.document(doc_id)["chain_doc_id"]
    return env.client.portal.call(client.get_version, chain_doc_id, version_no)  # type: ignore[union-attr,no-any-return]


def pointer(env: Env, doc_id: str) -> tuple[Any, Any]:
    doc = env.document(doc_id)
    return doc["latest_approved_revision_id"], doc["latest_approved_version_no"]
