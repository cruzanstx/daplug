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
    assert model_id == "openai:gpt-5.3-codex"
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
    assert cli == "opencode"
    assert model_id.startswith("local:lmstudio")
    assert cmd[0:4] == ["opencode", "run", "--format", "json"]
    assert "-m" in cmd
    idx_m = cmd.index("-m")
    assert cmd[idx_m + 1].startswith("lmstudio/")


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
    for key in ["codex", "gemini", "gemini31pro", "local", "opencode", "claude"]:
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


# --- Comprehensive model coverage tests ---


@pytest.fixture
def full_cache(monkeypatch):
    """Cache with all CLIs installed and no errors."""
    fake = _FakeCache(
        {
            "clis": {
                "claude": {"installed": True, "issues": []},
                "codex": {"installed": True, "issues": []},
                "gemini": {"installed": True, "issues": []},
                "opencode": {"installed": True, "issues": []},
                "aider": {"installed": True, "issues": []},
            },
            "providers": {
                "lmstudio": {
                    "running": True,
                    "endpoint": "http://localhost:1234/v1",
                    "loaded_models": ["qwen3-coder-next", "devstral-small-2-2512", "glm-4.7-flash", "qwen3-4b-2507"],
                },
            },
        }
    )
    monkeypatch.setattr(router, "load_cache_file", lambda: fake)
    return fake


class TestOpenAIModels:
    """Test all OpenAI/Codex model shorthands."""

    @pytest.mark.parametrize(
        "shorthand,expected_model,expected_reasoning",
        [
            ("codex", "gpt-5.3-codex", None),
            ("codex-high", "gpt-5.3-codex", "high"),
            ("codex-xhigh", "gpt-5.3-codex", "xhigh"),
            ("gpt52", "gpt-5.2", None),
            ("gpt52-high", "gpt-5.2", "high"),
            ("gpt52-xhigh", "gpt-5.2", "xhigh"),
        ],
    )
    def test_codex_models(self, full_cache, shorthand, expected_model, expected_reasoning):
        cli, model_id, cmd = router.resolve_model(shorthand)
        assert cli == "codex"
        assert expected_model in model_id
        assert cmd[0] == "codex"
        assert "exec" in cmd
        assert "--full-auto" in cmd
        if expected_reasoning:
            assert any(expected_reasoning in str(c) for c in cmd)

    @pytest.mark.parametrize(
        "alias,expected_shorthand",
        [
            ("gpt-5.2", "gpt52"),
            ("gpt5.2", "gpt52"),
            ("gpt-5.2-high", "gpt52-high"),
            ("gpt-5.2-xhigh", "gpt52-xhigh"),
        ],
    )
    def test_codex_aliases(self, full_cache, alias, expected_shorthand):
        cli, model_id, cmd = router.resolve_model(alias)
        assert cli == "codex"
        assert "gpt-5.2" in model_id


class TestGeminiModels:
    """Test all Google/Gemini model shorthands."""

    @pytest.mark.parametrize(
        "shorthand,expected_model",
        [
            ("gemini", "gemini-3-flash-preview"),
            ("gemini-high", "gemini-2.5-pro"),
            ("gemini-xhigh", "gemini-3-pro-preview"),
            ("gemini25pro", "gemini-2.5-pro"),
            ("gemini25flash", "gemini-2.5-flash"),
            ("gemini25lite", "gemini-2.5-flash-lite"),
            ("gemini3flash", "gemini-3-flash-preview"),
            ("gemini3pro", "gemini-3-pro-preview"),
            ("gemini31pro", "gemini-3.1-pro-preview"),
        ],
    )
    def test_gemini_models(self, full_cache, shorthand, expected_model):
        cli, model_id, cmd = router.resolve_model(shorthand)
        assert cli == "gemini"
        assert expected_model in model_id
        assert cmd[0] == "gemini"
        assert "-y" in cmd
        assert "-m" in cmd
        assert "-p" in cmd


class TestZAIModels:
    """Test Z.AI model shorthands."""

    def test_zai_prefers_opencode(self, full_cache):
        """zai shorthand prefers opencode CLI (first in zai fallback chain)."""
        cli, model_id, cmd = router.resolve_model("zai")
        # zai family fallback chain: ["opencode", "codex"]
        # When opencode is installed, it's preferred
        assert cli == "opencode"
        assert "glm-4.7" in model_id
        assert cmd[0] == "opencode"

    def test_zai_falls_back_to_codex_profile(self, monkeypatch):
        """When opencode not installed, zai falls back to codex with zai profile."""
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

        cli, model_id, cmd = router.resolve_model("zai")
        assert cli == "codex"
        assert "glm-4.7" in model_id
        assert "--profile" in cmd
        assert "zai" in cmd

    def test_opencode_uses_opencode_cli(self, full_cache):
        """opencode shorthand forces opencode CLI (strict_cli=True)."""
        cli, model_id, cmd = router.resolve_model("opencode")
        assert cli == "opencode"
        assert "glm-4.7" in model_id
        assert cmd[0] == "opencode"
        assert "run" in cmd
        assert "--format" in cmd
        assert "json" in cmd


