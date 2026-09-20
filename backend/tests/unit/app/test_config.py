import pytest
from pydantic import ValidationError

from app.config import DEFAULT_JWT_SECRET, Settings


def test_prod_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="prod")


def test_prod_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="prod", jwt_secret="short")


def test_prod_accepts_strong_secret() -> None:
    Settings(_env_file=None, app_env="prod", jwt_secret="k" * 32)


@pytest.mark.parametrize("env", ["dev", "test"])
def test_non_prod_allows_default_secret(env: str) -> None:
    assert Settings(_env_file=None, app_env=env).jwt_secret == DEFAULT_JWT_SECRET  # type: ignore[arg-type]


def test_prod_does_not_yet_check_anchor_key() -> None:
    """Deliberate: the anchor_private_key half is owned by P4-03 (see TASKS.md)."""
    Settings(_env_file=None, app_env="prod", jwt_secret="k" * 32, anchor_private_key="")
