"""RegistryClient interface (docs/05_SMART_CONTRACT.md, Backend client)."""

from typing import Protocol

from app.chain.types import AnchorReceipt, ChainHealth, OnChainVersion, TxReceipt


class RegistryClient(Protocol):
    async def anchor_version(
        self, doc_id: str, file_hash: str, text_root: str, canon_version: int
    ) -> AnchorReceipt: ...

    async def revoke_version(self, doc_id: str, version_no: int, reason: str) -> TxReceipt: ...

    async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None: ...

    async def version_count(self, doc_id: str) -> int: ...

    async def health(self) -> ChainHealth: ...

    async def aclose(self) -> None: ...


def is_already_anchored(latest: OnChainVersion | None, file_hash: str, text_root: str) -> bool:
    """Idempotency rule shared by all clients (05, Backend client).

    Only the latest version counts, and a revoked one never does: re-anchoring identical
    content after a revoke must create a fresh, valid version.
    """
    return (
        latest is not None
        and not latest.revoked
        and latest.file_hash == file_hash
        and latest.text_root == text_root
    )
