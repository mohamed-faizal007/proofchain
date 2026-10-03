"""Chain metrics (docs/08 C.3, Chain): gas per ``anchorVersion``, cost estimate, anchoring latency.

Pure logic over a ``ChainProbe``; the web3 implementation is ``chain_probe.py``. Every send is
spent from a ``TxBudget`` and the whole plan is checked against ``max_transactions`` before the
first send. There is no retry anywhere: a failure ends the run and is recorded. After the run the
cap is re-checked against the sender's on-chain nonce, which counts transactions regardless of
what this code believes it sent.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Protocol

CHAIN_IDS = {"local": 31337, "sepolia": 11155111}
CANON_VERSION = 1
WEI_PER_ETH = 10**18


class TxCapExceededError(Exception):
    """The run would send (or has sent) more transactions than ``max_transactions``."""


class WrongChainError(Exception):
    """The probe is connected to a different chain than the target names."""


@dataclass(frozen=True)
class TxSample:
    kind: str  # "v1" (first version of a document) or "subsequent"
    version_no: int
    tx_hash: str
    block_number: int
    gas_used: int
    effective_gas_price_wei: int
    latency_s: float


class ChainProbe(Protocol):
    async def chain_id(self) -> int: ...

    async def balance_wei(self) -> int: ...

    async def tx_count(self) -> int:
        """Sender nonce on chain: the number of transactions it has ever sent."""
        ...

    async def anchor(self, doc_id: str, file_hash: str, text_root: str) -> TxSample: ...


class TxBudget:
    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.used = 0

    def spend(self) -> None:
        if self.used >= self.cap:
            raise TxCapExceededError(f"transaction cap of {self.cap} reached")
        self.used += 1


def plan_transactions(latency_samples: int, subsequent_versions: int) -> list[tuple[int, int]]:
    """(doc index, version): v1 for every document, then v2 for the first few documents."""
    if subsequent_versions > latency_samples:
        raise ValueError("subsequent_versions cannot exceed latency_samples")
    return [(i, 1) for i in range(latency_samples)] + [(i, 2) for i in range(subsequent_versions)]


def _digest(*parts: object) -> str:
    return hashlib.sha256(
        ":".join(str(p) for p in ("proofchain-chain-eval", *parts)).encode()
    ).hexdigest()


def doc_id(seed: int, nonce: str, index: int) -> str:
    """Fresh per run (the nonce) so a rerun never lands on an already anchored document."""
    return _digest(seed, nonce, "doc", index)


def version_hashes(seed: int, index: int, version: int) -> tuple[str, str]:
    """Deterministic (file hash, text root): identical calldata on every run."""
    return _digest(seed, index, version, "file"), _digest(seed, index, version, "root")


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered)) - 1  # nearest-rank percentile
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "mean": round(statistics.fmean(ordered), 6),
        "p95": ordered[rank],
        "max": ordered[-1],
    }


def cost_estimate(
    gas: float, gas_price_gwei: float, eth_usd: float, eth_inr: float
) -> dict[str, float]:
    eth = gas * gas_price_gwei * 1e-9
    return {
        "gas": gas,
        "gas_price_gwei": gas_price_gwei,
        "eth": eth,
        "usd": eth * eth_usd,
        "inr": eth * eth_inr,
    }


def _by_kind(samples: list[TxSample], field: str) -> dict[str, dict[str, float]]:
    out = {"all": summarize([float(getattr(s, field)) for s in samples])}
    for kind in ("v1", "subsequent"):
        out[kind] = summarize([float(getattr(s, field)) for s in samples if s.kind == kind])
    return out


async def run_measurement(
    probe: ChainProbe, cfg: dict[str, Any], target: str, nonce: str
) -> dict[str, Any]:
    cap = int(cfg["max_transactions"])
    plan = plan_transactions(int(cfg["latency_samples"]), int(cfg["subsequent_versions"]))
    if len(plan) > cap:
        raise TxCapExceededError(f"plan of {len(plan)} transactions exceeds the cap of {cap}")
    chain_id = await probe.chain_id()
    if chain_id != CHAIN_IDS[target]:
        raise WrongChainError(f"target {target} expects chain {CHAIN_IDS[target]}, got {chain_id}")

    seed = int(cfg["seed"])
    budget = TxBudget(cap)
    balance_before = await probe.balance_wei()
    nonce_before = await probe.tx_count()
    samples: list[TxSample] = []
    aborted: dict[str, Any] | None = None
    for index, version in plan:
        budget.spend()
        file_hash, text_root = version_hashes(seed, index, version)
        try:
            samples.append(await probe.anchor(doc_id(seed, nonce, index), file_hash, text_root))
        except Exception as exc:  # noqa: BLE001 - stop at once; only the type is kept (no URLs)
            aborted = {"after_samples": len(samples), "error": type(exc).__name__}
            break
    balance_after = await probe.balance_wei()
    nonce_after = await probe.tx_count()

    sent = nonce_after - nonce_before
    fees = sum(s.gas_used * s.effective_gas_price_wei for s in samples)
    spent = balance_before - balance_after
    return {
        "target": target,
        "chain_id": chain_id,
        "nonce": nonce,
        "config": {
            "latency_samples": int(cfg["latency_samples"]),
            "subsequent_versions": int(cfg["subsequent_versions"]),
            "seed": seed,
        },
        "transactions": {
            "planned": len(plan),
            "sent": sent,
            "cap": cap,
            "cap_held": sent <= cap,
            "nonce_before": nonce_before,
            "nonce_after": nonce_after,
        },
        "balance": {
            "before_wei": balance_before,
            "after_wei": balance_after,
            "spent_wei": spent,
            "fees_from_receipts_wei": fees,
            "matches_receipts": spent == fees,
        },
        "gas": _by_kind(samples, "gas_used"),
        "latency_s": _by_kind(samples, "latency_s"),
        "samples": [asdict(s) for s in samples],
        "aborted": aborted,
    }
