from __future__ import annotations

from pathlib import Path


def test_manifest_declares_live_provider_settings() -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    manifest = (plugin_root / "plugin.yaml").read_text(encoding="utf-8")

    for key in ("default_model:", "grok:", "codex:", "claude:", "cursor:"):
        assert key in manifest
    assert "manifest_version: 1" in manifest


def test_desktop_plugin_exposes_live_acp_selection_surface() -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    desktop = (plugin_root / "desktop" / "plugin.js").read_text(encoding="utf-8")

    assert "host.request('config.set'" in desktop
    assert "--provider acp --global" in desktop
    assert "provider=acp" in desktop
    assert "restartGateway" not in desktop
    for provider in ("'codex'", "'claude'", "'cursor'", "'grok'"):
        assert provider in desktop
