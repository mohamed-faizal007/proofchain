"""In-memory RegistryClient mirroring ProofChainRegistry rules, for tests."""

import asyncio
import hashlib
from dataclasses import replace

from app.chain.hexutil import to_bytes32
from app.chain.registry_client import is_already_anchored
from app.chain.types import (
    ZERO_HASH,
    AnchorReceipt,
    ChainHealth,
    OnChainVersion,
    TxReceipt,
)
from app.errors import AnchorFailedError


class FakeRegistryClient:
    def __init__(self, chain_id: int = 31337) -> None:
        self._chain_id = chain_id
        self._versions: dict[str, list[OnChainVersion]] = {}
        self._tx_count = 0
        self._block = 0
        self._lock = asyncio.Lock()

    def _next_tx(self, *parts: str) -> tuple[str, int]:
        self._tx_count += 1
        self._block += 1
        digest = hashlib.sha256("|".join((str(self._tx_count), *parts)).encode()).hexdigest()
        return "0x" + digest, self._block

    async def anchor_version(
        self, doc_id: str, file_hash: str, text_root: str, canon_version: int
    ) -> AnchorReceipt:
        for value in (doc_id, file_hash, text_root):
            to_bytes32(value)
        if ZERO_HASH in (doc_id, file_hash, text_root):
            raise AnchorFailedError("ZeroHash: docId, fileHash and textRoot must be non-zero")
        async with self._lock:
            versions = self._versions.setdefault(doc_id, [])
            latest = versions[-1] if versions else None
            if latest is not None and is_already_anchored(latest, file_hash, text_root):
                return AnchorReceipt(latest.version_no, None, None, True)
            tx_hash, block = self._next_tx("anchor", doc_id, file_hash, text_root)
            version_no = len(versions) + 1
            versions.append(
                OnChainVersion(
                    version_no=version_no,
                    file_hash=file_hash,
                    text_root=text_root,
                    prev_text_root=latest.text_root if latest else ZERO_HASH,
                    anchored_at=block,
                    canon_version=canon_version,
                    revoked=False,
                )
            )
            return AnchorReceipt(version_no, tx_hash, block, False)

    async def revoke_version(self, doc_id: str, version_no: int, reason: str) -> TxReceipt:
        to_bytes32(doc_id)
        async with self._lock:
            versions = self._versions.get(doc_id, [])
            if not 1 <= version_no <= len(versions):
                raise AnchorFailedError(f"VersionNotFound: version {version_no}")
            if versions[version_no - 1].revoked:
                raise AnchorFailedError(f"AlreadyRevoked: version {version_no}")
            versions[version_no - 1] = replace(versions[version_no - 1], revoked=True)
            tx_hash, block = self._next_tx("revoke", doc_id, str(version_no), reason)
            return TxReceipt(tx_hash, block)

    async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None:
        to_bytes32(doc_id)
        versions = self._versions.get(doc_id, [])
        if not 1 <= version_no <= len(versions):
            return None
        return versions[version_no - 1]

    async def version_count(self, doc_id: str) -> int:
        to_bytes32(doc_id)
        return len(self._versions.get(doc_id, []))

    async def aclose(self) -> None:
        return None

    async def health(self) -> ChainHealth:
        return ChainHealth(ok=True, chain_id=self._chain_id, block_number=self._block)
