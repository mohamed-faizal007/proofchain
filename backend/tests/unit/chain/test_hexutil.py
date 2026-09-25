import pytest

from app.chain.hexutil import from_bytes32, to_bytes32

H = "ab" * 32


def test_round_trip() -> None:
    assert from_bytes32(to_bytes32(H)) == H
    assert to_bytes32(H) == bytes.fromhex(H)


@pytest.mark.parametrize(
    "bad",
    ["", "ab" * 31, "ab" * 33, "AB" * 32, "0x" + "ab" * 32, "zz" * 32],
)
def test_rejects_non_canonical_hex(bad: str) -> None:
    with pytest.raises(ValueError):
        to_bytes32(bad)


def test_from_bytes32_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        from_bytes32(b"\x00" * 31)
