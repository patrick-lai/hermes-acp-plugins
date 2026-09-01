"""Hermes ACP plugin registration."""

from __future__ import annotations

import os
from typing import Any

from .config import available_models
from .middleware import llm_execution_middleware

_MIDDLEWARE_REGISTERED = False
_PROVIDER_REGISTERED = False


def register(ctx: Any = None) -> None:
    """Register the provider profile and, when supplied, execution middleware."""

    global _MIDDLEWARE_REGISTERED
    _register_provider_if_available()
    if ctx is None or _MIDDLEWARE_REGISTERED:
        return
    ctx.register_middleware("llm_execution", llm_execution_middleware)
    _MIDDLEWARE_REGISTERED = True


def _register_provider_if_available() -> bool:
    global _PROVIDER_REGISTERED
    if _PROVIDER_REGISTERED:
        return True
    try:
        from providers import ProviderProfile, register_provider
    except ModuleNotFoundError as exc:
        if exc.name == "providers":
            return False
        raise

    # Satisfy Hermes's API-key-shaped early registry without asking the user
    # for a fake credential. This marker stays process-local and middleware
    # prevents the placeholder transport from receiving it.
    os.environ.setdefault("HERMES_ACP_ENABLED", "1")
    register_provider(
        ProviderProfile(
            name="acp",
            api_mode="chat_completions",
            base_url="http://127.0.0.1:1/v1",
            # Hermes v0.21 only adds third-party profiles to its early auth
            # registry when they use the API-key shape. The value is a local
            # routing sentinel; middleware short-circuits before HTTP.
            auth_type="api_key",
            env_vars=("HERMES_ACP_ENABLED",),
            supports_health_check=False,
            fallback_models=available_models(),
        )
    )
    _PROVIDER_REGISTERED = True
    return True


# Provider discovery imports the package entry point before the general plugin
# manager creates a PluginContext. Register the profile at that first import;
# register(ctx) later attaches the execution middleware.
_register_provider_if_available()


__all__ = ["register"]
