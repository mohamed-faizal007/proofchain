"""Gas price and ETH/USD/INR snapshot for the cost estimate (docs/08 C.3, Chain).

Network access lives here and in ``measure_chain.py`` only; the runner and the report are offline.
Each field is fetched on its own from a public endpoint and falls back, per field, to the config
default. A snapshot is ``live`` only when every field was fetched; the report words the two cases
differently. ``fetch`` is injectable so the tests never touch the network.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

# Ethereum mainnet (the cost is quoted for mainnet), tried in order; TLS is always verified.
GAS_RPCS = ("https://1rpc.io/eth", "https://eth.drpc.org", "https://ethereum-rpc.publicnode.com")
PRICE_API = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd,inr"
TIMEOUT_S = 10.0
Fetch = Callable[[str, dict[str, Any] | None], Any]


def http_fetch(url: str, payload: dict[str, Any] | None) -> Any:
    """GET, or POST of a JSON-RPC payload; returns the decoded JSON."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(  # noqa: S310 - https URLs fixed above
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "proofchain-eval"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
        return json.loads(resp.read())


def _positive(x: Any) -> float:
    value = float(x)
    if not value > 0:
        raise ValueError("non-positive")
    return value


def _live_field(source_url: str, read: Callable[[], float]) -> dict[str, Any] | None:
    try:
        return {"value": read(), "source": f"live: {urlparse(source_url).netloc}"}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def snapshot(
    defaults: dict[str, float], fetch: Fetch = http_fetch, now: datetime | None = None
) -> dict[str, Any]:
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "eth_gasPrice", "params": []}

    def gas_price(url: str) -> Callable[[], float]:
        return lambda: _positive(int(fetch(url, rpc)["result"], 16)) / 1e9

    gas = None
    for url in GAS_RPCS:
        gas = _live_field(url, gas_price(url))
        if gas:
            break

    def price(currency: str) -> Callable[[], float]:
        return lambda: _positive(fetch(PRICE_API, None)["ethereum"][currency])

    fields = {
        "gas_price_gwei": gas,
        "eth_usd": _live_field(PRICE_API, price("usd")),
        "eth_inr": _live_field(PRICE_API, price("inr")),
    }
    out: dict[str, Any] = {}
    for name, live in fields.items():
        out[name] = live or {"value": float(defaults[name]), "source": "config default"}
    taken = (now or datetime.now(UTC)).astimezone(UTC)
    return {
        "taken_at_utc": taken.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "live": all(f is not None for f in fields.values()),
        **out,
    }
