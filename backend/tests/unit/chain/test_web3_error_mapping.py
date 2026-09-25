"""Web3RegistryClient error mapping must not leak secrets (RPC URL API key, revert payloads)."""

import http.server
import logging
import threading
import traceback
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from web3.exceptions import ContractLogicError

from app.chain.web3_client import Web3RegistryClient
from app.errors import AnchorFailedError, ChainUnavailableError

API_KEY = "SECRET_API_KEY_123"
REVERT_TEXT = "execution reverted: SECRET_REVERT_PAYLOAD"
DOC, FILE, ROOT = "ab" * 32, "cd" * 32, "ef" * 32
PRIVATE_KEY = "0x" + "11" * 32


class _Unauthorized(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.send_response(401)
        self.end_headers()
        self.wfile.write(b"denied")

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def rpc_url() -> Iterator[str]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Unauthorized)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v3/{API_KEY}"
    server.shutdown()
    server.server_close()


@pytest.fixture
async def client(rpc_url: str) -> AsyncIterator[Web3RegistryClient]:
    c = Web3RegistryClient(rpc_url, 31337, "0x" + "22" * 20, PRIVATE_KEY, rpc_timeout=2.0)
    yield c
    await c.aclose()


def _assert_no_secret(exc: BaseException, caplog: pytest.LogCaptureFixture) -> None:
    assert exc.__cause__ is None
    rendered = "".join(traceback.format_exception(exc)) + caplog.text
    assert API_KEY not in rendered
    assert PRIVATE_KEY[2:] not in rendered


async def test_http_error_from_provider_does_not_leak_url_key_on_read(
    client: Web3RegistryClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ChainUnavailableError) as info:
        await client.version_count(DOC)
    assert info.value.message == "Blockchain node unreachable or timed out"
    _assert_no_secret(info.value, caplog)


async def test_http_error_from_provider_does_not_leak_url_key_on_send(
    client: Web3RegistryClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ChainUnavailableError) as info:
        await client.revoke_version(DOC, 1, "x")
    _assert_no_secret(info.value, caplog)


async def test_contract_revert_message_is_fixed_and_hides_node_payload(
    client: Web3RegistryClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def reverting(*args: Any, **kwargs: Any) -> int:
        raise ContractLogicError(REVERT_TEXT)

    monkeypatch.setattr(client._w3.eth, "get_transaction_count", reverting)
    with pytest.raises(AnchorFailedError) as info:
        await client.revoke_version(DOC, 1, "x")
    assert info.value.message == "Contract rejected the transaction"
    assert "SECRET_REVERT_PAYLOAD" not in info.value.message
    assert "SECRET_REVERT_PAYLOAD" not in str(info.value.details)