class TestLocalModels:
    """Test local model shorthands (qwen, devstral, local)."""

    def test_local_routes_to_lmstudio(self, full_cache):
        cli, model_id, cmd = router.resolve_model("local")
        assert cli == "opencode"
        assert "local:lmstudio" in model_id
        assert cmd[0:4] == ["opencode", "run", "--format", "json"]
        assert "-m" in cmd
        idx_m = cmd.index("-m")
        assert cmd[idx_m + 1].startswith("lmstudio/")

    def test_qwen_routes_to_local_profile(self, full_cache):
        cli, model_id, cmd = router.resolve_model("qwen")
        assert cli == "opencode"
        assert "qwen3-coder-next" in model_id
        assert cmd[0:4] == ["opencode", "run", "--format", "json"]
        idx_m = cmd.index("-m")
        assert cmd[idx_m + 1] == "lmstudio/qwen3-coder-next"

    def test_devstral_routes_to_local_devstral_profile(self, full_cache):
        cli, model_id, cmd = router.resolve_model("devstral")
        assert cli == "opencode"
        assert "devstral-small-2-2512" in model_id
        assert cmd[0:4] == ["opencode", "run", "--format", "json"]
        idx_m = cmd.index("-m")
        assert cmd[idx_m + 1] == "lmstudio/devstral-small-2-2512"

    def test_glm_local_routes_to_opencode(self, full_cache):
        cli, model_id, cmd = router.resolve_model("glm-local")
        assert cli == "opencode"
        assert "glm-4.7-flash" in model_id
        assert cmd[0:4] == ["opencode", "run", "--format", "json"]
        idx_m = cmd.index("-m")
        assert cmd[idx_m + 1] == "lmstudio/glm-4.7-flash"

    def test_qwen_small_routes_to_opencode(self, full_cache):
        cli, model_id, cmd = router.resolve_model("qwen-small")
        assert cli == "opencode"
        assert "qwen3-4b-2507" in model_id
        assert cmd[0:4] == ["opencode", "run", "--format", "json"]
        idx_m = cmd.index("-m")
        assert cmd[idx_m + 1] == "lmstudio/qwen3-4b-2507"

    def test_local_falls_back_to_codex_when_opencode_missing(self, monkeypatch):
        fake = _FakeCache(
            {
                "clis": {
                    "codex": {"installed": True, "issues": []},
                    "opencode": {"installed": False, "issues": []},
                },
                "providers": {
                    "lmstudio": {
                        "running": True,
                        "endpoint": "http://localhost:1234/v1",
                        "loaded_models": ["qwen3-coder-next"],
                    },
                },
            }
        )
        monkeypatch.setattr(router, "load_cache_file", lambda: fake)

        cli, model_id, cmd = router.resolve_model("local")
        assert cli == "codex"
        assert "local:lmstudio" in model_id
        assert cmd[:3] == ["codex", "exec", "--full-auto"]
        assert "--profile" in cmd
        assert "local" in cmd


class TestClaudeModel:
    """Test Claude Code CLI command generation."""

    def test_claude_returns_headless_command(self, full_cache):
        cli, model_id, cmd = router.resolve_model("claude")
        assert cli == "claude"
        assert "claude" in model_id
        assert cmd[0] == "claude"
        assert "--print" in cmd or "-p" in cmd
        assert "--input-format" in cmd
        assert "--permission-mode" in cmd
        # Base shorthand should not force a specific model (uses Claude Code config defaults).
        assert "--model" not in cmd

    @pytest.mark.parametrize(
        "shorthand,expected_model",
        [
            ("cc-sonnet", "sonnet"),
            ("cc-opus", "opus"),
        ],
    )
    def test_cc_models_force_model_selection(self, full_cache, shorthand, expected_model):
        cli, model_id, cmd = router.resolve_model(shorthand)
        assert cli == "claude"
        assert model_id.endswith(f":{expected_model}")
        assert cmd[0] == "claude"
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == expected_model


class TestAllModelsHaveValidCommands:
    """Ensure all defined shorthands produce valid output."""

    def test_all_shorthands_resolve(self, full_cache):
        """Every shorthand in _SHORTHAND should resolve without error."""
        for shorthand in router._SHORTHAND.keys():
            cli, model_id, cmd = router.resolve_model(shorthand)
            assert cli is not None, f"{shorthand} returned None cli"
            assert model_id is not None, f"{shorthand} returned None model_id"
            # cmd should be a list (may be empty in exceptional cases, but should not be None)
            assert isinstance(cmd, list), f"{shorthand} cmd is not a list"

    def test_all_aliases_resolve(self, full_cache):
        """Every alias in _ALIASES should resolve without error."""
        for alias in router._ALIASES.keys():
            cli, model_id, cmd = router.resolve_model(alias)
            assert cli is not None, f"Alias {alias} returned None cli"


class TestCommandStructure:
    """Test that generated commands match expected CLI patterns."""

    def test_codex_command_structure(self, full_cache):
        """Codex commands should follow: codex exec --full-auto [-m model] [-c config]"""
        cli, model_id, cmd = router.resolve_model("codex")
        assert cmd[0:3] == ["codex", "exec", "--full-auto"]

    def test_gemini_command_structure(self, full_cache):
        """Gemini commands should follow: gemini -y -m model -p"""
        cli, model_id, cmd = router.resolve_model("gemini")
        assert cmd[0] == "gemini"
        assert "-y" in cmd
        idx_m = cmd.index("-m")
        assert cmd[idx_m + 1].startswith("gemini-")
        assert cmd[-1] == "-p"

    def test_opencode_command_structure(self, full_cache):
        """OpenCode commands should follow: opencode run --format json -m provider/model"""
        cli, model_id, cmd = router.resolve_model("opencode")
        assert cmd[0:4] == ["opencode", "run", "--format", "json"]
        assert "-m" in cmd
        idx_m = cmd.index("-m")
        assert "/" in cmd[idx_m + 1]  # e.g., "zai/glm-4.7"
