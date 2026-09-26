"""Review state machine (03_DATA_MODEL): PENDING -> APPROVED | REJECTED, everything else 409.

Concurrency tests hold both requests at a barrier right after the PENDING pre-check, so both pass
it and the race is decided by the conditional `set_review` write, not by request timing.
"""

import asyncio
from typing import Any

import httpx
import pytest

from app.repositories.events import EventRepository
from app.repositories.revisions import RevisionRepository
from tests.unit.app.docs_env import PREFIX, Env

ACTIONS = ["approve", "reject"]
EVENT = {"approve": "REVISION_APPROVED", "reject": "REVISION_REJECTED"}
FINAL = {"approve": "APPROVED", "reject": "REJECTED"}


def pending(env: Env) -> Any:
    reg = env.post_pdf(env.issuer()).json()
    return reg["revision"]["id"], reg["document"]["id"]


@pytest.mark.parametrize("first", ACTIONS)
@pytest.mark.parametrize("second", ACTIONS)
def test_reviewed_revision_is_terminal(env: Env, first: str, second: str) -> None:
    rev_id, _ = pending(env)
    assert env.review(env.approver("a1@example.com"), rev_id, first).status_code in (200, 202)
    before = (env.revision(rev_id), len(env.events()))

    r = env.review(env.approver("a2@example.com"), rev_id, second)

    assert (r.status_code, r.json()["error"]["code"]) == (409, "REVISION_NOT_PENDING")
    assert (env.revision(rev_id), len(env.events())) == before


@pytest.mark.parametrize("action", ACTIONS)
def test_revoked_revision_cannot_be_reviewed(env: Env, action: str) -> None:
    rev_id, _ = pending(env)
    env.set_status(rev_id, "REVOKED")
    r = env.review(env.approver(), rev_id, action)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "REVISION_NOT_PENDING")
    assert env.events(EVENT[action]) == []


def race(
    env: Env, monkeypatch: pytest.MonkeyPatch, calls: list[tuple[str, dict[str, str]]]
) -> list[Any]:
    """Send `calls` concurrently; all pass the PENDING pre-check before any write."""
    barrier = asyncio.Barrier(len(calls))
    original = RevisionRepository.get

    async def get_then_wait(self: RevisionRepository, id_: str) -> Any:
        found = await original(self, id_)
        await asyncio.wait_for(barrier.wait(), timeout=5)
        return found

    monkeypatch.setattr(RevisionRepository, "get", get_then_wait)

    async def go() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=env.client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            return list(
                await asyncio.gather(
                    *(
                        client.post(f"{PREFIX}/revisions/{path}", headers=h, json={"comment": "c"})
                        for path, h in calls
                    )
                )
            )

    try:
        return env.client.portal.call(go)  # type: ignore[union-attr]
    finally:
        monkeypatch.undo()


def test_concurrent_approves_have_exactly_one_winner(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    rev_id, doc_id = pending(env)
    a1 = env.user(["APPROVER"], "a1@example.com")
    a2 = env.user(["APPROVER"], "a2@example.com")

    responses = race(
        env,
        monkeypatch,
        [(f"{rev_id}/approve", env.auth(a1)), (f"{rev_id}/approve", env.auth(a2))],
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [202, 409], [r.text for r in responses]
    winner = next(r for r in responses if r.status_code == 202).json()
    loser = next(r for r in responses if r.status_code == 409).json()
    assert loser["error"]["code"] == "REVISION_NOT_PENDING"
    stored = env.revision(rev_id)
    assert (stored["status"], stored["reviewed_by"]) == ("APPROVED", winner["reviewed_by"])
    [event] = env.events("REVISION_APPROVED")
    assert event["actor_id"] == winner["reviewed_by"]
    assert env.document(doc_id)["latest_approved_revision_id"] == rev_id
    assert env.client.portal.call(EventRepository(env.db).verify_chain, doc_id).ok  # type: ignore[union-attr]


def test_concurrent_approve_and_reject_have_exactly_one_winner(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    rev_id, doc_id = pending(env)
    headers = [env.approver("a1@example.com"), env.approver("a2@example.com")]

    responses = race(
        env, monkeypatch, [(f"{rev_id}/approve", headers[0]), (f"{rev_id}/reject", headers[1])]
    )

    ok = [r for r in responses if r.status_code in (200, 202)]
    assert len(ok) == 1 and len(responses) == 2, [r.text for r in responses]
    [loser] = [r for r in responses if r not in ok]
    assert (loser.status_code, loser.json()["error"]["code"]) == (409, "REVISION_NOT_PENDING")
    won = "approve" if ok[0].status_code == 202 else "reject"
    assert env.revision(rev_id)["status"] == FINAL[won]
    assert len(env.events(EVENT[won])) == 1
    lost = "reject" if won == "approve" else "approve"
    assert env.events(EVENT[lost]) == []
    assert env.client.portal.call(EventRepository(env.db).verify_chain, doc_id).ok  # type: ignore[union-attr]
