"""Deterministic ACP subprocess used by the hermes-acp test suite."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import acp
from acp.schema import (
    AgentCapabilities,
    AuthenticateResponse,
    AuthMethodAgent,
    Implementation,
    InitializeResponse,
    NewSessionResponse,
    PermissionOption,
    PromptResponse,
    ToolCallUpdate,
)


class FakeAgent:
    def __init__(self, mode: str, events: Path | None) -> None:
        self.mode = mode
        self.events = events
        self.connection: Any = None
        self.cancelled = asyncio.Event()

    def on_connect(self, connection: Any) -> None:
        self.connection = connection

    async def initialize(self, protocol_version: int, **kwargs: Any) -> InitializeResponse:
        self._record("initialize", protocol_version=protocol_version, kwargs=kwargs)
        auth_methods = (
            [AuthMethodAgent(id="fake-login", name="Fake login")] if self.mode == "auth" else []
        )
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_capabilities=AgentCapabilities(),
            agent_info=Implementation(name="fake-acp", version="1.0.0"),
            auth_methods=auth_methods,
        )

    async def authenticate(self, method_id: str, **kwargs: Any) -> AuthenticateResponse:
        self._record("authenticate", method_id=method_id, kwargs=kwargs)
        return AuthenticateResponse()

    async def new_session(
        self, cwd: str, mcp_servers: list[Any], **kwargs: Any
    ) -> NewSessionResponse:
        self._record("new_session", cwd=cwd, mcp_servers=mcp_servers, kwargs=kwargs)
        return NewSessionResponse(session_id="fake-session")

    async def prompt(self, prompt: list[Any], session_id: str, **kwargs: Any) -> PromptResponse:
        text = prompt[0].text
        self._record("prompt", prompt=text, session_id=session_id, kwargs=kwargs)
        if self.mode == "error":
            raise RuntimeError("deterministic prompt failure")
        if self.mode == "hang":
            await self.cancelled.wait()
            return PromptResponse(stop_reason="cancelled")
        if self.mode in {"permission", "permission_allow"}:
            response = await self.connection.request_permission(
                session_id=session_id,
                tool_call=ToolCallUpdate(tool_call_id="tool-1", title="Fake write"),
                options=[
                    PermissionOption(
                        option_id="yes-once",
                        name="Allow once",
                        kind="allow_once",
                    ),
                    PermissionOption(
                        option_id="no-once",
                        name="Reject once",
                        kind="reject_once",
                    ),
                ],
            )
            outcome = response.outcome
            self._record(
                "permission_result",
                outcome=outcome.outcome,
                option_id=getattr(outcome, "option_id", None),
            )
        if self.mode == "extension":
            try:
                await self.connection.ext_method("unknown", {"value": 1})
            except Exception as exc:
                self._record("extension_rejected", error=str(exc))

        await self.connection.session_update(
            session_id=session_id,
            update=acp.update_agent_thought_text("First thought. "),
        )
        await self.connection.session_update(
            session_id=session_id,
            update=acp.update_agent_thought_text("Second thought."),
        )
        await self.connection.session_update(
            session_id=session_id,
            update=acp.update_agent_message_text("Hello "),
        )
        if self.mode == "large_frame":
            await self.connection.session_update(
                session_id=session_id,
                update=acp.update_agent_message_text("x" * 131_072),
            )
        await self.connection.session_update(
            session_id=session_id,
            update=acp.update_agent_message_text("from ACP."),
        )
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        self._record("cancel", session_id=session_id, kwargs=kwargs)
        self.cancelled.set()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._record("extension", method=method, params=params)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        self._record("extension_notification", method=method, params=params)

    def _record(self, event: str, **payload: Any) -> None:
        if self.events is None:
            return
        record = {"event": event, **_json_safe(payload)}
        with self.events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
        try:
            json.dumps(value)
        except TypeError:
            value = str(value)
        safe[key] = value
    return safe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--events", type=Path)
    parser.add_argument("--stderr", action="store_true")
    args = parser.parse_args()

    if args.stderr:
        print("deterministic diagnostic", file=sys.stderr, flush=True)
    if args.mode == "malformed":
        print("this is not json", flush=True)
        return
    if args.mode == "nonzero":
        print("deterministic nonzero failure", file=sys.stderr, flush=True)
        raise SystemExit(7)

    agent = FakeAgent(args.mode, args.events)
    asyncio.run(acp.run_agent(agent))
    if args.mode == "stubborn_shutdown":
        time.sleep(10)
    agent._record("shutdown")


if __name__ == "__main__":
    main()
