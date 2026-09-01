"""Hermes ``llm_execution`` middleware scoped to the ``acp`` provider."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .client import execute
from .completion import make_completion
from .config import resolve_settings
from .prompt import format_prompt


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
    result = execute(settings, format_prompt(messages))
    return make_completion(
        model=model,
        content=result.content,
        reasoning=result.reasoning,
    )
