"""P9-05 chain metrics (docs/08 C.3, Chain): gas per anchorVersion, cost, anchoring latency.

The measurement code takes a ``ChainProbe`` so everything here runs against a fake. The hard cap
on transactions is a property of the runner, not of the probe: it must hold before the first send.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import chain_metrics as cm


class FakeProbe:
    """Records every call. ``fail_on`` is the 1-based call number that raises."""

    def __init__(self, fail_on: int | None = None, balance: int = 10**18) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.fail_on = fail_on
        self.balance = balance
        self.nonce = 7
        self.gas_price = 2_000_000_000

    async def chain_id(self) -> int:
        return 11155111

    async def balance_wei(self) -> int:
        return self.balance

    async def tx_count(self) -> int:
        return self.nonce

    async def anchor(self, doc_id: str, file_hash: str, text_root: str) -> cm.TxSample:
        self.calls.append((doc_id, file_hash, text_root))
        if self.fail_on == len(self.calls):
            raise RuntimeError("boom")
        n = len(self.calls)
        first = sum(1 for c in self.calls if c[0] == doc_id) == 1
        gas = 90_000 if first else 60_000
        self.nonce += 1
        self.balance -= gas * self.gas_price
        return cm.TxSample(
            kind="v1" if first else "subsequent",
            version_no=1 if first else 2,
            tx_hash=f"0x{n:064x}",
            block_number=100 + n,
            gas_used=gas,
            effective_gas_price_wei=self.gas_price,
            latency_s=float(n),
        )


def _cfg(**over: Any) -> dict[str, Any]:
    base = {"latency_samples": 10, "subsequent_versions": 5, "max_transactions": 20, "seed": 1}
    return base | over


def _run(probe: FakeProbe, cfg: dict[str, Any], nonce: str = "t") -> dict[str, Any]:
    return asyncio.run(cm.run_measurement(probe, cfg, "sepolia", nonce))


def test_plan_is_v1_for_every_doc_then_v2_for_the_first_few() -> None:
    plan = cm.plan_transactions(10, 5)
    assert len(plan) == 15
    assert plan[:10] == [(i, 1) for i in range(10)]
    assert plan[10:] == [(i, 2) for i in range(5)]


def test_plan_rejects_more_subsequent_versions_than_docs() -> None:
    with pytest.raises(ValueError):
        cm.plan_transactions(3, 4)


def test_plan_over_the_cap_is_refused_before_any_send() -> None:
    probe = FakeProbe()
    with pytest.raises(cm.TxCapExceededError):
        _run(probe, _cfg(max_transactions=14))
    assert probe.calls == []


def test_cap_of_exactly_the_plan_size_is_allowed() -> None:
    probe = FakeProbe()
    out = _run(probe, _cfg(max_transactions=15))
    assert len(probe.calls) == 15 and out["transactions"]["sent"] == 15


def test_budget_stops_the_sixteenth_send() -> None:
    budget = cm.TxBudget(2)
    budget.spend()
    budget.spend()
    with pytest.raises(cm.TxCapExceededError):
        budget.spend()
    assert budget.used == 2


def test_a_failure_stops_the_run_and_is_never_retried() -> None:
    probe = FakeProbe(fail_on=3)
    out = _run(probe, _cfg())
    assert len(probe.calls) == 3
    assert out["aborted"] == {"after_samples": 2, "error": "RuntimeError"}
    assert len(out["samples"]) == 2


def test_cap_check_uses_the_on_chain_nonce_not_our_own_count() -> None:
    out = _run(FakeProbe(), _cfg())
    t = out["transactions"]
    assert (t["planned"], t["sent"], t["cap"], t["cap_held"]) == (15, 15, 20, True)
    assert t["nonce_before"] == 7 and t["nonce_after"] == 22


def test_cap_held_is_false_if_the_chain_saw_more_txs_than_the_cap() -> None:
    probe = FakeProbe()
    original = probe.anchor

    async def sneaky(doc_id: str, file_hash: str, text_root: str) -> cm.TxSample:
        probe.nonce += 30  # a send that bypassed the budget
        return await original(doc_id, file_hash, text_root)

    probe.anchor = sneaky  # type: ignore[method-assign]
    out = _run(probe, _cfg(latency_samples=2, subsequent_versions=1, max_transactions=3))
    assert out["transactions"]["cap_held"] is False


def test_balance_before_after_and_fee_cross_check() -> None:
    out = _run(FakeProbe(balance=10**18), _cfg())
    b = out["balance"]
    fees = 10 * 90_000 * 2_000_000_000 + 5 * 60_000 * 2_000_000_000
    assert b["before_wei"] == 10**18 and b["after_wei"] == 10**18 - fees
    assert b["spent_wei"] == fees and b["fees_from_receipts_wei"] == fees
    assert b["matches_receipts"] is True


def test_gas_summary_separates_first_version_from_subsequent() -> None:
    out = _run(FakeProbe(), _cfg())
    g = out["gas"]
    assert g["v1"]["n"] == 10 and g["v1"]["median"] == 90_000
    assert g["subsequent"]["n"] == 5 and g["subsequent"]["median"] == 60_000


def test_latency_summary_overall_and_by_kind() -> None:
    out = _run(FakeProbe(), _cfg())
    lat = out["latency_s"]
    assert lat["all"]["n"] == 15 and lat["all"]["min"] == 1.0 and lat["all"]["max"] == 15.0
    assert lat["all"]["median"] == 8.0 and lat["v1"]["n"] == 10 and lat["subsequent"]["n"] == 5


def test_summary_stats_nearest_rank_p95_and_empty() -> None:
    s = cm.summarize([float(i) for i in range(1, 21)])
    assert s["median"] == 10.5 and s["p95"] == 19.0 and s["mean"] == 10.5
    assert cm.summarize([]) == {"n": 0}


def test_doc_ids_are_unique_per_nonce_and_hashes_do_not_depend_on_it() -> None:
    a, b = FakeProbe(), FakeProbe()
    _run(a, _cfg(), nonce="x")
    _run(b, _cfg(), nonce="y")
    assert {c[0] for c in a.calls}.isdisjoint({c[0] for c in b.calls})
    assert [c[1:] for c in a.calls] == [c[1:] for c in b.calls]
    assert all(len(h) == 64 and h == h.lower() for c in a.calls for h in c)


def test_wrong_chain_is_refused_before_any_send() -> None:
    probe = FakeProbe()
    with pytest.raises(cm.WrongChainError):
        asyncio.run(cm.run_measurement(probe, _cfg(), "local", "t"))  # fake says Sepolia
    assert probe.calls == []


def test_cost_estimate_arithmetic() -> None:
    c = cm.cost_estimate(100_000, gas_price_gwei=20.0, eth_usd=2000.0, eth_inr=170_000.0)
    assert c["eth"] == pytest.approx(0.002)
    assert c["usd"] == pytest.approx(4.0)
    assert c["inr"] == pytest.approx(340.0)


def test_measurement_is_deterministic_apart_from_nonce_and_timings() -> None:
    a = _run(FakeProbe(), _cfg(), nonce="n")
    b = _run(FakeProbe(), _cfg(), nonce="n")
    assert a == b
