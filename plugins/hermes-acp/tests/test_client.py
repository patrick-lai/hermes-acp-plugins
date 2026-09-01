from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import read_events

from hermes_acp.client import (
    ACPInterruptedError,
    ACPProcessError,
    ACPProtocolError,
    ACPTimeoutError,
    execute,
)


def test_lifecycle_framing_message_and_thought_updates(fake_settings) -> None:
    settings, events_path = fake_settings(stderr=True)
    result = execute(settings, "single ACP prompt")

    assert result.content == "Hello from ACP."
    assert result.reasoning == "First thought. Second thought."
    assert result.stop_reason == "end_turn"
    assert result.stderr == "deterministic diagnostic"
    events = read_events(events_path)
    assert [event["event"] for event in events[:3]] == [
        "initialize",
        "new_session",
        "prompt",
    ]
    assert events[0]["protocol_version"] == 1
    assert Path(events[1]["cwd"]).is_absolute()
    assert events[1]["mcp_servers"] == []
    assert events[2]["prompt"] == "single ACP prompt"
    assert events[-1]["event"] == "shutdown"


def test_success_survives_forced_post_response_cleanup(fake_settings) -> None:
    settings, _ = fake_settings(mode="stubborn_shutdown")
    result = execute(settings, "complete before cleanup")

    assert result.content == "Hello from ACP."
    assert result.stop_reason == "end_turn"


def test_large_acp_json_frame_exceeding_asyncio_default_is_supported(fake_settings) -> None:
    settings, _ = fake_settings(mode="large_frame")
    result = execute(settings, "return a large frame")

    assert len(result.content) == 131_072
    assert set(result.content) == {"L"}
    assert result.stop_reason == "end_turn"


def test_permission_reject_is_default(fake_settings) -> None:
    settings, events_path = fake_settings(mode="permission")
    execute(settings, "permission please")
    permission = next(
        event for event in read_events(events_path) if event["event"] == "permission_result"
    )
    assert permission["outcome"] == "cancelled"
    assert permission["option_id"] is None


def test_explicit_allow_once_selects_only_allow_once(fake_settings) -> None:
    settings, events_path = fake_settings(mode="permission_allow", permission_mode="allow_once")
    execute(settings, "permission please")
    permission = next(
        event for event in read_events(events_path) if event["event"] == "permission_result"
    )
    assert permission == {
        "event": "permission_result",
        "option_id": "yes-once",
        "outcome": "selected",
    }


def test_timeout_sends_cancel_and_cleans_up(fake_settings) -> None:
    # Leave enough time for the isolated Python subprocess to initialize and
    # create its ACP session before expiring the deliberately hung prompt.
    settings, events_path = fake_settings(mode="hang", timeout_seconds=2)
    with pytest.raises(ACPTimeoutError, match="timed out"):
        execute(settings, "never completes")
    assert "cancel" in [event["event"] for event in read_events(events_path)]


def test_interrupt_sends_cancel_and_cleans_up(fake_settings) -> None:
    settings, events_path = fake_settings(mode="hang", timeout_seconds=5)
    checks = 0

    def interrupted() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(ACPInterruptedError, match="interrupted"):
        execute(settings, "stop this turn", cancel_check=interrupted)
    assert "cancel" in [event["event"] for event in read_events(events_path)]


@pytest.mark.parametrize("mode", ["malformed", "nonzero"])
def test_malformed_and_nonzero_processes_fail(mode: str, fake_settings) -> None:
    settings, _ = fake_settings(mode=mode)
    with pytest.raises(ACPProcessError):
        execute(settings, "fail")


def test_rpc_error_includes_protocol_failure(fake_settings) -> None:
    settings, _ = fake_settings(mode="error")
    # ACP deliberately redacts arbitrary server exceptions to a JSON-RPC
    # internal error; the bridge must still classify it as a protocol failure.
    with pytest.raises(ACPProtocolError, match="ACP protocol failed: Internal error"):
        execute(settings, "fail")


def test_unknown_extension_is_rejected_without_breaking_turn(fake_settings) -> None:
    settings, events_path = fake_settings(mode="extension")
    result = execute(settings, "extension")
    assert result.content == "Hello from ACP."
    assert "extension_rejected" in [event["event"] for event in read_events(events_path)]


def test_authentication_uses_only_explicit_advertised_method(fake_settings) -> None:
    settings, events_path = fake_settings(mode="auth", auth_method="fake-login")
    result = execute(settings, "authenticated")
    assert result.advertised_auth_methods == ("fake-login",)
    assert "authenticate" in [event["event"] for event in read_events(events_path)]


def test_advertised_auth_is_inspected_without_guessing(fake_settings) -> None:
    settings, events_path = fake_settings(mode="auth")
    result = execute(settings, "already authenticated")
    assert result.advertised_auth_methods == ("fake-login",)
    assert "authenticate" not in [event["event"] for event in read_events(events_path)]


def test_unadvertised_auth_method_fails_without_guessing(fake_settings) -> None:
    settings, _ = fake_settings(mode="auth", auth_method="different-login")
    with pytest.raises(ACPProtocolError, match="was not advertised"):
        execute(settings, "authenticated")


def test_missing_executable_is_reported(tmp_path: Path) -> None:
    from hermes_acp.config import ACPSettings, BackendSpec

    settings = ACPSettings(
        backend=BackendSpec("grok", str(tmp_path / "missing"), ()),
        permission_mode="reject",
        timeout_seconds=1,
        cwd=Path(os.getcwd()).resolve(),
    )
    with pytest.raises(ACPProcessError, match="executable not found"):
        execute(settings, "fail")
