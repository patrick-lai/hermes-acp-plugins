"""Hermes configuration and ACP backend resolution."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class BackendSpec:
    """An exact executable and argument vector for one ACP backend."""

    name: str
    command: str
    args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ACPSettings:
    """Resolved settings for one intercepted Hermes provider call."""

    backend: BackendSpec
    permission_mode: str
    timeout_seconds: float
    cwd: Path
    auth_method: str | None = None


_DEFAULT_BACKENDS = {
    "grok": BackendSpec("grok", "grok", ("agent", "stdio")),
    "codex": BackendSpec(
        "codex",
        "npx",
        ("-y", "@agentclientprotocol/codex-acp@1.7.0"),
    ),
    "claude": BackendSpec(
        "claude",
        "npx",
        ("-y", "@agentclientprotocol/claude-agent-acp"),
    ),
    "cursor": BackendSpec("cursor", "cursor-agent", ("agent", "acp")),
}

ACP_MODELS = tuple(_DEFAULT_BACKENDS)


def load_hermes_config() -> Mapping[str, Any]:
    """Load the normal Hermes config without introducing an alternate channel."""

    try:
        from hermes_cli.config import load_config_readonly
    except ImportError:
        try:
            from hermes_cli.config import load_config as load_config_readonly
        except ImportError:
            return {}
    loaded = load_config_readonly() or {}
    return loaded if isinstance(loaded, Mapping) else {}


def plugin_settings(config: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Return settings below ``plugins.entries.hermes-acp``.

    Hermes v0.21 stores plugin-owned values in ``settings``. The earlier
    ``config`` child and direct entry values are read as migration fallbacks.
    """

    root = config if config is not None else load_hermes_config()
    plugins = root.get("plugins") if isinstance(root, Mapping) else None
    entries = plugins.get("entries") if isinstance(plugins, Mapping) else None
    entry = entries.get("hermes-acp") if isinstance(entries, Mapping) else None
    if not isinstance(entry, Mapping):
        return {}

    merged: dict[str, Any] = {
        key: value for key, value in entry.items() if key not in {"settings", "config"}
    }
    legacy = entry.get("config")
    if isinstance(legacy, Mapping):
        merged.update(legacy)
    canonical = entry.get("settings")
    if isinstance(canonical, Mapping):
        merged.update(canonical)
    return merged


def backend_for_model(
    model: str,
    settings: Mapping[str, Any] | None = None,
) -> BackendSpec:
    """Resolve a live ACP model selection and apply its command override.

    Hermes's own model picker sends an explicit model for a session or bot.
    An empty, ``auto``, or ``default`` model instead resolves this plugin's
    current ``default_model`` setting, which lets the Desktop ACP page change
    the profile default without restarting or reinstalling the plugin.
    """

    values = settings or {}
    backend_name = _selected_model(model, values)
    if backend_name not in _DEFAULT_BACKENDS:
        choices = ", ".join(repr(name) for name in ACP_MODELS)
        raise ValueError(f"Unsupported ACP model {model!r}; choose one of {choices}")
    default = _DEFAULT_BACKENDS[backend_name]
    raw = values.get(backend_name)
    flat_command = values.get(f"{backend_name}_command")
    flat_args = values.get(f"{backend_name}_args")
    if raw is None and flat_command is None and flat_args is None:
        return default
    if raw is not None and not isinstance(raw, Mapping):
        raise ValueError(f"hermes-acp setting {backend_name!r} must be a mapping")

    backend_values = raw or {}
    command_value = backend_values.get(
        "command", flat_command if flat_command is not None else default.command
    )
    args_value = backend_values.get("args", flat_args if flat_args is not None else default.args)
    if isinstance(command_value, str):
        command = command_value.strip()
    else:
        raise ValueError(f"{backend_name}.command must be a string")
    if not command:
        raise ValueError(f"{backend_name}.command must not be empty")
    args = _string_tuple(args_value, f"{backend_name}.args")
    return BackendSpec(backend_name, command, args)


def available_models() -> tuple[str, ...]:
    """Return the stable model identifiers exposed to Hermes's model picker."""

    return ACP_MODELS


def resolve_settings(
    model: str,
    *,
    config: Mapping[str, Any] | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> ACPSettings:
    """Resolve backend, security mode, timeout, and absolute session cwd."""

    settings = plugin_settings(config)
    permission = str(settings.get("permission_mode", "reject")).strip().lower()
    if permission in {"reject", "cancel"}:
        permission = "reject"
    elif permission != "allow_once":
        raise ValueError("hermes-acp permission_mode must be 'reject' or explicit 'allow_once'")

    timeout_raw = settings.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout_raw, bool):
        raise ValueError("hermes-acp timeout_seconds must be a positive number")
    try:
        timeout_seconds = float(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("hermes-acp timeout_seconds must be a positive number") from exc
    if timeout_seconds <= 0:
        raise ValueError("hermes-acp timeout_seconds must be a positive number")

    configured_cwd = settings.get("cwd")
    if configured_cwd is not None and not isinstance(configured_cwd, (str, os.PathLike)):
        raise ValueError("hermes-acp cwd must be a path string")
    cwd_value = configured_cwd if configured_cwd not in (None, "") else cwd
    resolved_cwd = Path(cwd_value or os.getcwd()).expanduser().resolve()
    if not resolved_cwd.is_absolute():  # Defensive: resolve() should guarantee it.
        raise ValueError("hermes-acp cwd must resolve to an absolute path")

    auth_value = settings.get("auth_method")
    auth_method = None
    if auth_value is not None:
        if not isinstance(auth_value, str) or not auth_value.strip():
            raise ValueError("hermes-acp auth_method must be a non-empty string")
        auth_method = auth_value.strip()

    return ACPSettings(
        backend=backend_for_model(model, settings),
        permission_mode=permission,
        timeout_seconds=timeout_seconds,
        cwd=resolved_cwd,
        auth_method=auth_method,
    )


def command_argv(spec: BackendSpec) -> tuple[str, ...]:
    """Return the full launch vector, useful for diagnostics and tests."""

    return (spec.command, *spec.args)


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, str):
        parsed = tuple(shlex.split(value))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if any(not isinstance(item, str) for item in value):
            raise ValueError(f"{label} must contain only strings")
        parsed = tuple(value)
    else:
        raise ValueError(f"{label} must be a string or list of strings")
    if any(not item for item in parsed):
        raise ValueError(f"{label} must not contain empty arguments")
    return parsed


def _selected_model(model: str, settings: Mapping[str, Any]) -> str:
    requested = model.strip().lower()
    if requested not in {"", "auto", "default"}:
        return requested

    configured = settings.get("default_model", "codex")
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError("hermes-acp default_model must be a non-empty ACP model name")
    return configured.strip().lower()
