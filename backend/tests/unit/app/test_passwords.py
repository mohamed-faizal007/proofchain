import pytest

from app.errors import ValidationFailed
from app.security.passwords import MAX_PASSWORD_BYTES, hash_password, verify_password


def test_hash_then_verify_succeeds() -> None:
    assert verify_password("correct horse", hash_password("correct horse"))


def test_wrong_password_fails() -> None:
    assert not verify_password("wrong", hash_password("correct horse"))


def test_hash_is_salted_and_not_plaintext() -> None:
    a, b = hash_password("same-password"), hash_password("same-password")
    assert a != b
    assert "same-password" not in a


def test_password_over_72_bytes_is_rejected_not_truncated() -> None:
    with pytest.raises(ValidationFailed):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_limit_is_in_bytes_not_characters() -> None:
    with pytest.raises(ValidationFailed):
        hash_password("é" * 37)  # 74 bytes
    assert verify_password("é" * 36, hash_password("é" * 36))  # 72 bytes


def test_verify_overlong_password_returns_false() -> None:
    assert not verify_password("a" * 100, hash_password("a" * 72))


@pytest.mark.parametrize("bad", ["", "not-a-hash", "$2b$12$short"])
def test_malformed_hash_returns_false(bad: str) -> None:
    assert not verify_password("x", bad)
