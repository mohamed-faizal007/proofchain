"""Optional LLM explanation (docs/06_NLP_SPEC.md Pipeline step 7), behind `NLP_LLM_EXPLANATIONS`.

Sends only one region's before/after text and its already-detected category labels to produce
a one-paragraph plain-English explanation -- never the whole document, the tree, or any
revision/document metadata (06: "Never sends whole documents"). 10s timeout; any failure
(disabled, no API key, package missing, timeout, API error) returns None so the caller keeps
its existing template explanation (06 "must degrade gracefully" rule) -- this module never
raises.
"""

from __future__ import annotations

import asyncio
from typing import Any

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
TIMEOUT_SECONDS = 10.0

_SYSTEM_PROMPT = (
    "You explain a single detected change in a contract clause in one short, plain-English "
    "paragraph for a non-lawyer reader. You are given only the clause text before and after "
    "the change, plus its already-detected change categories. Do not invent facts not present "
    "in the given text. Reply with the explanation paragraph only, no preamble."
)

_client: Any | None = None
_client_load_attempted = False


def _load_client(api_key: str) -> Any | None:
    if not api_key:
        return None
    try:
        import anthropic

        return anthropic.AsyncAnthropic(api_key=api_key)
    except Exception:
        # ImportError (package missing) plus anything the SDK itself might raise on
        # construction (e.g. a malformed key); client setup must never break the pipeline.
        return None


def get_llm_client(api_key: str) -> Any | None:
    """Lazy singleton; None if `NLP_LLM_EXPLANATIONS` has no key or the package is unavailable."""
    global _client, _client_load_attempted
    if not _client_load_attempted:
        _client = _load_client(api_key)
        _client_load_attempted = True
    return _client


def _user_message(before: str, after: str, categories: list[str]) -> str:
    return f"Detected categories: {', '.join(categories)}\n\nBefore:\n{before}\n\nAfter:\n{after}"


async def explain_with_llm(
    before: str,
    after: str,
    categories: list[str],
    client: Any | None,
    model: str,
) -> str | None:
    """The LLM's one-paragraph explanation, or None on any failure/timeout/disabled client
    (the caller keeps its own template explanation). The only request content is `before`,
    `after` and `categories` -- no region id, document id, filename or other metadata.
    """
    if client is None:
        return None
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _user_message(before, after, categories)}],
            ),
            timeout=TIMEOUT_SECONDS,
        )
    except Exception:
        return None
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    return text or None
