"""Web3RegistryClient: signs and sends ProofChainRegistry txs (docs/05_SMART_CONTRACT.md)."""

import asyncio
import json
import logging
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, TypeVar

from aiohttp import ClientError
from eth_account import Account
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.exceptions import ContractLogicError

from app.chain.hexutil import from_bytes32, to_bytes32
from app.chain.registry_client import is_already_anchored
from app.chain.types import AnchorReceipt, ChainHealth, OnChainVersion, TxReceipt
from app.config import Settings
from app.errors import AnchorFailedError, ChainUnavailableError

ABI_PATH = Path(__file__).parent / "abi" / "ProofChainRegistry.json"
RECEIPT_TIMEOUT_SECONDS = 120.0
_T = TypeVar("_T")
logger = logging.getLogger(__name__)
# web3 logs the full RPC URI (API key included) at DEBUG on every request.
logging.getLogger("web3").setLevel(logging.WARNING)


def _unavailable(exc: BaseException) -> ChainUnavailableError:
    """Drop the cause on purpose: aiohttp errors embed the RPC URL, which may hold an API key."""
    logger.warning("chain RPC unavailable: %s", type(exc).__name__)
    return ChainUnavailableError("Blockchain node unreachable or timed out")


class Web3RegistryClient:
    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
        registry_address: str,
        private_key: str,
        confirmations: int = 1,
        rpc_timeout: float = 10.0,
    ) -> None:
        self._w3 = AsyncWeb3(
            AsyncHTTPProvider(
                rpc_url,
                request_kwargs={"timeout": rpc_timeout},
                # No hidden backoff retries: a down node must fail fast (retries belong to P5-04).
                exception_retry_configuration=None,
            )
        )
        self._chain_id = chain_id
        self._confirmations = max(1, confirmations)
        self._account = Account.from_key(private_key)
        self._address = AsyncWeb3.to_checksum_address(registry_address)
        abi = json.loads(ABI_PATH.read_text(encoding="utf-8"))
        self._contract = self._w3.eth.contract(address=self._address, abi=abi)
        self._lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "Web3RegistryClient":
        return cls(
            settings.chain_rpc_url,
            settings.chain_id,
            settings.registry_address,
            settings.anchor_private_key,
            settings.chain_confirmations,
        )

    async def anchor_version(
        self, doc_id: str, file_hash: str, text_root: str, canon_version: int
    ) -> AnchorReceipt:
        doc_b, file_b, root_b = to_bytes32(doc_id), to_bytes32(file_hash), to_bytes32(text_root)
        async with self._lock:
            count = await self._rpc(self._contract.functions.versionCount(doc_b).call())
            if count > 0:
                latest = await self._read_version(doc_b, count)
                if is_already_anchored(latest, file_hash, text_root):
                    return AnchorReceipt(count, None, None, True)
            fn = self._contract.functions.anchorVersion(doc_b, file_b, root_b, canon_version)
            receipt = await self._send(fn)
            events = self._contract.events.VersionAnchored().process_receipt(receipt)
            if len(events) != 1 or bytes(events[0]["args"]["docId"]) != doc_b:
                raise AnchorFailedError("VersionAnchored event missing from receipt")
            return AnchorReceipt(
                int(events[0]["args"]["versionNo"]),
                "0x" + receipt["transactionHash"].hex().removeprefix("0x"),
                int(receipt["blockNumber"]),
                False,
            )

    async def revoke_version(self, doc_id: str, version_no: int, reason: str) -> TxReceipt:
        doc_b = to_bytes32(doc_id)
        async with self._lock:
            receipt = await self._send(
                self._contract.functions.revokeVersion(doc_b, version_no, reason)
            )
            return TxReceipt(
                "0x" + receipt["transactionHash"].hex().removeprefix("0x"),
                int(receipt["blockNumber"]),
            )

    async def get_version(self, doc_id: str, version_no: int) -> OnChainVersion | None:
        doc_b = to_bytes32(doc_id)
        count = await self._rpc(self._contract.functions.versionCount(doc_b).call())
        if not 1 <= version_no <= count:
            return None
        return await self._read_version(doc_b, version_no)

    async def version_count(self, doc_id: str) -> int:
        return int(
            await self._rpc(self._contract.functions.versionCount(to_bytes32(doc_id)).call())
        )

    async def aclose(self) -> None:
        await self._w3.provider.disconnect()

    async def health(self) -> ChainHealth:
        try:
            chain_id = await self._w3.eth.chain_id
            block = await self._w3.eth.block_number
            code = await self._w3.eth.get_code(self._address)
        except Exception:  # noqa: BLE001 - any failure means unhealthy; never surface text
            return ChainHealth(ok=False)
        return ChainHealth(
            ok=chain_id == self._chain_id and len(code) > 0,
            chain_id=chain_id,
            block_number=block,
            registry_address=self._address,
        )

    async def _read_version(self, doc_b: bytes, version_no: int) -> OnChainVersion:
        raw = await self._rpc(self._contract.functions.getVersion(doc_b, version_no).call())
        file_h, root, prev, anchored_at, canon, revoked = raw
        return OnChainVersion(
            version_no=version_no,
            file_hash=from_bytes32(bytes(file_h)),
            text_root=from_bytes32(bytes(root)),
            prev_text_root=from_bytes32(bytes(prev)),
            anchored_at=int(anchored_at),
            canon_version=int(canon),
            revoked=bool(revoked),
        )

    async def _send(self, fn: Any) -> Any:
        """Build an EIP-1559 tx, sign, send, wait for confirmations. Caller holds the lock."""
        sender = self._account.address
        try:
            nonce = await self._w3.eth.get_transaction_count(sender, "pending")
            latest = await self._w3.eth.get_block("latest")
            priority = await self._w3.eth.max_priority_fee
            base = latest.get("baseFeePerGas", 0)
            tx = await fn.build_transaction(
                {
                    "from": sender,
                    "chainId": self._chain_id,
                    "nonce": nonce,
                    "maxPriorityFeePerGas": priority,
                    "maxFeePerGas": 2 * base + priority,
                }
            )
            signed = self._account.sign_transaction(tx)
            tx_hash = await self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = await self._w3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS
            )
            await self._wait_confirmations(int(receipt["blockNumber"]))
        except ContractLogicError as exc:
            raise AnchorFailedError("Contract rejected the transaction") from exc
        except (OSError, ClientError, TimeoutError) as exc:
            raise _unavailable(exc) from None
        if receipt["status"] != 1:
            raise AnchorFailedError("Transaction reverted")
        return receipt

    async def _wait_confirmations(self, block_number: int) -> None:
        target = block_number + self._confirmations - 1
        async with asyncio.timeout(RECEIPT_TIMEOUT_SECONDS):
            while await self._w3.eth.block_number < target:
                await asyncio.sleep(1)

    async def _rpc(self, call: Awaitable[_T]) -> _T:
        try:
            return await call
        except (OSError, ClientError, TimeoutError) as exc:
            raise _unavailable(exc) from None
