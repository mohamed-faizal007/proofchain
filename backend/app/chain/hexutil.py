"""Python 64-char lowercase hex <-> on-chain bytes32. Only chain clients use this."""

import re

_HEX32 = re.compile(r"[0-9a-f]{64}")


def to_bytes32(value: str) -> bytes:
    if not _HEX32.fullmatch(value):
        raise ValueError("expected 64 lowercase hex chars (no 0x prefix)")
    return bytes.fromhex(value)


def from_bytes32(value: bytes) -> str:
    if len(value) != 32:
        raise ValueError("expected exactly 32 bytes")
    return value.hex()
