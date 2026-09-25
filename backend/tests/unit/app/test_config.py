import pytest
from pydantic import ValidationError

from app.config import DEFAULT_JWT_SECRET, Settings


def test_prod_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="prod")


def test_prod_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="prod", jwt_secret="short")


@pytest.mark.parametrize("env", ["dev", "test"])
def test_non_prod_allows_default_secret(env: str) -> None:
    assert Settings(_env_file=None, app_env=env).jwt_secret == DEFAULT_JWT_SECRET  # type: ignore[arg-type]


PROD = {"app_env": "prod", "jwt_secret": "k" * 32}
ANCHOR = {"anchor_private_key": "0x" + "1" * 64, "registry_address": "0x" + "2" * 40}


@pytest.mark.parametrize("value", ["", "   "])
def test_prod_rejects_empty_anchor_key(value: str) -> None:
    with pytest.raises(ValidationError, match="ANCHOR_PRIVATE_KEY"):
        Settings(_env_file=None, **{**PROD, **ANCHOR, "anchor_private_key": value})  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["", "   "])
def test_prod_rejects_empty_registry_address(value: str) -> None:
    with pytest.raises(ValidationError, match="REGISTRY_ADDRESS"):
        Settings(_env_file=None, **{**PROD, **ANCHOR, "registry_address": value})  # type: ignore[arg-type]


def test_prod_accepts_anchor_settings() -> None:
    Settings(_env_file=None, **PROD, **ANCHOR)  # type: ignore[arg-type]


@pytest.mark.parametrize("env", ["dev", "test"])
def test_non_prod_allows_empty_anchor_settings(env: str) -> None:
    s = Settings(_env_file=None, app_env=env)  # type: ignore[arg-type]
    assert s.anchor_private_key == "" and s.registry_address == ""
