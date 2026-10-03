"""Chain section of REPORT.md: gas, cost estimate, latency, transaction cap and balance.

The cost estimate applies the measured gas to the price snapshot recorded next to the
measurement; the snapshot date is printed beside every cost figure. A snapshot with any
config-default field is announced as illustrative, not current, in a banner at the top.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chain_metrics
import figures
from report_fmt import fig, money, table

CHAIN_FILES = ("sepolia", "local")
KINDS = (("v1", "first (v1)"), ("subsequent", "subsequent"))
PRICE_KEYS = ("gas_price_gwei", "eth_usd", "eth_inr")
NOT_RUN = (
    "## Chain (gas and anchoring latency)\n\nnot run (no `chain_*.json`; see `measure_chain.py`)."
)
NO_PRICES = (
    "> **No price snapshot was recorded for this measurement, so no cost estimate is given.**\n"
)
ILLUSTRATIVE = (
    "> **ILLUSTRATIVE ONLY, NOT CURRENT.** At least one price below could not be fetched live "
    "and is a config default, not a market value. Treat the cost figures as an example of the "
    "arithmetic, not as an estimate of what an anchor costs today.\n>\n"
)


def _eth(wei: int) -> str:
    return f"{wei / chain_metrics.WEI_PER_ETH:.9f} ETH"


def _prices_block(p: dict[str, Any] | None) -> tuple[str, dict[str, float] | None]:
    if p is None:
        return NO_PRICES, None
    vals = {k: float(p[k]["value"]) for k in PRICE_KEYS}
    line = (
        f"gas price: {vals['gas_price_gwei']:g} gwei, ETH/USD: {money('$', vals['eth_usd'])}, "
        f"ETH/INR: {money('₹', vals['eth_inr'])} (snapshot {p['taken_at_utc']})"
    )
    sources = "; ".join(f"{k}: {p[k]['source']}" for k in PRICE_KEYS)
    if p["live"]:
        return f"Cost basis: {line}. Sources: {sources}.\n", vals
    return f"{ILLUSTRATIVE}> {line}. Sources: {sources}.\n", vals


def _stats_table(d: dict[str, Any]) -> str:
    header = ["version", "n", "gas median", "gas min", "gas max", "latency median (s)", "p95 (s)"]
    rows = []
    for kind, label in KINDS:
        g, lat = d["gas"][kind], d["latency_s"][kind]
        if g["n"]:
            rows.append(
                [
                    label,
                    g["n"],
                    f"{g['median']:,.0f}",
                    f"{g['min']:,.0f}",
                    f"{g['max']:,.0f}",
                    f"{lat['median']:.2f}",
                    f"{lat['p95']:.2f}",
                ]
            )
    return table(header, rows) + "\n"


def _cost_table(d: dict[str, Any], vals: dict[str, float]) -> str:
    rows = []
    for kind, label in KINDS:
        if d["gas"][kind]["n"]:
            c = chain_metrics.cost_estimate(
                d["gas"][kind]["median"], vals["gas_price_gwei"], vals["eth_usd"], vals["eth_inr"]
            )
            rows.append(
                [
                    label,
                    f"{c['gas']:,.0f}",
                    f"{c['eth']:.6f}",
                    money("$", round(c["usd"], 2)),
                    money("₹", round(c["inr"], 2)),
                ]
            )
    return (
        "\nEstimated cost of one anchor at the cost basis above (gas measured here):\n\n"
        + table(["version", "gas", "ETH", "USD", "INR"], rows)
        + "\n"
    )


def _run_summary(d: dict[str, Any]) -> str:
    t, b = d["transactions"], d["balance"]
    text = (
        f"**{d['target']}** (chain {d['chain_id']}, {d.get('confirmations', '?')} confirmations): "
        f"{t['sent']} transactions sent (planned {t['planned']}, cap of {t['cap']}; "
        f"cap held: {t['cap_held']}; counted from the sender nonce {t['nonce_before']} to "
        f"{t['nonce_after']}). Latency is the wall time of `anchor_version` (reads, send, "
        "receipt and confirmations).\n\n"
        f"- balance before: {_eth(b['before_wei'])}\n"
        f"- balance after: {_eth(b['after_wei'])}\n"
        f"- spent: {_eth(b['spent_wei'])} (sum of gas used x effective price from the receipts: "
        f"{_eth(b['fees_from_receipts_wei'])}; match: {b['matches_receipts']})\n"
    )
    if d.get("aborted"):
        ab = d["aborted"]
        text += f"- **run aborted** after {ab['after_samples']} samples ({ab['error']})\n"
    return text


def section(measurements: Path | None, results: Path) -> str:
    found: dict[str, dict[str, Any]] = {}
    for target in CHAIN_FILES:
        path = measurements / f"chain_{target}.json" if measurements else None
        if path and path.exists():
            found[target] = json.loads(path.read_text(encoding="utf-8"))
    if not found:
        return NOT_RUN
    price_path = measurements / "chain_prices.json" if measurements else None
    snap = None
    if price_path and price_path.exists():
        snap = json.loads(price_path.read_text(encoding="utf-8"))
    banner, vals = _prices_block(snap)
    parts = ["## Chain (gas and anchoring latency)\n", banner]
    for target, d in found.items():
        body = _run_summary(d) + "\n" + _stats_table(d)
        parts.append(f"### {target}\n\n" + body + (_cost_table(d, vals) if vals else ""))
    parts.append(
        "Testnet gas is free; the cost tables apply the measured gas to the stated mainnet "
        "gas price. Gas used does not depend on the gas price.\n"
    )
    figures.chain(found.get("sepolia") or found["local"], results / "figures")
    return "\n".join(parts) + "\n" + fig(["chain"])
