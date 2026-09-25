from app.chain.registry_client import is_already_anchored
from app.chain.types import OnChainVersion

F, R = "f1" * 32, "a1" * 32


def _v(file_hash: str = F, text_root: str = R, revoked: bool = False) -> OnChainVersion:
    return OnChainVersion(1, file_hash, text_root, "0" * 64, 1, 1, revoked)


def test_matching_live_latest_is_already_anchored() -> None:
    assert is_already_anchored(_v(), F, R) is True


def test_no_latest() -> None:
    assert is_already_anchored(None, F, R) is False


def test_revoked_latest_is_not_already_anchored() -> None:
    assert is_already_anchored(_v(revoked=True), F, R) is False


def test_mismatch_is_not_already_anchored() -> None:
    assert is_already_anchored(_v(file_hash="f2" * 32), F, R) is False
    assert is_already_anchored(_v(text_root="a2" * 32), F, R) is False
