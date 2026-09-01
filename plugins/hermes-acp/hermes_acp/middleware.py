"""Hermes ``llm_execution`` middleware scoped to the ``acp`` provider."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .client import ACPError, execute
from .completion import make_completion
from .config import resolve_settings
from .prompt import format_prompt

logger = logging.getLogger(__name__)
# Hermes's root logger defaults to WARNING in one-shot mode. Keep this plugin's
# two credential-safe lifecycle records visible without raising global noise.
logger.setLevel(logging.INFO)


def llm_execution_middleware(
    *,
    request: dict[str, Any],
    next_call: Callable[[dict[str, Any]], Any],
    **context: Any,
) -> Any:
    """Intercept ACP requests and transparently pass every other provider."""

    # Hermes v0.21.0 supplies provider identity as execution-middleware
    # context, not inside the provider request body. Keep the request fallback
    # for direct callers and older middleware hosts.
    provider = context.get("provider", request.get("provider"))
    if provider != "acp":
        return next_call(request)

    model = str(request.get("model") or "")
    supplied_config = context.get("config")
    config = supplied_config if isinstance(supplied_config, Mapping) else None
    cwd = request.get("cwd") or context.get("cwd") or context.get("project_root")
    settings = resolve_settings(model, config=config, cwd=cwd)
    messages = request.get("messages") or []
    if not isinstance(messages, (list, tuple)):
        raise TypeError("ACP request messages must be a list or tuple")
    backend = settings.backend.name
    logger.info(
        "Hermes ACP execution started provider=acp backend=%s executable=%s cwd=%s",
        backend,
        Path(settings.backend.command).name,
        settings.cwd,
    )
    try:
        result = execute(settings, format_prompt(messages))
    except ACPError as exc:
        logger.warning(
            "Hermes ACP execution failed provider=acp backend=%s error_type=%s error=%s",
            backend,
            type(exc).__name__,
            exc,
        )
        raise type(exc)(f"Hermes ACP backend {backend!r} failed: {exc}") from exc
    logger.info(
        "Hermes ACP execution completed provider=acp backend=%s stop_reason=%s content_chars=%d",
        backend,
        getattr(result, "stop_reason", "unknown"),
        len(result.content),
    )
    return make_completion(
        model=backend,
        content=result.content,
        reasoning=result.reasoning,
    )
