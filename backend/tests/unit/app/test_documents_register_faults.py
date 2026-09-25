"""POST /documents fault injection: failure at every write step, and failure of the rollback itself.

Forward order: s3 put -> document -> revision -> tree -> event 1 -> event 2.
Rollback undoes tree, revision, document, s3 (best effort, every step attempted).
The caller must always see the ORIGINAL error (never a 2xx, never the cleanup error), and the
service log must carry class names and ids only, never exception text.
"""

import logging
import re
from collections.abc import Callable
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
SERVICE_LOGGER = "app.services.documents"

# resource -> (class, method) that rolls it back
DELETES: dict[str, tuple[type, str]] = {
    "s3": (S3Storage, "delete"),
    "document": (DocumentRepository, "delete"),
    "revision": (RevisionRepository, "delete"),
    "tree": (TreeRepository, "delete"),
}
# failing forward step -> (class, method, resources written before it, undo steps registered)
# DB undo steps are registered BEFORE their write, so a failing DB step's resource is registered.
STEPS: dict[str, tuple[type, str, set[str], set[str]]] = {
    "s3_put": (S3Storage, "put", set(), set()),
    "doc_insert": (DocumentRepository, "insert", {"s3"}, {"s3", "document"}),
    "rev_insert": (
        RevisionRepository,
        "insert",
        {"s3", "document"},
        {"s3", "document", "revision"},
    ),
    "tree_upsert": (
        TreeRepository,
        "upsert",
        {"s3", "document", "revision"},
        {"s3", "document", "revision", "tree"},
    ),
    "event_1": (
        EventRepository,
        "append",
        {"s3", "document", "revision", "tree"},
        {"s3", "document", "revision", "tree"},
    ),
    "event_2": (
        EventRepository,
        "append",
        {"s3", "document", "revision", "tree"},
        {"s3", "document", "revision", "tree"},
    ),
}
DB_STEPS = ["doc_insert", "rev_insert", "tree_upsert"]


def inject_failure(mp: pytest.MonkeyPatch, step: str, mode: str = "before") -> None:
    cls, name, _, _ = STEPS[step]
    original = getattr(cls, name)
    calls = {"n": 0}

    async def faulty(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if step == "event_1" and calls["n"] != 1:
            return await original(self, *args, **kwargs)
        if step == "event_2" and calls["n"] != 2:
            return await original(self, *args, **kwargs)
        if step == "s3_put":
            raise StorageError("failed to store object")
        if mode == "after":
            await original(self, *args, **kwargs)  # committed, then the ack is "lost"
        raise RuntimeError(SECRET)

    mp.setattr(cls, name, faulty)


def track_rollback(mp: pytest.MonkeyPatch, failing: set[str]) -> dict[str, int]:
    """Wrap every rollback method to count attempts; those in `failing` raise after being called."""
    attempts = dict.fromkeys(DELETES, 0)
    for res, (cls, name) in DELETES.items():
        original = getattr(cls, name)

        def make(res: str = res, original: Callable[..., Any] = original) -> Any:
            async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                attempts[res] += 1
                if res in failing:
                    raise RuntimeError(f"{SECRET}-cleanup-{res}")
                return await original(self, *args, **kwargs)

            return wrapper

        mp.setattr(cls, name, make())
    return attempts


def state(env: Env) -> dict[str, int]:
    return {
        "document": env.count("documents"),
        "revision": env.count("revisions"),
        "tree": env.count("integrity_trees"),
        "s3": len(env.s3_keys()),
        "events": env.count("provenance_events"),
    }


def assert_original_error(r: Any, step: str) -> None:
    if step == "s3_put":
        assert r.status_code == 502
        assert r.json()["error"]["code"] == "STORAGE_ERROR"
    else:
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    text = r.text
    assert SECRET not in text  # no exception text (original or cleanup) reaches the client
    assert "document" not in r.json() and "revision" not in r.json()  # no partial success
    assert "cleanup" not in text.lower() and "rollback" not in text.lower()


def service_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == SERVICE_LOGGER]


# --- Part A: single failure, rollback works ----------------------------------------------------


