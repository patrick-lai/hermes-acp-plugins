from __future__ import annotations

from pathlib import Path

import pytest

from hermes_acp.config import (
    available_models,
    backend_for_model,
    command_argv,
    plugin_settings,
    resolve_settings,
)


def test_exact_launch_specs_for_every_selectable_acp_model() -> None:
    assert command_argv(backend_for_model("grok")) == ("grok", "agent", "stdio")
    assert command_argv(backend_for_model("codex")) == (
        "npx",
        "-y",
        "@agentclientprotocol/codex-acp@1.7.0",
    )
    assert command_argv(backend_for_model("claude")) == (
        "npx",
        "-y",
        "@agentclientprotocol/claude-agent-acp",
    )
    assert command_argv(backend_for_model("cursor")) == ("cursor-agent", "agent", "acp")
    assert available_models() == ("grok", "codex", "claude", "cursor")


def test_blank_model_uses_the_current_plugin_default(tmp_path: Path) -> None:
    config = {
        "plugins": {
            "entries": {
                "hermes-acp": {"settings": {"default_model": "cursor", "cwd": str(tmp_path)}}
            }
        }
    }

    settings = resolve_settings("", config=config)

    assert settings.backend.name == "cursor"
    assert command_argv(settings.backend) == ("cursor-agent", "agent", "acp")


def test_backend_override_and_canonical_settings(tmp_path: Path) -> None:
    config = {
        "plugins": {
            "entries": {
                "hermes-acp": {
                    "permission_mode": "reject",
                    "settings": {
                        "permission_mode": "allow_once",
                        "timeout_seconds": 12,
                        "cwd": str(tmp_path),
                        "codex": {"command": "/bin/example", "args": "--stdio --fixed"},
                    },
                }
            }
        }
    }
    assert plugin_settings(config)["permission_mode"] == "allow_once"
    settings = resolve_settings("codex", config=config)
    assert command_argv(settings.backend) == ("/bin/example", "--stdio", "--fixed")
    assert settings.permission_mode == "allow_once"
    assert settings.timeout_seconds == 12
    assert settings.cwd == tmp_path.resolve()


def test_flat_backend_override_is_supported(tmp_path: Path) -> None:
    config = {
        "plugins": {
            "entries": {
                "hermes-acp": {
                    "settings": {
                        "grok_command": "/bin/grok-test",
                        "grok_args": ["serve", "stdio"],
                        "cwd": str(tmp_path),
                    }
                }
            }
        }
    }
    settings = resolve_settings("grok", config=config)
    assert command_argv(settings.backend) == ("/bin/grok-test", "serve", "stdio")
    assert settings.permission_mode == "reject"


@pytest.mark.parametrize("model", ["Grok latest", "aider"])
def test_unsupported_models_are_rejected(model: str) -> None:
    with pytest.raises(ValueError, match="choose one"):
        backend_for_model(model)


def test_invalid_default_model_is_rejected(tmp_path: Path) -> None:
    config = {
        "plugins": {
            "entries": {
                "hermes-acp": {"settings": {"default_model": "not-an-agent", "cwd": str(tmp_path)}}
            }
        }
    }

    with pytest.raises(ValueError, match="Unsupported ACP model"):
        resolve_settings("auto", config=config)


def test_permission_mode_is_fail_closed(tmp_path: Path) -> None:
    config = {
        "plugins": {
            "entries": {
                "hermes-acp": {
                    "settings": {"permission_mode": "allow_always", "cwd": str(tmp_path)}
                }
            }
        }
    }
    with pytest.raises(ValueError, match="allow_once"):
        resolve_settings("grok", config=config)
