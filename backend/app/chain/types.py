"""Value types returned by RegistryClient. Hashes: 64 lowercase hex; tx hashes: 0x-prefixed."""

from dataclasses import dataclass

ZERO_HASH = "0" * 64


@dataclass(frozen=True)
class AnchorReceipt:
    version_no: int
    tx_hash: str | None  # None when the version was already anchored (no tx sent)
    block_number: int | None
    already_anchored: bool


@dataclass(frozen=True)
class TxReceipt:
    tx_hash: str
    block_number: int


@dataclass(frozen=True)
class OnChainVersion:
    version_no: int
    file_hash: str
    text_root: str
    prev_text_root: str
    anchored_at: int
    canon_version: int
    revoked: bool


@dataclass(frozen=True)
class ChainHealth:
    ok: bool
    chain_id: int | None = None
    block_number: int | None = None
    registry_address: str | None = None
