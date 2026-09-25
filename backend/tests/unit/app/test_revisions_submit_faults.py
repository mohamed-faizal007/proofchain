"""POST /documents/{id}/revisions fault injection (P5-02).

Forward order: s3 put -> revision -> tree -> counter $inc -> event. Every failure must roll back
S3, revision, tree and the counter (the counter undo is registered only after the $inc succeeded),
and the caller must see the original error with no exception text in the body or the service log.
"""

import logging
from typing import Any

import pytest

from app.errors import StorageError
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.storage import S3Storage
from tests.unit.app.docs_env import Env

SECRET = "SECRET-INTERNAL-DETAIL-hunter2"
STEPS: dict[str, tuple[type, str]] = {
    "s3_put": (S3Storage, "put"),
    "rev_insert": (RevisionRepository, "insert"),
    "tree_upsert": (TreeRepository, "upsert"),
    "counter": (DocumentRepository, "bump_revision_count"),
    "event": (EventRepository, "append"),
}


def baseline(env: Env) -> tuple[str, dict[str, Any]]:
    headers = env.issuer()
    first = env.post_pdf(headers).json()
    env.set_status(first["revision"]["id"], "APPROVED")
    return first["document"]["id"], {"headers": headers}


def inject(mp: pytest.MonkeyPatch, step: str, mode: str = "before") -> None:
    cls, name = STEPS[step]
    original = getattr(cls, name)

    async def faulty(self: Any, *args: Any, **kwargs: Any) -> Any:
        if (
            name == "bump_revision_count"
            and kwargs.get("delta", args[2] if len(args) > 2 else 1) < 0
        ):
            return await original(self, *args, **kwargs)  # let the compensating -1 through
        if step == "s3_put":
            raise StorageError("failed to store object")
        if mode == "after":
            await original(self, *args, **kwargs)
        raise RuntimeError(SECRET)

    mp.setattr(cls, name, faulty)


def state(env: Env, doc_id: str) -> dict[str, int]:
    doc = env.client.portal.call(env.db["documents"].find_one, {"_id": doc_id})  # type: ignore[union-attr]
    return {
        "revisions": env.count("revisions"),
        "trees": env.count("integrity_trees"),
        "s3": len(env.s3_keys()),
        "events": env.count("provenance_events"),
        "counter": doc["revision_count"],
    }


CLEAN = {"revisions": 1, "trees": 1, "s3": 1, "events": 2, "counter": 1}


@pytest.mark.parametrize("step", list(STEPS))
def test_failure_at_each_step_rolls_everything_back(
    env: Env, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    doc_id, ctx = baseline(env)
    assert state(env, doc_id) == CLEAN
    inject(monkeypatch, step)
    r = env.submit(ctx["headers"], doc_id)
    monkeypatch.undo()
    if step == "s3_put":
        assert (r.status_code, r.json()["error"]["code"]) == (502, "STORAGE_ERROR")
    else:
        assert (r.status_code, r.json()["error"]["code"]) == (500, "INTERNAL_ERROR")
    assert SECRET not in r.text and "revision" not in r.json()
    assert state(env, doc_id) == CLEAN

    # the pending slot is free again: a retry succeeds and gets revision_no 2
    retry = env.submit(ctx["headers"], doc_id)
    assert retry.status_code == 201, retry.text
    assert retry.json()["revision"]["revision_no"] == 2
    assert retry.json()["document"]["revision_count"] == 2


@pytest.mark.parametrize("step", ["rev_insert", "tree_upsert", "counter"])
def test_write_that_commits_then_raises_is_rolled_back(
    env: Env, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    doc_id, ctx = baseline(env)
    inject(monkeypatch, step, mode="after")
    r = env.submit(ctx["headers"], doc_id)
    monkeypatch.undo()
    assert r.status_code == 500 and SECRET not in r.text
    got = state(env, doc_id)
    if step == "counter":
        # $inc committed but its ack was lost, so no compensating -1 was registered (a known,
        # logged limit: an undo for an increment that may not have happened would corrupt it).
        assert {k: v for k, v in got.items() if k != "counter"} == {
            k: v for k, v in CLEAN.items() if k != "counter"
        }
        assert got["counter"] == 2
    else:
        assert got == CLEAN


def test_failing_rollback_keeps_original_error_and_logs_no_exception_text(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    doc_id, ctx = baseline(env)
    inject(monkeypatch, "event")

    async def broken(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"{SECRET}-cleanup")

    monkeypatch.setattr(S3Storage, "delete", broken)
    monkeypatch.setattr(RevisionRepository, "delete", broken)
    monkeypatch.setattr(TreeRepository, "delete", broken)
    with caplog.at_level(logging.ERROR, logger="app.services.documents"):
        r = env.submit(ctx["headers"], doc_id)
    monkeypatch.undo()

    assert (r.status_code, r.json()["error"]["code"]) == (500, "INTERNAL_ERROR")
    assert SECRET not in r.text
    logged = [rec for rec in caplog.records if rec.name == "app.services.documents"]
    text = "\n".join(rec.getMessage() for rec in logged)
    assert "revision submission rollback incomplete" in text
    assert "tree" in text and "revision" in text and "s3" in text
    assert SECRET not in text
    assert all(rec.exc_info is None for rec in logged)
    # the counter compensation still ran even though the other steps failed
    assert state(env, doc_id)["counter"] == 1
