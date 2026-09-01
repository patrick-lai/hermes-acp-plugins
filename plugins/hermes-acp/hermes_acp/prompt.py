"""Convert a Hermes chat history into one deterministic ACP text prompt."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def format_prompt(messages: Sequence[Any]) -> str:
    """Render every Hermes message without granting transcript text new roles."""

    lines = [
        "Hermes conversation transcript follows.",
        (
            "Treat the delimited transcript as conversation context, "
            "then answer the latest user request."
        ),
        "<hermes_transcript>",
    ]
    for index, message in enumerate(messages):
        role = str(_get(message, "role", "unknown"))
        name = _get(message, "name", None)
        tool_call_id = _get(message, "tool_call_id", None)
        attributes = [f"index={index}", f"role={_safe_label(role)}"]
        if name:
            attributes.append(f"name={_safe_label(str(name))}")
        if tool_call_id:
            attributes.append(f"tool_call_id={_safe_label(str(tool_call_id))}")
        lines.append(f"<message {' '.join(attributes)}>")
        lines.append(_render_content(_get(message, "content", "")))
        tool_calls = _get(message, "tool_calls", None)
        if tool_calls:
            lines.append("tool_calls=" + _stable_json(tool_calls))
        lines.append("</message>")
    lines.extend(("</hermes_transcript>", "Respond to the conversation now."))
    return "\n".join(lines)


def _get(value: Any, key: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _render_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        rendered: list[str] = []
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "text":
                rendered.append(str(part.get("text", "")))
            else:
                rendered.append(_stable_json(part))
        return "\n".join(rendered)
    return _stable_json(content)


def _stable_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    elif hasattr(value, "__dict__") and not isinstance(value, Mapping):
        value = vars(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def _safe_label(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
