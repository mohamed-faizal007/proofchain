"""GET /documents, /documents/{id}, its revisions and provenance (P5-05)."""

import datetime as dt
from typing import Any

import pytest

from tests.unit.app.docs_env import PREFIX, Env


def verifier(env: Env) -> dict[str, str]:
    return env.auth(env.user(["VERIFIER"], "verifier@example.com"))


def register(env: Env, issuer: dict[str, str], title: str, **form: str) -> tuple[str, str]:
    r = env.post_pdf(issuer, title=title, **form)
    assert r.status_code == 201, r.text
    return r.json()["document"]["id"], r.json()["revision"]["id"]


def listing(env: Env, headers: dict[str, str], **params: Any) -> Any:
    return env.client.get(f"{PREFIX}/documents", headers=headers, params=params)


def ids(resp: Any) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [d["id"] for d in resp.json()["items"]]


def set_updated(env: Env, doc_id: str, minutes_ago: int) -> None:
    at = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=minutes_ago)
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["documents"].update_one, {"_id": doc_id}, {"$set": {"updated_at": at}}
    )


# --- GET /documents ---


def test_list_is_paginated_newest_activity_first(env: Env) -> None:
    issuer = env.issuer()
    docs = [register(env, issuer, f"Doc {i}")[0] for i in range(3)]
    for minutes, doc_id in zip((30, 10, 20), docs, strict=True):
        set_updated(env, doc_id, minutes)
    reader = verifier(env)

    first = listing(env, reader, page=1, page_size=2)
    second = listing(env, reader, page=2, page_size=2)

    assert ids(first) == [docs[1], docs[2]]
    assert ids(second) == [docs[0]]
    assert {k: first.json()[k] for k in ("page", "page_size", "total")} == {
        "page": 1,
        "page_size": 2,
        "total": 3,
    }
    assert ids(listing(env, reader, page=3, page_size=2)) == []


def test_default_page_size_is_20(env: Env) -> None:
    r = listing(env, env.issuer())
    assert (r.json()["page"], r.json()["page_size"], r.json()["total"]) == (1, 20, 0)


def test_q_is_a_case_insensitive_literal_substring(env: Env) -> None:
    issuer = env.issuer()
    lease, _ = register(env, issuer, "Office LEASE 2026")
    regexy, _ = register(env, issuer, "Rates (v1).*")
    register(env, issuer, "Invoice")
    reader = verifier(env)

    assert ids(listing(env, reader, q="lease")) == [lease]
    assert ids(listing(env, reader, q=".*")) == [regexy]  # not a regex: matches only the literal
    assert ids(listing(env, reader, q="(v1)")) == [regexy]
    assert ids(listing(env, reader, q="nothing")) == []


def test_doc_type_filter(env: Env) -> None:
    issuer = env.issuer()
    invoice, _ = register(env, issuer, "A", doc_type="INVOICE")
    register(env, issuer, "B", doc_type="CONTRACT")
    assert ids(listing(env, verifier(env), doc_type="INVOICE")) == [invoice]


def test_status_filter_matches_documents_with_a_revision_in_that_status(env: Env) -> None:
    issuer, approver = env.issuer(), env.approver()
    pending, _ = register(env, issuer, "Pending only")
    approved, rev = register(env, issuer, "Approved only")
    assert env.review(approver, rev, "approve").status_code == 202
    reader = verifier(env)

    assert ids(listing(env, reader, status="PENDING")) == [pending]
    assert ids(listing(env, reader, status="APPROVED")) == [approved]
    assert ids(listing(env, reader, status="REJECTED")) == []


def test_status_filter_matches_document_under_every_status_its_revisions_have(env: Env) -> None:
    """Decision 4, intentional: v1 APPROVED + v2 PENDING -> listed under both filters."""
    issuer, approver = env.issuer(), env.approver()
    doc_id, v1 = register(env, issuer, "Mixed")
    assert env.review(approver, v1, "approve").status_code == 202
    assert env.submit(issuer, doc_id).status_code == 201  # v2 PENDING
    reader = verifier(env)

    assert ids(listing(env, reader, status="APPROVED")) == [doc_id]
    assert ids(listing(env, reader, status="PENDING")) == [doc_id]
    assert listing(env, reader, status="PENDING").json()["total"] == 1  # never duplicated


