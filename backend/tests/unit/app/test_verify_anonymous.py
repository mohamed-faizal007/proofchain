"""Anonymous /verify reports must not disclose stored content or revocation notes (P6-review).

Authenticated callers keep the full report; the stored anonymous record equals what was returned.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.unit.app.docs_env import Env
from tests.unit.app.revoke_helpers import install, revoke
from tests.unit.app.verify_helpers import (
    NEW,
    OLD,
    edited,
    original,
    register_approved,
    step,
    submit,
    verify,
)

REASON = "signed by mistake, fraud inquiry 7"


@pytest.fixture
def v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    return edited(tmp_path, monkeypatch)


def stored(env: Env) -> list[dict[str, Any]]:
    async def load() -> list[dict[str, Any]]:
        return [d async for d in env.db["verifications"].find({})]

    return env.client.portal.call(load)  # type: ignore[union-attr,no-any-return]


def dump(obj: Any) -> str:
    return json.dumps(obj, default=str)


def test_anonymous_tampered_report_carries_no_reference_or_candidate_text(
    env: Env, v2: bytes
) -> None:
    _, _, doc_id, rev_id = register_approved(env)

    body = verify(env, v2, document_id=doc_id).json()

    assert body["verdict"] == "TAMPERED" and body["reference_revision"]["id"] == rev_id
    [region] = body["localization"]["regions"]
    assert region["type"] == "MODIFIED" and region["ref_page"] == region["cand_page"] == 1
    for field in (
        "ref_text",
        "cand_text",
        "ref_bbox",
        "cand_bbox",
        "ref_chunk_id",
        "section_title",
    ):
        assert region[field] is None, field
    assert OLD not in dump(body) and NEW not in dump(body)
    assert body["summary"] == "1 change on page(s) 2 vs approved revision 1 (v1)"
    assert OLD not in dump(stored(env)) and NEW not in dump(stored(env))


def test_anonymous_whole_document_probe_returns_no_text(env: Env) -> None:
    """An unrelated PDF against a known document must not read the approved text back."""
    _, _, doc_id, _ = register_approved(env)
    from tests.unit.app.docs_env import PDFS

    body = verify(env, (PDFS / "one_page.pdf").read_bytes(), document_id=doc_id).json()

    assert body["verdict"] == "TAMPERED" and body["localization"]["regions"]
    assert all(
        r["ref_text"] is None and r["cand_text"] is None for r in body["localization"]["regions"]
    )
    assert "per month" not in dump(body)


def test_authenticated_report_still_has_the_full_localization(env: Env, v2: bytes) -> None:
    _, _, doc_id, _ = register_approved(env)
    headers = env.auth(env.user(["VERIFIER"], "v@example.com"))

    [region] = verify(env, v2, headers, document_id=doc_id).json()["localization"]["regions"]

    assert OLD in region["ref_text"] and NEW in region["cand_text"]
    assert region["ref_bbox"] is not None and region["cand_bbox"] is not None


def test_anonymous_revoked_match_hides_reason_and_revoker_but_keeps_the_fact(
    env: Env, v2: bytes
) -> None:
    install(env)
    issuer, approver, doc_id, rev1 = register_approved(env)
    rev2 = submit(env, issuer, doc_id, v2)
    assert env.review(approver, rev2, "approve").status_code == 202
    assert revoke(env, approver, rev1, REASON).status_code == 200
    revoked_by = env.revision(rev1)["revocation"]["by"]
    on = env.revision(rev1)["revocation"]["at"].date().isoformat()

    body = verify(env, original()).json()

    assert body["verdict"] == "UNAUTHORIZED_VERSION"
    assert body["matched_revision"]["status"] == "REVOKED"
    assert set(body["matched_revision"]["revocation"]) == {"at"}
    assert f"revoked on {on}" in step(body, "AUTHORIZATION")["detail"]
    for leaked in (REASON, "fraud", revoked_by):
        assert leaked not in dump(body), leaked
        assert leaked not in dump(stored(env)), leaked


def test_authenticated_revoked_match_still_shows_reason(env: Env, v2: bytes) -> None:
    install(env)
    issuer, approver, doc_id, rev1 = register_approved(env)
    rev2 = submit(env, issuer, doc_id, v2)
    assert env.review(approver, rev2, "approve").status_code == 202
    assert revoke(env, approver, rev1, REASON).status_code == 200

    body = verify(env, original(), env.auth(env.user(["VERIFIER"], "v@example.com"))).json()

    assert body["matched_revision"]["revocation"]["reason"] == REASON
    assert REASON in step(body, "AUTHORIZATION")["detail"] and REASON in body["summary"]


def test_admin_reads_back_exactly_what_the_anonymous_caller_got(env: Env, v2: bytes) -> None:
    _, _, doc_id, _ = register_approved(env)
    admin = env.auth(env.user(["ADMIN"], "a@example.com"))

    posted = verify(env, v2, document_id=doc_id).json()
    read = env.client.get(f"/api/v1/verifications/{posted['id']}", headers=admin)

    assert read.status_code == 200 and read.json() == posted


def test_unknown_document_id_is_a_uniform_no_match_for_anonymous_callers(
    env: Env, v2: bytes
) -> None:
    register_approved(env)

    with_id = verify(env, v2, document_id="00000000-0000-4000-8000-000000000000")
    without = verify(env, v2)

    assert with_id.status_code == 200
    a, b = with_id.json(), without.json()
    for volatile in ("id", "at", "timings_ms"):
        a.pop(volatile), b.pop(volatile)
    assert a == b and a["verdict"] == "UNKNOWN_DOCUMENT"


def test_unknown_document_id_stays_404_for_authenticated_callers(env: Env, v2: bytes) -> None:
    register_approved(env)
    headers = env.auth(env.user(["VERIFIER"], "v@example.com"))

    r = verify(env, v2, headers, document_id="00000000-0000-4000-8000-000000000000")

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_known_limit_existence_is_still_inferable_from_the_verdict(env: Env, v2: bytes) -> None:
    """Pins ADR-021's residual: a known id gives TAMPERED, an unknown one UNKNOWN_DOCUMENT."""
    _, _, doc_id, _ = register_approved(env)

    known = verify(env, v2, document_id=doc_id).json()["verdict"]
    unknown = verify(env, v2, document_id="00000000-0000-4000-8000-000000000000").json()["verdict"]

    assert (known, unknown) == ("TAMPERED", "UNKNOWN_DOCUMENT")
