from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from hermes_acp.config import ACPSettings, resolve_settings

FAKE_AGENT = Path(__file__).with_name("fake_agent.py").resolve()


@pytest.fixture
def fake_settings(tmp_path: Path):
    def factory(
        *,
        mode: str = "normal",
        permission_mode: str = "reject",
        timeout_seconds: float = 3,
        stderr: bool = False,
        auth_method: str | None = None,
    ) -> tuple[ACPSettings, Path]:
        events = tmp_path / f"{mode}-{permission_mode}.jsonl"
        args = [str(FAKE_AGENT), "--mode", mode, "--events", str(events)]
        if stderr:
            args.append("--stderr")
        values: dict[str, Any] = {
            "permission_mode": permission_mode,
            "timeout_seconds": timeout_seconds,
            "cwd": str(tmp_path),
            "grok": {"command": sys.executable, "args": args},
        }
        if auth_method is not None:
            values["auth_method"] = auth_method
        config = {
            "plugins": {
                "entries": {
                    "hermes-acp": {
                        "settings": values,
                    }
                }
            }
        }
        return resolve_settings("grok", config=config), events

    return factory


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
