"""Helpers for /verify tests (P6-04): real register/approve/anchor flow on the fake chain."""

from pathlib import Path
from typing import Any

import pytest

from tests.fixtures import make_fixtures
from tests.unit.app.docs_env import PDFS, PREFIX, Env

OLD, NEW = "2% per month", "3% per month"


def original() -> bytes:
    return (PDFS / "contract_3page.pdf").read_bytes()


def edited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    """contract_3page.pdf with one edit on page 2 (index 1), from the same fixture generator."""
    pages = [[(k, t.replace(OLD, NEW)) for k, t in page] for page in make_fixtures.CONTRACT_PAGES]
    monkeypatch.setattr(make_fixtures, "CONTRACT_PAGES", pages)
    path = tmp_path / "contract_v2.pdf"
    make_fixtures._contract(path)
    return path.read_bytes()


def verify(
    env: Env,
    data: bytes,
    headers: dict[str, str] | None = None,
    filename: str = "upload.pdf",
    **form: str,
) -> Any:
    return env.client.post(
        f"{PREFIX}/verify",
        headers=headers or {},
        files={"file": (filename, data, "application/pdf")},
        data=form,
    )


def register_approved(env: Env) -> tuple[dict[str, str], dict[str, str], str, str]:
    """(issuer, approver, document_id, revision_id): revision 1 APPROVED and ANCHORED."""
    issuer, approver = env.issuer(), env.approver()
    reg = env.post_pdf(issuer).json()
    doc_id, rev_id = reg["document"]["id"], reg["revision"]["id"]
    assert env.review(approver, rev_id, "approve").status_code == 202
    assert env.revision(rev_id)["anchor"]["status"] == "ANCHORED"
    return issuer, approver, doc_id, rev_id


def submit(env: Env, issuer: dict[str, str], doc_id: str, data: bytes) -> str:
    r = env.submit(issuer, doc_id, data)
    assert r.status_code == 201, r.text
    return str(r.json()["revision"]["id"])


def step(report: dict[str, Any], name: str) -> dict[str, Any]:
    [found] = [s for s in report["steps"] if s["name"] == name]
    return found  # type: ignore[no-any-return]


def edit_mongo(env: Env, revision_id: str, **fields: Any) -> None:
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["revisions"].update_one, {"_id": revision_id}, {"$set": fields}
    )
