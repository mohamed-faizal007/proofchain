"""POST /verify (P6-04): every PRD 5 verdict, end to end on the real services and fake chain."""

from pathlib import Path

import pytest

from app.chain import FakeRegistryClient
from app.chain.types import OnChainVersion
from app.errors import ChainUnavailableError
from tests.unit.app.docs_env import PDFS, Env
from tests.unit.app.revoke_helpers import install, revoke
from tests.unit.app.verify_helpers import (
    NEW,
    OLD,
    edit_mongo,
    edited,
    original,
    register_approved,
    step,
    submit,
    verify,
)


@pytest.fixture
def v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    return edited(tmp_path, monkeypatch)


def test_authentic_latest(env: Env) -> None:
    _, _, doc_id, rev_id = register_approved(env)

    r = verify(env, original())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "AUTHENTIC_LATEST"
    assert body["document"]["id"] == doc_id and body["document"]["title"] == "Lease"
    assert body["matched_revision"]["id"] == rev_id and body["matched_revision"]["version_no"] == 1
    assert body["localization"] is None and body["analysis"] is None
    assert body["chain_check"]["performed"] is True and body["chain_check"]["ok"] is True
    assert body["chain_check"]["tx_hash"].startswith("0x")
    assert [s["name"] for s in body["steps"]] == [
        "FILE_HASH",
        "TEXT_ROOT",
        "LOCALIZATION",
        "AUTHORIZATION",
        "CHAIN_CHECK",
        "SEMANTIC_ANALYSIS",
    ]
    assert step(body, "FILE_HASH")["status"] == "PASS"
    assert step(body, "AUTHORIZATION")["status"] == "PASS"
    assert step(body, "CHAIN_CHECK")["status"] == "PASS"


def test_authentic_superseded(env: Env, v2: bytes) -> None:
    issuer, approver, doc_id, _ = register_approved(env)
    rev2 = submit(env, issuer, doc_id, v2)
    assert env.review(approver, rev2, "approve").status_code == 202

    old = verify(env, original()).json()
    new = verify(env, v2).json()

    assert old["verdict"] == "AUTHENTIC_SUPERSEDED"
    assert "newer approved version" in step(old, "AUTHORIZATION")["detail"]
    assert new["verdict"] == "AUTHENTIC_LATEST"


def test_content_equivalent_is_never_authentic(env: Env) -> None:
    register_approved(env)
    resaved = original() + b"\n% harmless trailing bytes\n"

    body = verify(env, resaved).json()

    assert body["verdict"] == "CONTENT_EQUIVALENT"
    assert step(body, "FILE_HASH")["status"] == "FAIL"
    assert step(body, "TEXT_ROOT")["status"] == "PASS"
    assert step(body, "AUTHORIZATION")["status"] == "WARN"
    assert "not reported as authentic" in step(body, "AUTHORIZATION")["detail"]


@pytest.mark.parametrize("action", ["pending", "reject"])
def test_never_approved_match_is_unauthorized(env: Env, v2: bytes, action: str) -> None:
    issuer, approver, doc_id, _ = register_approved(env)
    rev2 = submit(env, issuer, doc_id, v2)
    if action == "reject":
        assert env.review(approver, rev2, "reject").status_code == 200

    body = verify(env, v2).json()

    assert body["verdict"] == "UNAUTHORIZED_VERSION"
    assert body["matched_revision"]["id"] == rev2
    detail = step(body, "AUTHORIZATION")["detail"]
    assert (
        "never approved" in detail and ("REJECTED" if action == "reject" else "PENDING") in detail
    )
    assert body["chain_check"]["performed"] is False
    assert step(body, "CHAIN_CHECK")["status"] == "SKIPPED"  # not anchored: nothing to compare