def test_filters_combine(env: Env) -> None:
    issuer = env.issuer()
    match, _ = register(env, issuer, "Lease A", doc_type="CONTRACT")
    register(env, issuer, "Lease B", doc_type="INVOICE")
    register(env, issuer, "Other", doc_type="CONTRACT")
    r = listing(env, verifier(env), q="lease", doc_type="CONTRACT", status="PENDING")
    assert ids(r) == [match]


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"status": "DRAFT"},
        {"doc_type": "MEMO"},
        {"q": "x" * 201},
    ],
)
def test_bad_list_params_are_422(env: Env, params: dict[str, Any]) -> None:
    r = listing(env, env.issuer(), **params)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_read_routes_need_authentication(env: Env) -> None:
    doc_id, _ = register(env, env.issuer(), "Lease")
    for path in ("", f"/{doc_id}", f"/{doc_id}/revisions", f"/{doc_id}/provenance"):
        assert env.client.get(f"{PREFIX}/documents{path}").status_code == 401, path


# --- GET /documents/{id} and /documents/{id}/revisions ---


def test_detail_has_latest_approved_revision_or_null(env: Env) -> None:
    issuer, approver = env.issuer(), env.approver()
    doc_id, v1 = register(env, issuer, "Lease")
    reader = verifier(env)
    url = f"{PREFIX}/documents/{doc_id}"

    body = env.client.get(url, headers=reader).json()
    assert (body["document"]["id"], body["latest_approved_revision"]) == (doc_id, None)

    assert env.review(approver, v1, "approve").status_code == 202
    assert env.submit(issuer, doc_id).status_code == 201  # a PENDING v2 is not "approved"
    latest = env.client.get(url, headers=reader).json()["latest_approved_revision"]
    assert (latest["id"], latest["status"], latest["version_no"]) == (v1, "APPROVED", 1)
    assert "s3_key" not in str(latest)


def test_revisions_are_ordered_by_revision_no(env: Env) -> None:
    issuer, approver = env.issuer(), env.approver()
    doc_id, v1 = register(env, issuer, "Lease")
    env.review(approver, v1, "reject", "no")
    v2 = env.submit(issuer, doc_id).json()["revision"]["id"]

    r = env.client.get(f"{PREFIX}/documents/{doc_id}/revisions", headers=verifier(env))

    assert r.status_code == 200
    assert [(x["id"], x["revision_no"], x["status"]) for x in r.json()] == [
        (v1, 1, "REJECTED"),
        (v2, 2, "PENDING"),
    ]


@pytest.mark.parametrize("suffix", ["", "/revisions", "/provenance"])
def test_unknown_document_is_404(env: Env, suffix: str) -> None:
    r = env.client.get(f"{PREFIX}/documents/nope{suffix}", headers=env.issuer())
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


# --- GET /documents/{id}/provenance ---


def test_provenance_lists_events_in_chain_order_with_valid_chain(env: Env) -> None:
    issuer, approver = env.issuer(), env.approver()
    doc_id, v1 = register(env, issuer, "Lease")
    assert env.review(approver, v1, "approve").status_code == 202

    body = env.client.get(f"{PREFIX}/documents/{doc_id}/provenance", headers=verifier(env)).json()

    assert (body["document_id"], body["chain_valid"]) == (doc_id, True)
    events = body["events"]
    assert [e["type"] for e in events] == [
        "DOCUMENT_CREATED",
        "REVISION_SUBMITTED",
        "REVISION_APPROVED",
        "VERSION_ANCHORED",
    ]
    assert events[0]["prev_event_hash"] is None
    for prev, cur in zip(events, events[1:], strict=False):
        assert cur["prev_event_hash"] == prev["event_hash"]


def test_tampered_event_makes_chain_invalid(env: Env) -> None:
    issuer = env.issuer()
    doc_id, _ = register(env, issuer, "Lease")
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["provenance_events"].update_one,
        {"document_id": doc_id, "type": "REVISION_SUBMITTED"},
        {"$set": {"data.change_note": "forged"}},
    )
    body = env.client.get(f"{PREFIX}/documents/{doc_id}/provenance", headers=issuer).json()
    assert body["chain_valid"] is False
    assert len(body["events"]) == 2  # still listed so the tampering is visible
