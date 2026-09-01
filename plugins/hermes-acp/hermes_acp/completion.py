"""OpenAI-compatible completion conversion for Hermes."""

from __future__ import annotations

from types import SimpleNamespace


def make_completion(*, model: str, content: str, reasoning: str) -> SimpleNamespace:
    """Build the attribute-based Chat Completions shape Hermes consumes."""

    message = SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=None,
        reasoning=reasoning or None,
        reasoning_content=reasoning or None,
    )
    choice = SimpleNamespace(
        index=0,
        message=message,
        finish_reason="stop",
        logprobs=None,
    )
    usage = SimpleNamespace(
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )
    return SimpleNamespace(
        id="chatcmpl-hermes-acp",
        object="chat.completion",
        created=0,
        model=model,
        provider="acp",
        acp_backend=model,
        choices=[choice],
        usage=usage,
        reasoning=reasoning or None,
    )
