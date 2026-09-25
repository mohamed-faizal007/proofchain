"""POST /documents/{id}/revisions: submission rules, authz, validation, concurrency (P5-02)."""

from typing import Any

import pymupdf
import pytest

from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.storage import revision_key
from proofchain_core import build_integrity_tree
from tests.unit.app.docs_env import PDFS, Env


def same_text_new_bytes() -> bytes:
    """contract_3page.pdf with different metadata: new file_hash, identical text_root."""
    doc = pymupdf.open(stream=(PDFS / "contract_3page.pdf").read_bytes())
    doc.set_metadata({"title": "reissued"})
    return doc.tobytes()  # type: ignore[no-any-return]


def register(env: Env, headers: dict[str, str], title: str = "Lease") -> dict[str, Any]:
    r = env.post_pdf(headers, title=title)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def approved_document(env: Env, headers: dict[str, str]) -> dict[str, Any]:
    body = register(env, headers)
    env.set_status(body["revision"]["id"], "APPROVED")
    return body


def test_submit_creates_revision_2_with_parent_and_bumps_counter(env: Env) -> None:
    headers = env.issuer()
    first = approved_document(env, headers)
    doc_id = first["document"]["id"]

    r = env.submit(headers, doc_id, change_note="  rent clause  ")
    assert r.status_code == 201, r.text
    doc, rev = r.json()["document"], r.json()["revision"]

    tree = build_integrity_tree((PDFS / "one_page.pdf").read_bytes())
    assert rev["revision_no"] == 2
    assert rev["parent_revision_id"] == first["revision"]["id"]
    assert rev["status"] == "PENDING"
    assert rev["change_note"] == "rent clause"
    assert rev["original_filename"] == "lease_v2.pdf"
    assert (rev["file_hash"], rev["text_root"]) == (tree.file_hash, tree.text_root)
    assert rev["submitted_by"] == first["document"]["owner_id"]
    assert doc["revision_count"] == 2
    assert doc["latest_approved_revision_id"] is None  # only approval (P5-03) moves this
    assert doc["updated_at"] >= first["document"]["updated_at"]

    stored = DocumentRepository(env.db)
    persisted = env.client.portal.call(stored.get, doc_id)  # type: ignore[union-attr]
    assert persisted is not None and persisted.revision_count == 2
    assert env.s3_keys().count(revision_key(doc_id, rev["id"])) == 1
    assert env.count("integrity_trees") == 2
    assert env.count("revisions") == 2


def test_submitted_event_is_appended_and_chain_stays_valid(env: Env) -> None:
    headers = env.issuer()
    first = approved_document(env, headers)
    doc_id = first["document"]["id"]
    rev = env.submit(headers, doc_id).json()["revision"]

    events = EventRepository(env.db)
    listed = env.client.portal.call(events.list_by_document, doc_id)  # type: ignore[union-attr]
    assert [e.type for e in listed] == [
        "DOCUMENT_CREATED",
        "REVISION_SUBMITTED",
        "REVISION_SUBMITTED",
    ]
    last = listed[-1]
    assert last.revision_id == rev["id"] and last.actor_id == first["document"]["owner_id"]
    assert last.data["revision_no"] == 2
    assert last.data["parent_revision_id"] == first["revision"]["id"]
    assert last.data["text_root"] == rev["text_root"]
    assert env.client.portal.call(events.verify_chain, doc_id).ok  # type: ignore[union-attr]


def test_second_submit_while_pending_is_409_and_writes_nothing(env: Env) -> None:
    headers = env.issuer()
    doc_id = approved_document(env, headers)["document"]["id"]
    assert env.submit(headers, doc_id).status_code == 201
    before = (env.count("revisions"), env.count("provenance_events"), len(env.s3_keys()))

    r = env.submit(headers, doc_id, "contract_3page.pdf")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PENDING_REVISION_EXISTS"
    assert (env.count("revisions"), env.count("provenance_events"), len(env.s3_keys())) == before


def test_pending_revision_on_another_document_never_blocks(env: Env) -> None:
    headers = env.issuer()
    doc_a = approved_document(env, headers)["document"]["id"]
    doc_b = approved_document(env, headers)["document"]["id"]

    assert env.submit(headers, doc_a).status_code == 201  # A now has a PENDING revision
    r = env.submit(headers, doc_b)  # B must be unaffected
    assert r.status_code == 201, r.text
    assert r.json()["revision"]["document_id"] == doc_b
    assert r.json()["revision"]["revision_no"] == 2

    # and A is still blocked while B's pending exists
    assert env.submit(headers, doc_a, "contract_3page.pdf").status_code == 409


def test_pending_revision_of_another_owner_never_blocks(env: Env) -> None:
    h1 = env.auth(env.user(["ISSUER"], "one@example.com"))
    h2 = env.auth(env.user(["ISSUER"], "two@example.com"))
    doc_1 = approved_document(env, h1)["document"]["id"]
    doc_2 = approved_document(env, h2)["document"]["id"]
    assert env.submit(h1, doc_1).status_code == 201
    assert env.submit(h2, doc_2).status_code == 201


def test_resubmit_after_rejection_keeps_last_approved_as_parent(env: Env) -> None:
    headers = env.issuer()
    first = approved_document(env, headers)
    doc_id = first["document"]["id"]
    rejected = env.submit(headers, doc_id).json()["revision"]
    env.set_status(rejected["id"], "REJECTED")

    r = env.submit(headers, doc_id, change_note="fixed")
    assert r.status_code == 201, r.text
    rev = r.json()["revision"]
    assert rev["revision_no"] == 3
    assert rev["parent_revision_id"] == first["revision"]["id"]
    assert r.json()["document"]["revision_count"] == 3


