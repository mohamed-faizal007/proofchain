"""Web3RegistryClient without a node (P5 review M5): a stubbed `eth` module and contract functions.

Only the RPC surface is faked. Signing (eth_account), the VersionAnchored event decoding (the real
ABI's `contract.events`), bytes32 <-> hex conversion and all client logic run for real. The same
paths are exercised against a real Hardhat node by `-m chain` (tests/integration/, CI job
`chain-integration`).
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from eth_abi.abi import encode
from eth_account import Account
from hexbytes import HexBytes
from web3 import Web3

from app.chain import web3_client
from app.chain.types import ZERO_HASH, AnchorReceipt, OnChainVersion, TxReceipt
from app.chain.web3_client import Web3RegistryClient
from app.config import Settings
from app.errors import AnchorFailedError, ChainUnavailableError

PRIVATE_KEY = "0x" + "11" * 32
SENDER = Account.from_key(PRIVATE_KEY).address
REGISTRY = Web3.to_checksum_address("0x" + "22" * 20)
DOC, FILE, ROOT = "ab" * 32, "cd" * 32, "ef" * 32
OTHER = "12" * 32
TX_HASH = HexBytes(b"\x09" * 32)
EVENT_TOPIC = Web3.keccak(
    text="VersionAnchored(bytes32,uint32,bytes32,bytes32,bytes32,uint16,uint64)"
)
BASE_FEE, PRIORITY = 7, 3


def _b(hex_: str) -> bytes:
    return bytes.fromhex(hex_)


@dataclass
class FakeChain:
    """In-memory registry + node state behind the stubs."""

    versions: dict[bytes, list[tuple[bytes, bytes, bytes, int, int, bool]]] = field(
        default_factory=dict
    )
    chain_id: int = 31337
    blocks: list[int] = field(default_factory=lambda: [10])  # successive eth_blockNumber reads
    nonce_pending: int = 4
    nonce_latest: int = 4
    code: bytes = b"\x60\x80"
    receipt_status: int = 1
    receipt_block: int = 10
    emit_event: bool = True
    event_doc: bytes | None = None  # override the event's docId
    built: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    sent: list[bytes] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)

    def add(self, doc: str, file_h: str, root: str, *, revoked: bool = False) -> None:
        versions = self.versions.setdefault(_b(doc), [])
        prev = versions[-1][1] if versions else bytes(32)
        versions.append((_b(file_h), _b(root), prev, 1_700_000_000 + len(versions), 2, revoked))


class _Call:
    def __init__(self, chain: FakeChain, name: str, args: tuple[Any, ...], result: Any) -> None:
        self._chain, self._name, self._args, self._result = chain, name, args, result

    async def call(self) -> Any:
        self._chain.reads.append(self._name)
        return self._result

    async def build_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        self._chain.built.append((self._name, self._args, params))
        return {**params, "to": REGISTRY, "data": "0x1234", "gas": 200_000, "value": 0}


class FakeFunctions:
    def __init__(self, chain: FakeChain) -> None:
        self._c = chain

    def versionCount(self, doc_b: bytes) -> _Call:  # noqa: N802 - contract ABI name
        return _Call(self._c, "versionCount", (doc_b,), len(self._c.versions.get(doc_b, [])))

    def getVersion(self, doc_b: bytes, n: int) -> _Call:  # noqa: N802
        return _Call(self._c, "getVersion", (doc_b, n), self._c.versions[doc_b][n - 1])

    def anchorVersion(self, *args: Any) -> _Call:  # noqa: N802
        return _Call(self._c, "anchorVersion", args, None)

    def revokeVersion(self, *args: Any) -> _Call:  # noqa: N802
        return _Call(self._c, "revokeVersion", args, None)


class FakeEth:
    def __init__(self, chain: FakeChain) -> None:
        self._c = chain

    @staticmethod
    async def _value(v: Any) -> Any:
        return v

    @property
    def chain_id(self) -> Any:
        return self._value(self._c.chain_id)

    @property
    def block_number(self) -> Any:
        blocks = self._c.blocks
        return self._value(blocks.pop(0) if len(blocks) > 1 else blocks[0])

    @property
    def max_priority_fee(self) -> Any:
        return self._value(PRIORITY)

    async def get_code(self, _: str) -> bytes:
        return self._c.code

    async def get_transaction_count(self, address: str, block: str) -> int:
        assert address == SENDER
        return self._c.nonce_pending if block == "pending" else self._c.nonce_latest

    async def get_block(self, _: str) -> dict[str, int]:
        return {"baseFeePerGas": BASE_FEE}

    async def send_raw_transaction(self, raw: bytes) -> HexBytes:
        self._c.sent.append(bytes(raw))
        return TX_HASH

    async def wait_for_transaction_receipt(self, tx_hash: HexBytes, timeout: float) -> Any:
        assert tx_hash == TX_HASH
        return {
            "status": self._c.receipt_status,
            "blockNumber": self._c.receipt_block,
            "transactionHash": TX_HASH,
            "logs": self._logs(),
        }

    def _logs(self) -> list[dict[str, Any]]:
        name, args, _ = self._c.built[-1]
        if name != "anchorVersion" or not self._c.emit_event:
            return []
        doc_b, file_b, root_b, canon = args
        versions = self._c.versions.setdefault(doc_b, [])
        prev = versions[-1][1] if versions else bytes(32)
        versions.append((file_b, root_b, prev, 1_700_000_100, canon, False))
        data = encode(
            ["bytes32", "bytes32", "bytes32", "uint16", "uint64"],
            [file_b, root_b, prev, canon, 1_700_000_100],
        )
        event_doc = self._c.event_doc if self._c.event_doc is not None else doc_b
        return [
            {
                "address": REGISTRY,
                "topics": [
                    EVENT_TOPIC,
                    HexBytes(event_doc),
                    HexBytes(encode(["uint32"], [len(versions)])),
                ],
                "data": HexBytes(data),
                "blockNumber": self._c.receipt_block,
                "transactionHash": TX_HASH,
                "transactionIndex": 0,
                "logIndex": 0,
                "blockHash": HexBytes(b"\x08" * 32),
            }
        ]


def patch_sleep(monkeypatch: pytest.MonkeyPatch, sleep: Any) -> None:
    """Replace `asyncio.sleep` for web3_client only (never the global asyncio module)."""
    local = SimpleNamespace(sleep=sleep, timeout=asyncio.timeout, Lock=asyncio.Lock)
    monkeypatch.setattr(web3_client, "asyncio", local)


def stub(client: Web3RegistryClient, chain: FakeChain) -> None:
    real_events = client._contract.events
    client._contract = SimpleNamespace(functions=FakeFunctions(chain), events=real_events)  # type: ignore[assignment]
    client._w3 = SimpleNamespace(eth=FakeEth(chain), provider=client._w3.provider)  # type: ignore[assignment]


@pytest.fixture
def chain() -> FakeChain:
    return FakeChain()


@pytest.fixture
async def client(chain: FakeChain) -> AsyncIterator[Web3RegistryClient]:
    c = Web3RegistryClient("http://127.0.0.1:1", 31337, REGISTRY.lower(), PRIVATE_KEY)
    provider = c._w3.provider
    stub(c, chain)
    yield c
    await provider.disconnect()


# --- from_settings / constructor ---


async def test_from_settings_wires_every_chain_setting() -> None:
    settings = Settings(
        app_env="test",
        chain_rpc_url="http://127.0.0.1:9999",
        chain_id=11155111,
        registry_address="0x" + "22" * 20,
        anchor_private_key=PRIVATE_KEY,
        chain_confirmations=3,
    )
    c = Web3RegistryClient.from_settings(settings)
    try:
        assert c._chain_id == 11155111
        assert c._confirmations == 3
        assert c._address == REGISTRY  # checksummed
        assert c._account.address == SENDER
        assert c._w3.provider.endpoint_uri == "http://127.0.0.1:9999"
        assert c._contract.address == REGISTRY
    finally:
        await c.aclose()


async def test_confirmations_below_one_are_clamped_to_one() -> None:
    c = Web3RegistryClient("http://127.0.0.1:1", 31337, REGISTRY, PRIVATE_KEY, confirmations=0)
    assert c._confirmations == 1
    await c.aclose()


# --- anchor_version orchestration ---


async def test_anchor_new_document_sends_signed_eip1559_tx_and_parses_the_event(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    receipt = await client.anchor_version(DOC, FILE, ROOT, 2)

    assert receipt == AnchorReceipt(1, "0x" + "09" * 32, 10, False)
    [(name, args, params)] = chain.built
    assert name == "anchorVersion"
    assert args == (_b(DOC), _b(FILE), _b(ROOT), 2)
    assert params == {
        "from": SENDER,
        "chainId": 31337,
        "nonce": 4,
        "maxPriorityFeePerGas": PRIORITY,
        "maxFeePerGas": 2 * BASE_FEE + PRIORITY,
    }
    [raw] = chain.sent
    assert Account.recover_transaction(raw) == SENDER  # signed by the anchor key
    assert chain.reads == ["versionCount"]  # empty document: no getVersion read


async def test_anchor_links_to_the_previous_version(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    chain.add(DOC, OTHER, OTHER)
    receipt = await client.anchor_version(DOC, FILE, ROOT, 2)
    assert (receipt.version_no, receipt.already_anchored) == (2, False)
    assert chain.reads == ["versionCount", "getVersion"]


async def test_anchor_is_skipped_when_latest_version_already_matches(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    chain.add(DOC, OTHER, OTHER)
    chain.add(DOC, FILE, ROOT)

    receipt = await client.anchor_version(DOC, FILE, ROOT, 2)

    assert receipt == AnchorReceipt(2, None, None, True)
    assert chain.built == [] and chain.sent == []


@pytest.mark.parametrize(
    ("file_h", "root", "revoked"),
    [(FILE, ROOT, True), (FILE, OTHER, False), (OTHER, ROOT, False)],
    ids=["latest_revoked", "root_differs", "file_differs"],
)
async def test_anchor_sends_a_fresh_tx_unless_latest_matches_and_is_live(
    client: Web3RegistryClient, chain: FakeChain, file_h: str, root: str, revoked: bool
) -> None:
    chain.add(DOC, file_h, root, revoked=revoked)
    receipt = await client.anchor_version(DOC, FILE, ROOT, 2)
    assert (receipt.version_no, receipt.already_anchored) == (2, False)
    assert len(chain.sent) == 1


@pytest.mark.parametrize("case", ["no_event", "event_for_another_document"])
async def test_anchor_without_a_matching_event_fails(
    client: Web3RegistryClient, chain: FakeChain, case: str
) -> None:
    if case == "no_event":
        chain.emit_event = False
    else:
        chain.event_doc = _b(OTHER)
    with pytest.raises(AnchorFailedError) as info:
        await client.anchor_version(DOC, FILE, ROOT, 2)
    assert info.value.message == "VersionAnchored event missing from receipt"


async def test_reverted_receipt_fails(client: Web3RegistryClient, chain: FakeChain) -> None:
    chain.receipt_status = 0
    with pytest.raises(AnchorFailedError) as info:
        await client.anchor_version(DOC, FILE, ROOT, 2)
    assert info.value.message == "Transaction reverted"


async def test_anchor_rejects_non_canonical_hashes_before_any_rpc(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    with pytest.raises(ValueError):
        await client.anchor_version(DOC, "0x" + FILE, ROOT, 2)
    assert chain.reads == [] and chain.sent == []


async def test_concurrent_anchors_are_serialized_by_the_lock(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    """Two anchors of the same content: the second sees the first on-chain and sends nothing."""
    first, second = await asyncio.gather(
        client.anchor_version(DOC, FILE, ROOT, 2), client.anchor_version(DOC, FILE, ROOT, 2)
    )
    assert sorted([first.already_anchored, second.already_anchored]) == [False, True]
    assert len(chain.sent) == 1


# --- revoke_version ---


async def test_revoke_sends_the_tx_and_returns_hash_and_block(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    chain.receipt_block = chain.blocks[0] = 42  # node head at the mined block
    receipt = await client.revoke_version(DOC, 3, "superseded")
    assert receipt == TxReceipt("0x" + "09" * 32, 42)
    [(name, args, params)] = chain.built
    assert (name, args, params["nonce"]) == ("revokeVersion", (_b(DOC), 3, "superseded"), 4)
    assert Account.recover_transaction(chain.sent[0]) == SENDER


# --- get_version bounds and _read_version decoding ---


async def test_get_version_decodes_the_struct(client: Web3RegistryClient, chain: FakeChain) -> None:
    chain.add(DOC, OTHER, OTHER)
    chain.add(DOC, FILE, ROOT, revoked=True)

    v1 = await client.get_version(DOC, 1)
    v2 = await client.get_version(DOC, 2)

    assert v1 == OnChainVersion(1, OTHER, OTHER, ZERO_HASH, 1_700_000_000, 2, False)
    assert v2 == OnChainVersion(2, FILE, ROOT, OTHER, 1_700_000_001, 2, True)
    assert isinstance(v2.revoked, bool) and isinstance(v2.anchored_at, int)


@pytest.mark.parametrize("version_no", [0, -1, 3, 99])
async def test_get_version_out_of_range_is_none_without_reading(
    client: Web3RegistryClient, chain: FakeChain, version_no: int
) -> None:
    chain.add(DOC, FILE, ROOT)
    chain.add(DOC, OTHER, OTHER)
    assert await client.get_version(DOC, version_no) is None
    assert chain.reads == ["versionCount"]


async def test_get_version_on_unknown_document_is_none(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    assert await client.get_version(OTHER, 1) is None


async def test_version_count(client: Web3RegistryClient, chain: FakeChain) -> None:
    chain.add(DOC, FILE, ROOT)
    assert await client.version_count(DOC) == 1
    assert await client.version_count(OTHER) == 0


# --- _wait_confirmations ---


async def test_single_confirmation_does_not_poll(
    client: Web3RegistryClient, chain: FakeChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    polled: list[int] = []
    real = FakeEth.block_number

    def spy(self: FakeEth) -> Any:
        polled.append(1)
        return real.fget(self)  # type: ignore[attr-defined]

    monkeypatch.setattr(FakeEth, "block_number", property(spy))
    chain.blocks = [10]
    await client.revoke_version(DOC, 1, "x")
    assert len(polled) == 1  # block 10 >= target 10 on the first read


async def test_waits_until_the_confirmation_depth_is_reached(
    client: Web3RegistryClient, chain: FakeChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    client._confirmations = 3  # mined at 10 -> needs block 12
    chain.blocks = [10, 11, 11, 12]
    sleeps: list[float] = []

    async def no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    patch_sleep(monkeypatch, no_sleep)
    await client.revoke_version(DOC, 1, "x")
    assert sleeps == [1, 1, 1]
    assert chain.blocks == [12]


async def test_confirmation_timeout_maps_to_chain_unavailable_known_issue_m2(
    client: Web3RegistryClient, chain: FakeChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KNOWN ISSUE (PROGRESS.md, P5 review M2), pinned, not endorsed: the tx is mined, but a
    confirmation-wait timeout surfaces as CHAIN_UNAVAILABLE. Change this test with the fix."""
    client._confirmations = 5
    chain.blocks = [10]  # the chain never advances
    monkeypatch.setattr(web3_client, "RECEIPT_TIMEOUT_SECONDS", 0.05)

    async def short_sleep(_: float) -> None:
        await asyncio.sleep(0.01)  # the real one: this test module's global asyncio

    patch_sleep(monkeypatch, short_sleep)
    with pytest.raises(ChainUnavailableError):
        await client.revoke_version(DOC, 1, "x")
    assert len(chain.sent) == 1  # the tx was sent and mined


# --- health ---


async def test_health_ok_reports_chain_block_and_address(
    client: Web3RegistryClient, chain: FakeChain
) -> None:
    chain.blocks = [77]
    h = await client.health()
    assert (h.ok, h.chain_id, h.block_number, h.registry_address) == (True, 31337, 77, REGISTRY)


@pytest.mark.parametrize("case", ["wrong_chain_id", "no_code_at_address"])
async def test_health_not_ok_on_wrong_chain_or_missing_contract(
    client: Web3RegistryClient, chain: FakeChain, case: str
) -> None:
    if case == "wrong_chain_id":
        chain.chain_id = 1
    else:
        chain.code = b""
    h = await client.health()
    assert h.ok is False
    assert h.chain_id == chain.chain_id  # details still reported for diagnosis
