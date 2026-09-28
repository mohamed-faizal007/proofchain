"""GET /revisions?status=PENDING (P8-04): the approvals queue, across all documents."""

import datetime as dt
from typing import Any

import pytest

from app.repositories.documents import DocumentRepository
from tests.unit.app.docs_env import PREFIX, Env


def register(env: Env, issuer: dict[str, str], title: str, **form: str) -> tuple[str, str]:
    r = env.post_pdf(issuer, title=title, **form)
    assert r.status_code == 201, r.text
    return r.json()["document"]["id"], r.json()["revision"]["id"]


def set_submitted_at(env: Env, revision_id: str, at: dt.datetime) -> None:
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["revisions"].update_one, {"_id": revision_id}, {"$set": {"submitted_at": at}}
    )


def queue(env: Env, headers: dict[str, str], **params: Any) -> Any:
    return env.client.get(f"{PREFIX}/revisions", headers=headers, params=params)


def test_lists_pending_revisions_across_documents_oldest_first(env: Env) -> None:
    issuer_a = env.user(["ISSUER"], "issuer-a@example.com")
    issuer_b = env.user(["ISSUER"], "issuer-b@example.com")
    doc_a, rev_a = register(env, env.auth(issuer_a), "Lease A")
    doc_b, rev_b = register(env, env.auth(issuer_b), "Lease B")
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    set_submitted_at(env, rev_a, now - dt.timedelta(minutes=5))
    set_submitted_at(env, rev_b, now - dt.timedelta(minutes=10))

    r = queue(env, env.approver(), status="PENDING")

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 20, 2)
    assert [item["id"] for item in body["items"]] == [rev_b, rev_a]  # oldest first
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[rev_a]["document_id"] == doc_a
    assert by_id[rev_a]["document_title"] == "Lease A"
    assert by_id[rev_b]["document_title"] == "Lease B"
    assert "file" not in by_id[rev_a] and "s3_key" not in r.text


def test_approved_and_rejected_revisions_are_excluded(env: Env) -> None:
    issuer = env.auth(env.user(["ISSUER"], "issuer@example.com"))
    _, rev_pending = register(env, issuer, "Still pending")
    _, rev_approved = register(env, issuer, "Will be approved")
    approver = env.approver()
    env.review(approver, rev_approved, "approve")

    r = queue(env, approver, status="PENDING")

    assert [item["id"] for item in r.json()["items"]] == [rev_pending]


def test_pagination(env: Env) -> None:
    issuer = env.auth(env.user(["ISSUER"], "issuer@example.com"))
    ids = [register(env, issuer, f"Doc {i}")[1] for i in range(3)]
    approver = env.approver()

    page1 = queue(env, approver, status="PENDING", page=1, page_size=2)
    page2 = queue(env, approver, status="PENDING", page=2, page_size=2)

    assert (page1.json()["total"], page2.json()["total"]) == (3, 3)
    assert len(page1.json()["items"]) == 2
    assert len(page2.json()["items"]) == 1
    seen = [i["id"] for i in page1.json()["items"]] + [i["id"] for i in page2.json()["items"]]
    assert sorted(seen) == sorted(ids)


def test_requires_authentication(env: Env) -> None:
    assert queue(env, {}, status="PENDING").status_code == 401


@pytest.mark.parametrize("roles", [["ISSUER"], ["VERIFIER"]])
def test_forbidden_for_issuer_and_verifier(env: Env, roles: list[str]) -> None:
    headers = env.auth(env.user(roles, "u@example.com"))  # type: ignore[arg-type]
    r = queue(env, headers, status="PENDING")
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


def test_admin_may_also_read_the_queue(env: Env) -> None:
    issuer = env.auth(env.user(["ISSUER"], "issuer@example.com"))
    register(env, issuer, "Doc")
    admin = env.auth(env.user(["ADMIN"], "admin@example.com"))
    r = queue(env, admin, status="PENDING")
    assert r.status_code == 200, r.text


def test_bad_status_value_is_422(env: Env) -> None:
    r = queue(env, env.approver(), status="APPROVED")
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_missing_status_is_422(env: Env) -> None:
    r = env.client.get(f"{PREFIX}/revisions", headers=env.approver())
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_page_size_over_max_is_422(env: Env) -> None:
    r = queue(env, env.approver(), status="PENDING", page_size=101)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_empty_queue(env: Env) -> None:
    r = queue(env, env.approver(), status="PENDING")
    assert r.status_code == 200, r.text
    assert (r.json()["items"], r.json()["total"]) == ([], 0)


def test_no_n_plus_one_document_lookup(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    issuer = env.auth(env.user(["ISSUER"], "issuer@example.com"))
    for i in range(5):
        register(env, issuer, f"Doc {i}")
    calls: list[list[str]] = []
    original = DocumentRepository.find_by_ids

    async def counting(self: DocumentRepository, ids: list[str]) -> Any:
        calls.append(ids)
        return await original(self, ids)

    monkeypatch.setattr(DocumentRepository, "find_by_ids", counting)

    r = queue(env, env.approver(), status="PENDING")

    assert r.status_code == 200, r.text
    assert len(calls) == 1  # one batched lookup, not one per revision
    assert len(calls[0]) == 5
