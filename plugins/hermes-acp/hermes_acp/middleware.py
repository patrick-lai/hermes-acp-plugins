"""Hermes ``llm_execution`` middleware scoped to the ``acp`` provider."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from .client import execute
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
    messages = request.get("messages") or []
    backend = model.strip().lower() or "default"
    try:
        if not isinstance(messages, (list, tuple)):
            raise TypeError("ACP request messages must be a list or tuple")
        cwd = (
            request.get("cwd")
            or context.get("cwd")
            or context.get("project_root")
            or context.get("working_dir")
            or _cwd_for_task(context.get("task_id"))
        )
        settings = resolve_settings(model, config=config, cwd=cwd)
        backend = settings.backend.name
        logger.info(
            "Hermes ACP execution started provider=acp backend=%s executable=%s cwd=%s",
            backend,
            Path(settings.backend.command).name,
            settings.cwd,
        )
        result = execute(
            settings,
            format_prompt(messages),
            cancel_check=_hermes_cancel_check(),
        )
    except Exception as exc:
        logger.warning(
            "Hermes ACP execution failed provider=acp backend=%s error_type=%s error=%s",
            backend,
            type(exc).__name__,
            _error_summary(exc),
        )
        # Hermes v0.21 treats a middleware exception as permission to continue
        # into the next executor. For this provider that means retrying an inert
        # localhost placeholder and then starting ACP again on Hermes's next
        # provider retry. Return a normal completion instead so the selected
        # ACP route fails once, visibly, and never falls through to HTTP.
        return make_completion(
            model=backend,
            content=_user_failure(backend, exc),
            reasoning="",
        )
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


def _cwd_for_task(task_id: Any) -> str | PathLike[str] | None:
    """Read the Desktop/project cwd Hermes registered for this turn."""

    if not isinstance(task_id, str) or not task_id:
        return None
    try:
        from tools.terminal_tool import resolve_task_overrides
    except ImportError:
        return None
    try:
        value = resolve_task_overrides(task_id).get("cwd")
    except Exception:
        logger.debug("Could not resolve Hermes task cwd", exc_info=True)
        return None
    return value if isinstance(value, (str, PathLike)) else None


def _hermes_cancel_check() -> Callable[[], bool] | None:
    """Use Hermes's thread-scoped stop signal when the host exposes it."""

    try:
        from tools.interrupt import is_thread_interrupted
    except ImportError:
        return None
    origin_thread = threading.current_thread().ident
    return lambda: is_thread_interrupted(origin_thread)


def _user_failure(backend: str, exc: Exception) -> str:
    # ACP stderr can contain noisy or credential-adjacent vendor diagnostics.
    # Keep every surfaced error concise.
    return f"Hermes ACP could not complete the {backend} turn: {_error_summary(exc)}"


def _error_summary(exc: Exception) -> str:
    return str(exc).partition("\nACP stderr:")[0].strip() or type(exc).__name__
