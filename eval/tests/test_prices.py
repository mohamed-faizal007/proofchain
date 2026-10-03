"""P9-05 price snapshot: live where cheap, an explicit illustrative fallback otherwise."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import prices

NOW = datetime(2026, 10, 3, 12, 30, 45, tzinfo=UTC)
DEFAULTS = {"gas_price_gwei": 20.0, "eth_usd": 3000.0, "eth_inr": 250000.0}


def _live(url: str, payload: dict[str, Any] | None) -> Any:
    if payload is not None:  # JSON-RPC eth_gasPrice
        return {"jsonrpc": "2.0", "id": 1, "result": hex(1_500_000_000)}
    return {"ethereum": {"usd": 2500.5, "inr": 210000.0}}


def _down(url: str, payload: dict[str, Any] | None) -> Any:
    raise OSError("no network")


def test_all_live_snapshot_records_values_sources_and_time() -> None:
    s = prices.snapshot(DEFAULTS, fetch=_live, now=NOW)
    assert s["live"] is True
    assert s["taken_at_utc"] == "2026-10-03T12:30:45Z"
    assert s["gas_price_gwei"]["value"] == 1.5 and s["gas_price_gwei"]["source"].startswith("live")
    assert s["eth_usd"]["value"] == 2500.5 and s["eth_inr"]["value"] == 210000.0


def test_no_network_falls_back_to_config_and_says_so() -> None:
    s = prices.snapshot(DEFAULTS, fetch=_down, now=NOW)
    assert s["live"] is False
    assert s["gas_price_gwei"] == {"value": 20.0, "source": "config default"}
    assert s["eth_usd"]["source"] == "config default"


def test_partial_failure_is_per_field_and_not_live() -> None:
    def gas_only(url: str, payload: dict[str, Any] | None) -> Any:
        if payload is None:
            raise OSError("price api down")
        return _live(url, payload)

    s = prices.snapshot(DEFAULTS, fetch=gas_only, now=NOW)
    assert s["live"] is False
    assert s["gas_price_gwei"]["source"].startswith("live")
    assert s["eth_usd"]["source"] == "config default"


def test_malformed_response_is_a_fallback_not_a_crash() -> None:
    def junk(url: str, payload: dict[str, Any] | None) -> Any:
        return {"unexpected": True}

    s = prices.snapshot(DEFAULTS, fetch=junk, now=NOW)
    assert s["live"] is False and s["eth_usd"]["value"] == 3000.0


def test_nonpositive_values_are_rejected_as_malformed() -> None:
    def zero(url: str, payload: dict[str, Any] | None) -> Any:
        if payload is not None:
            return {"result": "0x0"}
        return {"ethereum": {"usd": 0, "inr": -1}}

    s = prices.snapshot(DEFAULTS, fetch=zero, now=NOW)
    assert s["live"] is False


def test_gas_price_falls_through_to_the_next_endpoint() -> None:
    def first_down(url: str, payload: dict[str, Any] | None) -> Any:
        if payload is not None and url == prices.GAS_RPCS[0]:
            raise OSError("endpoint down")
        if payload is not None and url == prices.GAS_RPCS[1]:
            return {"error": {"message": "unauthorized"}}  # no "result": also skipped
        return _live(url, payload)

    s = prices.snapshot(DEFAULTS, fetch=first_down, now=NOW)
    assert s["gas_price_gwei"]["value"] == 1.5 and s["live"] is True
    assert prices.GAS_RPCS[2].split("//")[1] in s["gas_price_gwei"]["source"]