def test_revoked_match_runs_the_chain_check_and_its_detail_differs_from_never_approved(
    env: Env, v2: bytes
) -> None:
    install(env)
    issuer, approver, doc_id, rev1 = register_approved(env)
    rev2 = submit(env, issuer, doc_id, v2)
    assert env.review(approver, rev2, "approve").status_code == 202
    assert revoke(env, approver, rev1, "signed by mistake").status_code == 200
    other = env.post_pdf(issuer, "one_page.pdf", title="Other").json()
    assert other["revision"]["status"] == "PENDING"

    headers = env.auth(env.user(["VERIFIER"], "v@example.com"))  # anonymous reports omit the reason
    revoked = verify(env, original(), headers).json()
    pending = verify(env, (PDFS / "one_page.pdf").read_bytes(), headers).json()

    assert revoked["verdict"] == pending["verdict"] == "UNAUTHORIZED_VERSION"
    assert revoked["matched_revision"]["status"] == "REVOKED"
    assert revoked["matched_revision"]["revocation"]["reason"] == "signed by mistake"
    detail = step(revoked, "AUTHORIZATION")["detail"]
    on = env.revision(rev1)["revocation"]["at"].date().isoformat()
    assert f"revoked on {on}" in detail and "signed by mistake" in detail
    assert "never approved" not in detail
    assert "never approved" in step(pending, "AUTHORIZATION")["detail"]
    assert step(pending, "AUTHORIZATION")["detail"] != detail
    # the chain check really ran for the revoked match, and agreed
    assert revoked["chain_check"]["performed"] is True and revoked["chain_check"]["ok"] is True
    assert step(revoked, "CHAIN_CHECK")["status"] == "PASS"
    assert pending["chain_check"]["performed"] is False


def test_revoked_in_mongo_but_active_on_chain_escalates_to_record_mismatch(env: Env) -> None:
    """Capstone for ADR-020 + P6-03: a REVOKED match is chain-checked, and a disagreement on
    revocation overrides UNAUTHORIZED_VERSION."""
    install(env)
    _, _, _, rev1 = register_approved(env)
    edit_mongo(env, rev1, status="REVOKED")  # the chain was never told: revoked=false on-chain

    body = verify(env, original()).json()

    assert body["verdict"] == "RECORD_MISMATCH"
    assert body["chain_check"]["performed"] is True and body["chain_check"]["ok"] is False
    assert body["chain_check"]["mismatches"] == ["revoked"]
    assert step(body, "CHAIN_CHECK")["status"] == "FAIL"
    assert "revoked" in step(body, "CHAIN_CHECK")["detail"]
    assert "UNAUTHORIZED_VERSION" in body["summary"]  # what the off-chain records alone said
    assert step(body, "AUTHORIZATION")["detail"].startswith("Matches revision 1")


def test_revoked_on_chain_but_approved_in_mongo_is_record_mismatch(env: Env) -> None:
    client = install(env)
    _, _, doc_id, _ = register_approved(env)
    chain_doc = env.document(doc_id)["chain_doc_id"]
    env.client.portal.call(client.revoke_version, chain_doc, 1, "tampered off-chain")  # type: ignore[union-attr]

    body = verify(env, original()).json()

    assert body["verdict"] == "RECORD_MISMATCH"
    assert body["chain_check"]["mismatches"] == ["revoked"]
    assert "AUTHENTIC_LATEST" in body["summary"]


def test_mongo_text_root_edit_is_record_mismatch(env: Env) -> None:
    _, _, _, rev_id = register_approved(env)
    edit_mongo(env, rev_id, text_root="e" * 64)

    body = verify(env, original()).json()

    assert body["verdict"] == "RECORD_MISMATCH"
    assert body["chain_check"]["mismatches"] == ["text_root"]
    assert "text_root" in body["summary"]


def test_tampered_with_reference_localizes_and_names_the_reference(env: Env, v2: bytes) -> None:
    _, _, doc_id, rev_id = register_approved(env)

    headers = env.auth(env.user(["VERIFIER"], "v@example.com"))  # anonymous reports carry no text
    body = verify(env, v2, headers, document_id=doc_id).json()

    assert body["verdict"] == "TAMPERED"
    assert body["matched_revision"] is None
    assert body["reference_revision"]["id"] == rev_id
    assert body["no_reference_reason"] is None
    [region] = body["localization"]["regions"]
    assert OLD in region["ref_text"] and NEW in region["cand_text"]
    assert body["summary"] == "1 change on page(s) 2 vs approved revision 1 (v1)"
    assert step(body, "LOCALIZATION")["status"] == "DONE"
    assert "vs revision 1 (v1)" in step(body, "LOCALIZATION")["detail"]
    assert step(body, "AUTHORIZATION")["status"] == "FAIL"
    assert body["chain_check"]["performed"] is True and body["chain_check"]["ok"] is True


