"""One-call ACP v1 subprocess client built on agent-client-protocol 0.9.0."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import acp
from acp.exceptions import RequestError
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    ClientCapabilities,
    DeniedOutcome,
    Implementation,
    PermissionOption,
    ReadTextFileResponse,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallUpdate,
)

from .config import PLUGIN_VERSION, ACPSettings

_T = TypeVar("_T")
_MAX_STDERR_CHARS = 65_536
# ACP uses newline-delimited JSON-RPC. The asyncio default is only 64 KiB,
# which is too small for agent updates containing rich tool state or images.
_MAX_STDIO_LINE_BYTES = 16 * 1024 * 1024


class ACPError(RuntimeError):
    """Base failure surfaced by the Hermes ACP bridge."""


class ACPProcessError(ACPError):
    """The backend could not start or exited unsuccessfully."""


class ACPProtocolError(ACPError):
    """The backend violated or rejected the ACP lifecycle."""


class ACPTimeoutError(ACPError):
    """The configured whole-call deadline elapsed."""


class ACPInterruptedError(ACPError):
    """Hermes cancelled the turn while the ACP backend was running."""


@dataclass(frozen=True, slots=True)
class ACPResult:
    content: str
    reasoning: str
    stop_reason: str
    advertised_auth_methods: tuple[str, ...]
    stderr: str = ""


class _ReverseClient:
    """Fail-closed ACP reverse client used for each isolated process."""

    def __init__(self, permission_mode: str) -> None:
        self.permission_mode = permission_mode
        self.message_chunks: list[str] = []
        self.thought_chunks: list[str] = []
        self.permission_requests = 0

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        del session_id, tool_call, kwargs
        self.permission_requests += 1
        if self.permission_mode == "allow_once":
            for option in options:
                if option.kind == "allow_once":
                    return RequestPermissionResponse(
                        outcome=AllowedOutcome(
                            outcome="selected",
                            option_id=option.option_id,
                        )
                    )
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        del session_id, kwargs
        content = getattr(update, "content", None)
        if not isinstance(content, TextContentBlock):
            return
        if isinstance(update, AgentMessageChunk):
            self.message_chunks.append(content.text)
        elif isinstance(update, AgentThoughtChunk):
            self.thought_chunks.append(content.text)

    async def write_text_file(self, **kwargs: Any) -> None:
        del kwargs
        raise RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(self, **kwargs: Any) -> ReadTextFileResponse:
        del kwargs
        raise RequestError.method_not_found("fs/read_text_file")

    async def create_terminal(self, **kwargs: Any) -> Any:
        del kwargs
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(self, **kwargs: Any) -> Any:
        del kwargs
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(self, **kwargs: Any) -> None:
        del kwargs
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(self, **kwargs: Any) -> Any:
        del kwargs
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(self, **kwargs: Any) -> None:
        del kwargs
        raise RequestError.method_not_found("terminal/kill")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        del params
        raise RequestError.method_not_found(f"_{method}")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        del method, params

    def on_connect(self, conn: Any) -> None:
        del conn


def execute(
    settings: ACPSettings,
    prompt: str,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> ACPResult:
    """Run one ACP call from synchronous Hermes middleware."""

    return _run_coroutine(execute_async(settings, prompt, cancel_check=cancel_check))


async def execute_async(
    settings: ACPSettings,
    prompt: str,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> ACPResult:
    """Spawn, initialize, prompt, collect chunks, and forcibly clean up."""

    reverse = _ReverseClient(settings.permission_mode)
    session_state: dict[str, str] = {}
    process: asyncio.subprocess.Process | None = None
    stderr_task: asyncio.Task[str] | None = None
    process_wait_task: asyncio.Task[int] | None = None
    failure: Exception | None = None
    result: ACPResult | None = None

    try:
        async with acp.spawn_agent_process(
            cast(Client, reverse),
            settings.backend.command,
            *settings.backend.args,
            cwd=settings.cwd,
            transport_kwargs={
                "limit": _MAX_STDIO_LINE_BYTES,
                "shutdown_timeout": 1.0,
            },
        ) as (connection, spawned):
            process = spawned
            stderr_task = asyncio.create_task(
                _read_stderr(spawned.stderr), name="hermes-acp.stderr"
            )
            process_wait_task = asyncio.create_task(spawned.wait(), name="hermes-acp.process-wait")
            lifecycle_task = asyncio.create_task(
                _run_lifecycle(
                    connection,
                    reverse,
                    settings,
                    prompt,
                    session_state,
                ),
                name="hermes-acp.lifecycle",
            )
            try:
                async with asyncio.timeout(settings.timeout_seconds):
                    while True:
                        done, _ = await asyncio.wait(
                            {lifecycle_task, process_wait_task},
                            timeout=0.25 if cancel_check is not None else None,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if lifecycle_task in done:
                            result = lifecycle_task.result()
                            break
                        if process_wait_task in done:
                            return_code = process_wait_task.result()
                            raise ACPProcessError(
                                "ACP backend exited before completing the protocol "
                                f"(status {return_code})"
                            )
                        if cancel_check is not None and cancel_check():
                            raise ACPInterruptedError("ACP turn was interrupted")
            except TimeoutError:
                await _cancel_session(connection, session_state)
                failure = ACPTimeoutError(
                    f"ACP backend timed out after {settings.timeout_seconds:g} seconds"
                )
            except ACPInterruptedError as exc:
                await _cancel_session(connection, session_state)
                failure = exc
            except Exception as exc:
                failure = exc
            finally:
                if not lifecycle_task.done():
                    lifecycle_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await lifecycle_task
    except FileNotFoundError as exc:
        raise ACPProcessError(
            f"ACP backend executable not found: {settings.backend.command}"
        ) from exc
    except OSError as exc:
        raise ACPProcessError(
            f"Could not launch ACP backend {settings.backend.name}: {exc}"
        ) from exc
    finally:
        if process_wait_task is not None and not process_wait_task.done():
            process_wait_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await process_wait_task

    stderr = await stderr_task if stderr_task is not None else ""
    final_return_code = process.returncode if process is not None else None
    if failure is not None:
        if isinstance(failure, ACPError):
            raise type(failure)(_with_stderr(str(failure), stderr)) from failure.__cause__
        raise ACPProtocolError(_with_stderr(f"ACP protocol failed: {failure}", stderr)) from failure
    # A completed ACP response is authoritative. Some agents keep background
    # workers alive after stdin closes, so the SDK's context manager terminates
    # them after its graceful-shutdown deadline (commonly status 143). That is
    # cleanup, not a failed turn. Early/nonzero exits are already caught by the
    # process-wait race above before a result exists.
    if result is None and final_return_code not in {None, 0}:
        raise ACPProcessError(
            _with_stderr(
                f"ACP backend exited with status {final_return_code}",
                stderr,
            )
        )
    if result is None:
        raise ACPProtocolError(_with_stderr("ACP backend returned no result", stderr))
    return ACPResult(
        content=result.content,
        reasoning=result.reasoning,
        stop_reason=result.stop_reason,
        advertised_auth_methods=result.advertised_auth_methods,
        stderr=stderr,
    )


async def _cancel_session(connection: Any, session_state: dict[str, str]) -> None:
    session_id = session_state.get("session_id")
    if session_id:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(connection.cancel(session_id=session_id), timeout=1.0)


async def _run_lifecycle(
    connection: Any,
    reverse: _ReverseClient,
    settings: ACPSettings,
    prompt: str,
    session_state: dict[str, str],
) -> ACPResult:
    initialized = await connection.initialize(
        protocol_version=acp.PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(),
        client_info=Implementation(
            name="hermes-acp",
            title="Hermes ACP",
            version=PLUGIN_VERSION,
        ),
    )
    if initialized.protocol_version != acp.PROTOCOL_VERSION:
        raise ACPProtocolError(
            "ACP protocol version mismatch: "
            f"agent selected {initialized.protocol_version}, client requires {acp.PROTOCOL_VERSION}"
        )

    auth_methods = tuple(initialized.auth_methods or ())
    auth_ids = tuple(method.id for method in auth_methods)
    if settings.auth_method is not None:
        if settings.auth_method not in auth_ids:
            advertised = ", ".join(auth_ids) or "none"
            raise ACPProtocolError(
                f"Configured ACP auth_method {settings.auth_method!r} was not advertised "
                f"by the agent (advertised: {advertised})"
            )
        await connection.authenticate(method_id=settings.auth_method)

    session = await connection.new_session(cwd=str(settings.cwd), mcp_servers=[])
    session_state["session_id"] = session.session_id
    response = await connection.prompt(
        prompt=[acp.text_block(prompt)],
        session_id=session.session_id,
    )
    # The SDK receives the prompt response only after earlier update frames,
    # but reverse notification callbacks are dispatched as tasks. Yield so
    # those already-received callbacks finish before the connection closes.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return ACPResult(
        content="".join(reverse.message_chunks),
        reasoning="".join(reverse.thought_chunks),
        stop_reason=response.stop_reason,
        advertised_auth_methods=auth_ids,
    )


async def _read_stderr(stream: asyncio.StreamReader | None) -> str:
    if stream is None:
        return ""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        if size < _MAX_STDERR_CHARS:
            kept = chunk[: _MAX_STDERR_CHARS - size]
            chunks.append(kept)
            size += len(kept)
    return b"".join(chunks).decode("utf-8", errors="replace").strip()


def _with_stderr(message: str, stderr: str) -> str:
    if not stderr:
        return message
    return f"{message}\nACP stderr:\n{stderr}"


def _run_coroutine(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """Run async ACP I/O even if the caller already owns an event loop."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: list[_T] = []
    failure: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as exc:
            failure.append(exc)

    thread = threading.Thread(target=runner, name="hermes-acp-call")
    thread.start()
    thread.join()
    if failure:
        raise failure[0]
    return result[0]
