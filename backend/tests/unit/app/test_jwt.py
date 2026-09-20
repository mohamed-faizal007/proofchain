import datetime as dt

import jwt as pyjwt
import pytest

from app.config import Settings
from app.errors import UnauthorizedError
from app.security.jwt import create_access_token, decode_access_token

NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.UTC)


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, app_env="test", jwt_secret="s" * 40, **kw)  # type: ignore[arg-type]


def _raw(claims: dict[str, object], secret: str = "s" * 40, alg: str = "HS256") -> str:
    return pyjwt.encode(claims, secret, algorithm=alg)


def _good(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": "u1",
        "roles": ["ISSUER"],
        "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
    }
    return {**base, **over}


def test_round_trip_preserves_claims() -> None:
    s = _settings()
    tok = create_access_token("u1", ["ISSUER", "APPROVER"], s)
    c = decode_access_token(tok, s)
    assert c.sub == "u1"
    assert c.roles == ["ISSUER", "APPROVER"]


def test_expiry_uses_settings_and_injected_clock() -> None:
    s = _settings(jwt_expire_minutes=30)
    tok = create_access_token("u1", ["VERIFIER"], s, now=NOW)
    payload = pyjwt.decode(tok, options={"verify_signature": False})
    assert payload["exp"] == int((NOW + dt.timedelta(minutes=30)).timestamp())
    assert pyjwt.get_unverified_header(tok)["alg"] == "HS256"


def test_expired_token_rejected() -> None:
    s = _settings()
    tok = create_access_token(
        "u1", ["VERIFIER"], s, now=dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(tok, s)


def test_wrong_secret_rejected() -> None:
    tok = create_access_token("u1", ["VERIFIER"], _settings())
    with pytest.raises(UnauthorizedError):
        decode_access_token(tok, _settings().model_copy(update={"jwt_secret": "x" * 40}))


def test_tampered_payload_rejected() -> None:
    s = _settings()
    head, _, sig = create_access_token("u1", ["VERIFIER"], s).split(".")
    forged = _raw(_good(roles=["ADMIN"])).split(".")[1]
    with pytest.raises(UnauthorizedError):
        decode_access_token(f"{head}.{forged}.{sig}", s)


def test_alg_none_rejected() -> None:
    tok = pyjwt.encode(_good(), key=None, algorithm="none")  # type: ignore[arg-type]
    with pytest.raises(UnauthorizedError):
        decode_access_token(tok, _settings())


def test_other_hmac_alg_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(_raw(_good(), alg="HS512"), _settings())


@pytest.mark.parametrize("missing", ["sub", "roles", "exp"])
def test_missing_claim_rejected(missing: str) -> None:
    claims = _good()
    del claims[missing]
    with pytest.raises(UnauthorizedError):
        decode_access_token(_raw(claims), _settings())


@pytest.mark.parametrize("bad", [{"roles": ["ROOT"]}, {"roles": "ADMIN"}, {"sub": ""}, {"sub": 5}])
def test_invalid_claim_values_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(_raw(_good(**bad)), _settings())


@pytest.mark.parametrize("junk", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_rejected(junk: str) -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(junk, _settings())
