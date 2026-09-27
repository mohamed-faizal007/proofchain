import asyncio
import sys

import pytest

from app.nlp.llm import explain_with_llm, get_llm_client


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, reply: str | Exception | float) -> None:
        self._reply = reply
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._reply, Exception):
            raise self._reply
        if isinstance(self._reply, float):
            await asyncio.sleep(self._reply)
            return _FakeResponse("too late")
        return _FakeResponse(self._reply)


class _FakeAnthropicClient:
    def __init__(self, reply: str | Exception | float) -> None:
        self.messages = _FakeMessages(reply)


async def test_explain_with_llm_returns_the_model_reply_on_success():
    client = _FakeAnthropicClient("The rent obligation was weakened from a duty to an option.")
    result = await explain_with_llm(
        "The tenant shall pay rent.", "The tenant may pay rent.", ["OBLIGATION_CHANGE"], client, "m"
    )
    assert result == "The rent obligation was weakened from a duty to an option."


async def test_explain_with_llm_returns_none_when_client_is_none():
    result = await explain_with_llm("a", "b", ["MINOR_EDIT"], None, "m")
    assert result is None


async def test_explain_with_llm_returns_none_on_api_error():
    client = _FakeAnthropicClient(RuntimeError("api down"))
    result = await explain_with_llm("a", "b", ["MINOR_EDIT"], client, "m")
    assert result is None


async def test_explain_with_llm_returns_none_on_timeout(monkeypatch):
    import app.nlp.llm as llm_module

    monkeypatch.setattr(llm_module, "TIMEOUT_SECONDS", 0.01)
    client = _FakeAnthropicClient(1.0)  # sleeps 1s, well past the 0.01s timeout
    result = await explain_with_llm("a", "b", ["MINOR_EDIT"], client, "m")
    assert result is None


async def test_explain_with_llm_returns_none_for_blank_reply():
    client = _FakeAnthropicClient("   ")
    result = await explain_with_llm("a", "b", ["MINOR_EDIT"], client, "m")
    assert result is None


async def test_explain_with_llm_sends_only_before_after_and_categories():
    client = _FakeAnthropicClient("ok")
    await explain_with_llm(
        "BEFORE_TEXT", "AFTER_TEXT", ["AMOUNT_CHANGE", "OBLIGATION_CHANGE"], client, "claude-x"
    )
    [call] = client.messages.calls
    assert call["model"] == "claude-x"
    [message] = call["messages"]
    content = message["content"]
    assert "BEFORE_TEXT" in content
    assert "AFTER_TEXT" in content
    assert "AMOUNT_CHANGE" in content
    assert "OBLIGATION_CHANGE" in content
    # the whole request is built from exactly these three inputs, nothing else
    assert set(call.keys()) <= {"model", "max_tokens", "system", "messages"}


def test_get_llm_client_returns_none_when_api_key_is_empty():
    assert get_llm_client("") is None


def test_get_llm_client_returns_none_when_anthropic_is_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    import app.nlp.llm as llm_module

    assert llm_module._load_client("sk-fake-key") is None


def test_get_llm_client_caches_after_first_load(monkeypatch):
    import app.nlp.llm as llm_module

    calls = []

    def _fake_loader(api_key: str):
        calls.append(api_key)
        return "sentinel-client"

    monkeypatch.setattr(llm_module, "_client_load_attempted", False)
    monkeypatch.setattr(llm_module, "_client", None)
    monkeypatch.setattr(llm_module, "_load_client", _fake_loader)
    assert llm_module.get_llm_client("k") == "sentinel-client"
    assert llm_module.get_llm_client("k") == "sentinel-client"
    assert len(calls) == 1


@pytest.mark.nlp
def test_load_client_returns_none_when_anthropic_sdk_raises(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    import app.nlp.llm as llm_module

    def _raise(**kwargs):
        raise RuntimeError("bad key")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _raise)
    assert llm_module._load_client("sk-fake-key") is None


@pytest.mark.nlp
def test_real_anthropic_client_constructs_without_a_network_call():
    import app.nlp.llm as llm_module

    client = llm_module._load_client("sk-fake-not-a-real-key")
    assert client is not None
