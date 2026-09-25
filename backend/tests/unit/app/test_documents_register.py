"""POST /documents: registration happy path, authz and validation (P5-01)."""

import hashlib

from app.repositories.events import EventRepository
from app.storage import revision_key
from proofchain_core import build_integrity_tree
from tests.unit.app.docs_env import PDFS, Env


def test_issuer_registers_document_and_revision_1(env: Env) -> None:
    headers = env.issuer()
    r = env.post_pdf(headers, change_note="first upload")
    assert r.status_code == 201, r.text
    body = r.json()
    doc, rev = body["document"], body["revision"]

    tree = build_integrity_tree((PDFS / "contract_3page.pdf").read_bytes())
    assert rev["file_hash"] == tree.file_hash
    assert rev["text_root"] == tree.text_root
    assert rev["canon_version"] == tree.canon_version
    assert rev["page_count"] == 3
    assert rev["chunk_count"] == sum(len(p.chunks) for p in tree.pages)
    assert rev["status"] == "PENDING"
    assert rev["revision_no"] == 1
    assert rev["parent_revision_id"] is None
    assert rev["version_no"] is None
    assert rev["anchor"]["status"] == "NOT_REQUESTED"
    assert rev["change_note"] == "first upload"
    assert rev["original_filename"] == "lease.pdf"
    assert "file" not in rev and "s3_key" not in str(rev)

    assert doc["title"] == "Lease"
    assert doc["doc_type"] == "CONTRACT"
    assert doc["revision_count"] == 1
    assert doc["latest_approved_revision_id"] is None
    assert doc["chain_doc_id"] == hashlib.sha256(doc["id"].encode()).hexdigest()
    assert rev["document_id"] == doc["id"]
    assert rev["submitted_by"] == doc["owner_id"]


def test_state_is_persisted_and_events_chain_is_valid(env: Env) -> None:
    r = env.post_pdf(env.issuer())
    doc, rev = r.json()["document"], r.json()["revision"]

    assert env.s3_keys() == [revision_key(doc["id"], rev["id"])]
    stored = env.s3.get_object(Bucket="proofchain-test", Key=revision_key(doc["id"], rev["id"]))
    assert stored["Body"].read() == (PDFS / "contract_3page.pdf").read_bytes()

    assert (env.count("documents"), env.count("revisions"), env.count("integrity_trees")) == (
        1,
        1,
        1,
    )
    tree = env.client.portal.call(env.db["integrity_trees"].find_one, {"_id": rev["id"]})  # type: ignore[union-attr]
    assert tree["text_root"] == rev["text_root"]
    assert tree["document_id"] == doc["id"]
    assert tree["pages"][0]["chunks"][0]["text"]

    events = EventRepository(env.db)
    listed = env.client.portal.call(events.list_by_document, doc["id"])  # type: ignore[union-attr]
    assert [e.type for e in listed] == ["DOCUMENT_CREATED", "REVISION_SUBMITTED"]
    assert all(e.actor_id == doc["owner_id"] and e.revision_id == rev["id"] for e in listed)
    verdict = env.client.portal.call(events.verify_chain, doc["id"])  # type: ignore[union-attr]
    assert verdict.ok


def test_same_pdf_twice_creates_two_independent_documents(env: Env) -> None:
    headers = env.issuer()
    a = env.post_pdf(headers).json()
    b = env.post_pdf(headers).json()
    assert a["document"]["id"] != b["document"]["id"]
    assert a["document"]["chain_doc_id"] != b["document"]["chain_doc_id"]
    assert a["revision"]["file_hash"] == b["revision"]["file_hash"]
    assert env.count("documents") == 2


def test_requires_authentication(env: Env) -> None:
    r = env.post_pdf({})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_non_issuer_roles_are_forbidden(env: Env) -> None:
    for i, role in enumerate(["VERIFIER", "APPROVER", "ADMIN"]):
        headers = env.auth(env.user([role], f"r{i}@example.com"))  # type: ignore[list-item]
        r = env.post_pdf(headers)
        assert r.status_code == 403, role
        assert r.json()["error"]["code"] == "FORBIDDEN"
    assert env.count("documents") == 0
    assert env.s3_keys() == []


def _assert_rejected_cleanly(env: Env, r: object, status: int, code: str) -> None:
    assert r.status_code == status, r.text  # type: ignore[attr-defined]
    assert r.json()["error"]["code"] == code  # type: ignore[attr-defined]
    assert env.count("documents") == 0
    assert env.count("revisions") == 0
    assert env.count("provenance_events") == 0
    assert env.s3_keys() == []


def test_non_pdf_is_invalid_pdf(env: Env) -> None:
    r = env.post_pdf(env.issuer(), b"just some text, not a pdf")
    _assert_rejected_cleanly(env, r, 422, "INVALID_PDF")


def test_not_a_pdf_fixture_is_invalid_pdf(env: Env) -> None:
    r = env.post_pdf(env.issuer(), "not_a_pdf.pdf")
    _assert_rejected_cleanly(env, r, 422, "INVALID_PDF")


def test_pdf_header_with_garbage_body_is_invalid_pdf(env: Env) -> None:
    r = env.post_pdf(env.issuer(), b"%PDF-1.7\n" + b"\x00garbage" * 50)
    _assert_rejected_cleanly(env, r, 422, "INVALID_PDF")


def test_image_only_pdf_has_no_extractable_text(env: Env) -> None:
    r = env.post_pdf(env.issuer(), "image_only.pdf")
    _assert_rejected_cleanly(env, r, 422, "NO_EXTRACTABLE_TEXT")


def test_encrypted_pdf_is_rejected(env: Env) -> None:
    r = env.post_pdf(env.issuer(), "encrypted.pdf")
    _assert_rejected_cleanly(env, r, 422, "ENCRYPTED_PDF")


def test_oversize_upload_is_413(env: Env) -> None:
    big = b"%PDF-1.7\n" + b"0" * (1024 * 1024)  # limit is 1 MB in the test settings
    r = env.post_pdf(env.issuer(), big)
    _assert_rejected_cleanly(env, r, 413, "FILE_TOO_LARGE")


def test_bad_form_fields_are_422(env: Env) -> None:
    headers = env.issuer()
    _assert_rejected_cleanly(env, env.post_pdf(headers, doc_type="MEME"), 422, "VALIDATION_ERROR")
    _assert_rejected_cleanly(env, env.post_pdf(headers, title="   "), 422, "VALIDATION_ERROR")
    _assert_rejected_cleanly(env, env.post_pdf(headers, title="x" * 201), 422, "VALIDATION_ERROR")
    _assert_rejected_cleanly(
        env, env.post_pdf(headers, change_note="n" * 2001), 422, "VALIDATION_ERROR"
    )


def test_missing_file_is_422(env: Env) -> None:
    r = env.client.post(
        "/api/v1/documents", headers=env.issuer(), data={"title": "t", "doc_type": "OTHER"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_filename_path_is_stripped(env: Env) -> None:
    data = (PDFS / "one_page.pdf").read_bytes()
    r = env.client.post(
        "/api/v1/documents",
        headers=env.issuer(),
        files={"file": ("C:\\Users\\x\\..\\secret\\lease.pdf", data, "application/pdf")},
        data={"title": "t", "doc_type": "OTHER"},
    )
    assert r.status_code == 201
    assert r.json()["revision"]["original_filename"] == "lease.pdf"
