from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import router  # noqa: E402
from providers.base import get_provider_endpoint, load_daplug_config, _parse_block  # noqa: E402
from providers.lmstudio import LMStudioProvider  # noqa: E402
from providers.ollama import OllamaProvider  # noqa: E402
from providers.vllm import VLLMProvider  # noqa: E402


class _FakeCache:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


def test_resolve_model_returns_installed_cli(monkeypatch):
    fake = _FakeCache(
        {
            "clis": {
                "codex": {"installed": True, "issues": []},
                "opencode": {"installed": False, "issues": []},
            },
            "providers": {},
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    cli, model_id, cmd = router.resolve_model("codex")
    assert cli == "codex"
    assert model_id == "openai:gpt-5.2-codex"
    assert cmd[:3] == ["codex", "exec", "--full-auto"]


def test_resolve_model_falls_back_when_preferred_missing(monkeypatch):
    fake = _FakeCache(
        {
            "clis": {
                "gemini": {"installed": False, "issues": []},
                "opencode": {"installed": True, "issues": []},
            },
            "providers": {},
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    cli, model_id, cmd = router.resolve_model("gemini-high", preferred_cli="gemini")
    assert cli == "opencode"
    assert model_id.startswith("google:")
    assert cmd[0] == "opencode"


def test_resolve_local_model_prefers_lmstudio(monkeypatch):
    fake = _FakeCache(
        {
            "clis": {
                "codex": {"installed": True, "issues": []},
                "opencode": {"installed": True, "issues": []},
            },
            "providers": {
                "lmstudio": {
                    "running": True,
                    "endpoint": "http://192.168.1.50:1234/v1",
                    "loaded_models": ["qwen2.5-coder:32b"],
                    "compatible_clis": ["codex", "opencode"],
                },
                "ollama": {
                    "running": True,
                    "endpoint": "http://localhost:11434/v1",
                    "loaded_models": ["qwen2.5-coder:32b"],
                    "compatible_clis": ["opencode"],
                },
            },
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    cli, model_id, cmd = router.resolve_model("local")
    assert cli == "codex"
    assert model_id.startswith("local:lmstudio")
    assert cmd[:3] == ["codex", "exec", "--full-auto"]


def test_resolve_local_model_uses_configured_endpoint(monkeypatch):
    # Provider endpoint should prefer daplug_config over defaults.
    monkeypatch.setattr(
        "providers.base.load_daplug_config",
        lambda: {"local_providers": {"lmstudio": "http://gpu-server.local:1234/v1"}},
    )

    provider = LMStudioProvider()
    monkeypatch.setattr("providers.lmstudio.http_get_json", lambda *_a, **_k: {})

    running, endpoint = provider.detect_running(timeout_s=0.01)
    assert running is True
    assert endpoint == "http://gpu-server.local:1234/v1"


def test_resolve_model_raises_when_nothing_available(monkeypatch):
    fake = _FakeCache({"clis": {}, "providers": {}})
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    with pytest.raises(router.ModelNotAvailable):
        router.resolve_model("codex")


def test_get_routing_table_shows_all_options(monkeypatch):
    fake = _FakeCache({"clis": {"codex": {"installed": True, "issues": []}}, "providers": {}})
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    table = router.get_routing_table()
    for key in ["codex", "gemini", "local", "opencode", "claude"]:
        assert key in table


def test_backward_compat_when_cache_missing(monkeypatch):
    # Executor should fall back to hardcoded models when cache is missing.
    repo_root = Path(__file__).resolve().parents[3]
    executor_dir = repo_root / "skills" / "prompt-executor" / "scripts"
    sys.path.insert(0, str(executor_dir))
    import executor  # noqa: E402

    router_dir = repo_root / "skills" / "cli-detector" / "scripts"
    sys.path.insert(0, str(router_dir))
    import router as imported_router  # noqa: E402

    monkeypatch.setattr(imported_router, "load_cache_file", lambda: None)

    info = executor.get_cli_info("opencode", repo_root=repo_root)
    assert info["command"] == ["opencode", "run", "--format", "json", "-m", "zai/glm-4.7"]


def test_get_provider_endpoint_priority(monkeypatch):
    monkeypatch.delenv("LMSTUDIO_ENDPOINT", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    monkeypatch.setattr(
        "providers.base.load_daplug_config",
        lambda: {"local_providers": {"lmstudio": "http://cfg:1234/v1"}},
    )
    monkeypatch.setenv("LMSTUDIO_ENDPOINT", "http://env:1234/v1")
    assert get_provider_endpoint("lmstudio") == "http://cfg:1234/v1"

    monkeypatch.setattr("providers.base.load_daplug_config", lambda: {"local_providers": {}})
    assert get_provider_endpoint("lmstudio") == "http://env:1234/v1"

    monkeypatch.delenv("LMSTUDIO_ENDPOINT", raising=False)
    assert get_provider_endpoint("lmstudio") == "http://localhost:1234/v1"


# --- Additional tests for edge cases ---


def test_resolve_model_with_alias(monkeypatch):
    """Verify aliases like gpt-5.2 -> gpt52 work correctly."""
    fake = _FakeCache(
        {
            "clis": {"codex": {"installed": True, "issues": []}},
            "providers": {},
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    # Test various aliases
    for alias, expected_shorthand in [
        ("gpt-5.2", "gpt52"),
        ("gpt5.2", "gpt52"),
        ("gpt-5.2-high", "gpt52-high"),
        ("gpt-5.2-xhigh", "gpt52-xhigh"),
    ]:
        cli, model_id, cmd = router.resolve_model(alias)
        assert cli == "codex", f"Alias {alias} should resolve to codex CLI"
        assert "gpt-5.2" in model_id, f"Alias {alias} should resolve to gpt-5.2 model"


def test_resolve_model_with_raw_model_id(monkeypatch):
    """Direct model IDs like openai:gpt-5.2 should work."""
    fake = _FakeCache(
        {
            "clis": {
                "codex": {"installed": True, "issues": []},
                "opencode": {"installed": True, "issues": []},
            },
            "providers": {},
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    # Raw OpenAI model ID
    cli, model_id, cmd = router.resolve_model("openai:gpt-5.2")
    assert cli == "codex"
    assert model_id == "openai:gpt-5.2"

    # Raw Google model ID
    cli, model_id, cmd = router.resolve_model("google:gemini-2.5-pro")
    assert cli in ["gemini", "opencode"]  # Falls back if gemini not installed
    assert model_id == "google:gemini-2.5-pro"


def test_cli_with_error_issues_skipped(monkeypatch):
    """CLIs with severity=error issues should be skipped in fallback chain."""
    fake = _FakeCache(
        {
            "clis": {
                "codex": {
                    "installed": True,
                    "issues": [{"type": "auth", "severity": "error", "message": "Not authenticated"}],
                },
                "opencode": {"installed": True, "issues": []},
            },
            "providers": {},
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    # Should skip codex (has error) and fall back to opencode
    cli, model_id, cmd = router.resolve_model("codex")
    assert cli == "opencode", "Should skip CLI with error-severity issues"


def test_cli_with_warning_issues_not_skipped(monkeypatch):
    """CLIs with warning-level issues should still be used."""
    fake = _FakeCache(
        {
            "clis": {
                "codex": {
                    "installed": True,
                    "issues": [{"type": "config", "severity": "warning", "message": "Minor issue"}],
                },
                "opencode": {"installed": True, "issues": []},
            },
            "providers": {},
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)

    cli, model_id, cmd = router.resolve_model("codex")
    assert cli == "codex", "Warning-level issues should not cause fallback"


def test_vllm_provider_detect_running(monkeypatch):
    """vLLM provider detection should work with configured endpoint."""
    monkeypatch.setattr(
        "providers.base.load_daplug_config",
        lambda: {"local_providers": {"vllm": "http://inference.local:8000/v1"}},
    )

    provider = VLLMProvider()
    # Mock successful API response
    monkeypatch.setattr(
        "providers.vllm.http_get_json",
        lambda url, **kw: {"data": [{"id": "meta-llama/Llama-3-70b"}]} if "models" in url else None,
    )

    running, endpoint = provider.detect_running(timeout_s=0.01)
    assert running is True
    assert endpoint == "http://inference.local:8000/v1"

    # Test list_models
    models = provider.list_models(endpoint, timeout_s=0.01)
    assert "meta-llama/Llama-3-70b" in models


def test_vllm_provider_not_running(monkeypatch):
    """vLLM provider should report not running when API fails."""
    monkeypatch.setattr(
        "providers.base.load_daplug_config",
        lambda: {"local_providers": {}},
    )
    monkeypatch.delenv("VLLM_ENDPOINT", raising=False)

    provider = VLLMProvider()
    monkeypatch.setattr("providers.vllm.http_get_json", lambda *a, **kw: None)

    running, endpoint = provider.detect_running(timeout_s=0.01)
    assert running is False
    assert endpoint == "http://localhost:8000/v1"


def test_ollama_remote_endpoint(monkeypatch):
    """Ollama provider should use configured remote endpoint."""
    monkeypatch.setattr(
        "providers.base.load_daplug_config",
        lambda: {"local_providers": {"ollama": "http://gpu-server.local:11434/v1"}},
    )

    provider = OllamaProvider()
    # Ollama uses api/version for detect_running, api/tags for list_models
    monkeypatch.setattr(
        "providers.ollama.http_get_json",
        lambda url, **kw: {"version": "0.1.0"} if "version" in url else (
            {"models": [{"name": "qwen2.5-coder:32b"}]} if "tags" in url else None
        ),
    )

    running, endpoint = provider.detect_running(timeout_s=0.01)
    assert running is True
    assert endpoint == "http://gpu-server.local:11434/v1"

    # Also test list_models
    models = provider.list_models(endpoint, timeout_s=0.01)
    assert "qwen2.5-coder:32b" in models


def test_executor_router_import_failure_fallback(monkeypatch):
    """Executor should gracefully handle router import/runtime errors."""
    repo_root = Path(__file__).resolve().parents[3]
    executor_dir = repo_root / "skills" / "prompt-executor" / "scripts"
    if str(executor_dir) not in sys.path:
        sys.path.insert(0, str(executor_dir))

    # Need to reload executor to get fresh import
    import importlib
    import executor  # noqa: E402
    importlib.reload(executor)

    router_dir = repo_root / "skills" / "cli-detector" / "scripts"
    if str(router_dir) not in sys.path:
        sys.path.insert(0, str(router_dir))
    import router as imported_router  # noqa: E402

    # Simulate router raising an exception
    def raise_error(*args, **kwargs):
        raise RuntimeError("Simulated router failure")

    monkeypatch.setattr(imported_router, "resolve_model", raise_error)

    # Executor should fall back to hardcoded models
    info = executor.get_cli_info("codex", repo_root=repo_root)
    assert info is not None
    assert "command" in info
    # Should get the hardcoded codex config
    assert info["command"][0] == "codex"


def test_local_providers_yaml_parsing():
    """Multi-line YAML-ish format in <daplug_config> should parse correctly."""
    block_content = """
preferred_agent: codex
worktree_dir: .worktrees/
local_providers:
  lmstudio: http://192.168.1.50:1234/v1
  ollama: http://gpu-server.local:11434/v1
  vllm: http://inference.local:8000/v1
ai_usage_awareness: enabled
"""
    result = _parse_block(block_content)

    assert result.get("preferred_agent") == "codex"
    assert result.get("worktree_dir") == ".worktrees/"
    assert result.get("ai_usage_awareness") == "enabled"

    local_providers = result.get("local_providers", {})
    assert local_providers.get("lmstudio") == "http://192.168.1.50:1234/v1"
    assert local_providers.get("ollama") == "http://gpu-server.local:11434/v1"
    assert local_providers.get("vllm") == "http://inference.local:8000/v1"


def test_local_providers_json_inline_parsing():
    """Inline JSON format for local_providers should also work."""
    block_content = """
preferred_agent: gemini
local_providers: {"lmstudio": "http://host:1234/v1", "ollama": "http://host:11434/v1"}
"""
    result = _parse_block(block_content)

    assert result.get("preferred_agent") == "gemini"
    local_providers = result.get("local_providers", {})
    assert local_providers.get("lmstudio") == "http://host:1234/v1"
    assert local_providers.get("ollama") == "http://host:11434/v1"

