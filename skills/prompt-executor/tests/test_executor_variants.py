import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
EXECUTOR_PATH = SCRIPT_DIR / "executor.py"
EXECUTOR_SPEC = importlib.util.spec_from_file_location("executor", EXECUTOR_PATH)
if EXECUTOR_SPEC is None or EXECUTOR_SPEC.loader is None:
    raise RuntimeError(f"Unable to load executor from {EXECUTOR_PATH}")
executor = importlib.util.module_from_spec(EXECUTOR_SPEC)
sys.modules["executor"] = executor
EXECUTOR_SPEC.loader.exec_module(executor)

import models  # noqa: E402  -- needed so monkeypatch can target models' namespace
import loop  # noqa: E402


@pytest.fixture()
def no_router(monkeypatch):
    monkeypatch.setattr(models, "_resolve_router_command", lambda *_args, **_kwargs: None)


@pytest.fixture()
def prompt_repo(tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "001-test-prompt.md"
    prompt_file.write_text("# Test Prompt\n\nDo the thing.\n")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    monkeypatch.setattr(executor, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(executor, "get_cli_logs_dir", lambda _repo_root: logs_dir)
    monkeypatch.setattr(models, "_resolve_router_command", lambda *_args, **_kwargs: None)

    return tmp_path, logs_dir, prompt_file


@pytest.fixture()
def loop_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "loop-state"
    state_dir.mkdir()
    monkeypatch.setattr(executor, "get_loop_state_dir", lambda: state_dir)
    monkeypatch.setattr(loop, "get_loop_state_dir", lambda: state_dir)
    return state_dir


def _reasoning_value(command: list[str]) -> str:
    joined = " ".join(command)
    if 'model_reasoning_effort="high"' in joined:
        return "high"
    if 'model_reasoning_effort="xhigh"' in joined:
        return "xhigh"
    return ""




SYNTHETIC_MODELS = {
    "synthetic": ("synthetic:syn:large:text", "synthetic/syn:large:text"),
    "syn-flash": ("synthetic:syn:small:text", "synthetic/syn:small:text"),
    "syn-kimi": ("synthetic:syn:large:vision", "synthetic/syn:large:vision"),
    "syn-qwen": ("synthetic:syn:small:vision", "synthetic/syn:small:vision"),
}


def test_synthetic_model_specs_are_opencode_provider_refs():
    for shorthand, (model_id, _opencode_ref) in SYNTHETIC_MODELS.items():
        assert executor.MODEL_SPECS[shorthand]["model_id"] == model_id
        assert executor.MODEL_SPECS[shorthand]["default_cli"] == "opencode"
        assert executor.MODEL_SPECS[shorthand]["supports_codex_reasoning"] is False


def test_synthetic_models_build_opencode_commands(no_router, tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_KEY", "test-key")

    for shorthand, (model_id, opencode_ref) in SYNTHETIC_MODELS.items():
        info = executor.get_cli_info(shorthand, repo_root=tmp_path)
        assert info["selected_cli"] == "opencode"
        assert info["model_id"] == model_id
        assert info["command"] == ["opencode", "run", "--format", "json", "-m", opencode_ref]
        assert info["env"] == {}


def test_synthetic_models_require_api_key(no_router, tmp_path, monkeypatch):
    monkeypatch.delenv("SYNTHETIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SYNTHETIC_API_KEY is required"):
        executor.get_cli_info("synthetic", repo_root=tmp_path)


def test_main_argparse_accepts_synthetic_shorthands(prompt_repo, monkeypatch, capsys):
    monkeypatch.setenv("SYNTHETIC_API_KEY", "test-key")
    repo_root, _logs_dir, _prompt_file = prompt_repo

    for shorthand in SYNTHETIC_MODELS:
        monkeypatch.setattr(sys, "argv", ["executor.py", "001", "--model", shorthand])
        executor.main()
        output = json.loads(capsys.readouterr().out)
        assert output["prompts"][0]["cli_command"][5].startswith("synthetic/syn:")

def test_variant_parsing_precedence_over_alias_defaults(no_router, tmp_path):
    info_default = executor.get_cli_info("codex-high", repo_root=tmp_path)
    assert _reasoning_value(info_default["command"]) == "high"

    info_override = executor.get_cli_info("codex-high", repo_root=tmp_path, variant="xhigh")
    assert _reasoning_value(info_override["command"]) == "xhigh"

    info_none = executor.get_cli_info("codex-high", repo_root=tmp_path, variant="none")
    assert _reasoning_value(info_none["command"]) == ""


def test_codex_variant_mapping_high_and_xhigh(no_router, tmp_path):
    high_info = executor.get_cli_info("codex", repo_root=tmp_path, variant="high")
    xhigh_info = executor.get_cli_info("codex", repo_root=tmp_path, variant="xhigh")

    assert _reasoning_value(high_info["command"]) == "high"
    assert _reasoning_value(xhigh_info["command"]) == "xhigh"


def test_opencode_command_includes_variant_when_requested(no_router, tmp_path):
    info = executor.get_cli_info("codex", repo_root=tmp_path, cli_override="opencode", variant="high")

    assert info["selected_cli"] == "opencode"
    assert info["command"][:4] == ["opencode", "run", "--format", "json"]
    assert "--variant" in info["command"]
    assert info["command"][info["command"].index("--variant") + 1] == "high"


def test_explicit_cli_opencode_respected_for_supported_model(no_router, tmp_path):
    info = executor.get_cli_info("gpt52-high", repo_root=tmp_path, cli_override="opencode")

    assert info["selected_cli"] == "opencode"
    assert info["command"][0] == "opencode"


def test_agy_cli_override_for_google_models(no_router, tmp_path):
    info = executor.get_cli_info("gemini", repo_root=tmp_path, cli_override="agy")

    assert info["selected_cli"] == "agy"
    assert info["stdin_mode"] == "arg"
    assert info["command"] == ["agy", "--model", "Gemini 3.5 Flash (Medium)", "--print"]

    pro_info = executor.get_cli_info("gemini31pro", repo_root=tmp_path, cli_override="antigravity")
    assert pro_info["selected_cli"] == "agy"
    assert pro_info["command"] == ["agy", "--model", "Gemini 3.1 Pro (High)", "--print"]


def test_legacy_gemini_cli_override_still_works(no_router, tmp_path):
    info = executor.get_cli_info("gemini31pro", repo_root=tmp_path, cli_override="gemini")

    assert info["selected_cli"] == "gemini"
    assert info["stdin_mode"] == "arg"
    assert info["command"] == ["gemini", "-y", "-m", "gemini-3.1-pro-preview", "-p"]


def test_router_selected_agy_uses_executor_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr(
        models,
        "_resolve_router_command",
        lambda *_args, **_kwargs: ("agy", "google:gemini-2.5-pro", ["agy", "--model", "Gemini 3.1 Pro (High)", "--print"]),
    )

    info = executor.get_cli_info("gemini-high", repo_root=tmp_path)
    assert info["selected_cli"] == "agy"
    assert info["stdin_mode"] == "arg"
    assert info["command"] == ["agy", "--model", "Gemini 3.1 Pro (High)", "--print"]

def test_explicit_cli_opencode_errors_for_unsupported_model(no_router, tmp_path):
    with pytest.raises(ValueError, match="--cli opencode is not supported with --model gemini"):
        executor.get_cli_info("gemini", repo_root=tmp_path, cli_override="opencode")


def test_explicit_cli_override_takes_precedence_over_router_default(tmp_path, monkeypatch):
    monkeypatch.setattr(
        models,
        "_resolve_router_command",
        lambda *_args, **_kwargs: ("codex", "openai:gpt-5.3-codex", ["codex", "exec", "--full-auto"]),
    )

    info = executor.get_cli_info("codex", repo_root=tmp_path, cli_override="opencode", variant="high")
    assert info["selected_cli"] == "opencode"
    assert info["model_id"] == "openai:gpt-5.3-codex"
    assert info["command"][:4] == ["opencode", "run", "--format", "json"]
    assert "--variant" in info["command"]
    assert info["command"][info["command"].index("--variant") + 1] == "high"
    assert "via OpenCode" in info["display"]


def test_default_router_selection_unchanged_without_cli_override(tmp_path, monkeypatch):
    monkeypatch.setattr(
        models,
        "_resolve_router_command",
        lambda *_args, **_kwargs: ("opencode", "openai:gpt-5.3-codex", ["opencode", "run", "--format", "json"]),
    )

    info = executor.get_cli_info("codex", repo_root=tmp_path)
    assert info["selected_cli"] == "opencode"
    assert info["command"][:4] == ["opencode", "run", "--format", "json"]


def test_legacy_aliases_remain_backward_compatible(no_router, tmp_path):
    codex_alias = executor.get_cli_info("codex-xhigh", repo_root=tmp_path)
    gpt_alias = executor.get_cli_info("gpt52-high", repo_root=tmp_path)

    assert codex_alias["command"][0:3] == ["codex", "exec", "--full-auto"]
    assert _reasoning_value(codex_alias["command"]) == "xhigh"

    assert gpt_alias["command"][0:5] == ["codex", "exec", "--full-auto", "-m", "gpt-5.2"]
    assert _reasoning_value(gpt_alias["command"]) == "high"


def test_invalid_variant_combinations_error_actionably(no_router, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Codex supports high/xhigh only"):
        executor.get_cli_info("codex", repo_root=tmp_path, variant="medium")

    monkeypatch.setattr(executor.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)
    with pytest.raises(ValueError, match="is not supported with --model cc-sonnet"):
        executor.get_cli_info("cc-sonnet", repo_root=tmp_path, variant="high")


def test_main_info_only_honors_explicit_variant_precedence(prompt_repo, monkeypatch, capsys):
    argv = [
        "executor.py",
        "001",
        "--model",
        "codex-high",
        "--variant",
        "none",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["model"] == "codex-high"
    assert parsed["selected_cli"] == "codex"
    assert parsed["variant"] is None
    assert _reasoning_value(parsed["cli_command"]) == ""


def test_main_run_smoke_renders_codex_variant_command(prompt_repo, monkeypatch, capsys):
    _repo_root, _logs_dir, _prompt_file = prompt_repo
    captured = {}

    def fake_run_cli(cli_info, content, cwd, log_file):
        captured["command"] = list(cli_info["command"])
        Path(log_file).write_text("ok\n")
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli", fake_run_cli)
    argv = [
        "executor.py",
        "001",
        "--model",
        "codex",
        "--variant",
        "high",
        "--run",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["selected_cli"] == "codex"
    assert _reasoning_value(captured["command"]) == "high"
    assert parsed["prompts"][0]["execution"]["status"] == "completed"


def test_main_run_smoke_renders_opencode_variant_command(prompt_repo, monkeypatch, capsys):
    _repo_root, _logs_dir, _prompt_file = prompt_repo
    captured = {}

    def fake_run_cli(cli_info, content, cwd, log_file):
        captured["command"] = list(cli_info["command"])
        Path(log_file).write_text("ok\n")
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli", fake_run_cli)
    argv = [
        "executor.py",
        "001",
        "--model",
        "codex",
        "--cli",
        "opencode",
        "--variant",
        "medium",
        "--run",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["selected_cli"] == "opencode"
    assert captured["command"][0:4] == ["opencode", "run", "--format", "json"]
    assert "--variant" in captured["command"]
    assert captured["command"][captured["command"].index("--variant") + 1] == "medium"
    assert parsed["prompts"][0]["execution"]["status"] == "completed"


def test_loop_background_propagates_cli_and_variant_flags(tmp_path, loop_state_dir, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    captured = {}

    class DummyProc:
        pid = 4242

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        stdout_handle = kwargs.get("stdout")
        if stdout_handle:
            stdout_handle.write("fake popen output\n")
            stdout_handle.close()
        return DummyProc()

    monkeypatch.setattr(executor.subprocess, "Popen", fake_popen)

    executor.run_verification_loop_background(
        cli_info={"command": ["codex"], "env": {}, "stdin_mode": "dash"},
        original_content="# Test\n\nDo the thing.\n",
        cwd=str(tmp_path),
        log_dir=log_dir,
        prompt_number="001",
        model="codex",
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260119-150550",
        worktree_path=None,
        branch_name=None,
        cli_override="opencode",
        variant="none",
    )

    cmd = captured["cmd"]
    assert "--cli" in cmd
    assert cmd[cmd.index("--cli") + 1] == "opencode"
    assert "--variant" in cmd
    assert cmd[cmd.index("--variant") + 1] == "none"

EXPECTED_MODEL_KEYS = [
    "claude",
    "cc-sonnet",
    "cc-opus",
    "codex",
    "codex-spark",
    "codex-high",
    "codex-xhigh",
    "gpt54",
    "gpt54-high",
    "gpt54-xhigh",
    "gpt55",
    "gpt55-high",
    "gpt55-xhigh",
    "gpt52",
    "gpt52-high",
    "gpt52-xhigh",
    "gemini",
    "gemini-high",
    "gemini-xhigh",
    "gemini25pro",
    "gemini25flash",
    "gemini25lite",
    "gemini3flash",
    "gemini3pro",
    "gemini31pro",
    "zai",
    "glm5",
    "glm52",
    "kimi",
    "synthetic",
    "syn-flash",
    "syn-kimi",
    "syn-qwen",
    "opencode",
    "local",
    "qwen",
    "devstral",
    "glm-local",
    "qwen-small",
]


def test_registry_contains_exact_model_key_list():
    assert list(executor.MODEL_CHOICES) == EXPECTED_MODEL_KEYS
    assert list(executor.LEGACY_MODEL_DISPLAY) == EXPECTED_MODEL_KEYS


def test_registry_models_have_required_fields():
    required = executor._REQUIRED_MODEL_FIELDS
    for key in EXPECTED_MODEL_KEYS:
        model = executor.MODEL_REGISTRY_BY_NAME[key]
        assert required <= set(model), key
        assert isinstance(model["routing"], dict)
        assert isinstance(model["docs"], dict)
        assert isinstance(model["command"], list)
        assert all(isinstance(item, str) for item in model["command"])
        assert isinstance(model["env"], dict)
        assert model["stdin_mode"] in executor._ALLOWED_STDIN_MODES


def test_default_runtime_uses_registry_command_env_and_stdin(no_router, tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_KEY", "test-key")
    monkeypatch.setattr(models, "_require_claude_cli", lambda: None)

    for key in executor.MODEL_CHOICES:
        info = executor.get_cli_info(key, repo_root=tmp_path)
        model = executor.MODEL_REGISTRY_BY_NAME[key]
        assert info["command"] == model["command"], key
        assert info["env"] == model["env"], key
        assert info["stdin_mode"] == model["stdin_mode"], key


def test_main_argparse_accepts_every_registry_key(monkeypatch):
    import argparse as _argparse

    real_parse = _argparse.ArgumentParser.parse_args

    def capture(self, *args, **kwargs):
        namespace = real_parse(self, *args, **kwargs)
        raise SystemExit((0, namespace.model))

    monkeypatch.setattr(_argparse.ArgumentParser, "parse_args", capture)

    for key in executor.MODEL_CHOICES:
        monkeypatch.setattr(sys, "argv", ["executor.py", "--model", key])
        with pytest.raises(SystemExit) as exc:
            executor.main()
        assert exc.value.code == (0, key)


def test_main_argparse_rejects_unknown_model(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["executor.py", "--model", "not-a-model"])
    with pytest.raises(SystemExit) as exc:
        executor.main()
    assert exc.value.code == 2


def test_model_registry_loads_when_cwd_is_not_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _registry, by_name = executor._load_model_registry()
    assert list(by_name) == EXPECTED_MODEL_KEYS
    assert by_name["glm52"]["model_id"] == "zai:glm-5.2"

