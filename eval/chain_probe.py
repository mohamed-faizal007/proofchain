"""Web3 implementation of ``chain_metrics.ChainProbe`` over the backend's own registry client.

Sends go through ``Web3RegistryClient.anchor_version`` (the code path the API uses). Latency is
the wall time of that call: version-count and latest-version reads, send, receipt and
``confirmations`` blocks. Gas comes from the transaction receipt.
"""

from __future__ import annotations

import time

from app.chain.web3_client import Web3RegistryClient
from eth_account import Account
from web3 import AsyncHTTPProvider, AsyncWeb3

from chain_metrics import CANON_VERSION, TxSample


class Web3Probe:
    def __init__(
        self, rpc_url: str, chain_id: int, registry: str, private_key: str, confirmations: int
    ) -> None:
        self._client = Web3RegistryClient(
            rpc_url, chain_id, registry, private_key, confirmations, rpc_timeout=30.0
        )
        self._w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url, exception_retry_configuration=None))
        self._sender = Account.from_key(private_key).address

    async def chain_id(self) -> int:
        return int(await self._w3.eth.chain_id)

    async def balance_wei(self) -> int:
        return int(await self._w3.eth.get_balance(self._sender))

    async def tx_count(self) -> int:
        return int(await self._w3.eth.get_transaction_count(self._sender, "latest"))

    async def anchor(self, doc_id: str, file_hash: str, text_root: str) -> TxSample:
        start = time.perf_counter()
        receipt = await self._client.anchor_version(doc_id, file_hash, text_root, CANON_VERSION)
        latency = time.perf_counter() - start
        if receipt.tx_hash is None or receipt.block_number is None:
            raise RuntimeError("no transaction was sent (already anchored)")
        tx = await self._w3.eth.get_transaction_receipt(receipt.tx_hash)
        return TxSample(
            kind="v1" if receipt.version_no == 1 else "subsequent",
            version_no=receipt.version_no,
            tx_hash=receipt.tx_hash,
            block_number=receipt.block_number,
            gas_used=int(tx["gasUsed"]),
            effective_gas_price_wei=int(tx["effectiveGasPrice"]),
            latency_s=round(latency, 3),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
        await self._w3.provider.disconnect()