def test_tampered_without_any_approved_reference(env: Env, v2: bytes) -> None:
    """A document with only a PENDING revision: TAMPERED, but nothing was compared."""
    doc_id = env.post_pdf(env.issuer()).json()["document"]["id"]  # revision 1 stays PENDING

    body = verify(env, v2, document_id=doc_id).json()

    assert body["verdict"] == "TAMPERED"
    assert body["localization"] is None and body["reference_revision"] is None
    assert body["no_reference_reason"] == "NO_APPROVED_REVISION"
    assert body["summary"].startswith("TAMPERED, no reference available")
    assert "No changes were localized" in body["summary"]
    loc = step(body, "LOCALIZATION")
    assert loc["status"] == "SKIPPED" and loc["detail"].startswith("NO_REFERENCE")
    assert body["chain_check"]["performed"] is False
    assert step(body, "CHAIN_CHECK")["status"] == "SKIPPED"


def test_tampered_with_and_without_reference_never_look_alike(env: Env, v2: bytes) -> None:
    issuer, _, ref_doc, _ = register_approved(env)
    bare_doc = env.post_pdf(issuer, "one_page.pdf", title="Bare").json()["document"]["id"]

    with_ref = verify(env, v2, document_id=ref_doc).json()
    without = verify(env, v2, document_id=bare_doc).json()

    assert with_ref["verdict"] == without["verdict"] == "TAMPERED"
    assert with_ref["summary"] != without["summary"]
    assert "no reference" not in with_ref["summary"] and "vs approved" not in without["summary"]
    assert with_ref["localization"] is not None and without["localization"] is None
    assert step(with_ref, "LOCALIZATION")["status"] != step(without, "LOCALIZATION")["status"]
    assert with_ref["no_reference_reason"] is None
    assert without["no_reference_reason"] == "NO_APPROVED_REVISION"


def test_unknown_document(env: Env, v2: bytes) -> None:
    register_approved(env)

    body = verify(env, v2).json()  # matches nothing and no document_id was supplied

    assert body["verdict"] == "UNKNOWN_DOCUMENT"
    assert body["document"] is None and body["localization"] is None
    assert step(body, "LOCALIZATION")["status"] == "SKIPPED"
    assert body["chain_check"]["performed"] is False


def test_chain_outage_keeps_the_verdict_and_says_not_performed(env: Env) -> None:
    class Down(FakeRegistryClient):
        async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None:
            raise ChainUnavailableError("node down")

    register_approved(env)
    env.client.app.state.registry_client = Down()  # type: ignore[attr-defined]

    body = verify(env, original()).json()

    assert body["verdict"] == "AUTHENTIC_LATEST"
    assert body["chain_check"]["performed"] is False
    assert body["chain_check"]["reason"] == "CHAIN_UNAVAILABLE"
    assert step(body, "CHAIN_CHECK")["status"] == "SKIPPED"
    assert "CHAIN_UNAVAILABLE" in step(body, "CHAIN_CHECK")["detail"]


def test_no_registry_configured_reports_not_performed(env: Env) -> None:
    register_approved(env)
    env.client.app.state.registry_client = None  # type: ignore[attr-defined]

    body = verify(env, original()).json()

    assert body["verdict"] == "AUTHENTIC_LATEST"
    assert body["chain_check"]["reason"] == "CHAIN_NOT_CONFIGURED"


def test_include_nlp_flag_never_changes_the_verdict(env: Env, v2: bytes) -> None:
    """Both calls here are anonymous (no auth header), so NLP is skipped either way (P7-04:
    never run for anonymous callers, see test_verify_nlp.py); this test's own point is that
    `include_nlp` affects only the SEMANTIC_ANALYSIS step, never `verdict`/`localization`."""
    doc_id = register_approved(env)[2]
    on = verify(env, v2, document_id=doc_id, include_nlp="true").json()
    off = verify(env, v2, document_id=doc_id, include_nlp="false").json()

    assert on["verdict"] == off["verdict"] == "TAMPERED"
    assert on["localization"] == off["localization"]
    assert on["analysis"] is None and off["analysis"] is None
    assert step(off, "SEMANTIC_ANALYSIS")["detail"] == "Not requested"
    assert step(on, "SEMANTIC_ANALYSIS") == {
        "name": "SEMANTIC_ANALYSIS",
        "status": "SKIPPED",
        "detail": "Not available for anonymous requests",
    }
