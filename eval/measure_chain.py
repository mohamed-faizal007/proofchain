"""Gas and anchoring-latency measurement (docs/08 C.3, Chain). Spends gas; opt-in; never part of CI.

    $env:CHAIN_RPC_URL = "<rpc>"; $env:ANCHOR_PRIVATE_KEY = "<key with ANCHOR_ROLE>"
    python measure_chain.py --target sepolia --dry-run     # plan, cap and balance; sends nothing
    python measure_chain.py --target sepolia               # the live run

The registry address is ``REGISTRY_ADDRESS`` or ``contracts/deployments/<network>.json``. Writes
``measurements/<run-name>/chain_<target>.json`` and (for sepolia, or when absent)
``chain_prices.json``.
Exit codes: 0 ok, 1 usage/config, 3 balance below ``chain.min_balance_eth``, 4 run aborted or the
cap check failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chain_metrics as cm
import metrics
import prices
from chain_probe import Web3Probe
from generate_corpus import load_config

EVAL_DIR = Path(__file__).resolve().parent
DEPLOYMENTS = EVAL_DIR.parent / "contracts" / "deployments"
NETWORK = {"local": "localhost", "sepolia": "sepolia"}


def _eth(wei: int) -> str:
    return f"{wei / cm.WEI_PER_ETH:.9f} ETH"


def _registry(target: str) -> str:
    env = os.environ.get("REGISTRY_ADDRESS")
    if env:
        return env
    return str(json.loads((DEPLOYMENTS / f"{NETWORK[target]}.json").read_text())["address"])


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _run(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    chain_cfg = cfg["chain"]
    rpc, key = os.environ.get("CHAIN_RPC_URL"), os.environ.get("ANCHOR_PRIVATE_KEY")
    if not rpc or not key:
        print("set CHAIN_RPC_URL and ANCHOR_PRIVATE_KEY in the environment", file=sys.stderr)
        return 1
    registry = _registry(args.target)
    confirmations = int(chain_cfg["confirmations"][args.target])
    probe = Web3Probe(rpc, cm.CHAIN_IDS[args.target], registry, key, confirmations)
    try:
        planned = len(
            cm.plan_transactions(
                int(chain_cfg["latency_samples"]), int(chain_cfg["subsequent_versions"])
            )
        )
        cap, balance = int(chain_cfg["max_transactions"]), await probe.balance_wei()
        print(f"target {args.target} (chain {await probe.chain_id()}), registry {registry}")
        print(f"plan: {planned} transactions, hard cap {cap}, no retries")
        print(f"confirmations awaited per transaction: {confirmations}")
        print(f"balance before: {_eth(balance)}")
        if planned > cap:
            print(f"REFUSED: plan of {planned} exceeds the cap of {cap}", file=sys.stderr)
            return 4
        if balance < int(float(chain_cfg["min_balance_eth"]) * cm.WEI_PER_ETH):
            print(f"REFUSED: balance below chain.min_balance_eth {chain_cfg['min_balance_eth']}")
            return 3
        if args.dry_run:
            print("dry run: nothing sent")
            return 0

        snap = prices.snapshot(chain_cfg["prices"])
        nonce = "local" if args.target == "local" else _now()
        started = _now()
        result = await cm.run_measurement(probe, chain_cfg, args.target, nonce)
    finally:
        await probe.aclose()
    result |= {
        "confirmations": confirmations,
        "registry": registry,
        "started_at_utc": started,
        "finished_at_utc": _now(),
    }
    out = _out_dir(args, cfg)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"chain_{args.target}.json").write_text(metrics.dumps(result), encoding="utf-8")
    if args.target == "sepolia" or not (out / "chain_prices.json").exists():
        (out / "chain_prices.json").write_text(metrics.dumps(snap), encoding="utf-8")

    t, b = result["transactions"], result["balance"]
    print(f"transactions sent {t['sent']} of cap {t['cap']} (planned {t['planned']})")
    print(f"cap held: {t['cap_held']}")
    print(f"balance before: {_eth(b['before_wei'])}\nbalance after:  {_eth(b['after_wei'])}")
    print(f"spent: {_eth(b['spent_wei'])}; receipts say {_eth(b['fees_from_receipts_wei'])}")
    print(f"spend matches receipts: {b['matches_receipts']}")
    for kind in ("v1", "subsequent"):
        g, lat = result["gas"][kind], result["latency_s"][kind]
        if g["n"]:
            print(f"{kind}: n={g['n']} gas median {g['median']:.0f}")
            print(f"{kind}: latency median {lat['median']:.2f}s")
    print(f"wrote {out}")
    if result["aborted"] or not t["cap_held"]:
        print(f"ABORTED/CAP: {result['aborted']}", file=sys.stderr)
        return 4
    return 0


def _out_dir(args: argparse.Namespace, cfg: dict[str, Any]) -> Path:
    base = args.measurements_dir or EVAL_DIR / cfg["chain"]["measurements_dir"]
    return Path(base) / (args.run_name or f"seed{cfg['seed']}")


def _refresh_prices(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    out = _out_dir(args, cfg)
    out.mkdir(parents=True, exist_ok=True)
    snap = prices.snapshot(cfg["chain"]["prices"])
    (out / "chain_prices.json").write_text(metrics.dumps(snap), encoding="utf-8")
    print(f"snapshot {snap['taken_at_utc']} live={snap['live']} -> {out / 'chain_prices.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=sorted(cm.CHAIN_IDS), required=True)
    ap.add_argument("--config", type=Path, default=EVAL_DIR / "configs" / "default.yaml")
    ap.add_argument("--run-name", help="measurements sub-directory (default seed<seed>)")
    ap.add_argument("--measurements-dir", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="print plan, cap, balance; send nothing")
    ap.add_argument(
        "--refresh-prices",
        action="store_true",
        help="only re-take the price snapshot into chain_prices.json (no chain access, no gas)",
    )
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.refresh_prices:
        return _refresh_prices(args, cfg)
    return asyncio.run(_run(args, cfg))


if __name__ == "__main__":
    sys.exit(main())
