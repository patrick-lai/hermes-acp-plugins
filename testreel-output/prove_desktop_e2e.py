"""Drive the live Hermes Desktop backend through its JSON-RPC WebSocket."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import websockets

EXPECTED = "DESKTOP_HERMES_ACP_E2E_OK"
WORKSPACE = Path(__file__).resolve().parents[1]
DESKTOP_LOG = Path.home() / ".hermes" / "logs" / "desktop.log"


def latest_port() -> int:
    matches = re.findall(r"HERMES_BACKEND_READY port=(\d+)", DESKTOP_LOG.read_text())
    if not matches:
        raise RuntimeError(f"no ready Desktop backend in {DESKTOP_LOG}")
    return int(matches[-1])


def session_token(port: int) -> str:
    with urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
        html = response.read().decode("utf-8")
    match = re.search(r"window\.__HERMES_SESSION_TOKEN__=([^;]+);", html)
    if not match:
        raise RuntimeError("Desktop backend did not publish its loopback session token")
    return str(json.loads(match.group(1)))


class Gateway:
    def __init__(self, websocket: websockets.ClientConnection) -> None:
        self.websocket = websocket
        self.next_id = 1
        self.events: list[dict] = []

    async def receive(self) -> dict:
        return json.loads(await self.websocket.recv())

    async def rpc(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        await self.websocket.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
        )
        while True:
            frame = await self.receive()
            if frame.get("id") == request_id:
                if "error" in frame:
                    raise RuntimeError(f"{method} failed: {frame['error']}")
                return frame["result"]
            if frame.get("method") == "event":
                self.events.append(frame["params"])

    async def event(self, event_type: str, session_id: str) -> dict:
        while True:
            for index, event in enumerate(self.events):
                if (
                    event.get("type") == event_type
                    and event.get("session_id") == session_id
                ):
                    return self.events.pop(index)
            frame = await self.receive()
            if frame.get("method") == "event":
                event = frame["params"]
                if (
                    event.get("type") == event_type
                    and event.get("session_id") == session_id
                ):
                    return event
                self.events.append(event)


async def prove(port: int) -> dict:
    token = session_token(port)
    query = urlencode({"token": token})
    url = f"ws://127.0.0.1:{port}/api/ws?{query}"
    origin = f"http://127.0.0.1:{port}"

    async with websockets.connect(url, origin=origin, open_timeout=10) as websocket:
        gateway = Gateway(websocket)
        ready = await gateway.receive()
        if ready.get("params", {}).get("type") != "gateway.ready":
            raise AssertionError(f"expected gateway.ready, got {ready}")

        options = await gateway.rpc("model.options", {"include_unconfigured": True})
        if options.get("provider") != "acp" or options.get("model") != "codex":
            raise AssertionError(
                f"live picker selected {options.get('provider')}/{options.get('model')}"
            )
        acp_row = next(
            (row for row in options.get("providers", []) if row.get("slug") == "acp"),
            None,
        )
        if acp_row is None or "codex" not in {
            str(model).lower() for model in acp_row.get("models", [])
        }:
            raise AssertionError("live picker does not expose Codex under provider ACP")

        created = await gateway.rpc(
            "session.create",
            {
                "cols": 120,
                "cwd": str(WORKSPACE),
                "source": "desktop",
                "model": "codex",
                "provider": "acp",
                "reasoning_effort": "high",
                "close_on_disconnect": True,
                "title": "Hermes ACP E2E proof",
            },
        )
        session_id = created["session_id"]
        info = created["info"]
        if info.get("provider") != "acp" or info.get("model") != "codex":
            raise AssertionError(
                f"session started as {info.get('provider')}/{info.get('model')}"
            )

        await gateway.rpc(
            "prompt.submit",
            {
                "session_id": session_id,
                "text": f"Return exactly {EXPECTED} and nothing else.",
            },
        )
        complete = await asyncio.wait_for(
            gateway.event("message.complete", session_id), timeout=180
        )
        payload = complete["payload"]
        if (
            payload.get("status") != "complete"
            or str(payload.get("text", "")).strip() != EXPECTED
        ):
            raise AssertionError(f"unexpected terminal message: {payload}")

        closed = await gateway.rpc("session.close", {"session_id": session_id})
        if not closed.get("closed"):
            raise AssertionError("proof session did not close cleanly")

        return {
            "result": "passed",
            "transport": "Hermes Desktop /api/ws JSON-RPC",
            "backend_port": port,
            "gateway_ready": True,
            "picker": {
                "provider": options["provider"],
                "model": options["model"],
                "acp_models": acp_row["models"],
            },
            "session": {
                "source": "desktop",
                "provider": info["provider"],
                "model": info["model"],
                "reasoning_effort": "high",
                "closed": True,
            },
            "response": {
                "status": payload["status"],
                "text": payload["text"],
                "usage": payload.get("usage", {}),
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=latest_port())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("desktop-e2e-proof.json"),
    )
    args = parser.parse_args()
    proof = asyncio.run(prove(args.port))
    args.output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(f"DESKTOP_E2E_RESULT={proof['result']}")
    print(
        f"DESKTOP_E2E_PICKER={proof['picker']['provider']}/{proof['picker']['model']}"
    )
    print(f"DESKTOP_E2E_RESPONSE={proof['response']['text']}")
    print(f"DESKTOP_E2E_ARTIFACT={args.output}")


if __name__ == "__main__":
    main()
