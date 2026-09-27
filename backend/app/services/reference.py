"""Closest approved version + localization for /verify (02 §9-10). Read-only; no verdict here."""

from dataclasses import dataclass

import anyio

from app.errors import NotFoundError
from app.models.revision import Revision
from app.repositories.revisions import RevisionRepository
from app.repositories.trees import TreeRepository
from app.services.tree_mapping import doc_to_tree
from proofchain_core import localize
from proofchain_core.types import IntegrityTree, LocalizationResult, LocalizationStatus

NO_APPROVED = "NO_APPROVED_REVISION"
CANON_MISMATCH = "CANON_VERSION_MISMATCH"


@dataclass(frozen=True)
class ReferenceResult:
    """`reference`/`localization` are None together; then `no_localization_reason` says why."""

    reference: Revision | None
    localization: LocalizationResult | None
    no_localization_reason: str | None


def equal_chunks(cand: IntegrityTree, result: LocalizationResult) -> int:
    """Candidate chunks that match the reference unchanged (02 §10 "equal" chunks).

    INTERPRETATION: an absolute count, as 02 §10 words it ("the most `equal` chunks"), not a
    ratio; see PROGRESS.md P6-02.
    """
    total = sum(len(p.chunks) for p in cand.pages)
    if result.status is not LocalizationStatus.CHANGED:
        return total
    return total - result.stats["modified"] - result.stats["inserted"]


class ReferenceService:
    def __init__(self, revisions: RevisionRepository, trees: TreeRepository) -> None:
        self._revisions = revisions
        self._trees = trees

    async def localize_against(self, cand: IntegrityTree, document_id: str) -> ReferenceResult:
        approved = [
            r for r in await self._revisions.list_by_document(document_id) if r.status == "APPROVED"
        ]
        if not approved:
            return ReferenceResult(None, None, NO_APPROVED)

        best: tuple[tuple[int, int], Revision, LocalizationResult] | None = None
        for rev in approved:  # ascending revision_no; scored below so ties resolve to the latest
            stored = await self._trees.get_for_revision(rev.id)
            if stored is None:
                raise NotFoundError("Integrity tree not found")
            # localize does not check canon_version (P1-09 finding 9): hashes made under other
            # rules are not comparable, so such a reference is never localized against.
            if stored.canon_version != cand.canon_version:
                continue
            result = await anyio.to_thread.run_sync(localize, doc_to_tree(stored), cand)
            score = (equal_chunks(cand, result), rev.revision_no)
            if best is None or score > best[0]:
                best = (score, rev, result)

        if best is None:
            return ReferenceResult(None, None, CANON_MISMATCH)
        return ReferenceResult(best[1], best[2], None)
