"""GET /revisions/{id}, /revisions/{id}/tree, /revisions/{id}/file (P5-05)."""

from urllib.parse import parse_qs, urlparse

import pytest

from proofchain_core import build_integrity_tree
from tests.unit.app.docs_env import PDFS, PREFIX, Env


def registered(env: Env) -> tuple[dict[str, str], str, str]:
    issuer = env.issuer()
    reg = env.post_pdf(issuer).json()
    return issuer, reg["document"]["id"], reg["revision"]["id"]


def reader(env: Env) -> dict[str, str]:
    return env.auth(env.user(["VERIFIER"], "verifier@example.com"))


def test_revision_detail(env: Env) -> None:
    _, doc_id, rev_id = registered(env)
    r = env.client.get(f"{PREFIX}/revisions/{rev_id}", headers=reader(env))
    assert r.status_code == 200
    body = r.json()
    assert (body["id"], body["document_id"], body["status"]) == (rev_id, doc_id, "PENDING")
    assert body["revocation"] is None
    assert "file" not in body and "s3_key" not in r.text


def test_tree_matches_the_core_library_for_the_uploaded_pdf(env: Env) -> None:
    _, doc_id, rev_id = registered(env)
    expected = build_integrity_tree((PDFS / "contract_3page.pdf").read_bytes())

    r = env.client.get(f"{PREFIX}/revisions/{rev_id}/tree", headers=reader(env))

    assert r.status_code == 200
    tree = r.json()
    assert (tree["revision_id"], tree["document_id"]) == (rev_id, doc_id)
    assert (tree["text_root"], tree["file_hash"]) == (expected.text_root, expected.file_hash)
    assert tree["page_count"] == expected.page_count == len(tree["pages"])
    leaves = [c["leaf_hash"] for p in tree["pages"] for c in p["chunks"]]
    assert leaves == [c.leaf_hash for p in expected.pages for c in p.chunks]
    assert [p["root"] for p in tree["pages"]] == [p.root for p in expected.pages]
    assert set(tree["pages"][0]["chunks"][0]) >= {"id", "index", "text", "leaf_hash", "bbox"}
    assert "_id" not in tree and "page_levels" not in tree


def test_tree_missing_for_an_existing_revision_is_404(env: Env) -> None:
    _, _, rev_id = registered(env)
    env.client.portal.call(env.db["integrity_trees"].delete_one, {"_id": rev_id})  # type: ignore[union-attr]
    r = env.client.get(f"{PREFIX}/revisions/{rev_id}/tree", headers=reader(env))
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_file_url_is_presigned_for_the_stored_version(env: Env) -> None:
    _, _, rev_id = registered(env)
    stored = env.revision(rev_id)["file"]

    r = env.client.get(f"{PREFIX}/revisions/{rev_id}/file", headers=reader(env))

    assert r.status_code == 200
    body = r.json()
    assert body["expires_in"] == 300  # s3_presign_expiry_seconds default
    url = urlparse(body["url"])
    assert url.path.endswith(stored["s3_key"])
    query = parse_qs(url.query)
    assert query["versionId"] == [stored["s3_version_id"]]
    assert query["X-Amz-Expires"] == ["300"]


def test_file_url_serves_the_original_bytes(env: Env) -> None:
    """The pinned version is the uploaded file even after a later overwrite of the same key."""
    _, _, rev_id = registered(env)
    stored = env.revision(rev_id)["file"]
    env.s3.put_object(Bucket="proofchain-test", Key=stored["s3_key"], Body=b"%PDF-overwritten")
    data = env.client.portal.call(env.storage.get, stored["s3_key"], stored["s3_version_id"])  # type: ignore[union-attr]
    assert data == (PDFS / "contract_3page.pdf").read_bytes()


@pytest.mark.parametrize("suffix", ["", "/tree", "/file"])
def test_unknown_revision_is_404(env: Env, suffix: str) -> None:
    r = env.client.get(f"{PREFIX}/revisions/nope{suffix}", headers=reader(env))
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


@pytest.mark.parametrize("suffix", ["", "/tree", "/file"])
def test_revision_reads_need_authentication(env: Env, suffix: str) -> None:
    _, _, rev_id = registered(env)
    assert env.client.get(f"{PREFIX}/revisions/{rev_id}{suffix}").status_code == 401
