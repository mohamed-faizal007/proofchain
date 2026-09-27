"""On-chain cross-check for /verify (02 §11, ADR-020). Reports only; the verdict is P6-04's job."""

from dataclasses import dataclass

from app.chain import RegistryClient
from app.errors import ChainUnavailableError
from app.models.revision import Revision

NOT_CONFIGURED = "CHAIN_NOT_CONFIGURED"
UNAVAILABLE = "CHAIN_UNAVAILABLE"
NOT_ANCHORED = "NOT_ANCHORED"
MISSING_ON_CHAIN = "missing_on_chain"


@dataclass(frozen=True)
class ChainCheckResult:
    """`ok` is None when the check was not performed (then `reason` says why, and the Mongo-based
    verdict stands). `mismatches` names the disagreeing fields only, never their values."""

    performed: bool
    ok: bool | None
    reason: str | None = None
    tx_hash: str | None = None
    mismatches: tuple[str, ...] = ()


def _skipped(reason: str) -> ChainCheckResult:
    return ChainCheckResult(performed=False, ok=None, reason=reason)


class ChainCheckService:
    def __init__(self, registry: RegistryClient | None) -> None:
        self._registry = registry

    async def check(self, revision: Revision, chain_doc_id: str) -> ChainCheckResult:
        """Compare the revision's Mongo record with its on-chain version.

        `chain_doc_id` is the owning `Document.chain_doc_id` (the on-chain key), not the Mongo id.

        An outage or missing configuration is NOT a mismatch (availability over guarantee: it
        never yields a false RECORD_MISMATCH); the caller keeps the Mongo-based verdict.
        """
        if self._registry is None:
            return _skipped(NOT_CONFIGURED)
        if revision.anchor.status != "ANCHORED" or revision.version_no is None:
            return _skipped(NOT_ANCHORED)
        try:
            onchain = await self._registry.get_version(chain_doc_id, revision.version_no)
        except ChainUnavailableError:
            return _skipped(UNAVAILABLE)

        tx_hash = revision.anchor.tx_hash
        if onchain is None:
            return ChainCheckResult(True, False, MISSING_ON_CHAIN, tx_hash, (MISSING_ON_CHAIN,))
        mismatches = tuple(
            name
            for name, differs in (
                ("file_hash", onchain.file_hash != revision.file_hash),
                ("text_root", onchain.text_root != revision.text_root),
                ("canon_version", onchain.canon_version != revision.canon_version),
                ("revoked", onchain.revoked != (revision.status == "REVOKED")),
            )
            if differs
        )
        return ChainCheckResult(True, not mismatches, None, tx_hash, mismatches)
