from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import hermes_acp
from hermes_acp.middleware import llm_execution_middleware


@dataclass
class FakeProfile:
    name: str
    api_mode: str
    base_url: str
    auth_type: str
    env_vars: tuple[str, ...]
    supports_health_check: bool
    fallback_models: tuple[str, ...]


class FakeContext:
    def __init__(self) -> None:
        self.calls = []

    def register_middleware(self, kind, callback) -> None:
        self.calls.append((kind, callback))


def test_registration_profile_and_context_are_idempotent(monkeypatch) -> None:
    registered = []
    providers = ModuleType("providers")
    providers.ProviderProfile = FakeProfile
    providers.register_provider = registered.append
    monkeypatch.setitem(sys.modules, "providers", providers)
    hermes_acp._MIDDLEWARE_REGISTERED = False
    hermes_acp._PROVIDER_REGISTERED = False
    context = FakeContext()

    hermes_acp.register(context)
    hermes_acp.register(context)

    assert len(registered) == 1
    assert registered[-1] == FakeProfile(
        name="acp",
        api_mode="chat_completions",
        base_url="http://127.0.0.1:1/v1",
        auth_type="api_key",
        env_vars=("HERMES_ACP_ENABLED",),
        supports_health_check=False,
        fallback_models=("grok", "codex", "claude", "cursor"),
    )
    assert context.calls == [("llm_execution", llm_execution_middleware)]


def test_register_without_hermes_is_safe(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "providers", None)
    hermes_acp.register()


def test_root_shim_loads_as_a_github_directory_package() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "_hermes_acp_directory_test",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        assert callable(module.register)
    finally:
        sys.modules.pop(spec.name, None)


def test_packaged_entrypoint_stays_general_plugin_classifiable() -> None:
    import hermes_acp.entrypoint as entrypoint

    source = Path(entrypoint.__file__).read_text(encoding="utf-8")
    assert not ("register_provider" in source and "ProviderProfile" in source)
    assert entrypoint.register is hermes_acp.register
