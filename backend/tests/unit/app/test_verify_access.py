"""/verify persistence, timings, errors and /verifications access rules (P6-04)."""

from typing import Any

import pytest

from tests.unit.app.docs_env import PDFS, PREFIX, Env, settings
from tests.unit.app.verify_helpers import original, register_approved, verify


def rows(env: Env) -> list[dict[str, Any]]:
    async def load() -> list[dict[str, Any]]:
        return [d async for d in env.db["verifications"].find({})]

    return env.client.portal.call(load)  # type: ignore[union-attr,no-any-return]


def get(env: Env, verification_id: str, headers: dict[str, str] | None = None) -> Any:
    return env.client.get(f"{PREFIX}/verifications/{verification_id}", headers=headers or {})


def test_verification_is_persisted_with_timings_and_candidate(env: Env) -> None:
    _, _, doc_id, rev_id = register_approved(env)
    user = env.user(["VERIFIER"], "v@example.com")

    body = verify(env, original(), env.auth(user), filename="C:\\tmp\\copy.pdf").json()

    [row] = rows(env)
    assert row["_id"] == body["id"] and row["requested_by"] == user.id
    assert (row["verdict"], row["document_id"]) == ("AUTHENTIC_LATEST", doc_id)
    assert row["matched_revision_id"] == rev_id and row["reference_revision_id"] is None
    assert row["candidate"]["filename"] == "copy.pdf"  # path stripped
    assert len(row["candidate"]["file_hash"]) == len(row["candidate"]["text_root"]) == 64
    assert row["candidate"]["page_count"] == 3
    assert row["chain_check"]["ok"] is True
    assert set(row["timings_ms"]) == {"hash", "match", "localize", "chain", "nlp", "total"}
    assert row["timings_ms"]["total"] >= max(
        row["timings_ms"][k] for k in ("hash", "match", "localize", "chain")
    )
    assert body["timings_ms"] == row["timings_ms"]


def test_report_read_back_equals_the_verify_response(env: Env) -> None:
    register_approved(env)
    user = env.user(["VERIFIER"], "v@example.com")
    headers = env.auth(user)

    posted = verify(env, original(), headers).json()

    assert get(env, posted["id"], headers).json() == posted


def test_public_verify_allows_anonymous_and_stores_no_requester(env: Env) -> None:
    register_approved(env)

    r = verify(env, original())

    assert r.status_code == 200 and r.json()["verdict"] == "AUTHENTIC_LATEST"
    assert rows(env)[0]["requested_by"] is None


def test_verify_requires_login_when_public_verify_is_off(env: Env) -> None:
    register_approved(env)
    env.client.app.state.settings = settings().model_copy(update={"public_verify": False})  # type: ignore[attr-defined]

    anon = verify(env, original())
    authed = verify(env, original(), env.auth(env.user(["VERIFIER"], "v@example.com")))

    assert (anon.status_code, anon.json()["error"]["code"]) == (401, "UNAUTHORIZED")
    assert authed.status_code == 200
    assert len(rows(env)) == 1  # the refused request left nothing behind


@pytest.mark.parametrize(
    ("pdf", "status", "code"),
    [
        ("not_a_pdf.pdf", 422, "INVALID_PDF"),
        ("encrypted.pdf", 422, "ENCRYPTED_PDF"),
        ("image_only.pdf", 422, "NO_EXTRACTABLE_TEXT"),
    ],
)
def test_bad_uploads_use_the_usual_error_envelope(
    env: Env, pdf: str, status: int, code: str
) -> None:
    r = verify(env, (PDFS / pdf).read_bytes())
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)
    assert rows(env) == []


def test_oversized_upload_is_413(env: Env) -> None:
    r = verify(env, b"%PDF-" + b"0" * (1024 * 1024 + 10))
    assert (r.status_code, r.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


def test_unknown_document_id_is_404(env: Env) -> None:
    r = verify(env, original(), document_id="no-such-document")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_history_is_own_only_newest_first_and_paginated(env: Env) -> None:
    register_approved(env)
    alice = env.auth(env.user(["VERIFIER"], "alice@example.com"))
    bob = env.auth(env.user(["VERIFIER"], "bob@example.com"))
    ids = [verify(env, original(), alice).json()["id"] for _ in range(3)]
    verify(env, original(), bob)
    verify(env, original())  # anonymous, belongs to nobody

    first = env.client.get(f"{PREFIX}/verifications", params={"page_size": 2}, headers=alice).json()
    second = env.client.get(
        f"{PREFIX}/verifications", params={"page_size": 2, "page": 2}, headers=alice
    ).json()

    assert (first["total"], first["page"], first["page_size"]) == (3, 1, 2)
    assert [i["id"] for i in first["items"]] + [i["id"] for i in second["items"]] == ids[::-1]
    item = first["items"][0]
    assert item["verdict"] == "AUTHENTIC_LATEST" and item["document"]["title"] == "Lease"
    assert item["filename"] == "upload.pdf" and len(item["file_hash"]) == 64
    assert "steps" not in item


def test_history_requires_authentication(env: Env) -> None:
    r = env.client.get(f"{PREFIX}/verifications")
    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_owner_and_admin_can_read_a_report_other_users_cannot(env: Env) -> None:
    register_approved(env)
    owner = env.auth(env.user(["VERIFIER"], "owner@example.com"))
    other = env.auth(env.user(["VERIFIER"], "other@example.com"))
    admin = env.auth(env.user(["ADMIN"], "admin@example.com"))
    vid = verify(env, original(), owner).json()["id"]

    assert get(env, vid, owner).status_code == 200
    assert get(env, vid, admin).status_code == 200
    denied = get(env, vid, other)
    assert (denied.status_code, denied.json()["error"]["code"]) == (403, "FORBIDDEN")
    assert get(env, vid).status_code == 401


def test_anonymous_report_is_admin_only_even_for_authenticated_non_admins(env: Env) -> None:
    register_approved(env)
    vid = verify(env, original()).json()["id"]  # anonymous: requested_by is null
    verifier = env.auth(env.user(["VERIFIER"], "verifier@example.com"))
    issuer = env.auth(env.user(["ISSUER", "APPROVER"], "multi@example.com"))
    admin = env.auth(env.user(["ADMIN"], "admin@example.com"))

    for headers in (verifier, issuer):
        r = get(env, vid, headers)
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
    assert get(env, vid).status_code == 401
    assert get(env, vid, admin).status_code == 200
    assert get(env, vid, admin).json()["verdict"] == "AUTHENTIC_LATEST"


def test_unknown_verification_is_404(env: Env) -> None:
    r = get(env, "nope", env.auth(env.user(["VERIFIER"], "v@example.com")))
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
