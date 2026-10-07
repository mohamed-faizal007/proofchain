"""Seed the demo data through the public API and verify every demo file (P10-04).

    python scripts/demo_seed.py [--base-url URL] [--out DIR] [--no-require-anchor]

Idempotent: the demo document is found by its exact title, and each step (register v1, approve,
submit v2, approve, anchor) is skipped when already done, so a rerun, or a rerun after a half
finished run, converges on the same state. Verifications are always run again, so each run adds
rows to the verification history (that is a log, not demo data).

Exit status: 0 when every verdict is as expected, 1 otherwise (a wrong category is reported but
is explanation, not verdict, so it does not fail the run). Needs the seeded demo users
(`python -m app.scripts.seed`, which demo.ps1 runs). Password: $SEED_PASSWORD, else the public
dev default the seed script uses.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import sleep as real_sleep
from typing import Any

from demo_http import Api, ApiResponse, UrllibApi

DEFAULT_PASSWORD = "proofchain-demo-1"  # secret-scan: allow (public dev demo password)
ISSUER, APPROVER, ADMIN = (f"{r}@proofchain.local" for r in ("issuer", "approver", "admin"))
ANCHOR_POLLS = 120  # x 1 s


class DemoError(Exception):
    pass


@dataclass(frozen=True)
class Row:
    key: str
    label: str
    verdict: str
    expected_verdict: str
    category: str | None
    expected_category: str | None
    regions: int
    tx_hash: str | None
    verdict_ok: bool
    category_ok: bool


@dataclass
class DemoReport:
    document_id: str
    anchored: bool
    anchor_txs: list[str | None]
    rows: list[Row] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.verdict_ok for r in self.rows)


def _expect(resp: ApiResponse, status: int, what: str) -> Any:
    if resp.status != status:
        raise DemoError(f"{what}: HTTP {resp.status} (wanted {status}): {resp.body!r}"[:400])
    return resp.body


def _login(api: Api, email: str, password: str) -> str:
    body = _expect(
        api.call("POST", "/auth/login", json_body={"email": email, "password": password}),
        200,
        f"login {email} (is the demo seed done and SEED_PASSWORD right?)",
    )
    return str(body["access_token"])


def _find_document(api: Api, token: str, title: str) -> dict[str, Any] | None:
    page = _expect(
        api.call("GET", "/documents", token=token, params={"q": title, "page_size": "100"}),
        200,
        "list documents",
    )
    matches = [d for d in page["items"] if d["title"] == title]
    return matches[0] if matches else None


def _revisions(api: Api, token: str, document_id: str) -> list[dict[str, Any]]:
    return list(
        _expect(
            api.call("GET", f"/documents/{document_id}/revisions", token=token), 200, "revisions"
        )
    )


def _anchor(
    api: Api,
    rev: dict[str, Any],
    tokens: dict[str, str],
    require: bool,
    sleep: Callable[[float], None],
) -> tuple[bool, str | None]:
    """Wait for ANCHORED. A FAILED anchor is retried once through the admin endpoint."""
    retried = False
    state: dict[str, Any] = rev["anchor"]
    for _ in range(ANCHOR_POLLS):
        state = _expect(
            api.call("GET", f"/revisions/{rev['id']}", token=tokens["issuer"]), 200, "revision"
        )["anchor"]
        if state["status"] == "ANCHORED":
            return True, state.get("tx_hash")
        if state["status"] == "FAILED":
            if retried:
                break
            retried = True
            api.call("POST", f"/revisions/{rev['id']}/retry-anchor", token=tokens["admin"])
        sleep(1.0)
    if not require:
        return False, None
    raise DemoError(
        f"revision {rev['revision_no']} was not anchored "
        f"({state.get('error') or state['status']}). "
        "Anchoring needs the chain profile, a deployed registry and REGISTRY_ADDRESS / "
        "ANCHOR_PRIVATE_KEY passed to the backend (scripts/demo.ps1 does all of that); or pass "
        "--no-require-anchor to continue without on-chain anchors."
    )


def _ensure_approved(api: Api, rev: dict[str, Any], tokens: dict[str, str]) -> dict[str, Any]:
    if rev["status"] == "PENDING":
        _expect(
            api.call(
                "POST",
                f"/revisions/{rev['id']}/approve",
                token=tokens["approver"],
                json_body={"comment": "Demo approval"},
            ),
            202,
            f"approve revision {rev['revision_no']}",
        )
    elif rev["status"] != "APPROVED":
        raise DemoError(f"demo revision {rev['revision_no']} is {rev['status']}, not usable")
    return rev


def _row(copy: Any, report: dict[str, Any]) -> Row:
    categories = sorted({a["primary_category"] for a in report.get("analysis") or []})
    loc = report.get("localization")
    chain = report.get("chain_check") or {}
    return Row(
        key=copy.key,
        label=copy.label,
        verdict=report["verdict"],
        expected_verdict=copy.expected_verdict,
        category=", ".join(categories) or None,
        expected_category=copy.expected_category,
        regions=len(loc["regions"]) if loc else 0,
        tx_hash=chain.get("tx_hash"),
        verdict_ok=report["verdict"] == copy.expected_verdict,
        category_ok=copy.expected_category is None or copy.expected_category in categories,
    )


def run_demo(
    api: Api,
    demo: Any,
    *,
    password: str,
    require_anchor: bool = True,
    sleep: Callable[[float], None] = real_sleep,
) -> DemoReport:
    tokens = {
        "issuer": _login(api, ISSUER, password),
        "approver": _login(api, APPROVER, password),
        "admin": _login(api, ADMIN, password),
    }
    doc = _find_document(api, tokens["issuer"], demo.title)
    if doc is None:
        created = _expect(
            api.call(
                "POST",
                "/documents",
                token=tokens["issuer"],
                file=("demo_v1.pdf", demo.v1),
                fields={"title": demo.title, "doc_type": demo.doc_type},
            ),
            201,
            "register document",
        )
        doc = created["document"]
    revs = _revisions(api, tokens["issuer"], doc["id"])
    if len(revs) > 2:
        raise DemoError(f"{demo.title!r} has {len(revs)} revisions; expected the demo's two")
    v1 = _ensure_approved(api, revs[0], tokens)
    if len(revs) == 1:
        _anchor(api, v1, tokens, require_anchor, sleep)  # a revision must be approved to be parent
        submitted = _expect(
            api.call(
                "POST",
                f"/documents/{doc['id']}/revisions",
                token=tokens["issuer"],
                file=("demo_v2.pdf", demo.v2),
                fields={"change_note": demo.change_note},
            ),
            201,
            "submit v2",
        )
        revs.append(submitted["revision"])
    v2 = _ensure_approved(api, revs[1], tokens)
    results = [_anchor(api, rev, tokens, require_anchor, sleep) for rev in (v1, v2)]

    report = DemoReport(doc["id"], all(ok for ok, _ in results), [tx for _, tx in results])
    for copy in demo.copies:
        resp = api.call(
            "POST",
            "/verify",
            token=tokens["issuer"],
            file=(f"{copy.key}.pdf", copy.pdf),
            fields={"document_id": doc["id"]},
        )
        report.rows.append(_row(copy, _expect(resp, 200, f"verify {copy.key}")))
    return report


def render_table(report: DemoReport) -> str:
    lines = [f"{'file':26} {'verdict':22} {'category':20} regions  result"]
    for r in report.rows:
        result = "ok" if r.verdict_ok else f"WRONG VERDICT (wanted {r.expected_verdict})"
        if r.verdict_ok and not r.category_ok:
            result = f"verdict ok, category differs (wanted {r.expected_category})"
        lines.append(f"{r.key:26} {r.verdict:22} {r.category or '-':20} {r.regions:7}  {result}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).resolve().parents[1] / "demo" / "data"
    )
    parser.add_argument("--no-require-anchor", action="store_true")
    args = parser.parse_args(argv)

    import demo_data

    demo = demo_data.build_demo_set()
    files = demo_data.write_pdfs(demo, args.out)
    password = os.environ.get("SEED_PASSWORD") or DEFAULT_PASSWORD
    try:
        report = run_demo(
            UrllibApi(args.base_url),
            demo,
            password=password,
            require_anchor=not args.no_require_anchor,
        )
    except DemoError as err:
        print(f"demo seed failed: {err}", file=sys.stderr)
        return 1
    print(render_table(report))
    (args.out / "last_run.json").write_text(
        json.dumps(
            {"document_id": report.document_id, "rows": [asdict(r) for r in report.rows]}, indent=2
        ),
        encoding="utf-8",
    )
    wrong = sum(not r.category_ok for r in report.rows if r.verdict_ok)
    print(f"\ndocument id : {report.document_id}")
    print(f"anchored    : {'yes ' + str(report.anchor_txs) if report.anchored else 'NO'}")
    print(f"demo files  : {args.out} ({len(files)} PDFs, upload them in the Verify page)")
    print(f"categories  : {len(report.rows) - wrong}/{len(report.rows)} as expected")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
