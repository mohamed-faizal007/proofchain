"""/verify edge wording (P6-04): canon-mismatched reference, empty localization."""

from pathlib import Path

import pytest

from app.services.chain_check import ChainCheckResult
from app.services.verdict import Decision, summarize
from proofchain_core.types import LocalizationMethod, LocalizationResult, LocalizationStatus
from tests.unit.app.docs_env import Env
from tests.unit.app.verify_helpers import edited, register_approved, step, verify
from tests.unit.repositories.factories import make_revision


def test_only_approved_version_on_another_canon_is_no_reference_but_says_why(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, doc_id, rev_id = register_approved(env)
    env.client.portal.call(  # type: ignore[union-attr]
        env.db["integrity_trees"].update_one, {"_id": rev_id}, {"$set": {"canon_version": 1}}
    )

    body = verify(env, edited(tmp_path, monkeypatch), document_id=doc_id).json()

    assert body["verdict"] == "TAMPERED"
    assert body["localization"] is None and body["reference_revision"] is None
    assert body["no_reference_reason"] == "CANON_VERSION_MISMATCH"
    assert body["summary"].startswith("TAMPERED, no reference available")
    assert "canonicalization rules" in body["summary"]
    assert step(body, "LOCALIZATION")["detail"].startswith("NO_REFERENCE (CANON_VERSION_MISMATCH)")


def test_tampered_with_an_empty_localization_is_still_worded_as_a_comparison() -> None:
    loc = LocalizationResult(
        LocalizationStatus.CHANGED, (), (), (), LocalizationMethod.ALIGNMENT, 0, {}
    )
    ref = make_revision("d1", 3, version_no=3)
    decision = Decision("TAMPERED", "FAIL", "x")
    chain = ChainCheckResult(performed=False, ok=None, reason="NOT_ANCHORED")

    text = summarize(decision, "TAMPERED", "Lease", ref, loc, None, chain)

    assert text == "Matches no revision; no chunk-level changes vs approved revision 3 (v3)"