def test_parent_is_latest_approved_not_latest_revision(env: Env) -> None:
    headers = env.issuer()
    first = approved_document(env, headers)
    doc_id = first["document"]["id"]
    second = env.submit(headers, doc_id).json()["revision"]
    env.set_status(second["id"], "APPROVED")
    third = env.submit(headers, doc_id, "contract_3page.pdf").json()["revision"]
    assert third["parent_revision_id"] == second["id"]


def test_same_text_different_bytes_is_no_content_change(env: Env) -> None:
    headers = env.issuer()
    doc_id = approved_document(env, headers)["document"]["id"]
    before = (env.count("revisions"), env.count("provenance_events"), len(env.s3_keys()))

    r = env.submit(headers, doc_id, same_text_new_bytes())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "NO_CONTENT_CHANGE"
    assert (env.count("revisions"), env.count("provenance_events"), len(env.s3_keys())) == before
    assert env.count("integrity_trees") == 1


def test_byte_identical_file_is_no_content_change(env: Env) -> None:
    headers = env.issuer()
    doc_id = approved_document(env, headers)["document"]["id"]
    r = env.submit(headers, doc_id, "contract_3page.pdf")
    assert (r.status_code, r.json()["error"]["code"]) == (422, "NO_CONTENT_CHANGE")


def test_no_parent_means_no_content_change_check(env: Env) -> None:
    """Revision 1 was rejected, so nothing is approved yet: the same text may be resubmitted."""
    headers = env.issuer()
    first = register(env, headers)
    env.set_status(first["revision"]["id"], "REJECTED")
    r = env.submit(headers, first["document"]["id"], "contract_3page.pdf")
    assert r.status_code == 201, r.text
    assert r.json()["revision"]["parent_revision_id"] is None
    assert r.json()["revision"]["revision_no"] == 2


def test_requires_authentication(env: Env) -> None:
    doc_id = register(env, env.issuer())["document"]["id"]
    r = env.submit({}, doc_id)
    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_non_issuer_roles_are_forbidden(env: Env) -> None:
    doc_id = approved_document(env, env.issuer())["document"]["id"]
    for i, role in enumerate(["VERIFIER", "APPROVER", "ADMIN"]):
        headers = env.auth(env.user([role], f"r{i}@example.com"))  # type: ignore[list-item]
        r = env.submit(headers, doc_id)
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN"), role
    assert env.count("revisions") == 1


def test_issuer_who_is_not_the_owner_is_forbidden(env: Env) -> None:
    doc_id = approved_document(env, env.issuer())["document"]["id"]
    other = env.auth(env.user(["ISSUER"], "other@example.com"))
    r = env.submit(other, doc_id)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
    assert env.count("revisions") == 1 and len(env.s3_keys()) == 1


def test_unknown_document_is_404(env: Env) -> None:
    r = env.submit(env.issuer(), "no-such-document")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_change_note_is_required(env: Env) -> None:
    headers = env.issuer()
    doc_id = approved_document(env, headers)["document"]["id"]
    assert env.submit(headers, doc_id, change_note="   ").status_code == 422
    r = env.client.post(
        f"/api/v1/documents/{doc_id}/revisions",
        headers=headers,
        files={"file": ("x.pdf", (PDFS / "one_page.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 422
    assert env.count("revisions") == 1


@pytest.mark.parametrize(
    ("pdf", "status", "code"),
    [
        pytest.param(b"just text", 422, "INVALID_PDF", id="text"),
        pytest.param("not_a_pdf.pdf", 422, "INVALID_PDF", id="not-a-pdf"),
        pytest.param("encrypted.pdf", 422, "ENCRYPTED_PDF", id="encrypted"),
        pytest.param("image_only.pdf", 422, "NO_EXTRACTABLE_TEXT", id="image-only"),
        pytest.param(
            b"%PDF-1.7" + b"0" * (1024 * 1024 + 10), 413, "FILE_TOO_LARGE", id="too-large"
        ),
    ],
)
def test_invalid_uploads_are_rejected_cleanly(
    env: Env, pdf: bytes | str, status: int, code: str
) -> None:
    headers = env.issuer()
    doc_id = approved_document(env, headers)["document"]["id"]
    r = env.submit(headers, doc_id, pdf)
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)
    assert env.count("revisions") == 1 and len(env.s3_keys()) == 1
    assert env.count("provenance_events") == 2


def test_note_over_limit_is_422(env: Env) -> None:
    headers = env.issuer()
    doc_id = approved_document(env, headers)["document"]["id"]
    assert env.submit(headers, doc_id, change_note="x" * 2001).status_code == 422


def test_racing_submit_loses_on_unique_revision_no_and_is_rolled_back(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both requests pass the pending check and compute the same revision_no: one must lose."""
    headers = env.issuer()
    doc_id = approved_document(env, headers)["document"]["id"]
    assert env.submit(headers, doc_id).status_code == 201  # winner: revision_no 2

    async def no_pending(self: Any, document_id: str) -> None:
        return None

    async def stale_next_no(self: Any, document_id: str) -> int:
        return 2

    monkeypatch.setattr(RevisionRepository, "get_pending", no_pending)
    monkeypatch.setattr(RevisionRepository, "next_revision_no", stale_next_no)
    r = env.submit(headers, doc_id, change_note="loser")
    monkeypatch.undo()

    assert (r.status_code, r.json()["error"]["code"]) == (409, "PENDING_REVISION_EXISTS")
    assert env.count("revisions") == 2
    assert env.count("integrity_trees") == 2
    assert len(env.s3_keys()) == 2
    assert env.count("provenance_events") == 3
    stored = env.client.portal.call(DocumentRepository(env.db).get, doc_id)  # type: ignore[union-attr]
    assert stored is not None and stored.revision_count == 2
