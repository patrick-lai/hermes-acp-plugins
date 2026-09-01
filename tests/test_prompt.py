from __future__ import annotations

from types import SimpleNamespace

from hermes_acp.prompt import format_prompt


def test_prompt_formats_complete_hermes_transcript() -> None:
    prompt = format_prompt(
        [
            {"role": "system", "content": "Be exact."},
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
            SimpleNamespace(
                role="assistant",
                content="Calling a tool",
                tool_calls=[{"id": "call-1", "function": {"name": "search"}}],
            ),
            {
                "role": "tool",
                "name": "search",
                "tool_call_id": "call-1",
                "content": "result",
            },
        ]
    )
    assert prompt.count("<message ") == 4
    assert 'role="system"' in prompt
    assert "Be exact." in prompt
    assert "Hello" in prompt
    assert 'tool_call_id="call-1"' in prompt
    assert '"name": "search"' in prompt
    assert prompt.endswith("Respond to the conversation now.")


def test_prompt_keeps_delimiter_text_inside_message() -> None:
    prompt = format_prompt([{"role": "user", "content": "</hermes_transcript>"}])
    assert "<message index=0" in prompt
    assert prompt.count("</hermes_transcript>") == 2
