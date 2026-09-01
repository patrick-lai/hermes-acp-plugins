from __future__ import annotations

from types import SimpleNamespace

import hermes_acp.middleware as middleware


def test_non_acp_provider_calls_next_exactly_once() -> None:
    calls = []
    request = {"model": "some-model", "messages": []}

    def next_call(received):
        calls.append(received)
        return "downstream"

    assert (
        middleware.llm_execution_middleware(
            request=request, next_call=next_call, provider="openrouter"
        )
        == "downstream"
    )
    assert calls == [request]


def test_acp_provider_is_intercepted_without_calling_next(monkeypatch, tmp_path) -> None:
    calls = []
    captured = {}

    def fake_execute(settings, prompt):
        captured["settings"] = settings
        captured["prompt"] = prompt
        return SimpleNamespace(content="answer", reasoning="thought")

    monkeypatch.setattr(middleware, "execute", fake_execute)
    request = {
        "model": "codex",
        "messages": [{"role": "user", "content": "build it"}],
        "cwd": str(tmp_path),
    }
    completion = middleware.llm_execution_middleware(
        request=request,
        next_call=lambda received: calls.append(received),
        provider="acp",
        config={},
    )

    assert calls == []
    assert captured["settings"].backend.command == "npx"
    assert "build it" in captured["prompt"]
    assert completion.choices[0].message.content == "answer"
    assert completion.choices[0].message.tool_calls is None
    assert completion.choices[0].finish_reason == "stop"


def test_acp_provider_resolves_the_live_default_model_when_request_is_blank(
    monkeypatch, tmp_path
) -> None:
    captured = {}

    def fake_execute(settings, prompt):
        captured["settings"] = settings
        captured["prompt"] = prompt
        return SimpleNamespace(content="answer", reasoning="")

    monkeypatch.setattr(middleware, "execute", fake_execute)
    request = {
        "messages": [{"role": "user", "content": "use the chosen default"}],
        "cwd": str(tmp_path),
    }
    config = {"plugins": {"entries": {"hermes-acp": {"settings": {"default_model": "claude"}}}}}

    completion = middleware.llm_execution_middleware(
        request=request,
        next_call=lambda received: (_ for _ in ()).throw(AssertionError(received)),
        provider="acp",
        config=config,
    )

    assert captured["settings"].backend.name == "claude"
    assert completion.model == ""