@pytest.mark.parametrize("step", list(STEPS))
def test_single_failure_rolls_back_everything_but_events(
    env: Env, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    headers = env.issuer()
    inject_failure(monkeypatch, step)
    r = env.post_pdf(headers)
    assert_original_error(r, step)
    s = state(env)
    assert (s["document"], s["revision"], s["tree"], s["s3"]) == (0, 0, 0, 0)
    assert s["events"] == (1 if step == "event_2" else 0)


@pytest.mark.parametrize("step", DB_STEPS)
def test_write_that_commits_then_raises_is_still_rolled_back(
    env: Env, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    headers = env.issuer()
    inject_failure(monkeypatch, step, mode="after")
    r = env.post_pdf(headers)
    assert_original_error(r, step)
    s = state(env)
    assert (s["document"], s["revision"], s["tree"], s["s3"], s["events"]) == (0, 0, 0, 0, 0)


def test_event_2_failure_leaves_a_logged_orphan_event(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    headers = env.issuer()
    inject_failure(monkeypatch, "event_2")
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        env.post_pdf(headers)
    msgs = [r.getMessage() for r in service_records(caplog)]
    assert any("1 provenance event(s)" in m and "document_id=" in m for m in msgs)


def test_service_stays_usable_after_a_rolled_back_failure(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = env.issuer()
    with monkeypatch.context() as mp:
        inject_failure(mp, "tree_upsert")
        assert env.post_pdf(headers).status_code == 500
    assert env.post_pdf(headers).status_code == 201
    s = state(env)
    assert (s["document"], s["revision"], s["tree"], s["s3"], s["events"]) == (1, 1, 1, 1, 2)


# --- Part B: failure of the failure ------------------------------------------------------------


@pytest.mark.parametrize("cleanup", list(DELETES))
@pytest.mark.parametrize("step", list(STEPS))
def test_one_rollback_step_failing_does_not_stop_the_others_or_mask_the_error(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    step: str,
    cleanup: str,
) -> None:
    headers = env.issuer()
    _, _, written, registered = STEPS[step]
    inject_failure(monkeypatch, step)
    attempts = track_rollback(monkeypatch, failing={cleanup})
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        r = env.post_pdf(headers)

    assert_original_error(r, step)  # original error only, no partial success

    for res in DELETES:  # every registered undo step was attempted exactly once
        assert attempts[res] == (1 if res in registered else 0), res

    s = state(env)  # only the resource whose cleanup failed can remain, and only if it was written
    for res in DELETES:
        assert s[res] == (1 if res == cleanup and res in written else 0), res

    msgs = [rec.getMessage() for rec in service_records(caplog)]
    joined = "\n".join(msgs)
    assert SECRET not in joined  # class names only, never exception text
    if cleanup in registered:
        assert f"rollback step {cleanup} failed: RuntimeError" in joined
        orphan = [m for m in msgs if "orphaned resources" in m]
        assert orphan and cleanup in orphan[0]
        assert re.search(r"document_id=[0-9a-f-]{36}", orphan[0])
        assert re.search(r"revision_id=[0-9a-f-]{36}", orphan[0])
        assert "s3_key=documents/" in orphan[0]
    else:
        assert "orphaned resources" not in joined


@pytest.mark.parametrize("step", ["rev_insert", "tree_upsert", "event_1", "event_2"])
def test_every_rollback_step_failing_still_attempts_all_and_returns_original_error(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    step: str,
) -> None:
    headers = env.issuer()
    _, _, written, registered = STEPS[step]
    inject_failure(monkeypatch, step)
    attempts = track_rollback(monkeypatch, failing=set(DELETES))
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        r = env.post_pdf(headers)

    assert_original_error(r, step)
    assert {res for res, n in attempts.items() if n} == registered
    assert all(n <= 1 for n in attempts.values())
    s = state(env)
    assert {res for res in DELETES if s[res]} == written
    joined = "\n".join(rec.getMessage() for rec in service_records(caplog))
    assert SECRET not in joined
    orphan = next(m for m in joined.split("\n") if "orphaned resources" in m)
    assert all(res in orphan for res in registered)


def test_s3_put_failure_with_failing_cleanup_has_nothing_to_clean_up(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    headers = env.issuer()
    inject_failure(monkeypatch, "s3_put")
    attempts = track_rollback(monkeypatch, failing=set(DELETES))
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        r = env.post_pdf(headers)
    assert_original_error(r, "s3_put")
    assert sum(attempts.values()) == 0
    assert service_records(caplog) == []
