"""GET /revisions/{id}/diff?against= (P5-06): localization between two stored revisions."""

from pathlib import Path
from typing import Any

import pytest

from proofchain_core import CANON_VERSION, build_integrity_tree, localize
from tests.fixtures import make_fixtures
from tests.unit.app.docs_env import PDFS, PREFIX, Env

OLD, NEW = "2% per month", "3% per month"


def contract_v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    """contract_3page.pdf with one edit on page 2 (index 1), built by the same fixture generator."""
    pages = [[(k, t.replace(OLD, NEW)) for k, t in page] for page in make_fixtures.CONTRACT_PAGES]
    monkeypatch.setattr(make_fixtures, "CONTRACT_PAGES", pages)
    path = tmp_path / "contract_v2.pdf"
    make_fixtures._contract(path)
    return path.read_bytes()


def reader(env: Env) -> dict[str, str]:
    return env.auth(env.user(["VERIFIER"], "verifier@example.com"))


def two_revisions(env: Env, v2: bytes) -> tuple[str, str, str]:
    """(document_id, approved v1 id, pending v2 id), v2's parent is v1."""
    issuer = env.issuer()
    reg = env.post_pdf(issuer).json()
    doc_id, v1 = reg["document"]["id"], reg["revision"]["id"]
    env.set_status(v1, "APPROVED")
    sub = env.submit(issuer, doc_id, v2)
    assert sub.status_code == 201, sub.text
    return doc_id, v1, sub.json()["revision"]["id"]


def diff(
    env: Env, rev_id: str, against: str | None = None, headers: dict[str, str] | None = None
) -> Any:
    params = {} if against is None else {"against": against}
    headers = headers if headers is not None else reader(env)
    return env.client.get(f"{PREFIX}/revisions/{rev_id}/diff", params=params, headers=headers)


@pytest.fixture
def v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    return contract_v2(tmp_path, monkeypatch)


def test_default_diff_is_against_the_parent_and_matches_core(env: Env, v2: bytes) -> None:
    _, v1, rev2 = two_revisions(env, v2)
    events_before = env.count("provenance_events")
    ref = build_integrity_tree((PDFS / "contract_3page.pdf").read_bytes())
    cand = build_integrity_tree(v2)

    r = diff(env, rev2)

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["revision_id"], body["against_revision_id"]) == (rev2, v1)
    assert body["analysis"] is None  # NLP analysis is P7
    assert body["localization"] == localize(ref, cand).to_dict()
    loc = body["localization"]
    assert loc["status"] == "CHANGED"
    [region] = loc["regions"]
    assert region["type"] == "MODIFIED"
    assert OLD in region["ref_text"] and NEW in region["cand_text"]
    assert region["ref_page"] == region["cand_page"] == 1
    assert loc["changed_pages_ref"] == loc["changed_pages_cand"] == [1]
    assert env.count("provenance_events") == events_before  # read-only


def test_explicit_against_sets_the_reference_side(env: Env, v2: bytes) -> None:
    """`against` is the reference, `{id}` the candidate: diffing v1 against v2 swaps the texts."""
    _, v1, rev2 = two_revisions(env, v2)
    ref = build_integrity_tree(v2)
    cand = build_integrity_tree((PDFS / "contract_3page.pdf").read_bytes())

    r = diff(env, v1, against=rev2)

    assert r.status_code == 200, r.text
    assert (r.json()["revision_id"], r.json()["against_revision_id"]) == (v1, rev2)
    assert r.json()["localization"] == localize(ref, cand).to_dict()
    [region] = r.json()["localization"]["regions"]
    assert NEW in region["ref_text"] and OLD in region["cand_text"]


def test_diff_against_itself_is_identical(env: Env, v2: bytes) -> None:
    _, v1, _ = two_revisions(env, v2)
    r = diff(env, v1, against=v1)
    assert r.status_code == 200, r.text
    loc = r.json()["localization"]
    assert (loc["status"], loc["regions"], loc["method"]) == ("IDENTICAL", [], None)


@pytest.mark.parametrize("roles", [["VERIFIER"], ["ISSUER"], ["APPROVER"], ["ADMIN"]])
def test_any_authenticated_role_can_diff_a_pending_revision(
    env: Env, v2: bytes, roles: list[Any]
) -> None:
    """Approvers review a PENDING submission through this route, so status never restricts it."""
    _, _, rev2 = two_revisions(env, v2)
    assert env.revision(rev2)["status"] == "PENDING"
    headers = env.auth(env.user(roles, "someone@example.com"))
    assert diff(env, rev2, headers=headers).status_code == 200


@pytest.mark.parametrize("status", ["REJECTED", "REVOKED"])
def test_rejected_and_revoked_revisions_can_be_diffed(env: Env, v2: bytes, status: str) -> None:
    _, _, rev2 = two_revisions(env, v2)
    env.set_status(rev2, status)
    r = diff(env, rev2)
    assert r.status_code == 200 and r.json()["localization"]["status"] == "CHANGED"


def test_diff_requires_authentication(env: Env, v2: bytes) -> None:
    _, _, rev2 = two_revisions(env, v2)
    r = env.client.get(f"{PREFIX}/revisions/{rev2}/diff")
    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_unknown_revision_is_404(env: Env) -> None:
    r = diff(env, "no-such-revision")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_unknown_against_is_404(env: Env, v2: bytes) -> None:
    _, _, rev2 = two_revisions(env, v2)
    r = diff(env, rev2, against="no-such-revision")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


@pytest.mark.parametrize("side", ["revision", "against"])
def test_missing_tree_on_either_side_is_404(env: Env, v2: bytes, side: str) -> None:
    _, v1, rev2 = two_revisions(env, v2)
    gone = rev2 if side == "revision" else v1
    env.client.portal.call(env.db["integrity_trees"].delete_one, {"_id": gone})  # type: ignore[union-attr]
    r = diff(env, rev2)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_first_revision_without_against_is_422(env: Env) -> None:
    rev1 = env.post_pdf(env.issuer()).json()["revision"]["id"]
    r = diff(env, rev1)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert r.json()["error"]["details"] == {"field": "against"}


def test_against_from_another_document_is_422(env: Env, v2: bytes) -> None:
    _, _, rev2 = two_revisions(env, v2)
    other_issuer = env.auth(env.user(["ISSUER"], "issuer2@example.com"))
    other = env.post_pdf(other_issuer, title="Other").json()["revision"]["id"]
    r = diff(env, rev2, against=other)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert r.json()["error"]["details"] == {"field": "against"}


def test_canon_version_mismatch_is_409_conflict_and_localize_is_not_called(
    env: Env, v2: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-09 audit finding 9: localize does not check canon_version, so the service must.
    Hashes from different canonicalization rules are not comparable; no regions are returned."""
    _, v1, rev2 = two_revisions(env, v2)
    old = CANON_VERSION - 1
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["integrity_trees"].update_one, {"_id": v1}, {"$set": {"canon_version": old}}
    )

    def must_not_run(*_: object) -> None:
        raise AssertionError("localize called across canon versions")

    monkeypatch.setattr("app.services.queries.localize", must_not_run)

    r = diff(env, rev2)

    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "CONFLICT"
    assert err["details"] == {"canon_version": CANON_VERSION, "against_canon_version": old}
