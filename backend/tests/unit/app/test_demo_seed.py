"""P10-04: scripts/demo_seed.py drives the real API (fake chain) to the expected verdict table.

Rule-only classification is in play here (the env's default test classifier), so PARTY_CHANGE
degrades; the live run with the NLP image is where every category is expected to match.
"""

from collections.abc import Callable
from typing import Any

import pytest

from app.repositories.users import UserRepository
from app.scripts.seed import DEV_DEFAULT_PASSWORD, seed_users
from tests.unit.app.docs_env import PREFIX, Env
from tests.unit.deploy.script_loader import load_script

pytest.importorskip("faker")  # eval extra; the demo generator reuses eval/


class _TestClientApi:
    """demo_http.Api over a Starlette TestClient (paths are relative to /api/v1)."""

    def __init__(self, env: Env, response_cls: Any) -> None:
        self.env = env
        self.response_cls = response_cls

    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: Any = None,
        file: tuple[str, bytes] | None = None,
        fields: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        files = {"file": (file[0], file[1], "application/pdf")} if file else None
        r = self.env.client.request(
            method,
            f"{PREFIX}{path}",
            headers=headers,
            json=json_body,
            files=files,
            data=fields,
            params=params,
        )
        body = r.json() if "json" in r.headers.get("content-type", "") else r.content
        return self.response_cls(r.status_code, body)


@pytest.fixture(scope="module")
def demo_set() -> Any:
    return load_script("demo_data").build_demo_set()


@pytest.fixture
def seeded_env(env_factory: Callable[..., Env]) -> Env:
    env = env_factory()
    env.client.portal.call(seed_users, UserRepository(env.db), DEV_DEFAULT_PASSWORD)  # type: ignore[union-attr]
    return env


def _run(env: Env, demo_set: Any, **kw: Any) -> Any:
    mod = load_script("demo_seed")
    api = _TestClientApi(env, load_script("demo_http").ApiResponse)
    return mod.run_demo(api, demo_set, password=DEV_DEFAULT_PASSWORD, sleep=lambda _s: None, **kw)


def test_demo_default_password_matches_the_seed_script() -> None:
    assert load_script("demo_seed").DEFAULT_PASSWORD == DEV_DEFAULT_PASSWORD


def test_demo_expected_verdicts(seeded_env: Env, demo_set: Any) -> None:
    report = _run(seeded_env, demo_set)

    rows = {r.key: r for r in report.rows}
    assert set(rows) == {c.key for c in demo_set.copies}
    assert all(r.verdict_ok for r in report.rows), [(r.key, r.verdict) for r in report.rows]
    assert report.ok and report.anchored
    assert rows["original_v1"].verdict == "AUTHENTIC_SUPERSEDED"
    assert rows["approved_v2"].verdict == "AUTHENTIC_LATEST"
    assert rows["resaved_v2"].verdict == "CONTENT_EQUIVALENT"
    for key, row in rows.items():
        if key.startswith("tampered_"):
            assert row.verdict == "TAMPERED"
            assert row.regions >= 1  # localized, not "no reference available"
            if key != "tampered_party":  # PARTY_CHANGE needs spaCy; see module docstring
                assert row.category_ok, (key, row.category, row.expected_category)


def test_demo_seed_idempotent(seeded_env: Env, demo_set: Any) -> None:
    first = _run(seeded_env, demo_set)
    second = _run(seeded_env, demo_set)

    assert seeded_env.count("documents") == 1
    assert seeded_env.count("revisions") == 2
    assert second.document_id == first.document_id
    assert [(r.key, r.verdict, r.category) for r in second.rows] == [
        (r.key, r.verdict, r.category) for r in first.rows
    ]


def test_demo_resumes_from_a_half_finished_run(seeded_env: Env, demo_set: Any) -> None:
    """Only v1 was registered (PENDING) when the previous run died: the next run finishes."""
    issuer = seeded_env.auth(
        seeded_env.client.portal.call(  # type: ignore[union-attr]
            UserRepository(seeded_env.db).get_by_email, "issuer@proofchain.local"
        )
    )
    created = seeded_env.post_pdf(
        issuer, demo_set.v1, title=demo_set.title, doc_type=demo_set.doc_type
    )
    assert created.status_code == 201

    report = _run(seeded_env, demo_set)

    assert seeded_env.count("documents") == 1
    assert seeded_env.count("revisions") == 2
    assert report.ok


def test_demo_reports_unanchored_when_the_chain_is_not_configured(
    seeded_env: Env, demo_set: Any
) -> None:
    env = seeded_env
    env.client.app.state.registry_client = None  # type: ignore[attr-defined]  # as with no REGISTRY_ADDRESS
    mod = load_script("demo_seed")

    with pytest.raises(mod.DemoError, match="CHAIN_NOT_CONFIGURED"):
        _run(env, demo_set)
    # opting out still seeds and verifies, and says so
    report = _run(env, demo_set, require_anchor=False)
    assert report.anchored is False
